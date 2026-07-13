# SPDX-License-Identifier: Apache-2.0
"""Deterministic public-safe projection of verified annual National FARS burden.

The private national context contains proof lineage that is useful to an
operator but is unnecessary on the public site.  This module accepts only a
fully validated, nationally complete, effective-k=10 private artifact and
projects its state-by-involved-mode cells into a closed public contract.  Every
state always carries all six modes; a missing private cell becomes the single
non-value status ``suppressed_or_zero`` and is never represented as zero.
"""

from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Mapping
from types import MappingProxyType
from typing import Any, NoReturn, cast

from jsonschema import Draft202012Validator, FormatChecker

from .adapters.fars_joined import MODE_ORDER
from .fars_national_context import (
    FARS_NATIONAL_CONTEXT_ALGORITHM_VERSION,
    FARS_NATIONAL_CONTEXT_ARTIFACT_TYPE,
    build_verified_fars_national_context,
    build_verified_fars_year_national_context,
    fars_national_context_caveat,
    validate_fars_national_context_artifact,
)
from .fars_year_contracts import (
    FARS_RELEASE_STAGES,
    FARS_YEAR_CONTRACT_HISTORY,
    FarsYearContract,
    fars_year_contract_revision,
)
from .verified_outcomes import _VerifiedJoinedSnapshot

FARS_PUBLIC_CONTEXT_SCHEMA_VERSION = "1.0.0"
FARS_PUBLIC_CONTEXT_ARTIFACT_TYPE = "nearmiss.public.fars_state_context"
FARS_PUBLIC_CONTEXT_EFFECTIVE_K = 10
FARS_PUBLIC_CONTEXT_DISTRIBUTION_URL = (
    "https://static.nhtsa.gov/nhtsa/downloads/FARS/2024/National/FARS2024NationalCSV.zip"
)
FARS_PUBLIC_CONTEXT_SOURCE_REVISION_ID = "reviewed-20260712-5112727a8c0d"
FARS_PUBLIC_CONTEXT_RAW_SIZE_BYTES = 32_672_161
FARS_PUBLIC_CONTEXT_RAW_SHA256 = "5112727a8c0dc91ffee27ca05bddb073934f2d192ce4fae997da767dccdbe04f"
FARS_PUBLIC_STATE_CROSSWALK_VERSION = "fars-usps-50-states-dc-2024-v1"

FARS_PUBLIC_CONTEXT_CAVEAT = (
    "Counts are distinct 2024 FARS fatal crashes with at least one person in the involved mode, "
    "counted at most once per crash per mode. They are fatal-crash burden context, not "
    "exposure-normalized risk, incidence, causation, nonfatal crashes, near misses, record "
    "linkage, outcome validation, or a safety ranking. Mode cells overlap and are non-additive. "
    "A suppressed_or_zero cell combines a true zero with a positive count below k=10 and must "
    "never be read as zero. k=10 is a stability and publication guard for already-public FARS "
    "data, not a confidentiality guarantee. The official 2024 National archive covers the 50 "
    "states and District of Columbia; Puerto Rico requires a separately verified source."
)


def fars_public_context_title(year: int) -> str:
    """Return the exact annual public title."""
    fars_year_contract_revision(year, 1)
    return f"{year} US fatal-crash burden by state and involved mode"


def fars_public_context_caveat(year: int) -> str:
    """Return the exact annual public caveat, preserving the 2024 release."""
    fars_year_contract_revision(year, 1)
    return FARS_PUBLIC_CONTEXT_CAVEAT.replace("2024", str(year))


def fars_public_state_crosswalk_version(year: int) -> str:
    """Return the reviewed annual state-presentation contract version."""
    fars_year_contract_revision(year, 1)
    return f"fars-usps-50-states-dc-{year}-v1"


