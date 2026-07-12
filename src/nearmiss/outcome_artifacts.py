# SPDX-License-Identifier: Apache-2.0
"""Deterministic, self-validating artifacts for normalized official outcomes."""

from __future__ import annotations

import copy
import json
import math
import re
from collections.abc import Iterable, Mapping
from typing import Any, cast

from jsonschema import Draft202012Validator, FormatChecker

from .adapters.fars import (
    FARS_MAPPING_VERSION,
    fars_outcome_id,
    validate_fars_distribution_url,
)
from .adapters.outcomes import OutcomeProvenance

OUTCOME_ARTIFACT_SCHEMA_VERSION = "1.0.0"
OUTCOME_ARTIFACT_TYPE = "nearmiss.official_outcomes"

# This contract is embedded because the repository-level schema directory is
# not installed in the wheel. A test keeps it identical to the public schema.
OUTCOME_ARTIFACT_SCHEMA: dict[str, object] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "https://nearmiss.dev/schema/official-outcome-artifact.schema.json",
    "title": "NearMiss normalized official-outcome artifact",
    "type": "object",
    "additionalProperties": False,
    "required": [
        "schema_version",
        "artifact_type",
        "normalization",
        "provenance",
        "outcomes",
    ],
    "$defs": {
        "semver": {"type": "string", "pattern": r"^[0-9]+\.[0-9]+\.[0-9]+$"},
        "sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
        "normalization": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "adapter_id",
                "adapter_version",
                "expected_year",
                "distribution_url",
                "max_invalid_fraction",
                "allow_record_regression",
                "allow_year_regression",
            ],
            "properties": {
                "adapter_id": {"const": "fars"},
                "adapter_version": {"const": FARS_MAPPING_VERSION},
                "expected_year": {
                    "type": "integer",
                    "minimum": 1975,
                    "maximum": 9999,
                },
                "distribution_url": {
                    "type": "string",
                    "format": "uri",
                    "pattern": (
                        "^https://static\\.nhtsa\\.gov/nhtsa/downloads/FARS/[0-9]{4}/.+\\."
                        "(?:[zZ][iI][pP]|[cC][sS][vV])$"
                    ),
                },
                "max_invalid_fraction": {"type": "number", "minimum": 0, "maximum": 1},
                "allow_record_regression": {"type": "boolean"},
                "allow_year_regression": {"type": "boolean"},
            },
        },
        "provenance": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "source_id",
                "source_name",
                "source_url",
                "license",
                "dataset_years",
                "release_status",
                "scope",
                "limitations",
                "records_read",
                "records_accepted",
                "rejection_reasons",
                "input_sha256",
            ],
            "properties": {
                "source_id": {"type": "string", "minLength": 1},
                "source_name": {"type": "string", "minLength": 1},
                "source_url": {"type": "string", "format": "uri"},
                "license": {"type": "string", "minLength": 1},
                "dataset_years": {
                    "type": "array",
                    "minItems": 1,
                    "uniqueItems": True,
                    "items": {"type": "integer", "minimum": 1975, "maximum": 9999},
                },
                "release_status": {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": 64,
                    "pattern": r"^[^\x00-\x1f\x7f]+$",
                },
                "scope": {"type": "string", "minLength": 1},
                "limitations": {
                    "type": "array",
                    "items": {"type": "string", "minLength": 1},
                },
                "records_read": {"type": "integer", "minimum": 0},
                "records_accepted": {"type": "integer", "minimum": 0},
                "rejection_reasons": {
                    "type": "object",
                    "propertyNames": {"minLength": 1},
                    "additionalProperties": {"type": "integer", "minimum": 1},
                },
                "input_sha256": {"$ref": "#/$defs/sha256"},
            },
        },
        "location": {
            "type": "object",
            "additionalProperties": False,
            "required": ["lat", "lon"],
            "properties": {
                "lat": {"type": "number", "minimum": -90, "maximum": 90},
                "lon": {"type": "number", "minimum": -180, "maximum": 180},
            },
        },
        "outcome": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "schema_version",
                "id",
                "source_record_id",
                "occurred_on",
                "location",
                "outcome_type",
                "maximum_injury_severity",
                "fatality_count",
            ],
            "properties": {
                "schema_version": {"const": "1.0.0"},
                "id": {
                    "type": "string",
                    "format": "uuid",
                    "pattern": (
                        "^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
                        "[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
                    ),
                },
                "source_record_id": {
                    "type": "string",
                    "pattern": "^[0-9]{4}:[1-9][0-9]*$",
                },
                "occurred_on": {"type": "string", "format": "date"},
                "occurred_time_local": {
                    "type": "string",
                    "pattern": "^(?:[01][0-9]|2[0-3]):[0-5][0-9]$",
                },
                "location": {"$ref": "#/$defs/location"},
                "outcome_type": {"const": "motor_vehicle_traffic_crash"},
                "maximum_injury_severity": {"const": "fatal"},
                "fatality_count": {"type": "integer", "minimum": 1},
                "state_code": {"type": "string", "minLength": 1},
            },
        },
    },
    "properties": {
        "schema_version": {"const": OUTCOME_ARTIFACT_SCHEMA_VERSION},
        "artifact_type": {"const": OUTCOME_ARTIFACT_TYPE},
        "normalization": {"$ref": "#/$defs/normalization"},
        "provenance": {"$ref": "#/$defs/provenance"},
        "outcomes": {
            "type": "array",
            "minItems": 1,
            "items": {"$ref": "#/$defs/outcome"},
        },
    },
}

