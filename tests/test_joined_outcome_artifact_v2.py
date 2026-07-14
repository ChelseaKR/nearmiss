# SPDX-License-Identifier: Apache-2.0
"""Contract and adversarial tests for fixed-year joined artifact v2."""

from __future__ import annotations

import copy
import hashlib
import inspect
import io
import json
import time
import zipfile
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import pytest
from jsonschema import Draft202012Validator, FormatChecker

import nearmiss.fars_year_contracts as year_contracts
import nearmiss.joined_outcome_artifacts_v2 as artifacts_v2
from nearmiss.adapters.fars_joined import collect_joined, read_joined_export_bytes
from nearmiss.fars_year_contracts import (
    FARS_ACCIDENT_ROW_CAP,
    FARS_YEAR_CONTRACT_HISTORY,
    SUPPORTED_FARS_YEARS,
    fars_year_contract,
    fars_year_contract_descriptor,
    fars_year_contract_revision,
    fars_year_contract_sha256,
    validate_fars_year_contract_registry,
)
from nearmiss.joined_outcome_artifacts import JOINED_ARTIFACT_TYPE
from nearmiss.joined_outcome_artifacts_v2 import (
    JOINED_ARTIFACT_V2_MAX_INVALID_FRACTION,
    JOINED_ARTIFACT_V2_SCHEMA_VERSION,
    JOINED_ARTIFACT_V2_TYPE,
    JOINED_OUTCOME_ARTIFACT_V2_SCHEMA,
    canonical_joined_outcome_artifact_v2_bytes,
    canonical_joined_outcome_artifact_v2_from_pinned_archive,
    validate_joined_outcome_artifact_v2,
)

ROOT = Path(__file__).resolve().parents[1]
BASE_ACCIDENT = (
    (ROOT / "tests" / "fixtures" / "fars" / "accident.csv")
    .read_bytes()
    .replace(b",2023,", b",2024,")
)
PERSON = b"""STATE,ST_CASE,VEH_NO,PER_NO,PER_TYP,INJ_SEV,BODY_TYP
6,100001,1,1,1,4,4
6,100001,0,1,5,2,
6,100002,1,1,1,4,80
6,100002,0,1,6,4,
"""
FIXED_ZIP_TIMESTAMP = (2020, 1, 1, 0, 0, 0)


def _accident(year: int) -> bytes:
    lines = BASE_ACCIDENT.decode().replace(",2024,", f",{year},").splitlines()
    result = [lines[0].replace(",FATALS", ",COUNTY,FATALS")]
    for line, county in zip(lines[1:3], ("113", "997"), strict=True):
        values = line.split(",")
        values.insert(-1, county)
        result.append(",".join(values))
    return ("\n".join(result) + "\n").encode("cp1252" if year == 2020 else "utf-8-sig")


def _archive(year: int) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in (
            ("National/accident.csv", _accident(year)),
            ("National/person.csv", PERSON),
        ):
            member = zipfile.ZipInfo(name, date_time=FIXED_ZIP_TIMESTAMP)
            member.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(member, payload)
    return buffer.getvalue()


def test_archive_fixture_bytes_do_not_depend_on_wall_clock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        time,
        "localtime",
        lambda *_args: (2026, 7, 12, 23, 59, 58, 6, 193, 0),
    )
    before = _archive(2024)
    monkeypatch.setattr(
        time,
        "localtime",
        lambda *_args: (2026, 7, 13, 0, 0, 2, 0, 194, 0),
    )
    after = _archive(2024)

    assert before == after
    with zipfile.ZipFile(io.BytesIO(before)) as archive:
        assert {member.date_time for member in archive.infolist()} == {FIXED_ZIP_TIMESTAMP}


