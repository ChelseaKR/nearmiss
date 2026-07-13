"""Contract and known-answer tests for private national FARS context."""

from __future__ import annotations

import copy
import hashlib
import io
import json
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

import pytest
from jsonschema import Draft202012Validator

from nearmiss import fars_national_context as national_context
from nearmiss import verified_outcomes
from nearmiss.adapters.fars import FARS_MAPPING_VERSION
from nearmiss.adapters.fars_joined import (
    PERSON_MODE_MAPPING_VERSION,
    PersonJoinProvenance,
    collect_joined,
    read_joined_export_bytes,
)
from nearmiss.adapters.outcomes import OutcomeProvenance
from nearmiss.fars_national_context import (
    FARS_NATIONAL_CONTEXT_CAVEAT,
    _build_verified_fars_state_context,
    build_verified_fars_national_context,
    canonical_fars_national_context_bytes,
    fars_national_context_contract_descriptor,
    validate_fars_national_context_artifact,
)
from nearmiss.fars_national_context_schema import FARS_NATIONAL_CONTEXT_ARTIFACT_SCHEMA
from nearmiss.joined_outcome_artifacts import (
    build_joined_outcome_artifact,
    canonical_joined_outcome_artifact_bytes,
)
from nearmiss.verified_outcomes import VerifiedJoinedOutcomeEvidence, _VerifiedJoinedSnapshot

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schema" / "private-fars-national-context.schema.json"
FARS_URL = "https://static.nhtsa.gov/nhtsa/downloads/FARS/2024/National/FARS2024.zip"


def _joined_inputs() -> tuple[bytes, bytes, OutcomeProvenance, PersonJoinProvenance]:
    accident = ["STATE,ST_CASE,YEAR,MONTH,DAY,HOUR,MINUTE,LATITUDE,LONGITUD,FATALS"]
    person = ["STATE,ST_CASE,VEH_NO,PER_NO,PER_TYP,INJ_SEV,BODY_TYP"]

    cases: list[tuple[int, int, int, int]] = []
    # Five California pedestrian crashes: eligible at the hard floor.
    cases.extend((6, 600_000 + index, 5, 0) for index in range(1, 6))
    # Four California pedalcyclist crashes: suppressed at the hard floor.
    cases.extend((6, 610_000 + index, 6, 0) for index in range(1, 5))
    # Seven Texas motorcyclist crashes: eligible.
    cases.extend((48, 480_000 + index, 1, 80) for index in range(1, 8))
    # FARS uses 43, not Census/FIPS 72, for Puerto Rico.
    cases.append((43, 430_001, 5, 0))

    for day, (state, case, person_type, body_type) in enumerate(cases, start=1):
        accident.append(f"{state},{case},2024,1,{day},12,00,38.5,-121.7,1")
        vehicle = 1 if person_type == 1 else 0
        person.append(f"{state},{case},{vehicle},1,{person_type},4,{body_type}")

    # The same crash may contribute once to two modes; never twice to one mode.
    overlap_case = 620_001
    accident.append(f"6,{overlap_case},2024,1,18,12,00,38.5,-121.7,1")
    person.append(f"6,{overlap_case},1,1,1,4,1")
    person.append(f"6,{overlap_case},0,2,5,1,0")

    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in (
            ("FARS/accident.csv", "\n".join(accident) + "\n"),
            ("FARS/person.csv", "\n".join(person) + "\n"),
        ):
            member = zipfile.ZipInfo(name, date_time=(2024, 1, 1, 0, 0, 0))
            member.compress_type = zipfile.ZIP_DEFLATED
            member.external_attr = 0o100600 << 16
            archive.writestr(member, content)
    raw = stream.getvalue()
    outcomes, summaries, crash, joined = collect_joined(
        read_joined_export_bytes(raw), release_status="final"
    )
    artifact = build_joined_outcome_artifact(
        outcomes,
        summaries,
        joined,
        crash,
        distribution_url=FARS_URL,
    )
    return canonical_joined_outcome_artifact_bytes(artifact), raw, crash, joined


