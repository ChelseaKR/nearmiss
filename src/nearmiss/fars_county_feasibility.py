# SPDX-License-Identifier: Apache-2.0
"""Private, proof-bound feasibility accounting for county FARS context.

This module deliberately publishes nothing.  It reads an exact, verified annual
joined FARS snapshot, counts each crash once per involved mode, and separates
reported county contributions from the source-native sentinel county buckets.
The resulting private artifact proves whether a later, suppression-safe public
county projection can reconcile to the reviewed state-level contribution totals.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any, cast

from jsonschema import Draft202012Validator

from .adapters.fars_joined import MODE_ORDER
from .fars_national_context import FARS_2024_STATE_CODES, _verified_annual_joined_artifact
from .fars_year_contracts import (
    FARS_ACCIDENT_ROW_CAP,
    FarsYearContract,
    fars_year_contract_revision,
    fars_year_contract_sha256,
)

FARS_COUNTY_FEASIBILITY_SCHEMA_VERSION = "1.0.0"
FARS_COUNTY_FEASIBILITY_ARTIFACT_TYPE = "nearmiss.private.fars_county_feasibility"
FARS_COUNTY_FEASIBILITY_ALGORITHM_VERSION = "county-involved-mode-feasibility-v1"

_MAX_CASES = FARS_ACCIDENT_ROW_CAP
_MAX_CONTRIBUTIONS = _MAX_CASES * len(MODE_ORDER)
_MAX_STATES = len(FARS_2024_STATE_CODES)
_MAX_COUNTY_CELLS = _MAX_CONTRIBUTIONS
_STATE_CODE_RE = re.compile(r"^[1-9][0-9]?$", re.ASCII)
_COUNTY_CODE_RE = re.compile(r"^[0-9]{3}$", re.ASCII)
_SOURCE_RECORD_ID_RE = re.compile(r"^202[0-4]:[1-9][0-9]*$", re.ASCII)
_SENTINEL_STATUS_BY_CODE = {
    "000": "not_applicable",
    "997": "other",
    "998": "not_reported",
    "999": "unknown",
}
_SENTINEL_STATUSES = tuple(_SENTINEL_STATUS_BY_CODE.values())
_STATE_CODE_SET = frozenset(FARS_2024_STATE_CODES)
_NATIONAL_REQUIRED_STATE_CODES = _STATE_CODE_SET - {"43"}


def _closed(properties: Mapping[str, object]) -> dict[str, object]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": list(properties),
        "properties": dict(properties),
    }


def _count(*, maximum: int = _MAX_CONTRIBUTIONS, minimum: int = 0) -> dict[str, object]:
    return {"type": "integer", "minimum": minimum, "maximum": maximum}


_COUNTY_CELL_SCHEMA = _closed(
    {
        "county_code": {"type": "string", "pattern": "^[0-9]{3}$"},
        "involved_mode": {"type": "string", "enum": list(MODE_ORDER)},
        "crash_count": _count(minimum=1),
    }
)
_SENTINEL_CELL_SCHEMA = _closed(
    {
        "county_status": {"type": "string", "enum": list(_SENTINEL_STATUSES)},
        "involved_mode": {"type": "string", "enum": list(MODE_ORDER)},
        "crash_count": _count(minimum=1),
    }
)
_STATE_MODE_TOTAL_SCHEMA = _closed(
    {
        "involved_mode": {"type": "string", "enum": list(MODE_ORDER)},
        "crash_count": _count(minimum=1),
    }
)

FARS_COUNTY_FEASIBILITY_ARTIFACT_SCHEMA: dict[str, object] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "https://nearmiss.dev/schema/private-fars-county-feasibility.schema.json",
    "title": "Private NearMiss annual FARS county feasibility accounting",
    "type": "object",
    "additionalProperties": False,
    "required": [
        "schema_version",
        "artifact_type",
        "visibility",
        "dataset_year",
        "source_lineage",
        "method",
        "accounting",
        "states",
    ],
    "properties": {
        "schema_version": {"const": FARS_COUNTY_FEASIBILITY_SCHEMA_VERSION},
        "artifact_type": {"const": FARS_COUNTY_FEASIBILITY_ARTIFACT_TYPE},
        "visibility": {"const": "private"},
        "dataset_year": {"type": "integer", "minimum": 2020, "maximum": 2024},
        "source_lineage": _closed(
            {
                "source_id": {"type": "string", "minLength": 1},
                "contract_revision": {"type": "integer", "minimum": 1},
                "source_revision_id": {"type": "string", "minLength": 1},
                "contract_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                "normalized_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                "state_code_system": {"type": "string", "minLength": 1},
                "county_code_system": {"type": "string", "minLength": 1},
            }
        ),
        "method": _closed(
            {
                "algorithm_version": {"const": FARS_COUNTY_FEASIBILITY_ALGORITHM_VERSION},
                "geography": {"const": "fars_state_code_and_county_code"},
                "coverage": {"type": "string", "minLength": 1},
                "dimension": {"const": "involved_mode"},
                "contribution_unit": {"const": "distinct_crash_once_per_involved_mode"},
                "modes_non_additive": {"const": True},
                "modes": {
                    "type": "array",
                    "prefixItems": [{"const": mode} for mode in MODE_ORDER],
                    "items": False,
                    "minItems": len(MODE_ORDER),
                    "maxItems": len(MODE_ORDER),
                },
                "sentinel_statuses": {
                    "type": "array",
                    "prefixItems": [{"const": status} for status in _SENTINEL_STATUSES],
                    "items": False,
                    "minItems": len(_SENTINEL_STATUSES),
                    "maxItems": len(_SENTINEL_STATUSES),
                },
            }
        ),
        "accounting": _closed(
            {
                "case_count": _count(maximum=_MAX_CASES, minimum=1),
                "state_count": _count(maximum=_MAX_STATES, minimum=1),
                "reported_county_cell_count": _count(maximum=_MAX_COUNTY_CELLS),
                "sentinel_cell_count": _count(maximum=_MAX_CONTRIBUTIONS),
                "state_mode_total_count": _count(maximum=_MAX_CONTRIBUTIONS, minimum=1),
                "reported_county_contribution_total": _count(),
                "sentinel_contribution_total": _count(),
                "crash_contribution_total": _count(minimum=1),
            }
        ),
        "states": {
            "type": "array",
            "minItems": 1,
            "maxItems": _MAX_STATES,
            "items": _closed(
                {
                    "state_code": {"type": "string", "enum": list(FARS_2024_STATE_CODES)},
                    "county_cells": {
                        "type": "array",
                        "maxItems": _MAX_COUNTY_CELLS,
                        "items": _COUNTY_CELL_SCHEMA,
                    },
                    "sentinel_cells": {
                        "type": "array",
                        "maxItems": len(_SENTINEL_STATUSES) * len(MODE_ORDER),
                        "items": _SENTINEL_CELL_SCHEMA,
                    },
                    "state_mode_totals": {
                        "type": "array",
                        "minItems": 1,
                        "maxItems": len(MODE_ORDER),
                        "items": _STATE_MODE_TOTAL_SCHEMA,
                    },
                }
            ),
        },
    },
}

_VALIDATOR = Draft202012Validator(FARS_COUNTY_FEASIBILITY_ARTIFACT_SCHEMA)


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


def _schema_error(artifact: Mapping[str, object]) -> None:
    errors = sorted(_VALIDATOR.iter_errors(artifact), key=lambda error: list(error.absolute_path))
    if errors:
        error = errors[0]
        path = "/".join(str(part) for part in error.absolute_path) or "(root)"
        raise ValueError(
            f"invalid private FARS county feasibility artifact at {path}: {error.message}"
        )


def _required_mapping(record: Mapping[str, object], key: str) -> Mapping[str, object]:
    value = record.get(key)
    if not isinstance(value, Mapping):
        raise ValueError(f"private FARS county source record has invalid {key}")
    return value


def _canonical_state_code(value: object) -> str:
    if not isinstance(value, str) or _STATE_CODE_RE.fullmatch(value) is None:
        raise ValueError("private FARS county source has a noncanonical state code")
    if value not in _STATE_CODE_SET:
        raise ValueError("private FARS county source has an unsupported state code")
    return value


def _canonical_county_code(value: object) -> str:
    if not isinstance(value, str) or _COUNTY_CODE_RE.fullmatch(value) is None:
        raise ValueError("private FARS county source has a noncanonical county code")
    return value


def _source_record_id(value: object, *, year: int) -> str:
    if not isinstance(value, str) or _SOURCE_RECORD_ID_RE.fullmatch(value) is None:
        raise ValueError("private FARS county source has an invalid source record identity")
    if not value.startswith(f"{year}:"):
        raise ValueError("private FARS county source record identity does not match its year")
    return value


def _involved_modes(value: object) -> list[str]:
    if not isinstance(value, list) or any(mode not in MODE_ORDER for mode in value):
        raise ValueError("private FARS county source involved modes are invalid")
    if len(value) != len(set(value)):
        raise ValueError("private FARS county source involved modes are duplicated")
    return cast(list[str], value)


def _validate_source_lineage(artifact: Mapping[str, object]) -> FarsYearContract:
    year = cast(int, artifact["dataset_year"])
    source = cast(Mapping[str, object], artifact["source_lineage"])
    revision = cast(int, source["contract_revision"])
    try:
        contract = fars_year_contract_revision(year, revision)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "private FARS county feasibility uses an unregistered annual contract"
        ) from exc
    expected = {
        "source_id": contract.source_id,
        "source_revision_id": contract.source_revision_id,
        "contract_sha256": fars_year_contract_sha256(contract),
        "state_code_system": contract.state_code_system,
        "county_code_system": contract.county_code_system,
    }
    if any(source[key] != value for key, value in expected.items()):
        raise ValueError("private FARS county feasibility source lineage is inconsistent")
    return contract


def _canonical_state_keys(states: Sequence[Mapping[str, object]]) -> list[str]:
    keys = [cast(str, state["state_code"]) for state in states]
    if keys != sorted(keys, key=int) or len(keys) != len(set(keys)):
        raise ValueError(
            "private FARS county feasibility states are not uniquely canonically ordered"
        )
    return keys


def _canonical_mode_keys(cells: Sequence[Mapping[str, object]], *, key: str) -> None:
    if key == "county_cells":
        actual: list[tuple[str, str]] = [
            (cast(str, cell["county_code"]), cast(str, cell["involved_mode"])) for cell in cells
        ]
        expected = sorted(
            actual,
            key=lambda value: (int(value[0]), MODE_ORDER.index(value[1])),
        )
    elif key == "sentinel_cells":
        actual = [
            (cast(str, cell["county_status"]), cast(str, cell["involved_mode"])) for cell in cells
        ]
        expected = sorted(
            actual,
            key=lambda value: (
                _SENTINEL_STATUSES.index(value[0]),
                MODE_ORDER.index(value[1]),
            ),
        )
    else:
        actual_modes = [cast(str, cell["involved_mode"]) for cell in cells]
        expected_modes = sorted(actual_modes, key=MODE_ORDER.index)
        if actual_modes != expected_modes or len(actual_modes) != len(set(actual_modes)):
            raise ValueError(
                f"private FARS county feasibility {key} are not uniquely canonically ordered"
            )
        return
    if actual != expected or len(actual) != len(set(actual)):
        raise ValueError(
            f"private FARS county feasibility {key} are not uniquely canonically ordered"
        )


def validate_fars_county_feasibility_artifact(  # noqa: C901 - keep proof checks adjacent
    artifact: Mapping[str, object],
) -> None:
    """Reject a malformed, unreconciled, or noncanonical private artifact."""

    _schema_error(artifact)
    contract = _validate_source_lineage(artifact)
    source = cast(Mapping[str, object], artifact["source_lineage"])
    if not isinstance(source["normalized_sha256"], str):
        raise ValueError("private FARS county feasibility normalized lineage is invalid")
    method = cast(Mapping[str, object], artifact["method"])
    expected_coverage = f"official_{contract.year}_national_50_states_and_dc"
    if method["coverage"] != expected_coverage:
        raise ValueError("private FARS county feasibility coverage is inconsistent")
    states = cast(list[Mapping[str, object]], artifact["states"])
    state_codes = _canonical_state_keys(states)
    if set(state_codes) != _NATIONAL_REQUIRED_STATE_CODES:
        raise ValueError(
            "private FARS county feasibility does not cover the reviewed national states"
        )

    case_count = cast(int, cast(Mapping[str, object], artifact["accounting"])["case_count"])
    county_cell_count = 0
    sentinel_cell_count = 0
    state_mode_total_count = 0
    reported_total = 0
    sentinel_total = 0
    contribution_total = 0
    for state in states:
        county_cells = cast(list[Mapping[str, object]], state["county_cells"])
        sentinel_cells = cast(list[Mapping[str, object]], state["sentinel_cells"])
        state_totals = cast(list[Mapping[str, object]], state["state_mode_totals"])
        _canonical_mode_keys(county_cells, key="county_cells")
        _canonical_mode_keys(sentinel_cells, key="sentinel_cells")
        _canonical_mode_keys(state_totals, key="state_mode_totals")
        county_by_mode: Counter[str] = Counter()
        sentinel_by_mode: Counter[str] = Counter()
        for cell in county_cells:
            county_code = _canonical_county_code(cell["county_code"])
            if county_code in _SENTINEL_STATUS_BY_CODE:
                raise ValueError("private FARS county feasibility renders a sentinel as a county")
            count = cast(int, cell["crash_count"])
            if count > case_count:
                raise ValueError("private FARS county feasibility county cell exceeds case count")
            county_by_mode[cast(str, cell["involved_mode"])] += count
            reported_total += count
        for cell in sentinel_cells:
            status = cast(str, cell["county_status"])
            if status not in _SENTINEL_STATUSES:
                raise ValueError("private FARS county feasibility sentinel status is unsupported")
            count = cast(int, cell["crash_count"])
            if count > case_count:
                raise ValueError("private FARS county feasibility sentinel cell exceeds case count")
            sentinel_by_mode[cast(str, cell["involved_mode"])] += count
            sentinel_total += count
        expected_totals = {
            mode: county_by_mode[mode] + sentinel_by_mode[mode]
            for mode in MODE_ORDER
            if county_by_mode[mode] + sentinel_by_mode[mode]
        }
        actual_totals = {
            cast(str, cell["involved_mode"]): cast(int, cell["crash_count"])
            for cell in state_totals
        }
        if actual_totals != expected_totals:
            raise ValueError(
                "private FARS county feasibility state-mode reconciliation is inconsistent"
            )
        contribution_total += sum(actual_totals.values())
        county_cell_count += len(county_cells)
        sentinel_cell_count += len(sentinel_cells)
        state_mode_total_count += len(state_totals)

    accounting = cast(Mapping[str, int], artifact["accounting"])
    if not (
        accounting["state_count"] == len(states)
        and accounting["reported_county_cell_count"] == county_cell_count
        and accounting["sentinel_cell_count"] == sentinel_cell_count
        and accounting["state_mode_total_count"] == state_mode_total_count
        and accounting["reported_county_contribution_total"] == reported_total
        and accounting["sentinel_contribution_total"] == sentinel_total
        and accounting["crash_contribution_total"]
        == contribution_total
        == reported_total + sentinel_total
        and case_count <= contribution_total <= case_count * len(MODE_ORDER)
    ):
        raise ValueError("private FARS county feasibility accounting is inconsistent")


def _build_county_feasibility(  # noqa: C901 - keep source validation and accounting adjacent
    records: Sequence[Mapping[str, object]],
    *,
    contract: FarsYearContract,
    normalized_sha256: str,
    require_national_coverage: bool,
) -> dict[str, object]:
    if not records or len(records) > _MAX_CASES:
        raise ValueError("private FARS county source exceeds its case safety bounds")
    if (
        not isinstance(normalized_sha256, str)
        or re.fullmatch(r"[0-9a-f]{64}", normalized_sha256) is None
    ):
        raise ValueError("private FARS county source digest is invalid")

    county_counts: Counter[tuple[str, str, str]] = Counter()
    sentinel_counts: Counter[tuple[str, str, str]] = Counter()
    state_mode_totals: Counter[tuple[str, str]] = Counter()
    seen_ids: set[str] = set()
    states_with_records: set[str] = set()
    for record in records:
        outcome = _required_mapping(record, "outcome")
        summary = _required_mapping(record, "mode_summary")
        jurisdiction = _required_mapping(record, "jurisdiction")
        source_id = _source_record_id(outcome.get("source_record_id"), year=contract.year)
        if source_id in seen_ids:
            raise ValueError("private FARS county source contains duplicate crash identities")
        if (
            summary.get("source_record_id") != source_id
            or jurisdiction.get("source_record_id") != source_id
        ):
            raise ValueError("private FARS county source sibling identities do not match")
        seen_ids.add(source_id)
        state_code = _canonical_state_code(outcome.get("state_code"))
        if jurisdiction.get("state_code") != state_code:
            raise ValueError("private FARS county source jurisdiction state does not match outcome")
        if jurisdiction.get("state_code_system") != contract.state_code_system:
            raise ValueError("private FARS county source state code system is inconsistent")
        if jurisdiction.get("county_code_system") != contract.county_code_system:
            raise ValueError("private FARS county source county code system is inconsistent")
        county_code = _canonical_county_code(jurisdiction.get("county_code"))
        expected_status = _SENTINEL_STATUS_BY_CODE.get(county_code, "reported")
        if jurisdiction.get("county_status") != expected_status:
            raise ValueError("private FARS county source status is inconsistent")
        modes = _involved_modes(summary.get("involved_modes"))
        states_with_records.add(state_code)
        for mode in modes:
            state_mode_totals[(state_code, mode)] += 1
            if expected_status == "reported":
                county_counts[(state_code, county_code, mode)] += 1
            else:
                sentinel_counts[(state_code, expected_status, mode)] += 1

    if require_national_coverage and states_with_records != _NATIONAL_REQUIRED_STATE_CODES:
        raise ValueError("private FARS county source does not satisfy national coverage")

    mode_index = {mode: index for index, mode in enumerate(MODE_ORDER)}
    state_codes = sorted(states_with_records, key=int)
    states: list[dict[str, object]] = []
    for state_code in state_codes:
        county_cells = [
            {"county_code": county_code, "involved_mode": mode, "crash_count": count}
            for (cell_state, county_code, mode), count in sorted(
                county_counts.items(),
                key=lambda item: (int(item[0][0]), int(item[0][1]), mode_index[item[0][2]]),
            )
            if cell_state == state_code
        ]
        sentinel_cells = [
            {"county_status": status, "involved_mode": mode, "crash_count": count}
            for (cell_state, status, mode), count in sorted(
                sentinel_counts.items(),
                key=lambda item: (
                    int(item[0][0]),
                    _SENTINEL_STATUSES.index(item[0][1]),
                    mode_index[item[0][2]],
                ),
            )
            if cell_state == state_code
        ]
        totals = [
            {"involved_mode": mode, "crash_count": count}
            for (cell_state, mode), count in sorted(
                state_mode_totals.items(),
                key=lambda item: (int(item[0][0]), mode_index[item[0][1]]),
            )
            if cell_state == state_code
        ]
        states.append(
            {
                "state_code": state_code,
                "county_cells": county_cells,
                "sentinel_cells": sentinel_cells,
                "state_mode_totals": totals,
            }
        )

    reported_total = sum(county_counts.values())
    sentinel_total = sum(sentinel_counts.values())
    artifact: dict[str, object] = {
        "schema_version": FARS_COUNTY_FEASIBILITY_SCHEMA_VERSION,
        "artifact_type": FARS_COUNTY_FEASIBILITY_ARTIFACT_TYPE,
        "visibility": "private",
        "dataset_year": contract.year,
        "source_lineage": {
            "source_id": contract.source_id,
            "contract_revision": contract.revision,
            "source_revision_id": contract.source_revision_id,
            "contract_sha256": fars_year_contract_sha256(contract),
            "normalized_sha256": normalized_sha256,
            "state_code_system": contract.state_code_system,
            "county_code_system": contract.county_code_system,
        },
        "method": {
            "algorithm_version": FARS_COUNTY_FEASIBILITY_ALGORITHM_VERSION,
            "geography": "fars_state_code_and_county_code",
            "coverage": (
                f"official_{contract.year}_national_50_states_and_dc"
                if require_national_coverage
                else "state_codes_present_in_verified_snapshot"
            ),
            "dimension": "involved_mode",
            "contribution_unit": "distinct_crash_once_per_involved_mode",
            "modes_non_additive": True,
            "modes": list(MODE_ORDER),
            "sentinel_statuses": list(_SENTINEL_STATUSES),
        },
        "accounting": {
            "case_count": len(records),
            "state_count": len(states),
            "reported_county_cell_count": len(county_counts),
            "sentinel_cell_count": len(sentinel_counts),
            "state_mode_total_count": len(state_mode_totals),
            "reported_county_contribution_total": reported_total,
            "sentinel_contribution_total": sentinel_total,
            "crash_contribution_total": reported_total + sentinel_total,
        },
        "states": states,
    }
    if require_national_coverage:
        validate_fars_county_feasibility_artifact(artifact)
    return artifact


def build_verified_fars_year_county_feasibility(
    snapshot: object,
    *,
    year: int,
    contract_revision: int,
) -> dict[str, object]:
    """Build private county accounting only from an exact annual verified snapshot."""

    joined, evidence, contract = _verified_annual_joined_artifact(
        snapshot,
        year=year,
        contract_revision=contract_revision,
    )
    records = cast(list[Mapping[str, object]], joined["records"])
    normalized_sha256 = cast(str, cast(Any, evidence).normalized_sha256)
    return _build_county_feasibility(
        records,
        contract=contract,
        normalized_sha256=normalized_sha256,
        require_national_coverage=True,
    )


def canonical_fars_county_feasibility_bytes(artifact: Mapping[str, object]) -> bytes:
    """Return closed, canonical bytes for one validated private feasibility artifact."""

    validate_fars_county_feasibility_artifact(artifact)
    return _canonical_json_bytes(artifact)