@pytest.fixture(autouse=True)
def _register_exact_fixture_archives(monkeypatch: pytest.MonkeyPatch) -> None:
    """Exercise the production raw replay path against exact test-only contracts."""
    history: dict[int, tuple[Any, ...]] = {}
    contracts: dict[int, Any] = {}
    for year, registered_history in FARS_YEAR_CONTRACT_HISTORY.items():
        raw = _archive(year)
        raw_sha256 = hashlib.sha256(raw).hexdigest()
        fixture_history: list[Any] = []
        for registered in registered_history:
            if registered.revision == 1:
                fixture = replace(
                    registered,
                    source_revision_id=f"reviewed-20260712-{raw_sha256[:12]}",
                    raw_size_bytes=len(raw),
                    raw_sha256=raw_sha256,
                )
            else:
                fixture = replace(
                    registered,
                    predecessor_contract_sha256=year_contracts._unregistered_contract_sha256(
                        fixture_history[-1]
                    ),
                    source_revision_id=year_contracts._2024_arf_source_revision_id(raw_sha256),
                    raw_size_bytes=len(raw),
                    raw_sha256=raw_sha256,
                )
            fixture_history.append(fixture)
        history[year] = tuple(fixture_history)
        contracts[year] = fixture_history[-1]
    fixture_2024 = history[2024]
    monkeypatch.setattr(
        year_contracts,
        "_REVIEWED_2024_R1_CONTRACT_SHA256",
        year_contracts._unregistered_contract_sha256(fixture_2024[0]),
    )
    monkeypatch.setattr(
        year_contracts,
        "_REVIEWED_2024_ARF_CONTRACT_SHA256",
        year_contracts._unregistered_contract_sha256(fixture_2024[1]),
    )
    validate_fars_year_contract_registry(history)
    monkeypatch.setattr(year_contracts, "FARS_YEAR_CONTRACT_HISTORY", history)
    monkeypatch.setattr(year_contracts, "FARS_YEAR_CONTRACTS", contracts)
    monkeypatch.setattr(artifacts_v2, "FARS_YEAR_CONTRACT_HISTORY", history)
    schema = artifacts_v2._schema()
    monkeypatch.setattr(
        artifacts_v2,
        "_VALIDATOR",
        Draft202012Validator(schema, format_checker=FormatChecker()),
    )


def _inputs(year: int = 2024, revision: int = 1) -> tuple[list[Any], list[Any], Any, Any]:
    contract = fars_year_contract_revision(year, revision)
    outcomes, summaries, crash, person = collect_joined(
        read_joined_export_bytes(_archive(year), expected_year=year),
        release_status=contract.release_stage,
    )
    return (
        outcomes,
        summaries,
        replace(crash, input_sha256=contract.raw_sha256),
        replace(person, input_sha256=contract.raw_sha256),
    )


def _build(year: int = 2024, revision: int = 1) -> dict[str, object]:
    return cast(
        dict[str, object],
        json.loads(
            canonical_joined_outcome_artifact_v2_from_pinned_archive(
                _archive(year),
                year=year,
                contract_revision=revision,
            )
        ),
    )


def _records(artifact: dict[str, object]) -> list[dict[str, Any]]:
    return cast(list[dict[str, Any]], artifact["records"])


def _section(artifact: dict[str, object], key: str) -> dict[str, Any]:
    return cast(dict[str, Any], artifact[key])


def test_authority_boundary_accepts_only_exact_registered_raw_bytes() -> None:
    contract = fars_year_contract_revision(2024, 1)
    payload = canonical_joined_outcome_artifact_v2_from_pinned_archive(
        _archive(2024),
        year=2024,
        contract_revision=1,
    )
    artifact = cast(dict[str, object], json.loads(payload))
    assert payload == canonical_joined_outcome_artifact_v2_from_pinned_archive(
        _archive(2024),
        year=2024,
        contract_revision=1,
    )
    assert payload.endswith(b"\n")

    assert artifact["source_contract"] == fars_year_contract_descriptor(contract)
    assert _section(artifact, "crash_provenance")["input_sha256"] == contract.raw_sha256
    person = _section(artifact, "person_join")
    assert person["input_sha256"] == contract.raw_sha256
    assert person["accident_sha256"] == hashlib.sha256(_accident(2024)).hexdigest()
    assert person["person_sha256"] == hashlib.sha256(PERSON).hexdigest()


@pytest.mark.parametrize("payload", [_archive(2024)[:-1], _archive(2024) + b"substitute"])
def test_authority_boundary_rejects_wrong_length_before_reader(
    monkeypatch: pytest.MonkeyPatch,
    payload: bytes,
) -> None:
    parsed = False

    def fail_if_parsed(raw: bytes, *, contract: Any) -> Any:
        nonlocal parsed
        parsed = True
        raise AssertionError((raw, contract))

    monkeypatch.setattr(
        artifacts_v2,
        "read_pinned_joined_export_bytes_for_contract",
        fail_if_parsed,
    )
    with pytest.raises(ValueError, match="raw archive identity"):
        canonical_joined_outcome_artifact_v2_from_pinned_archive(
            payload,
            year=2024,
            contract_revision=1,
        )
    assert parsed is False