def _proof_snapshot(*, payload: bytes | None = None) -> _VerifiedJoinedSnapshot:
    normalized, raw, crash, joined = _joined_inputs()
    exact_payload = normalized if payload is None else payload
    evidence = VerifiedJoinedOutcomeEvidence(
        source_id="fars-joined",
        dataset_year=2024,
        crash_mapping_version=FARS_MAPPING_VERSION,
        person_mapping_version=PERSON_MODE_MAPPING_VERSION,
        release_status="final",
        crash_records_read=crash.records_read,
        crash_records_accepted=crash.records_accepted,
        crash_records_rejected=crash.records_read - crash.records_accepted,
        person_records_read=joined.records_read,
        person_records_accepted=joined.records_accepted,
        person_records_excluded=joined.records_excluded_with_rejected_crash,
        cases_joined=joined.cases_joined,
        cases_excluded=joined.cases_excluded_with_rejected_crash,
        raw_sha256=hashlib.sha256(raw).hexdigest(),
        accident_sha256=joined.accident_sha256,
        person_sha256=joined.person_sha256,
        normalized_sha256=hashlib.sha256(exact_payload).hexdigest(),
        attempt_id="national-context-proof",
        _proof_token=verified_outcomes._JOINED_PROOF_TOKEN,
    )
    return _VerifiedJoinedSnapshot(
        evidence=evidence,
        normalized_bytes=exact_payload,
        _proof_token=verified_outcomes._JOINED_SNAPSHOT_PROOF_TOKEN,
    )


def _joined_bytes() -> bytes:
    return _joined_inputs()[0]


def _artifact(*, requested_k: int = 5) -> dict[str, object]:
    return _build_verified_fars_state_context(
        _proof_snapshot(),
        requested_k=requested_k,
        require_national_coverage=False,
    )


def _cells(artifact: dict[str, object]) -> list[dict[str, Any]]:
    return cast(list[dict[str, Any]], artifact["cells"])


def _accounting(artifact: dict[str, object]) -> dict[str, int]:
    return cast(dict[str, int], artifact["accounting"])


def test_repository_schema_matches_the_embedded_contract() -> None:
    assert json.loads(SCHEMA_PATH.read_text(encoding="utf-8")) == (
        FARS_NATIONAL_CONTEXT_ARTIFACT_SCHEMA
    )
    Draft202012Validator.check_schema(FARS_NATIONAL_CONTEXT_ARTIFACT_SCHEMA)


def test_known_answer_counts_distinct_crashes_once_per_involved_mode() -> None:
    artifact = _artifact()
    assert _cells(artifact) == [
        {"state_code": "6", "involved_mode": "pedestrian", "crash_count": 6},
        {"state_code": "48", "involved_mode": "motorcyclist", "crash_count": 7},
    ]
    assert _accounting(artifact) == {
        "case_count": 18,
        "states_with_records": 3,
        "states_with_eligible_cells": 2,
        "positive_candidate_cell_count": 5,
        "eligible_cell_count": 2,
        "suppressed_cell_count": 3,
        "crash_contribution_total": 19,
        "eligible_crash_contribution_total": 13,
        "suppressed_crash_contribution_total": 6,
    }
    assert artifact["visibility"] == "private"
    assert artifact["caveat"] == FARS_NATIONAL_CONTEXT_CAVEAT


def test_requested_k_cannot_lower_the_hard_floor_and_can_raise_it() -> None:
    assert cast(dict[str, Any], _artifact(requested_k=1)["method"])["effective_k"] == 5
    raised = _artifact(requested_k=7)
    assert cast(dict[str, Any], raised["method"])["effective_k"] == 7
    assert _cells(raised) == [
        {"state_code": "48", "involved_mode": "motorcyclist", "crash_count": 7}
    ]


@pytest.mark.parametrize("requested", [True, 1.0, "5", None])
def test_requested_k_requires_a_real_integer(requested: object) -> None:
    with pytest.raises(TypeError, match="requested_k must be an integer"):
        _build_verified_fars_state_context(
            _proof_snapshot(),
            requested_k=cast(Any, requested),
            require_national_coverage=False,
        )


@pytest.mark.parametrize("requested", [0, 36_298])
def test_requested_k_is_bounded(requested: int) -> None:
    with pytest.raises(ValueError, match="requested_k must be between"):
        _build_verified_fars_state_context(
            _proof_snapshot(),
            requested_k=requested,
            require_national_coverage=False,
        )


def test_output_is_deterministic_canonical_and_contains_no_precise_fields() -> None:
    first = _artifact()
    second = _artifact()
    assert first == second
    payload = canonical_fars_national_context_bytes(first)
    assert payload == canonical_fars_national_context_bytes(copy.deepcopy(first))
    assert payload.endswith(b"\n") and b"\n" not in payload[:-1]
    forbidden = (
        b'"source_record_id":',
        b'"occurred_on":',
        b'"occurred_time_local":',
        b'"latitude":',
        b'"longitude":',
        b'"location":',
        b'"fatality_count":',
        b'"state_total":',
        b'"national_total":',
        b'"rank":',
        b'"rate":',
    )
    assert all(token not in payload for token in forbidden)


