# SPDX-License-Identifier: Apache-2.0
"""Machine-readable contract for private FARS context artifacts."""

from __future__ import annotations

from collections.abc import Mapping
from typing import cast

from jsonschema import Draft202012Validator, FormatChecker

from .adapters.fars import FARS_MAPPING_VERSION
from .adapters.fars_joined import MODE_ORDER, PERSON_MODE_MAPPING_VERSION
from .fars_context import (
    CONTEXT_MODE_ORDER,
    FARS_CONTEXT_ALGORITHM_VERSION,
    FARS_CONTEXT_ARTIFACT_TYPE,
    FARS_CONTEXT_MINIMUM_K,
    FARS_CONTEXT_SCHEMA_VERSION,
    LIMITATION_CODES,
    PART_OF_DAY_ORDER,
    fars_context_contract_descriptor,
    validate_fars_context_artifact,
)
from .point_snap import point_snap_method_descriptor

_CONTEXT_CAPS = cast(dict[str, object], fars_context_contract_descriptor()["caps"])


def _cap(name: str) -> int:
    value = _CONTEXT_CAPS[name]
    assert isinstance(value, int)
    return value


def _numeric_cap(name: str) -> float:
    value = _CONTEXT_CAPS[name]
    assert isinstance(value, (int, float)) and not isinstance(value, bool)
    return float(value)


_MAX_RECORDS = _cap("max_records")
_MAX_CRASH_SOURCE_RECORDS = _cap("max_crash_source_records")
_MAX_PERSON_SOURCE_RECORDS = _cap("max_person_source_records")
_MAX_SEGMENTS = _cap("max_segments")
_MAX_COORDINATES = _cap("max_coordinates")
_MAX_CELLS = _cap("max_cells")
_MAX_CONFIG_BYTES = _cap("max_config_bytes")
_MAX_NETWORK_BYTES = _cap("max_network_bytes")
_MAX_DISTANCE_M = _numeric_cap("max_distance_m")
_MAX_CONTRIBUTIONS = _cap("max_contributions")

_SHA256 = {"type": "string", "pattern": "^[0-9a-f]{64}$"}
_DATE_2024 = {
    "type": "string",
    "format": "date",
    "pattern": "^2024-[0-9]{2}-[0-9]{2}$",
}
_SAFE_CITY = {
    "type": "string",
    "minLength": 1,
    "maxLength": 128,
    "pattern": r"^(?!.*[\x00-\x1f\x7f\ud800-\udfff])\S(?:.*\S)?$",
}
_SAFE_SEGMENT = {
    "type": "string",
    "minLength": 1,
    "maxLength": 512,
    "pattern": r"^(?!.*[\x00-\x1f\x7f\ud800-\udfff])\S(?:.*\S)?$",
}


def _closed(properties: Mapping[str, object]) -> dict[str, object]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": list(properties),
        "properties": dict(properties),
    }


def _bounded_count(maximum: int, *, minimum: int = 0) -> dict[str, object]:
    return {"type": "integer", "minimum": minimum, "maximum": maximum}


_POINT_SNAP = point_snap_method_descriptor()
_POINT_SNAP_CAPS = _POINT_SNAP["caps"]
assert isinstance(_POINT_SNAP_CAPS, dict)

_POINT_SNAP_SCHEMA = _closed(
    {
        "version": {"const": _POINT_SNAP["version"]},
        "decision_tolerance_m": {"const": _POINT_SNAP["decision_tolerance_m"]},
        "densification_step_m": {"const": _POINT_SNAP["densification_step_m"]},
        "index_epsilon_m": {"const": _POINT_SNAP["index_epsilon_m"]},
        "index_padding_rule": {"const": _POINT_SNAP["index_padding_rule"]},
        "decision_radius_rule": {"const": _POINT_SNAP["decision_radius_rule"]},
        "distance_rule": {"const": _POINT_SNAP["distance_rule"]},
        "ambiguity_rule": {"const": _POINT_SNAP["ambiguity_rule"]},
        "caps": _closed({key: {"const": value} for key, value in _POINT_SNAP_CAPS.items()}),
    }
)

_TIME_BANDS = [
    {"key": "overnight", "start_hour_inclusive": 0, "end_hour_exclusive": 6},
    {"key": "am_peak", "start_hour_inclusive": 6, "end_hour_exclusive": 10},
    {"key": "midday", "start_hour_inclusive": 10, "end_hour_exclusive": 16},
    {"key": "pm_peak", "start_hour_inclusive": 16, "end_hour_exclusive": 20},
    {"key": "evening", "start_hour_inclusive": 20, "end_hour_exclusive": 24},
]

_CAVEAT = (
    "Fatal-crash co-location context only. It is not record linkage, not outcome validation, "
    "not causal evidence, not a measure of nonfatal risk, not a location ranking, not an "
    "intervention effect estimate, and not exposure-normalized risk. Involved-mode cells "
    "overlap and are non-additive; snapping and exclusions can bias coverage."
)