def test_authority_boundary_exposes_no_fabricatable_inputs() -> None:
    parameters = inspect.signature(
        canonical_joined_outcome_artifact_v2_from_pinned_archive
    ).parameters
    assert tuple(parameters) == ("raw_archive", "year", "contract_revision")
    assert parameters["year"].kind is inspect.Parameter.KEYWORD_ONLY
    assert parameters["contract_revision"].kind is inspect.Parameter.KEYWORD_ONLY

    outcomes, summaries, crash, person = _inputs()
    r1 = fars_year_contract_revision(2024, 1)
    forged_crash = replace(crash, input_sha256=r1.raw_sha256)
    forged_person = replace(person, input_sha256=r1.raw_sha256)
    with pytest.raises(TypeError):
        cast(Any, canonical_joined_outcome_artifact_v2_from_pinned_archive)(
            _archive(2024),
            year=2024,
            contract_revision=1,
            outcomes=outcomes,
            summaries=summaries,
            crash_provenance=forged_crash,
            person_provenance=forged_person,
            accident_member=forged_person.accident_member,
            person_member=forged_person.person_member,
        )


def test_schema_is_valid_and_equals_the_static_schema() -> None:
    Draft202012Validator.check_schema(JOINED_OUTCOME_ARTIFACT_V2_SCHEMA)
    static = json.loads(
        (ROOT / "schema" / "private-fars-joined-outcomes-v2.schema.json").read_text(
            encoding="utf-8"
        )
    )
    assert static == JOINED_OUTCOME_ARTIFACT_V2_SCHEMA


@pytest.mark.parametrize("year", SUPPORTED_FARS_YEARS)
def test_builds_closed_strict_artifact_for_each_fixed_year(year: int) -> None:
    artifact = _build(year)
    contract = fars_year_contract_revision(year, 1)
    assert artifact["schema_version"] == JOINED_ARTIFACT_V2_SCHEMA_VERSION
    assert artifact["artifact_type"] == JOINED_ARTIFACT_V2_TYPE
    assert artifact["source_contract"] == fars_year_contract_descriptor(contract)
    assert _section(artifact, "source_contract")["source_revision_id"] == (
        f"reviewed-20260712-{contract.raw_sha256[:12]}"
    )
    assert _section(artifact, "crash_normalization")["expected_year"] == year
    assert _section(artifact, "crash_normalization")["max_invalid_fraction"] == 0.05
    assert set(_section(artifact, "join_policy").values()) == {False}
    assert _section(artifact, "crash_provenance")["input_sha256"] == contract.raw_sha256
    assert _section(artifact, "person_join")["semantic_regime_id"] == (contract.semantic_regime_id)
    for record in _records(artifact):
        source_id = record["outcome"]["source_record_id"]
        assert source_id.startswith(f"{year}:")
        assert record["outcome"]["occurred_on"].startswith(f"{year}-")
        assert record["mode_summary"]["source_record_id"] == source_id
        assert record["jurisdiction"]["source_record_id"] == source_id
        assert record["jurisdiction"]["state_code_system"] == contract.state_code_system
        assert record["jurisdiction"]["county_code_system"] == contract.county_code_system
    validate_joined_outcome_artifact_v2(artifact)


def test_canonical_bytes_are_deterministic_under_input_reordering() -> None:
    outcomes, summaries, crash, person = _inputs()
    contract = fars_year_contract_revision(2024, 1)
    first = artifacts_v2._project_joined_outcome_artifact_v2_without_source_authority(
        outcomes,
        summaries,
        person,
        crash,
        contract=contract,
    )
    second = artifacts_v2._project_joined_outcome_artifact_v2_without_source_authority(
        reversed(outcomes),
        reversed(summaries),
        person,
        crash,
        contract=contract,
    )
    assert first == second
    payload = canonical_joined_outcome_artifact_v2_bytes(first)
    assert payload == canonical_joined_outcome_artifact_v2_bytes(copy.deepcopy(first))
    assert payload.endswith(b"\n")
    assert b"\n" not in payload[:-1]
    assert json.loads(payload) == first
    assert b"generated_at" not in payload