# Source-native FARS STATE code -> USPS abbreviation and display name. Puerto
# Rico (FARS code 43) is intentionally absent: the audited 2024 National archive
# covers exactly the 50 states and District of Columbia.
FARS_PUBLIC_STATE_CROSSWALK: Mapping[str, tuple[str, str]] = MappingProxyType(
    {
        "1": ("AL", "Alabama"),
        "2": ("AK", "Alaska"),
        "4": ("AZ", "Arizona"),
        "5": ("AR", "Arkansas"),
        "6": ("CA", "California"),
        "8": ("CO", "Colorado"),
        "9": ("CT", "Connecticut"),
        "10": ("DE", "Delaware"),
        "11": ("DC", "District of Columbia"),
        "12": ("FL", "Florida"),
        "13": ("GA", "Georgia"),
        "15": ("HI", "Hawaii"),
        "16": ("ID", "Idaho"),
        "17": ("IL", "Illinois"),
        "18": ("IN", "Indiana"),
        "19": ("IA", "Iowa"),
        "20": ("KS", "Kansas"),
        "21": ("KY", "Kentucky"),
        "22": ("LA", "Louisiana"),
        "23": ("ME", "Maine"),
        "24": ("MD", "Maryland"),
        "25": ("MA", "Massachusetts"),
        "26": ("MI", "Michigan"),
        "27": ("MN", "Minnesota"),
        "28": ("MS", "Mississippi"),
        "29": ("MO", "Missouri"),
        "30": ("MT", "Montana"),
        "31": ("NE", "Nebraska"),
        "32": ("NV", "Nevada"),
        "33": ("NH", "New Hampshire"),
        "34": ("NJ", "New Jersey"),
        "35": ("NM", "New Mexico"),
        "36": ("NY", "New York"),
        "37": ("NC", "North Carolina"),
        "38": ("ND", "North Dakota"),
        "39": ("OH", "Ohio"),
        "40": ("OK", "Oklahoma"),
        "41": ("OR", "Oregon"),
        "42": ("PA", "Pennsylvania"),
        "44": ("RI", "Rhode Island"),
        "45": ("SC", "South Carolina"),
        "46": ("SD", "South Dakota"),
        "47": ("TN", "Tennessee"),
        "48": ("TX", "Texas"),
        "49": ("UT", "Utah"),
        "50": ("VT", "Vermont"),
        "51": ("VA", "Virginia"),
        "53": ("WA", "Washington"),
        "54": ("WV", "West Virginia"),
        "55": ("WI", "Wisconsin"),
        "56": ("WY", "Wyoming"),
    }
)

_STATE_COUNT = 51
_STATE_MODE_CELL_COUNT = _STATE_COUNT * len(MODE_ORDER)
_MAX_CASES = 45_000
_MAX_CONTRIBUTIONS = _MAX_CASES * len(MODE_ORDER)
_MAX_PUBLIC_ARTIFACT_BYTES = 256 * 1024
_SHA256 = {"type": "string", "pattern": "^[0-9a-f]{64}$"}
_PUBLIC_RELEASE_CONTRACTS = tuple(
    contract for history in FARS_YEAR_CONTRACT_HISTORY.values() for contract in history
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


def _state_crosswalk_payload(year: int = 2024) -> dict[str, object]:
    return {
        "states": [
            {"state_code": code, "state_abbreviation": abbreviation, "state_name": name}
            for code, (abbreviation, name) in sorted(
                FARS_PUBLIC_STATE_CROSSWALK.items(), key=lambda item: item[1][1]
            )
        ],
        "version": fars_public_state_crosswalk_version(year),
    }


def fars_public_state_crosswalk_sha256(year: int = 2024) -> str:
    """Return the digest of the exact ordered public presentation crosswalk."""
    return hashlib.sha256(_canonical_json_bytes(_state_crosswalk_payload(year))).hexdigest()


def _closed(properties: Mapping[str, object]) -> dict[str, object]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": list(properties),
        "properties": dict(properties),
    }


def _count(maximum: int, *, minimum: int = 0) -> dict[str, object]:
    return {"type": "integer", "minimum": minimum, "maximum": maximum}