def test_source_hash_is_bound_to_exact_canonical_joined_bytes() -> None:
    source = cast(dict[str, Any], _artifact()["source_lineage"])
    assert source["normalized_sha256"] == hashlib.sha256(_joined_bytes()).hexdigest()
    assert source["cases_joined"] == 18
    assert source["attempt_id"] == "national-context-proof"


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda artifact: cast(dict[str, Any], artifact["accounting"]).__setitem__(
                "eligible_cell_count", 99
            ),
            "eligible cell accounting",
        ),
        (
            lambda artifact: cast(dict[str, Any], artifact["accounting"]).__setitem__(
                "case_count", 16
            ),
            "source case accounting",
        ),
        (
            lambda artifact: cast(dict[str, Any], artifact["accounting"]).__setitem__(
                "suppressed_cell_count", 99
            ),
            "cell accounting equation",
        ),
        (
            lambda artifact: cast(dict[str, Any], artifact["accounting"]).__setitem__(
                "suppressed_crash_contribution_total", 99
            ),
            "contribution accounting equation",
        ),
        (
            lambda artifact: cast(dict[str, Any], artifact["accounting"]).__setitem__(
                "states_with_eligible_cells", 1
            ),
            "eligible state accounting",
        ),
        (
            lambda artifact: _cells(artifact).reverse(),
            "canonically ordered",
        ),
    ],
)
def test_semantic_validator_rejects_inconsistent_artifacts(
    mutate: Callable[[dict[str, object]], None], message: str
) -> None:
    artifact = _artifact()
    mutate(artifact)
    with pytest.raises(ValueError, match=message):
        validate_fars_national_context_artifact(artifact)


def test_semantic_validator_rejects_impossible_cell_and_source_cardinality() -> None:
    artifact = _artifact()
    accounting = _accounting(artifact)
    _cells(artifact)[0]["crash_count"] = 19
    accounting["eligible_crash_contribution_total"] = 26
    accounting["crash_contribution_total"] = 32
    with pytest.raises(ValueError, match="cell exceeds the source case count"):
        validate_fars_national_context_artifact(artifact)

    artifact = _artifact()
    accounting = _accounting(artifact)
    accounting["states_with_records"] = 19
    with pytest.raises(ValueError, match="source cardinality bounds"):
        validate_fars_national_context_artifact(artifact)


def test_semantic_validator_rejects_impossible_suppression_bounds() -> None:
    artifact = _artifact()
    accounting = _accounting(artifact)
    accounting["suppressed_cell_count"] = 1
    accounting["positive_candidate_cell_count"] = 3
    accounting["suppressed_crash_contribution_total"] = 5
    accounting["crash_contribution_total"] = 18
    with pytest.raises(ValueError, match="suppressed contribution bounds"):
        validate_fars_national_context_artifact(artifact)

    artifact = _artifact()
    accounting = _accounting(artifact)
    _cells(artifact)[0]["crash_count"] = 11
    accounting["eligible_crash_contribution_total"] = 18
    accounting["suppressed_crash_contribution_total"] = 0
    accounting["crash_contribution_total"] = 18
    with pytest.raises(ValueError, match="suppressed contribution bounds"):
        validate_fars_national_context_artifact(artifact)

    artifact = _artifact(requested_k=100)
    accounting = _accounting(artifact)
    accounting["states_with_records"] = 1
    accounting["positive_candidate_cell_count"] = 1
    accounting["suppressed_cell_count"] = 1
    with pytest.raises(ValueError, match="suppressed contribution bounds"):
        validate_fars_national_context_artifact(artifact)


@pytest.mark.parametrize(
    "field",
    [
        "crash_records_read",
        "crash_records_accepted",
        "cases_excluded",
        "person_records_read",
    ],
)
def test_semantic_validator_rejects_source_lineage_accounting_drift(field: str) -> None:
    artifact = _artifact()
    source = cast(dict[str, int], artifact["source_lineage"])
    source[field] += 1
    if field == "crash_records_accepted":
        _accounting(artifact)["case_count"] += 1
        source["cases_joined"] += 1
    with pytest.raises(ValueError, match="source lineage accounting"):
        validate_fars_national_context_artifact(artifact)


def test_source_lineage_requires_person_coverage_for_joined_and_excluded_cases() -> None:
    artifact = _artifact()
    source = cast(dict[str, int], artifact["source_lineage"])
    source["person_records_accepted"] = 1
    source["person_records_read"] = 1 + source["person_records_excluded"]
    with pytest.raises(ValueError, match="source lineage accounting"):
        validate_fars_national_context_artifact(artifact)

    artifact = _artifact()
    source = cast(dict[str, int], artifact["source_lineage"])
    source["crash_records_rejected"] = 1
    source["cases_excluded"] = 1
    source["crash_records_read"] = source["crash_records_accepted"] + 1
    source["person_records_excluded"] = 0
    source["person_records_read"] = source["person_records_accepted"]
    with pytest.raises(ValueError, match="source lineage accounting"):
        validate_fars_national_context_artifact(artifact)