@pytest.mark.parametrize(
    "field",
    [
        "year",
        "source_id",
        "source_revision_id",
        "distribution_url",
        "raw_size_bytes",
        "raw_sha256",
        "accident_encoding",
        "person_encoding",
        "release_stage",
        "semantic_regime_id",
        "table_encoding_profile",
        "crash_mapping_version",
        "person_mapping_version",
        "source_record_id_scheme",
        "state_code_system",
        "county_code_system",
        "revision",
    ],
)
def test_rejects_any_source_contract_revision_tampering(field: str) -> None:
    artifact = _build()
    source = _section(artifact, "source_contract")
    value = source[field]
    source[field] = value + 1 if isinstance(value, int) else f"{value}-tampered"
    with pytest.raises(ValueError):
        validate_joined_outcome_artifact_v2(artifact)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda value: _section(value, "crash_normalization").update(expected_year=2023),
        lambda value: _section(value, "crash_normalization").update(max_invalid_fraction=0.0500001),
        lambda value: _section(value, "crash_normalization").update(allow_record_regression=True),
        lambda value: _section(value, "crash_normalization").update(
            distribution_url=fars_year_contract(2023).distribution_url
        ),
        lambda value: _section(value, "crash_provenance").update(dataset_years=[2023]),
        lambda value: _section(value, "crash_provenance").update(input_sha256="0" * 64),
        lambda value: _section(value, "crash_provenance").update(release_status="preliminary"),
        lambda value: _section(value, "person_join").update(dataset_year=2023),
        lambda value: _section(value, "person_join").update(
            semantic_regime_id="fars_union_legacy_v1"
        ),
        lambda value: _section(value, "person_join").update(input_sha256="0" * 64),
        lambda value: _section(value, "join_policy").update(allow_record_regression=True),
        lambda value: _section(value, "join_policy").update(allow_mode_regression=True),
        lambda value: _section(value, "join_policy").update(allow_year_regression=True),
        lambda value: _section(value, "join_policy").update(allow_release_regression=True),
    ],
)
def test_rejects_year_revision_and_provenance_tampering(mutate: Any) -> None:
    artifact = _build()
    mutate(artifact)
    with pytest.raises(ValueError):
        validate_joined_outcome_artifact_v2(artifact)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda value: _records(value)[0].pop("jurisdiction"),
        lambda value: _records(value)[0]["outcome"].update(source_record_id="2023:100001"),
        lambda value: _records(value)[0]["outcome"].update(occurred_on="2023-01-01"),
        lambda value: _records(value)[0]["mode_summary"].update(source_record_id="2024:999999"),
        lambda value: _records(value)[0]["jurisdiction"].update(source_record_id="2024:999999"),
        lambda value: _records(value)[0]["jurisdiction"].update(state_code="48"),
        lambda value: _records(value)[0]["jurisdiction"].update(
            state_code_system="nhtsa_fars_state_2023"
        ),
        lambda value: _records(value)[0]["jurisdiction"].update(
            county_code_system="nhtsa_fars_gsa_2023"
        ),
        lambda value: _records(value)[0]["jurisdiction"].update(county_status="unknown"),
        lambda value: _records(value)[0]["mode_summary"].update(
            involved_modes=["pedestrian", "motor_vehicle_occupant"]
        ),
        lambda value: value.update(generated_at="2026-07-12T00:00:00Z"),
    ],
)
def test_rejects_record_sibling_code_system_and_shape_tampering(mutate: Any) -> None:
    artifact = _build()
    mutate(artifact)
    with pytest.raises(ValueError):
        validate_joined_outcome_artifact_v2(artifact)


def test_rejects_unsupported_state_code_even_when_siblings_match() -> None:
    artifact = _build()
    record = _records(artifact)[0]
    record["outcome"]["state_code"] = "99"
    record["jurisdiction"]["state_code"] = "99"
    with pytest.raises(ValueError):
        validate_joined_outcome_artifact_v2(artifact)