_PUBLISHED_CELL_SCHEMA = _closed(
    {
        "involved_mode": {"type": "string", "enum": list(MODE_ORDER)},
        "status": {"const": "published"},
        "crash_count": _count(_MAX_CASES, minimum=FARS_PUBLIC_CONTEXT_EFFECTIVE_K),
    }
)
_SUPPRESSED_CELL_SCHEMA = _closed(
    {
        "involved_mode": {"type": "string", "enum": list(MODE_ORDER)},
        "status": {"const": "suppressed_or_zero"},
    }
)


def _release_schema_branch(contract: FarsYearContract) -> dict[str, object]:
    year = contract.year
    return {
        "properties": {
            "title": {"const": fars_public_context_title(year)},
            "dataset_year": {"const": year},
            "source": {
                "properties": {
                    "name": {"const": "NHTSA Fatality Analysis Reporting System (FARS)"},
                    "release_stage": {"const": contract.release_stage},
                    "distribution_url": {"const": contract.distribution_url},
                    "source_revision_id": {"const": contract.source_revision_id},
                    "raw_size_bytes": {"const": contract.raw_size_bytes},
                    "raw_sha256": {"const": contract.raw_sha256},
                }
            },
            "geography": {
                "properties": {
                    "coverage": {"const": f"official_{year}_national_50_states_and_dc"},
                    "state_crosswalk_version": {"const": fars_public_state_crosswalk_version(year)},
                    "state_crosswalk_sha256": {"const": fars_public_state_crosswalk_sha256(year)},
                }
            },
            "caveat": {"const": fars_public_context_caveat(year)},
        }
    }