@pytest.mark.parametrize(
    "forbidden",
    [
        {"source_record_id": "2024:1"},
        {"location": {"lat": 1, "lon": 2}},
        {"occurred_on": "2024-01-01"},
        {"suppressed_cells": [{"state_code": "6", "crash_count": 4}]},
        {"state_totals": {"6": 10}},
        {"visibility": "public"},
    ],
)
def test_closed_schema_rejects_precise_or_reconstructive_fields(
    forbidden: dict[str, object],
) -> None:
    artifact = _artifact()
    artifact.update(forbidden)
    with pytest.raises(ValueError, match="invalid private national FARS context"):
        validate_fars_national_context_artifact(artifact)


def test_builder_rejects_noncanonical_and_oversized_joined_bytes() -> None:
    canonical = _joined_bytes()
    noncanonical = json.dumps(json.loads(canonical), indent=2).encode()
    with pytest.raises(ValueError, match="not canonical"):
        _build_verified_fars_state_context(
            _proof_snapshot(payload=noncanonical),
            requested_k=5,
            require_national_coverage=False,
        )
    cap = cast(dict[str, int], fars_national_context_contract_descriptor()["caps"])[
        "max_joined_bytes"
    ]
    with pytest.raises(ValueError, match="byte safety limit"):
        national_context._joined_artifact_from_canonical_bytes(b" " * (cap + 1))


def test_builder_rejects_duplicate_keys_and_nonfinite_numbers() -> None:
    with pytest.raises(ValueError, match="duplicate key"):
        national_context._joined_artifact_from_canonical_bytes(b'{"a":1,"a":2}\n')
    with pytest.raises(ValueError, match="non-finite"):
        national_context._joined_artifact_from_canonical_bytes(b'{"a":NaN}\n')


def test_parser_rejects_recursion_and_bytes_subclasses() -> None:
    nested = b"[" * 20_000 + b"0" + b"]" * 20_000
    with pytest.raises(ValueError, match="JSON is invalid"):
        national_context._joined_artifact_from_canonical_bytes(nested)

    class HostileBytes(bytes):
        def decode(self, *_args: object, **_kwargs: object) -> str:
            return _joined_bytes().decode()

    with pytest.raises(TypeError, match="canonical joined bytes"):
        national_context._joined_artifact_from_canonical_bytes(HostileBytes(b"unrelated"))


@pytest.mark.parametrize("state_code", ["06", " 6", "6 ", "+6", "3", "72", "99"])
def test_builder_fails_closed_on_noncanonical_or_unsupported_state_codes(
    state_code: str,
) -> None:
    joined = json.loads(_joined_bytes())
    joined["records"][0]["outcome"]["state_code"] = state_code
    # Re-canonicalize without applying the joined validator: malformed source
    # must fail before it can be aggregated.
    payload = (json.dumps(joined, separators=(",", ":"), sort_keys=True) + "\n").encode()
    with pytest.raises(ValueError, match=r"state_code|state code"):
        _build_verified_fars_state_context(
            _proof_snapshot(payload=payload),
            requested_k=5,
            require_national_coverage=False,
        )


def test_production_builder_requires_proof_and_complete_national_coverage() -> None:
    with pytest.raises(TypeError, match="proof-bound joined snapshot"):
        build_verified_fars_national_context(cast(Any, _joined_bytes()))
    with pytest.raises(ValueError, match="national coverage bounds"):
        build_verified_fars_national_context(_proof_snapshot())


def test_partial_artifact_cannot_be_relabelled_as_official_national_coverage() -> None:
    artifact = _artifact()
    method = cast(dict[str, Any], artifact["method"])
    method["coverage"] = "official_2024_national_50_states_and_dc"
    with pytest.raises(ValueError, match="official coverage marker"):
        validate_fars_national_context_artifact(artifact)


def test_fars_puerto_rico_code_43_is_accepted_but_not_claimed_in_national_scope() -> None:
    artifact = _artifact()
    assert _accounting(artifact)["states_with_records"] == 3
    assert cast(dict[str, str], artifact["method"])["coverage"] == (
        "state_codes_present_in_verified_snapshot"
    )
    assert cast(dict[str, Any], artifact["method"])["coverage_state_codes"] == []