def test_rejects_aggregate_crash_rows_above_contract_cap() -> None:
    artifact = _build()
    records = _records(artifact)
    excluded = FARS_ACCIDENT_ROW_CAP - len(records) + 1
    crash = _section(artifact, "crash_provenance")
    crash["records_read"] = len(records) + excluded
    crash["rejection_reasons"] = {"invalid_location": excluded}
    person = _section(artifact, "person_join")
    person["records_excluded_with_rejected_crash"] = excluded
    person["cases_excluded_with_rejected_crash"] = excluded
    person["records_read"] = person["records_accepted"] + excluded
    person["rejection_reasons"] = {"parent_crash_rejected": excluded}
    with pytest.raises(ValueError):
        validate_joined_outcome_artifact_v2(artifact)


def test_rejects_legacy_artifact_type_and_non_native_source_descriptor() -> None:
    artifact = _build()
    artifact["artifact_type"] = JOINED_ARTIFACT_TYPE
    with pytest.raises(ValueError):
        validate_joined_outcome_artifact_v2(artifact)

    artifact = _build()
    source = _section(artifact, "source_contract")
    assert json.loads(json.dumps(source, allow_nan=False)) == source
    source["allowed_regressions"] = tuple(source["allowed_regressions"])
    with pytest.raises(ValueError):
        validate_joined_outcome_artifact_v2(artifact)


@pytest.mark.parametrize(
    ("argument", "value"),
    [
        ("max_invalid_fraction", 1.0),
        ("allow_record_regression", True),
        ("allow_mode_regression", True),
    ],
)
def test_builder_has_no_threshold_or_regression_escape_hatches(
    argument: str,
    value: object,
) -> None:
    with pytest.raises(TypeError):
        cast(Any, canonical_joined_outcome_artifact_v2_from_pinned_archive)(
            _archive(2024),
            year=2024,
            contract_revision=1,
            **{argument: value},
        )
    assert JOINED_ARTIFACT_V2_MAX_INVALID_FRACTION == 0.05


def test_schema_enumerates_a_future_registered_revision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    previous = fars_year_contract(2024)
    raw_sha256 = "2" * 64
    future = replace(
        previous,
        revision=3,
        predecessor_contract_sha256=fars_year_contract_sha256(previous),
        transition_review_reference="nearmiss-fars-source-audit-20260713",
        allowed_regressions=("record_counts",),
        source_revision_id=f"reviewed-20260713-{raw_sha256[:12]}",
        raw_size_bytes=previous.raw_size_bytes + 1,
        raw_sha256=raw_sha256,
        crash_mapping_version="2.0.0",
        person_mapping_version="2.0.0",
    )
    history = dict(year_contracts.FARS_YEAR_CONTRACT_HISTORY)
    history[2024] = (*history[2024], future)
    monkeypatch.setattr(year_contracts, "FARS_YEAR_CONTRACT_HISTORY", history)
    monkeypatch.setattr(artifacts_v2, "FARS_YEAR_CONTRACT_HISTORY", history)

    schema = artifacts_v2._schema()
    definitions = cast(dict[str, Any], schema["$defs"])
    assert "source_contract_2024_r1" in definitions
    assert "source_contract_2024_r2" in definitions
    assert "source_contract_2024_r3" in definitions
    assert len(cast(list[Any], schema["oneOf"])) == 7
    refs = {item["$ref"] for item in cast(dict[str, Any], definitions["source_contract"])["oneOf"]}
    assert "#/$defs/source_contract_2024_r3" in refs
    normalization = cast(dict[str, Any], definitions["normalization"])
    assert normalization["properties"]["adapter_version"]["enum"] == ["1.0.0", "2.0.0"]
    person_join = cast(dict[str, Any], definitions["person_join"])
    assert person_join["properties"]["mapping_version"]["enum"] == ["1.0.0", "2.0.0"]
    branches = cast(list[dict[str, Any]], schema["oneOf"])
    previous_branch = branches[-2]["properties"]
    future_branch = branches[-1]["properties"]
    assert previous_branch["source_contract"] == {"$ref": "#/$defs/source_contract_2024_r2"}
    assert previous_branch["crash_normalization"]["properties"]["adapter_version"] == {
        "const": "1.0.0"
    }
    assert previous_branch["person_join"]["properties"]["mapping_version"] == {"const": "1.0.0"}
    assert future_branch["source_contract"] == {"$ref": "#/$defs/source_contract_2024_r3"}
    assert future_branch["crash_normalization"]["properties"]["adapter_version"] == {
        "const": "2.0.0"
    }
    assert future_branch["person_join"]["properties"]["mapping_version"] == {"const": "2.0.0"}
    Draft202012Validator.check_schema(schema)


