# SPDX-License-Identifier: Apache-2.0
"""Deterministic private national FARS burden context.

This module deliberately starts at the coarsest useful nationwide projection:
one 2024 fatal crash contributes at most once to each involved-mode cell for
its source-native FARS state code.  The result is burden context, not a rate,
risk estimate, ranking, record linkage, or validation of community reports.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from collections.abc import Mapping
from typing import Any, NoReturn, cast

from .adapters.fars_joined import MODE_ORDER
from .joined_outcome_artifacts import (
    JOINED_ARTIFACT_SCHEMA_VERSION,
    JOINED_ARTIFACT_TYPE,
    canonical_joined_outcome_artifact_bytes,
    validate_joined_outcome_artifact,
)
from .verified_outcomes import VerifiedJoinedOutcomeEvidence, _VerifiedJoinedSnapshot

FARS_NATIONAL_CONTEXT_SCHEMA_VERSION = "1.0.0"
FARS_NATIONAL_CONTEXT_ARTIFACT_TYPE = "nearmiss.private.fars_national_context"
FARS_NATIONAL_CONTEXT_ALGORITHM_VERSION = "state-involved-mode-v1"
FARS_NATIONAL_CONTEXT_MINIMUM_K = 5
FARS_STATE_CODEBOOK_VERSION = "fars-state-codes-2024-v1"

_MAX_JOINED_BYTES = 64 * 1024 * 1024
_MAX_CASES = 36_297
_MAX_PERSON_RECORDS = 100_000
_MIN_NATIONAL_CASES = 30_000
_MAX_CELLS = 52 * len(MODE_ORDER)
_MAX_CONTRIBUTIONS = _MAX_CASES * len(MODE_ORDER)
_CANONICAL_STATE_RE = re.compile(r"^[1-9][0-9]?$", re.ASCII)

# Source-native FARS STATE values for the 50 states, DC, and Puerto Rico. FARS
# uses 43 for Puerto Rico rather than its Census/FIPS code 72, so these remain
# explicitly FARS codes until a pinned presentation join supplies names or
# geometry.
FARS_2024_STATE_CODES = (
    "1",
    "2",
    "4",
    "5",
    "6",
    "8",
    "9",
    "10",
    "11",
    "12",
    "13",
    "15",
    "16",
    "17",
    "18",
    "19",
    "20",
    "21",
    "22",
    "23",
    "24",
    "25",
    "26",
    "27",
    "28",
    "29",
    "30",
    "31",
    "32",
    "33",
    "34",
    "35",
    "36",
    "37",
    "38",
    "39",
    "40",
    "41",
    "42",
    "43",
    "44",
    "45",
    "46",
    "47",
    "48",
    "49",
    "50",
    "51",
    "53",
    "54",
    "55",
    "56",
)
_STATE_CODE_SET = frozenset(FARS_2024_STATE_CODES)
_NATIONAL_REQUIRED_STATE_CODES = _STATE_CODE_SET - {"43"}

FARS_NATIONAL_CONTEXT_CAVEAT = (
    "Fatal-crash burden context only. Counts are distinct FARS fatal crashes with at least one "
    "person in the involved mode. They are not exposure-normalized risk, incidence, causation, "
    "nonfatal crashes, near misses, record linkage, outcome validation, or a safety ranking. "
    "Mode cells overlap and are non-additive. The official 2024 National archive covers the 50 "
    "states and District of Columbia; Puerto Rico requires a separately verified source."
)


def _canonical_json_bytes(value: Mapping[str, object]) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def fars_state_codebook_sha256() -> str:
    """Return the digest of the exact ordered state-code contract."""
    payload = _canonical_json_bytes(
        {
            "codes": list(FARS_2024_STATE_CODES),
            "version": FARS_STATE_CODEBOOK_VERSION,
        }
    )
    return hashlib.sha256(payload).hexdigest()


def fars_national_context_contract_descriptor() -> dict[str, object]:
    """Return the immutable algorithm and safety contract."""
    return {
        "schema_version": FARS_NATIONAL_CONTEXT_SCHEMA_VERSION,
        "artifact_type": FARS_NATIONAL_CONTEXT_ARTIFACT_TYPE,
        "algorithm_version": FARS_NATIONAL_CONTEXT_ALGORITHM_VERSION,
        "minimum_k": FARS_NATIONAL_CONTEXT_MINIMUM_K,
        "state_codebook_version": FARS_STATE_CODEBOOK_VERSION,
        "state_codebook_sha256": fars_state_codebook_sha256(),
        "joined_schema_version": JOINED_ARTIFACT_SCHEMA_VERSION,
        "joined_artifact_type": JOINED_ARTIFACT_TYPE,
        "caps": {
            "max_joined_bytes": _MAX_JOINED_BYTES,
            "max_cases": _MAX_CASES,
            "max_person_records": _MAX_PERSON_RECORDS,
            "minimum_national_cases": _MIN_NATIONAL_CASES,
            "max_cells": _MAX_CELLS,
            "max_contributions": _MAX_CONTRIBUTIONS,
        },
    }


def _reject_constant(_value: str) -> NoReturn:
    raise ValueError("private national FARS source JSON contains a non-finite number")


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("private national FARS source JSON contains a duplicate key")
        result[key] = value
    return result


def _joined_artifact_from_canonical_bytes(payload: bytes) -> dict[str, object]:
    if type(payload) is not bytes:
        raise TypeError("private national FARS context requires canonical joined bytes")
    if not payload or len(payload) > _MAX_JOINED_BYTES:
        raise ValueError("private national FARS joined snapshot exceeds its byte safety limit")
    try:
        value = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_strict_object,
            parse_constant=_reject_constant,
        )
    except UnicodeDecodeError as exc:
        raise ValueError("private national FARS source JSON is not UTF-8") from exc
    except (json.JSONDecodeError, RecursionError) as exc:
        raise ValueError("private national FARS source JSON is invalid") from exc
    if not isinstance(value, dict):
        raise ValueError("private national FARS source JSON must be an object")
    artifact = cast(dict[str, object], value)
    validate_joined_outcome_artifact(artifact)
    if canonical_joined_outcome_artifact_bytes(artifact) != payload:
        raise ValueError("private national FARS source JSON is not canonical")
    return artifact


def _canonical_state_code(value: object) -> str:
    if not isinstance(value, str) or _CANONICAL_STATE_RE.fullmatch(value) is None:
        raise ValueError("private national FARS source has a noncanonical state code")
    if value not in _STATE_CODE_SET:
        raise ValueError("private national FARS source has an unsupported 2024 state code")
    return value


def _effective_k(requested_k: int) -> int:
    if isinstance(requested_k, bool) or not isinstance(requested_k, int):
        raise TypeError("private national FARS requested_k must be an integer")
    if not 1 <= requested_k <= _MAX_CASES:
        raise ValueError(f"private national FARS requested_k must be between 1 and {_MAX_CASES}")
    return max(FARS_NATIONAL_CONTEXT_MINIMUM_K, requested_k)


def _verified_joined_artifact(
    snapshot: _VerifiedJoinedSnapshot,
) -> tuple[dict[str, object], VerifiedJoinedOutcomeEvidence]:
    if type(snapshot) is not _VerifiedJoinedSnapshot:
        raise TypeError("private national FARS context requires a proof-bound joined snapshot")
    evidence = snapshot.evidence
    payload = snapshot.normalized_bytes
    if type(evidence) is not VerifiedJoinedOutcomeEvidence or type(payload) is not bytes:
        raise TypeError("private national FARS joined proof is invalid")
    if hashlib.sha256(payload).hexdigest() != evidence.normalized_sha256:
        raise ValueError("private national FARS joined proof digest does not match its evidence")
    joined = _joined_artifact_from_canonical_bytes(payload)
    crash = cast(Mapping[str, object], joined["crash_provenance"])
    normalization = cast(Mapping[str, object], joined["crash_normalization"])
    person = cast(Mapping[str, object], joined["person_join"])
    expected = {
        "dataset_year": person["dataset_year"],
        "crash_mapping_version": normalization["adapter_version"],
        "person_mapping_version": person["mapping_version"],
        "release_status": crash["release_status"],
        "crash_records_read": crash["records_read"],
        "crash_records_accepted": crash["records_accepted"],
        "crash_records_rejected": cast(int, crash["records_read"])
        - cast(int, crash["records_accepted"]),
        "person_records_read": person["records_read"],
        "person_records_accepted": person["records_accepted"],
        "person_records_excluded": person["records_excluded_with_rejected_crash"],
        "cases_joined": person["cases_joined"],
        "cases_excluded": person["cases_excluded_with_rejected_crash"],
        "raw_sha256": person["input_sha256"],
        "accident_sha256": person["accident_sha256"],
        "person_sha256": person["person_sha256"],
        "normalized_sha256": evidence.normalized_sha256,
    }
    if any(getattr(evidence, key) != value for key, value in expected.items()):
        raise ValueError("private national FARS joined proof disagrees with its artifact")
    return joined, evidence


def _require_national_coverage(
    joined: Mapping[str, object],
    evidence: VerifiedJoinedOutcomeEvidence,
    states_with_records: set[str],
) -> None:
    normalization = cast(Mapping[str, object], joined["crash_normalization"])
    distribution_url = normalization["distribution_url"]
    if (
        not isinstance(distribution_url, str)
        or not distribution_url.startswith(
            "https://static.nhtsa.gov/nhtsa/downloads/FARS/2024/National/"
        )
        or not distribution_url.casefold().endswith(".zip")
    ):
        raise ValueError("private national FARS context requires the official National ZIP scope")
    if (
        evidence.crash_records_read < _MIN_NATIONAL_CASES
        or evidence.cases_joined < _MIN_NATIONAL_CASES
        or not _NATIONAL_REQUIRED_STATE_CODES.issubset(states_with_records)
    ):
        raise ValueError("private national FARS source does not satisfy national coverage bounds")


def _build_verified_fars_state_context(
    snapshot: _VerifiedJoinedSnapshot,
    *,
    requested_k: int,
    require_national_coverage: bool,
) -> dict[str, object]:
    """Internal test seam; production callers require national coverage below."""
    joined, evidence = _verified_joined_artifact(snapshot)
    effective_k = _effective_k(requested_k)
    records = cast(list[Mapping[str, object]], joined["records"])
    if len(records) > _MAX_CASES:
        raise ValueError("private national FARS source exceeds its case safety limit")

    counts: Counter[tuple[str, str]] = Counter()
    states_with_records: set[str] = set()
    mode_set = frozenset(MODE_ORDER)
    for record in records:
        outcome = cast(Mapping[str, object], record["outcome"])
        summary = cast(Mapping[str, object], record["mode_summary"])
        state_code = _canonical_state_code(outcome.get("state_code"))
        states_with_records.add(state_code)
        involved_modes = summary["involved_modes"]
        if not isinstance(involved_modes, list):
            raise ValueError("private national FARS source involved modes are invalid")
        if any(not isinstance(mode, str) or mode not in mode_set for mode in involved_modes):
            raise ValueError("private national FARS source involved modes are invalid")
        if len(involved_modes) != len(set(involved_modes)):
            raise ValueError("private national FARS source involved modes are duplicated")
        for mode in involved_modes:
            counts[(state_code, mode)] += 1

    if require_national_coverage:
        _require_national_coverage(joined, evidence, states_with_records)

    mode_index = {mode: index for index, mode in enumerate(MODE_ORDER)}
    eligible = {key: count for key, count in counts.items() if count >= effective_k}
    ordered_keys = sorted(eligible, key=lambda key: (int(key[0]), mode_index[key[1]]))
    cells = [
        {"state_code": state_code, "involved_mode": mode, "crash_count": eligible[key]}
        for key in ordered_keys
        for state_code, mode in [key]
    ]
    total_contributions = sum(counts.values())
    eligible_contributions = sum(eligible.values())
    states_with_eligible = {state for state, _mode in eligible}

    artifact: dict[str, object] = {
        "schema_version": FARS_NATIONAL_CONTEXT_SCHEMA_VERSION,
        "artifact_type": FARS_NATIONAL_CONTEXT_ARTIFACT_TYPE,
        "visibility": "private",
        "caveat": FARS_NATIONAL_CONTEXT_CAVEAT,
        "source_lineage": {
            "source_id": evidence.source_id,
            "dataset_year": evidence.dataset_year,
            "release_status": evidence.release_status,
            "attempt_id": evidence.attempt_id,
            "raw_sha256": evidence.raw_sha256,
            "normalized_sha256": evidence.normalized_sha256,
            "accident_sha256": evidence.accident_sha256,
            "person_sha256": evidence.person_sha256,
            "joined_schema_version": joined["schema_version"],
            "crash_mapping_version": evidence.crash_mapping_version,
            "person_mapping_version": evidence.person_mapping_version,
            "crash_records_read": evidence.crash_records_read,
            "crash_records_accepted": evidence.crash_records_accepted,
            "crash_records_rejected": evidence.crash_records_rejected,
            "person_records_read": evidence.person_records_read,
            "person_records_accepted": evidence.person_records_accepted,
            "person_records_excluded": evidence.person_records_excluded,
            "cases_joined": evidence.cases_joined,
            "cases_excluded": evidence.cases_excluded,
        },
        "method": {
            "algorithm_version": FARS_NATIONAL_CONTEXT_ALGORITHM_VERSION,
            "geography": "fars_state_code",
            "coverage": (
                "official_2024_national_50_states_and_dc"
                if require_national_coverage
                else "state_codes_present_in_verified_snapshot"
            ),
            "coverage_state_codes": (
                sorted(_NATIONAL_REQUIRED_STATE_CODES, key=int) if require_national_coverage else []
            ),
            "dimension": "involved_mode",
            "contribution_unit": "distinct_crash_once_per_involved_mode",
            "minimum_k": FARS_NATIONAL_CONTEXT_MINIMUM_K,
            "effective_k": effective_k,
            "state_codebook_version": FARS_STATE_CODEBOOK_VERSION,
            "state_codebook_sha256": fars_state_codebook_sha256(),
            "modes_non_additive": True,
        },
        "accounting": {
            "case_count": len(records),
            "states_with_records": len(states_with_records),
            "states_with_eligible_cells": len(states_with_eligible),
            "positive_candidate_cell_count": len(counts),
            "eligible_cell_count": len(eligible),
            "suppressed_cell_count": len(counts) - len(eligible),
            "crash_contribution_total": total_contributions,
            "eligible_crash_contribution_total": eligible_contributions,
            "suppressed_crash_contribution_total": total_contributions - eligible_contributions,
        },
        "cells": cells,
    }
    validate_fars_national_context_artifact(artifact)
    return artifact


def build_verified_fars_national_context(
    snapshot: _VerifiedJoinedSnapshot,
    *,
    requested_k: int = FARS_NATIONAL_CONTEXT_MINIMUM_K,
) -> dict[str, object]:
    """Build private national context from a complete proof-bound 2024 snapshot."""
    return _build_verified_fars_state_context(
        snapshot,
        requested_k=requested_k,
        require_national_coverage=True,
    )


def _validate_cells(
    cells: list[Mapping[str, object]], *, effective_k: int, case_count: int
) -> tuple[int, set[str]]:
    expected_order = sorted(
        (
            (_canonical_state_code(cell["state_code"]), cast(str, cell["involved_mode"]))
            for cell in cells
        ),
        key=lambda key: (int(key[0]), MODE_ORDER.index(key[1])),
    )
    actual_order = [
        (cast(str, cell["state_code"]), cast(str, cell["involved_mode"])) for cell in cells
    ]
    if actual_order != expected_order or len(actual_order) != len(set(actual_order)):
        raise ValueError("private national FARS cells are not uniquely canonically ordered")
    if any(cast(int, cell["crash_count"]) < effective_k for cell in cells):
        raise ValueError("private national FARS cell is below effective k")
    if any(cast(int, cell["crash_count"]) > case_count for cell in cells):
        raise ValueError("private national FARS cell exceeds the source case count")
    return (
        sum(cast(int, cell["crash_count"]) for cell in cells),
        {cast(str, cell["state_code"]) for cell in cells},
    )


def _validate_accounting_bounds(accounting: Mapping[str, int], *, effective_k: int) -> None:
    case_count = accounting["case_count"]
    states = accounting["states_with_records"]
    positive = accounting["positive_candidate_cell_count"]
    contributions = accounting["crash_contribution_total"]
    if not (
        states <= min(case_count, positive)
        and positive <= min(contributions, states * len(MODE_ORDER))
        and case_count <= contributions <= case_count * len(MODE_ORDER)
        and accounting["states_with_eligible_cells"] <= accounting["eligible_cell_count"]
    ):
        raise ValueError("private national FARS source cardinality bounds are inconsistent")
    suppressed_cells = accounting["suppressed_cell_count"]
    suppressed_total = accounting["suppressed_crash_contribution_total"]
    if not (
        (suppressed_cells == 0 and suppressed_total == 0)
        or (
            suppressed_cells > 0
            and suppressed_cells
            <= suppressed_total
            <= suppressed_cells * min(effective_k - 1, case_count)
        )
    ):
        raise ValueError("private national FARS suppressed contribution bounds are inconsistent")


def _validate_source_accounting(source: Mapping[str, object]) -> None:
    if not (
        source["crash_records_read"]
        == cast(int, source["crash_records_accepted"]) + cast(int, source["crash_records_rejected"])
        and source["crash_records_accepted"] == source["cases_joined"]
        and source["cases_excluded"] == source["crash_records_rejected"]
        and source["person_records_read"]
        == cast(int, source["person_records_accepted"])
        + cast(int, source["person_records_excluded"])
        and cast(int, source["person_records_accepted"]) >= cast(int, source["cases_joined"])
        and cast(int, source["person_records_excluded"]) >= cast(int, source["cases_excluded"])
    ):
        raise ValueError("private national FARS source lineage accounting is inconsistent")


def _validate_coverage_marker(
    method: Mapping[str, object],
    accounting: Mapping[str, int],
    source: Mapping[str, object],
) -> None:
    coverage = method["coverage"]
    codes = method["coverage_state_codes"]
    if coverage == "state_codes_present_in_verified_snapshot":
        if codes != []:
            raise ValueError("private national FARS partial coverage marker is invalid")
        return
    expected_codes = sorted(_NATIONAL_REQUIRED_STATE_CODES, key=int)
    if not (
        codes == expected_codes
        and accounting["states_with_records"] == len(expected_codes)
        and accounting["case_count"] >= _MIN_NATIONAL_CASES
        and cast(int, source["crash_records_read"]) >= _MIN_NATIONAL_CASES
        and cast(int, source["cases_joined"]) >= _MIN_NATIONAL_CASES
    ):
        raise ValueError("private national FARS official coverage marker is invalid")


def validate_fars_national_context_artifact(artifact: Mapping[str, object]) -> None:
    """Validate the machine contract and all derivable accounting invariants."""
    from .fars_national_context_schema import validate_fars_national_context_schema

    validate_fars_national_context_schema(artifact)
    method = cast(Mapping[str, object], artifact["method"])
    accounting = cast(Mapping[str, int], artifact["accounting"])
    source = cast(Mapping[str, object], artifact["source_lineage"])
    cells = cast(list[Mapping[str, object]], artifact["cells"])
    effective_k = cast(int, method["effective_k"])
    if effective_k < FARS_NATIONAL_CONTEXT_MINIMUM_K:
        raise ValueError("private national FARS effective k is below the hard floor")
    case_count = accounting["case_count"]
    eligible_total, eligible_states = _validate_cells(
        cells, effective_k=effective_k, case_count=case_count
    )
    if accounting["eligible_cell_count"] != len(cells):
        raise ValueError("private national FARS eligible cell accounting is inconsistent")
    if accounting["case_count"] != source["cases_joined"]:
        raise ValueError("private national FARS source case accounting is inconsistent")
    _validate_source_accounting(source)
    if (
        accounting["positive_candidate_cell_count"]
        != accounting["eligible_cell_count"] + accounting["suppressed_cell_count"]
    ):
        raise ValueError("private national FARS cell accounting equation is inconsistent")
    if accounting["eligible_crash_contribution_total"] != eligible_total:
        raise ValueError("private national FARS eligible contribution accounting is inconsistent")
    if (
        accounting["crash_contribution_total"]
        != eligible_total + accounting["suppressed_crash_contribution_total"]
    ):
        raise ValueError("private national FARS contribution accounting equation is inconsistent")
    if accounting["states_with_eligible_cells"] != len(eligible_states):
        raise ValueError("private national FARS eligible state accounting is inconsistent")
    if accounting["states_with_eligible_cells"] > accounting["states_with_records"]:
        raise ValueError("private national FARS state accounting is inconsistent")
    _validate_coverage_marker(method, accounting, source)
    _validate_accounting_bounds(accounting, effective_k=effective_k)


def canonical_fars_national_context_bytes(artifact: Mapping[str, object]) -> bytes:
    """Serialize a validated artifact as deterministic canonical UTF-8 JSON."""
    validate_fars_national_context_artifact(artifact)
    return _canonical_json_bytes(artifact)


__all__ = [
    "FARS_2024_STATE_CODES",
    "FARS_NATIONAL_CONTEXT_ALGORITHM_VERSION",
    "FARS_NATIONAL_CONTEXT_ARTIFACT_TYPE",
    "FARS_NATIONAL_CONTEXT_CAVEAT",
    "FARS_NATIONAL_CONTEXT_MINIMUM_K",
    "FARS_NATIONAL_CONTEXT_SCHEMA_VERSION",
    "FARS_STATE_CODEBOOK_VERSION",
    "build_verified_fars_national_context",
    "canonical_fars_national_context_bytes",
    "fars_national_context_contract_descriptor",
    "fars_state_codebook_sha256",
    "validate_fars_national_context_artifact",
]