FARS_PUBLIC_CONTEXT_ARTIFACT_SCHEMA: dict[str, object] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "https://nearmiss.dev/schema/public-fars-state-context.schema.json",
    "title": "Public NearMiss annual FARS state burden context",
    "type": "object",
    "additionalProperties": False,
    "required": [
        "schema_version",
        "artifact_type",
        "visibility",
        "title",
        "dataset_year",
        "source",
        "geography",
        "metric",
        "accounting",
        "caveat",
        "states",
    ],
    "oneOf": [_release_schema_branch(contract) for contract in _PUBLIC_RELEASE_CONTRACTS],
    "properties": {
        "schema_version": {"const": FARS_PUBLIC_CONTEXT_SCHEMA_VERSION},
        "artifact_type": {"const": FARS_PUBLIC_CONTEXT_ARTIFACT_TYPE},
        "visibility": {"const": "public"},
        "title": {
            "enum": sorted({fars_public_context_title(c.year) for c in _PUBLIC_RELEASE_CONTRACTS})
        },
        "dataset_year": {"enum": sorted({contract.year for contract in _PUBLIC_RELEASE_CONTRACTS})},
        "source": _closed(
            {
                "name": {"const": "NHTSA Fatality Analysis Reporting System (FARS)"},
                "release_stage": {"enum": list(FARS_RELEASE_STAGES)},
                "distribution_url": {"type": "string", "format": "uri"},
                "source_revision_id": {"type": "string"},
                "raw_size_bytes": {"type": "integer", "minimum": 1},
                "raw_sha256": _SHA256,
            }
        ),
        "geography": _closed(
            {
                "type": {"const": "fars_state_code"},
                "coverage": {
                    "enum": sorted(
                        {
                            f"official_{contract.year}_national_50_states_and_dc"
                            for contract in _PUBLIC_RELEASE_CONTRACTS
                        }
                    )
                },
                "state_count": {"const": _STATE_COUNT},
                "state_crosswalk_version": {
                    "enum": sorted(
                        {
                            fars_public_state_crosswalk_version(contract.year)
                            for contract in _PUBLIC_RELEASE_CONTRACTS
                        }
                    )
                },
                "state_crosswalk_sha256": {
                    "enum": sorted(
                        {
                            fars_public_state_crosswalk_sha256(contract.year)
                            for contract in _PUBLIC_RELEASE_CONTRACTS
                        }
                    )
                },
            }
        ),
        "metric": _closed(
            {
                "algorithm_version": {"const": FARS_NATIONAL_CONTEXT_ALGORITHM_VERSION},
                "dimension": {"const": "involved_mode"},
                "contribution_unit": {"const": "distinct_crash_once_per_involved_mode"},
                "effective_k": {"const": FARS_PUBLIC_CONTEXT_EFFECTIVE_K},
                "modes_non_additive": {"const": True},
                "modes": {
                    "type": "array",
                    "prefixItems": [{"const": mode} for mode in MODE_ORDER],
                    "items": False,
                    "minItems": len(MODE_ORDER),
                    "maxItems": len(MODE_ORDER),
                },
            }
        ),
        "accounting": _closed(
            {
                "case_count": _count(_MAX_CASES, minimum=30_000),
                "state_count": {"const": _STATE_COUNT},
                "state_mode_cell_count": {"const": _STATE_MODE_CELL_COUNT},
                "published_cell_count": _count(_STATE_MODE_CELL_COUNT),
                "suppressed_or_zero_cell_count": _count(_STATE_MODE_CELL_COUNT),
                "positive_candidate_cell_count": _count(_STATE_MODE_CELL_COUNT),
                "positive_suppressed_cell_count": _count(_STATE_MODE_CELL_COUNT),
                "crash_contribution_total": _count(_MAX_CONTRIBUTIONS, minimum=30_000),
                "published_crash_contribution_total": _count(_MAX_CONTRIBUTIONS),
                "suppressed_crash_contribution_total": _count(_MAX_CONTRIBUTIONS),
            }
        ),
        "caveat": {
            "enum": sorted({fars_public_context_caveat(c.year) for c in _PUBLIC_RELEASE_CONTRACTS})
        },
        "states": {
            "type": "array",
            "minItems": _STATE_COUNT,
            "maxItems": _STATE_COUNT,
            "items": _closed(
                {
                    "state_code": {
                        "type": "string",
                        "enum": list(FARS_PUBLIC_STATE_CROSSWALK),
                    },
                    "state_abbreviation": {
                        "type": "string",
                        "enum": [value[0] for value in FARS_PUBLIC_STATE_CROSSWALK.values()],
                    },
                    "state_name": {
                        "type": "string",
                        "enum": [value[1] for value in FARS_PUBLIC_STATE_CROSSWALK.values()],
                    },
                    "cells": {
                        "type": "array",
                        "minItems": len(MODE_ORDER),
                        "maxItems": len(MODE_ORDER),
                        "items": {
                            "oneOf": [
                                _PUBLISHED_CELL_SCHEMA,
                                _SUPPRESSED_CELL_SCHEMA,
                            ]
                        },
                    },
                }
            ),
        },
    },
}

_VALIDATOR = Draft202012Validator(
    FARS_PUBLIC_CONTEXT_ARTIFACT_SCHEMA,
    format_checker=FormatChecker(),
)


def _schema_error(artifact: Mapping[str, object]) -> None:
    errors = sorted(_VALIDATOR.iter_errors(artifact), key=lambda error: list(error.absolute_path))
    if errors:
        error = errors[0]
        path = "/".join(str(part) for part in error.absolute_path) or "(root)"
        raise ValueError(f"invalid public FARS state context at {path}: {error.message}")


def _expected_states() -> list[tuple[str, str, str]]:
    return sorted(
        (
            (code, abbreviation, name)
            for code, (abbreviation, name) in FARS_PUBLIC_STATE_CROSSWALK.items()
        ),
        key=lambda value: value[2],
    )