def test_explicit_r1_replay_does_not_switch_to_latest_r2() -> None:
    r1 = fars_year_contract_revision(2024, 1)
    assert fars_year_contract(2024).revision == 2
    payload = canonical_joined_outcome_artifact_v2_from_pinned_archive(
        _archive(2024),
        year=2024,
        contract_revision=1,
    )
    artifact = cast(dict[str, Any], json.loads(payload))
    assert artifact["source_contract"] == fars_year_contract_descriptor(r1)
    assert artifact["crash_normalization"]["adapter_version"] == "1.0.0"
    assert artifact["person_join"]["mapping_version"] == "1.0.0"


def test_explicit_2024_r2_replay_changes_only_provenance_over_the_same_archive() -> None:
    r1 = _build(2024, 1)
    r2 = _build(2024, 2)
    r1_contract = fars_year_contract_revision(2024, 1)
    r2_contract = fars_year_contract_revision(2024, 2)

    assert r1["source_contract"] == fars_year_contract_descriptor(r1_contract)
    assert r2["source_contract"] == fars_year_contract_descriptor(r2_contract)
    assert _section(r1, "crash_provenance")["release_status"] == "final"
    assert _section(r2, "crash_provenance")["release_status"] == "annual_report_file"
    assert (
        _section(r1, "crash_provenance")["input_sha256"]
        == _section(r2, "crash_provenance")["input_sha256"]
    )
    assert (
        _section(r1, "crash_normalization")["adapter_version"]
        == _section(r2, "crash_normalization")["adapter_version"]
    )
    assert (
        _section(r1, "person_join")["mapping_version"]
        == _section(r2, "person_join")["mapping_version"]
    )
    assert r1["records"] == r2["records"]
    validate_joined_outcome_artifact_v2(r1)
    validate_joined_outcome_artifact_v2(r2)


@pytest.mark.parametrize(
    ("revision", "error"),
    [
        (True, TypeError),
        (1.0, TypeError),
        (0, ValueError),
        (3, ValueError),
    ],
)
def test_authority_boundary_rejects_noninteger_or_unregistered_revision(
    revision: object,
    error: type[Exception],
) -> None:
    with pytest.raises(error):
        canonical_joined_outcome_artifact_v2_from_pinned_archive(
            _archive(2024),
            year=2024,
            contract_revision=cast(Any, revision),
        )


def test_builder_rejects_missing_jurisdiction_and_mixed_year_contract() -> None:
    outcomes, summaries, crash, person = _inputs()
    summaries[0] = replace(summaries[0], jurisdiction=None)
    with pytest.raises(ValueError, match="jurisdiction for every record"):
        artifacts_v2._project_joined_outcome_artifact_v2_without_source_authority(
            outcomes,
            summaries,
            person,
            crash,
            contract=fars_year_contract_revision(2024, 1),
        )

    outcomes, summaries, crash, person = _inputs(2023)
    with pytest.raises(ValueError):
        artifacts_v2._project_joined_outcome_artifact_v2_without_source_authority(
            outcomes,
            summaries,
            person,
            crash,
            contract=fars_year_contract_revision(2024, 1),
        )


def test_builder_and_schema_cap_annual_records(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert (
        cast(dict[str, Any], JOINED_OUTCOME_ARTIFACT_V2_SCHEMA["properties"])["records"]["maxItems"]
        == 45_000
    )
    outcomes, summaries, crash, person = _inputs()
    monkeypatch.setattr("nearmiss.joined_outcome_artifacts_v2.FARS_ACCIDENT_ROW_CAP", 1)
    with pytest.raises(ValueError, match="annual row cap"):
        artifacts_v2._project_joined_outcome_artifact_v2_without_source_authority(
            outcomes,
            summaries,
            person,
            crash,
            contract=fars_year_contract_revision(2024, 1),
        )