_VALIDATOR = Draft202012Validator(OUTCOME_ARTIFACT_SCHEMA, format_checker=FormatChecker())


def _error_path(error: Any) -> str:
    path = "/".join(str(part) for part in error.absolute_path)
    return path or "(root)"


def _validate_metadata(
    normalization: Mapping[str, object],
    provenance: Mapping[str, object],
    *,
    expected_source_id: str | None,
) -> int:
    threshold = cast(float, normalization["max_invalid_fraction"])
    source_id = cast(str, provenance["source_id"])
    expected_year = cast(int, normalization["expected_year"])
    if not math.isfinite(threshold) or not 0 <= threshold <= 1:
        raise ValueError("official-outcome max_invalid_fraction must be finite and within [0, 1]")
    validate_fars_distribution_url(
        cast(str, normalization["distribution_url"]), expected_year=expected_year
    )
    if source_id != normalization["adapter_id"]:
        raise ValueError("official-outcome source_id must match normalization adapter_id")
    if expected_source_id is not None and source_id != expected_source_id:
        raise ValueError(
            f"official-outcome source_id {source_id!r} does not match {expected_source_id!r}"
        )
    if provenance["dataset_years"] != [expected_year]:
        raise ValueError("official-outcome dataset_years must contain exactly expected_year")
    return expected_year


def _validate_accounting(
    normalization: Mapping[str, object],
    provenance: Mapping[str, object],
    outcome_count: int,
) -> None:
    records_read = cast(int, provenance["records_read"])
    records_accepted = cast(int, provenance["records_accepted"])
    rejection_reasons = cast(Mapping[str, int], provenance["rejection_reasons"])
    rejected = sum(rejection_reasons.values())
    if records_accepted != outcome_count:
        raise ValueError("official-outcome accepted count must equal the outcome count")
    if records_accepted + rejected != records_read:
        raise ValueError("official-outcome provenance accounting must cover all records read")
    threshold = cast(float, normalization["max_invalid_fraction"])
    if rejected / records_read > threshold:
        raise ValueError("official-outcome invalid fraction exceeds max_invalid_fraction")