_SOURCE_LINEAGE_SCHEMA = _closed(
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
        "crash_mapping_version": {"const": FARS_MAPPING_VERSION},
        "person_mapping_version": {"const": PERSON_MODE_MAPPING_VERSION},
        "crash_records_read": _bounded_count(_MAX_CRASH_SOURCE_RECORDS),
        "crash_records_accepted": _bounded_count(_MAX_RECORDS),
        "crash_records_rejected": _bounded_count(_MAX_CRASH_SOURCE_RECORDS),
        "person_records_read": _bounded_count(_MAX_PERSON_SOURCE_RECORDS),
        "person_records_accepted": _bounded_count(_MAX_PERSON_SOURCE_RECORDS),
        "person_records_excluded": _bounded_count(_MAX_PERSON_SOURCE_RECORDS),
        "cases_joined": _bounded_count(_MAX_RECORDS),
        "cases_excluded": _bounded_count(_MAX_CRASH_SOURCE_RECORDS),
    }
)

_INPUT_LINEAGE_SCHEMA = _closed(
    {
        "config_raw_sha256": _SHA256,
        "config_raw_byte_count": _bounded_count(_MAX_CONFIG_BYTES, minimum=1),
        "network_raw_sha256": _SHA256,
        "network_raw_byte_count": _bounded_count(_MAX_NETWORK_BYTES, minimum=1),
        "network_canonical_sha256": _SHA256,
        "network_segment_count": _bounded_count(_MAX_SEGMENTS),
        "network_coordinate_count": _bounded_count(_MAX_COORDINATES),
    }
)

_REFERENCE_LATITUDE = {"type": "number", "minimum": -90, "maximum": 90}
_REFERENCE_LONGITUDE = {"type": "number", "minimum": -180, "maximum": 180}
_SNAP_SCHEMA = _closed(
    {
        "max_distance_m": {
            "type": "number",
            "exclusiveMinimum": 0,
            "maximum": _MAX_DISTANCE_M,
        },
        "ambiguity_margin_m": {
            "type": "number",
            "minimum": 0,
            "maximum": _MAX_DISTANCE_M,
        },
        "assignment_rule": {"const": "unique_nearest_within_max_distance_only"},
        "projection": {"const": "local_equirectangular_metres"},
        "reference_policy": {
            "type": "string",
            "enum": ["canonical_network_vertex_mean", "configured_reference_pair"],
        },
        "reference_lat": {"oneOf": [_REFERENCE_LATITUDE, {"type": "null"}]},
        "reference_lon": {"oneOf": [_REFERENCE_LONGITUDE, {"type": "null"}]},
        "point_snap": _POINT_SNAP_SCHEMA,
    }
)
_SNAP_SCHEMA["allOf"] = [
    {
        "if": {"properties": {"reference_policy": {"const": "canonical_network_vertex_mean"}}},
        "then": {
            "properties": {
                "reference_lat": {"type": "null"},
                "reference_lon": {"type": "null"},
            }
        },
    },
    {
        "if": {"properties": {"reference_policy": {"const": "configured_reference_pair"}}},
        "then": {
            "properties": {
                "reference_lat": _REFERENCE_LATITUDE,
                "reference_lon": _REFERENCE_LONGITUDE,
            }
        },
    },
]

_METHOD_SCHEMA = _closed(
    {
        "context": _closed(
            {
                "algorithm": {"const": "segment_part_of_day_involved_mode_fatal_crash_colocation"},
                "algorithm_version": {"const": FARS_CONTEXT_ALGORITHM_VERSION},
                "artifact_schema_version": {"const": FARS_CONTEXT_SCHEMA_VERSION},
            }
        ),
        "window": _closed(
            {
                "dataset_year": {"const": 2024},
                "effective_start_inclusive": _DATE_2024,
                "effective_end_inclusive": _DATE_2024,
            }
        ),
        "snap": _SNAP_SCHEMA,
        "time": _closed(
            {
                "bands": {"const": _TIME_BANDS},
                "order": {"const": list(PART_OF_DAY_ORDER)},
                "unknown_policy": {"const": "missing_clock_value_to_unknown_time"},
            }
        ),
        "mode": _closed(
            {
                "mapping_version": {"const": PERSON_MODE_MAPPING_VERSION},
                "source_order": {"const": list(MODE_ORDER)},
                "output_order": {"const": list(CONTEXT_MODE_ORDER)},
                "crash_basis": {"const": "one_contribution_per_crash_per_distinct_involved_mode"},
                "unknown_policy": {"const": "source_unknown_and_empty_mode_set_to_unknown_mode"},
                "unknown_preserved_alongside_known_modes": {"const": True},
                "strata_additive": {"const": False},
            }
        ),
        "privacy": _closed(
            {
                "requested_k": _bounded_count(_MAX_RECORDS, minimum=1),
                "minimum_k": {"const": FARS_CONTEXT_MINIMUM_K},
                "effective_k": _bounded_count(_MAX_RECORDS, minimum=FARS_CONTEXT_MINIMUM_K),
                "candidate_definition": {"const": "positive_observed_segment_time_mode_cell"},
                "eligibility_rule": {"const": "crash_count_greater_than_or_equal_to_effective_k"},
                "suppressed_output": {
                    "const": "global_positive_cell_count_and_contribution_total_only"
                },
                "cell_key_order": {"const": ["segment_id", "part_of_day", "involved_mode"]},
                "serialization_order": {
                    "const": [
                        "segment_id_lexical",
                        "part_of_day_declared_order",
                        "involved_mode_declared_order",
                    ]
                },
            }
        ),
        "limitation_codes": {"const": list(LIMITATION_CODES)},
    }
)