def validate_fars_public_context_artifact(artifact: Mapping[str, object]) -> None:
    """Reject structural, crosswalk, ordering, or accounting inconsistencies."""
    _schema_error(artifact)
    states = cast(list[Mapping[str, object]], artifact["states"])
    actual_states = [
        (state["state_code"], state["state_abbreviation"], state["state_name"]) for state in states
    ]
    if actual_states != _expected_states():
        raise ValueError("public FARS state crosswalk or canonical ordering is inconsistent")

    accounting = cast(Mapping[str, int], artifact["accounting"])
    case_count = accounting["case_count"]
    published_cells = 0
    published_contributions = 0
    for state in states:
        cells = cast(list[Mapping[str, object]], state["cells"])
        if [cell["involved_mode"] for cell in cells] != list(MODE_ORDER):
            raise ValueError(
                "public FARS state mode cells are not complete and canonically ordered"
            )
        for cell in cells:
            if cell["status"] == "published":
                published_cells += 1
                count = cast(int, cell["crash_count"])
                if count > case_count:
                    raise ValueError("public FARS cell exceeds the source case count")
                published_contributions += count

    contribution_total = accounting["crash_contribution_total"]
    positive_suppressed = accounting["positive_suppressed_cell_count"]
    suppressed_total = accounting["suppressed_crash_contribution_total"]
    suppressed_accounting_valid = (positive_suppressed == 0 and suppressed_total == 0) or (
        positive_suppressed >= 2
        and positive_suppressed
        <= suppressed_total
        <= positive_suppressed * (FARS_PUBLIC_CONTEXT_EFFECTIVE_K - 1)
    )
    if not (
        accounting["state_count"] == len(states) == _STATE_COUNT
        and accounting["state_mode_cell_count"] == len(states) * len(MODE_ORDER)
        and accounting["published_cell_count"] == published_cells
        and accounting["suppressed_or_zero_cell_count"]
        == accounting["state_mode_cell_count"] - published_cells
        and accounting["positive_candidate_cell_count"]
        == accounting["published_cell_count"] + accounting["positive_suppressed_cell_count"]
        and accounting["published_crash_contribution_total"] == published_contributions
        and contribution_total == published_contributions + suppressed_total
        and case_count <= contribution_total <= case_count * len(MODE_ORDER)
        and suppressed_accounting_valid
    ):
        raise ValueError("public FARS state context accounting is inconsistent")


def _require_public_source(private: Mapping[str, object]) -> None:
    source = cast(Mapping[str, object], private["source_lineage"])
    method = cast(Mapping[str, object], private["method"])
    if not (
        private["visibility"] == "private"
        and source["source_id"] == "fars-joined"
        and source["dataset_year"] == 2024
        and source["release_status"] == "final"
        and source["raw_sha256"] == FARS_PUBLIC_CONTEXT_RAW_SHA256
        and method["coverage"] == "official_2024_national_50_states_and_dc"
        and method["effective_k"] == FARS_PUBLIC_CONTEXT_EFFECTIVE_K
        and method["modes_non_additive"] is True
        and method["coverage_state_codes"] == sorted(FARS_PUBLIC_STATE_CROSSWALK, key=int)
    ):
        raise ValueError("public FARS projection requires the exact verified 2024 National context")