def _validate_outcomes(outcomes: list[Mapping[str, object]], *, expected_year: int) -> None:
    ids = [cast(str, outcome["id"]) for outcome in outcomes]
    if len(ids) != len(set(ids)):
        raise ValueError("official-outcome IDs must be unique")
    source_record_ids = [cast(str, outcome["source_record_id"]) for outcome in outcomes]
    if len(source_record_ids) != len(set(source_record_ids)):
        raise ValueError("official-outcome source_record_id values must be unique")
    order = [
        (cast(str, outcome["occurred_on"]), cast(str, outcome["source_record_id"]))
        for outcome in outcomes
    ]
    if order != sorted(order):
        raise ValueError("official outcomes must be ordered by occurred_on and source_record_id")
    if any(not occurred_on.startswith(f"{expected_year:04d}-") for occurred_on, _ in order):
        raise ValueError("every official outcome must occur in expected_year")
    for outcome in outcomes:
        source_record_id = cast(str, outcome["source_record_id"])
        identity = re.fullmatch(r"([0-9]{4}):([1-9][0-9]*)", source_record_id)
        if identity is None or int(identity.group(1)) != expected_year:
            raise ValueError(
                "official-outcome source_record_id must be expected_year:positive-digits"
            )
        if outcome["id"] != fars_outcome_id(expected_year, identity.group(2)):
            raise ValueError("official-outcome ID must be derived from its FARS source identity")
        location = cast(Mapping[str, float], outcome["location"])
        if not math.isfinite(location["lat"]) or not math.isfinite(location["lon"]):
            raise ValueError("official-outcome coordinates must be finite")


def validate_outcome_artifact(
    artifact: Mapping[str, object], *, expected_source_id: str | None = None
) -> None:
    """Fail closed if an official-outcome artifact violates its full contract."""
    errors = sorted(_VALIDATOR.iter_errors(artifact), key=lambda error: list(error.absolute_path))
    if errors:
        first = errors[0]
        raise ValueError(
            f"invalid official-outcome artifact at {_error_path(first)}: {first.message}"
        )

    normalization = cast(Mapping[str, object], artifact["normalization"])
    provenance = cast(Mapping[str, object], artifact["provenance"])
    outcomes = cast(list[Mapping[str, object]], artifact["outcomes"])
    expected_year = _validate_metadata(
        normalization, provenance, expected_source_id=expected_source_id
    )
    _validate_accounting(normalization, provenance, len(outcomes))
    _validate_outcomes(outcomes, expected_year=expected_year)


def build_outcome_artifact(
    outcomes: Iterable[Mapping[str, object]],
    provenance: OutcomeProvenance,
    *,
    expected_year: int,
    distribution_url: str,
    adapter_version: str = FARS_MAPPING_VERSION,
    max_invalid_fraction: float = 0.05,
    allow_record_regression: bool = False,
    allow_year_regression: bool = False,
) -> dict[str, object]:
    """Build a deterministic FARS crash-level artifact and validate it fully."""
    distribution_url = validate_fars_distribution_url(distribution_url, expected_year=expected_year)
    artifact: dict[str, object] = {
        "schema_version": OUTCOME_ARTIFACT_SCHEMA_VERSION,
        "artifact_type": OUTCOME_ARTIFACT_TYPE,
        "normalization": {
            "adapter_id": "fars",
            "adapter_version": adapter_version,
            "expected_year": expected_year,
            "distribution_url": distribution_url,
            "max_invalid_fraction": max_invalid_fraction,
            "allow_record_regression": allow_record_regression,
            "allow_year_regression": allow_year_regression,
        },
        "provenance": copy.deepcopy(provenance.as_dict()),
        "outcomes": [copy.deepcopy(dict(outcome)) for outcome in outcomes],
    }
    validate_outcome_artifact(artifact, expected_source_id="fars")
    return artifact


def canonical_outcome_artifact_bytes(artifact: Mapping[str, object]) -> bytes:
    """Serialize a valid artifact as stable, compact UTF-8 JSON with one newline."""
    validate_outcome_artifact(artifact)
    return (
        json.dumps(
            artifact,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")