_ACCOUNTING_SCHEMA = _closed(
    {
        "records_received": _bounded_count(_MAX_RECORDS),
        "records_outside_window": _bounded_count(_MAX_RECORDS),
        "records_in_window": _bounded_count(_MAX_RECORDS),
        "uniquely_snapped_crashes": _bounded_count(_MAX_RECORDS),
        "ambiguous_crashes": _bounded_count(_MAX_RECORDS),
        "unsnapped_crashes": _bounded_count(_MAX_RECORDS),
        "uniquely_snapped_timed_crashes": _bounded_count(_MAX_RECORDS),
        "uniquely_snapped_unknown_time_crashes": _bounded_count(_MAX_RECORDS),
        "positive_candidate_cell_count": _bounded_count(_MAX_CELLS),
        "eligible_cell_count": _bounded_count(_MAX_CELLS),
        "suppressed_positive_cell_count": _bounded_count(_MAX_CELLS),
        "crash_contribution_total": _bounded_count(_MAX_CONTRIBUTIONS),
        "eligible_crash_contribution_total": _bounded_count(_MAX_CONTRIBUTIONS),
        "suppressed_crash_contribution_total": _bounded_count(_MAX_CONTRIBUTIONS),
    }
)

_CELL_SCHEMA = _closed(
    {
        "segment_id": _SAFE_SEGMENT,
        "part_of_day": {"type": "string", "enum": list(PART_OF_DAY_ORDER)},
        "involved_mode": {"type": "string", "enum": list(CONTEXT_MODE_ORDER)},
        "crash_count": _bounded_count(_MAX_RECORDS, minimum=FARS_CONTEXT_MINIMUM_K),
    }
)

FARS_CONTEXT_ARTIFACT_SCHEMA: dict[str, object] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "https://nearmiss.dev/schema/private-fars-context.schema.json",
    "title": "Private NearMiss FARS context artifact",
    "description": (
        "Private, k-suppressed fatal-crash co-location context. This is not a public "
        "dataset and contains only eligible segment/time/involved-mode count cells."
    ),
    "type": "object",
    "additionalProperties": False,
    "required": [
        "schema_version",
        "artifact_type",
        "visibility",
        "city_key",
        "source_lineage",
        "input_lineage",
        "method",
        "method_sha256",
        "accounting",
        "caveat",
        "cells",
    ],
    "properties": {
        "schema_version": {"const": FARS_CONTEXT_SCHEMA_VERSION},
        "artifact_type": {"const": FARS_CONTEXT_ARTIFACT_TYPE},
        "visibility": {"const": "private"},
        "city_key": _SAFE_CITY,
        "source_lineage": _SOURCE_LINEAGE_SCHEMA,
        "input_lineage": _INPUT_LINEAGE_SCHEMA,
        "method": _METHOD_SCHEMA,
        "method_sha256": _SHA256,
        "accounting": _ACCOUNTING_SCHEMA,
        "caveat": {"const": _CAVEAT},
        "cells": {
            "type": "array",
            "maxItems": _MAX_CELLS,
            "items": _CELL_SCHEMA,
        },
    },
}

_VALIDATOR = Draft202012Validator(FARS_CONTEXT_ARTIFACT_SCHEMA, format_checker=FormatChecker())


def validate_fars_context_schema(artifact: Mapping[str, object]) -> None:
    """Validate both the machine shape and the existing semantic contract."""
    errors = sorted(_VALIDATOR.iter_errors(artifact), key=lambda error: list(error.absolute_path))
    if errors:
        error = errors[0]
        path = "/".join(str(part) for part in error.absolute_path) or "(root)"
        raise ValueError(f"invalid private FARS context artifact at {path}: {error.message}")
    validate_fars_context_artifact(artifact)


__all__ = ["FARS_CONTEXT_ARTIFACT_SCHEMA", "validate_fars_context_schema"]