def _project_fars_public_context(
    private: Mapping[str, object],
    *,
    contract: FarsYearContract,
) -> dict[str, object]:
    """Project one already-authorized private aggregate into closed public cells."""
    year = contract.year
    private_cells = cast(list[Mapping[str, object]], private["cells"])
    published_by_key = {
        (cast(str, cell["state_code"]), cast(str, cell["involved_mode"])): cast(
            int, cell["crash_count"]
        )
        for cell in private_cells
    }
    if len(published_by_key) != len(private_cells):
        raise ValueError("public FARS projection source cells are duplicated")

    states: list[dict[str, object]] = []
    for code, abbreviation, name in _expected_states():
        cells: list[dict[str, object]] = []
        for mode in MODE_ORDER:
            count = published_by_key.get((code, mode))
            if count is None:
                cells.append({"involved_mode": mode, "status": "suppressed_or_zero"})
            else:
                cells.append(
                    {
                        "involved_mode": mode,
                        "status": "published",
                        "crash_count": count,
                    }
                )
        states.append(
            {
                "state_code": code,
                "state_abbreviation": abbreviation,
                "state_name": name,
                "cells": cells,
            }
        )

    private_accounting = cast(Mapping[str, int], private["accounting"])
    accounting = {
        "case_count": private_accounting["case_count"],
        "state_count": _STATE_COUNT,
        "state_mode_cell_count": _STATE_MODE_CELL_COUNT,
        "published_cell_count": private_accounting["eligible_cell_count"],
        "suppressed_or_zero_cell_count": (
            _STATE_MODE_CELL_COUNT - private_accounting["eligible_cell_count"]
        ),
        "positive_candidate_cell_count": private_accounting["positive_candidate_cell_count"],
        "positive_suppressed_cell_count": private_accounting["suppressed_cell_count"],
        "crash_contribution_total": private_accounting["crash_contribution_total"],
        "published_crash_contribution_total": private_accounting[
            "eligible_crash_contribution_total"
        ],
        "suppressed_crash_contribution_total": private_accounting[
            "suppressed_crash_contribution_total"
        ],
    }
    artifact: dict[str, object] = {
        "schema_version": FARS_PUBLIC_CONTEXT_SCHEMA_VERSION,
        "artifact_type": FARS_PUBLIC_CONTEXT_ARTIFACT_TYPE,
        "visibility": "public",
        "title": fars_public_context_title(year),
        "dataset_year": year,
        "source": {
            "name": "NHTSA Fatality Analysis Reporting System (FARS)",
            "release_stage": contract.release_stage,
            "distribution_url": contract.distribution_url,
            "source_revision_id": contract.source_revision_id,
            "raw_size_bytes": contract.raw_size_bytes,
            "raw_sha256": contract.raw_sha256,
        },
        "geography": {
            "type": "fars_state_code",
            "coverage": f"official_{year}_national_50_states_and_dc",
            "state_count": _STATE_COUNT,
            "state_crosswalk_version": fars_public_state_crosswalk_version(year),
            "state_crosswalk_sha256": fars_public_state_crosswalk_sha256(year),
        },
        "metric": {
            "algorithm_version": FARS_NATIONAL_CONTEXT_ALGORITHM_VERSION,
            "dimension": "involved_mode",
            "contribution_unit": "distinct_crash_once_per_involved_mode",
            "effective_k": FARS_PUBLIC_CONTEXT_EFFECTIVE_K,
            "modes_non_additive": True,
            "modes": list(MODE_ORDER),
        },
        "accounting": accounting,
        "caveat": fars_public_context_caveat(year),
        "states": states,
    }
    validate_fars_public_context_artifact(artifact)
    return artifact


def _build_fars_public_context(private: Mapping[str, object]) -> dict[str, object]:
    """Legacy 2024 test seam retained as a byte-for-byte release anchor."""
    validate_fars_national_context_artifact(private)
    _require_public_source(private)
    return _project_fars_public_context(
        private,
        contract=fars_year_contract_revision(2024, 1),
    )


def _require_annual_public_source(
    private: Mapping[str, object],
    *,
    contract: FarsYearContract,
) -> None:
    source = cast(Mapping[str, object], private["source_lineage"])
    method = cast(Mapping[str, object], private["method"])
    if not (
        private["visibility"] == "private"
        and private["artifact_type"] == FARS_NATIONAL_CONTEXT_ARTIFACT_TYPE
        and private["caveat"] == fars_national_context_caveat(contract.year)
        and source["source_id"] == contract.source_id
        and source["dataset_year"] == contract.year
        and source["contract_revision"] == contract.revision
        and source["source_revision_id"] == contract.source_revision_id
        and source["release_status"] == contract.release_stage
        and source["raw_sha256"] == contract.raw_sha256
        and method["coverage"] == f"official_{contract.year}_national_50_states_and_dc"
        and method["effective_k"] == FARS_PUBLIC_CONTEXT_EFFECTIVE_K
        and method["modes_non_additive"] is True
        and method["coverage_state_codes"] == sorted(FARS_PUBLIC_STATE_CROSSWALK, key=int)
    ):
        raise ValueError("public FARS projection requires the exact verified annual context")


