# SPDX-License-Identifier: Apache-2.0
"""Machine-readable contract for private national FARS context artifacts."""

from __future__ import annotations

from collections.abc import Mapping
from typing import cast

from jsonschema import Draft202012Validator, FormatChecker

from .adapters.fars import FARS_MAPPING_VERSION
from .adapters.fars_joined import MODE_ORDER, PERSON_MODE_MAPPING_VERSION
from .fars_national_context import (
    FARS_2024_STATE_CODES,
    FARS_NATIONAL_CONTEXT_ALGORITHM_VERSION,
    FARS_NATIONAL_CONTEXT_ARTIFACT_TYPE,
    FARS_NATIONAL_CONTEXT_CAVEAT,
    FARS_NATIONAL_CONTEXT_MINIMUM_K,
    FARS_NATIONAL_CONTEXT_SCHEMA_VERSION,
    FARS_STATE_CODEBOOK_VERSION,
    fars_national_context_contract_descriptor,
    fars_state_codebook_sha256,
)
from .joined_outcome_artifacts import JOINED_ARTIFACT_SCHEMA_VERSION

_CAPS = cast(dict[str, object], fars_national_context_contract_descriptor()["caps"])
_MAX_CASES = cast(int, _CAPS["max_cases"])
_MAX_PERSON_RECORDS = cast(int, _CAPS["max_person_records"])
_MAX_CELLS = cast(int, _CAPS["max_cells"])
_MAX_CONTRIBUTIONS = cast(int, _CAPS["max_contributions"])
_SHA256 = {"type": "string", "pattern": "^[0-9a-f]{64}$"}


def _closed(properties: Mapping[str, object]) -> dict[str, object]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": list(properties),
        "properties": dict(properties),
    }


def _count(maximum: int, *, minimum: int = 0) -> dict[str, object]:
    return {"type": "integer", "minimum": minimum, "maximum": maximum}


FARS_NATIONAL_CONTEXT_ARTIFACT_SCHEMA: dict[str, object] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "https://nearmiss.dev/schema/private-fars-national-context.schema.json",
    "title": "Private NearMiss national FARS context artifact",
    "type": "object",
    "additionalProperties": False,
    "required": [
        "schema_version",
        "artifact_type",
        "visibility",
        "caveat",
        "source_lineage",
        "method",
        "accounting",
        "cells",
    ],
    "properties": {
        "schema_version": {"const": FARS_NATIONAL_CONTEXT_SCHEMA_VERSION},
        "artifact_type": {"const": FARS_NATIONAL_CONTEXT_ARTIFACT_TYPE},
        "visibility": {"const": "private"},
        "caveat": {"const": FARS_NATIONAL_CONTEXT_CAVEAT},
        "source_lineage": _closed(
            {
                "source_id": {"const": "fars-joined"},
                "dataset_year": {"const": 2024},
                "release_status": {"type": "string", "enum": ["preliminary", "final"]},
                "attempt_id": {
                    "type": "string",
                    "pattern": "^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$",
                },
                "raw_sha256": _SHA256,
                "normalized_sha256": _SHA256,
                "accident_sha256": _SHA256,
                "person_sha256": _SHA256,
                "joined_schema_version": {"const": JOINED_ARTIFACT_SCHEMA_VERSION},
                "crash_mapping_version": {"const": FARS_MAPPING_VERSION},
                "person_mapping_version": {"const": PERSON_MODE_MAPPING_VERSION},
                "crash_records_read": _count(_MAX_CASES, minimum=1),
                "crash_records_accepted": _count(_MAX_CASES, minimum=1),
                "crash_records_rejected": _count(_MAX_CASES),
                "person_records_read": _count(_MAX_PERSON_RECORDS, minimum=1),
                "person_records_accepted": _count(_MAX_PERSON_RECORDS, minimum=1),
                "person_records_excluded": _count(_MAX_PERSON_RECORDS),
                "cases_joined": _count(_MAX_CASES, minimum=1),
                "cases_excluded": _count(_MAX_CASES),
            }
        ),
        "method": _closed(
            {
                "algorithm_version": {"const": FARS_NATIONAL_CONTEXT_ALGORITHM_VERSION},
                "geography": {"const": "fars_state_code"},
                "coverage": {
                    "type": "string",
                    "enum": [
                        "state_codes_present_in_verified_snapshot",
                        "official_2024_national_50_states_and_dc",
                    ],
                },
                "coverage_state_codes": {
                    "type": "array",
                    "uniqueItems": True,
                    "maxItems": len(FARS_2024_STATE_CODES),
                    "items": {"type": "string", "enum": list(FARS_2024_STATE_CODES)},
                },
                "dimension": {"const": "involved_mode"},
                "contribution_unit": {"const": "distinct_crash_once_per_involved_mode"},
                "minimum_k": {"const": FARS_NATIONAL_CONTEXT_MINIMUM_K},
                "effective_k": _count(_MAX_CASES, minimum=FARS_NATIONAL_CONTEXT_MINIMUM_K),
                "state_codebook_version": {"const": FARS_STATE_CODEBOOK_VERSION},
                "state_codebook_sha256": {"const": fars_state_codebook_sha256()},
                "modes_non_additive": {"const": True},
            }
        ),
        "accounting": _closed(
            {
                "case_count": _count(_MAX_CASES, minimum=1),
                "states_with_records": _count(len(FARS_2024_STATE_CODES), minimum=1),
                "states_with_eligible_cells": _count(len(FARS_2024_STATE_CODES)),
                "positive_candidate_cell_count": _count(_MAX_CELLS, minimum=1),
                "eligible_cell_count": _count(_MAX_CELLS),
                "suppressed_cell_count": _count(_MAX_CELLS),
                "crash_contribution_total": _count(_MAX_CONTRIBUTIONS, minimum=1),
                "eligible_crash_contribution_total": _count(_MAX_CONTRIBUTIONS),
                "suppressed_crash_contribution_total": _count(_MAX_CONTRIBUTIONS),
            }
        ),
        "cells": {
            "type": "array",
            "maxItems": _MAX_CELLS,
            "items": _closed(
                {
                    "state_code": {"type": "string", "enum": list(FARS_2024_STATE_CODES)},
                    "involved_mode": {"type": "string", "enum": list(MODE_ORDER)},
                    "crash_count": _count(_MAX_CASES, minimum=FARS_NATIONAL_CONTEXT_MINIMUM_K),
                }
            ),
        },
    },
}

_VALIDATOR = Draft202012Validator(
    FARS_NATIONAL_CONTEXT_ARTIFACT_SCHEMA,
    format_checker=FormatChecker(),
)


def validate_fars_national_context_schema(artifact: Mapping[str, object]) -> None:
    """Reject the first deterministic machine-contract violation."""
    errors = sorted(_VALIDATOR.iter_errors(artifact), key=lambda error: list(error.absolute_path))
    if errors:
        error = errors[0]
        path = "/".join(str(part) for part in error.absolute_path) or "(root)"
        raise ValueError(f"invalid private national FARS context at {path}: {error.message}")


__all__ = [
    "FARS_NATIONAL_CONTEXT_ARTIFACT_SCHEMA",
    "validate_fars_national_context_schema",
]