def build_verified_fars_public_context(
    snapshot: _VerifiedJoinedSnapshot,
) -> dict[str, object]:
    """Build public context only through an exact proof-bound joined snapshot."""
    if type(snapshot) is not _VerifiedJoinedSnapshot:
        raise TypeError("public FARS context requires a proof-bound joined snapshot")
    private = build_verified_fars_national_context(
        snapshot,
        requested_k=FARS_PUBLIC_CONTEXT_EFFECTIVE_K,
    )
    return _build_fars_public_context(private)


def build_verified_fars_public_release(
    snapshot: object,
    *,
    year: int,
    contract_revision: int,
    effective_k: int = FARS_PUBLIC_CONTEXT_EFFECTIVE_K,
) -> dict[str, object]:
    """Build one annual public release only from exact replayed v2 authority."""
    if (
        isinstance(effective_k, bool)
        or not isinstance(effective_k, int)
        or effective_k != FARS_PUBLIC_CONTEXT_EFFECTIVE_K
    ):
        raise ValueError("public FARS releases require the reviewed effective k=10")
    contract = fars_year_contract_revision(year, contract_revision)
    private = build_verified_fars_year_national_context(
        snapshot,
        year=year,
        contract_revision=contract_revision,
        requested_k=effective_k,
    )
    validate_fars_national_context_artifact(private)
    _require_annual_public_source(private, contract=contract)
    return _project_fars_public_context(private, contract=contract)


def canonical_fars_public_context_bytes(artifact: Mapping[str, object]) -> bytes:
    """Serialize a valid public artifact as deterministic canonical UTF-8 JSON."""
    validate_fars_public_context_artifact(artifact)
    return _canonical_json_bytes(artifact)


def _reject_constant(_value: str) -> NoReturn:
    raise ValueError("public FARS JSON contains a non-finite number")


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("public FARS JSON contains a duplicate key")
        result[key] = value
    return result


def load_fars_public_context_bytes(payload: bytes) -> dict[str, object]:
    """Parse exact canonical public bytes, rejecting duplicate keys and nonstandard numbers."""
    if type(payload) is not bytes:
        raise TypeError("public FARS artifact payload must be bytes")
    if not payload or len(payload) > _MAX_PUBLIC_ARTIFACT_BYTES:
        raise ValueError("public FARS artifact exceeds its byte safety limit")
    try:
        value = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_strict_object,
            parse_constant=_reject_constant,
        )
    except UnicodeDecodeError as exc:
        raise ValueError("public FARS artifact is not UTF-8") from exc
    except (json.JSONDecodeError, RecursionError) as exc:
        raise ValueError("public FARS artifact is invalid JSON") from exc
    if not isinstance(value, dict):
        raise ValueError("public FARS artifact must be an object")
    artifact = cast(dict[str, object], value)
    if canonical_fars_public_context_bytes(artifact) != payload:
        raise ValueError("public FARS artifact is not canonical")
    return copy.deepcopy(artifact)


__all__ = [
    "FARS_PUBLIC_CONTEXT_ARTIFACT_SCHEMA",
    "FARS_PUBLIC_CONTEXT_ARTIFACT_TYPE",
    "FARS_PUBLIC_CONTEXT_CAVEAT",
    "FARS_PUBLIC_CONTEXT_DISTRIBUTION_URL",
    "FARS_PUBLIC_CONTEXT_EFFECTIVE_K",
    "FARS_PUBLIC_CONTEXT_RAW_SHA256",
    "FARS_PUBLIC_CONTEXT_RAW_SIZE_BYTES",
    "FARS_PUBLIC_CONTEXT_SCHEMA_VERSION",
    "FARS_PUBLIC_CONTEXT_SOURCE_REVISION_ID",
    "FARS_PUBLIC_STATE_CROSSWALK",
    "FARS_PUBLIC_STATE_CROSSWALK_VERSION",
    "build_verified_fars_public_context",
    "build_verified_fars_public_release",
    "canonical_fars_public_context_bytes",
    "fars_public_context_caveat",
    "fars_public_context_title",
    "fars_public_state_crosswalk_sha256",
    "fars_public_state_crosswalk_version",
    "load_fars_public_context_bytes",
    "validate_fars_public_context_artifact",
]
