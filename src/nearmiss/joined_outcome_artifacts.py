# SPDX-License-Identifier: Apache-2.0
"""Private deterministic artifact contract for FARS accident/person joins."""

from __future__ import annotations

import copy
import json
from collections.abc import Iterable, Mapping
from typing import cast

from jsonschema import Draft202012Validator, FormatChecker

from .adapters.fars_joined import (
    MODE_ORDER,
    PERSON_MODE_MAPPING_VERSION,
    FarsMemberDescriptor,
    FarsModeSummary,
    PersonJoinProvenance,
)
from .adapters.outcomes import OutcomeProvenance
from .outcome_artifacts import (
    OUTCOME_ARTIFACT_SCHEMA,
    build_outcome_artifact,
    validate_outcome_artifact,
)

JOINED_ARTIFACT_SCHEMA_VERSION = "1.0.0"
JOINED_ARTIFACT_TYPE = "nearmiss.private.fars_joined_outcomes"

_OUTCOME_DEFS = cast(Mapping[str, object], OUTCOME_ARTIFACT_SCHEMA["$defs"])
_MODE_ENUM = list(MODE_ORDER)
_MODE_COUNT_PROPERTIES = {mode: {"type": "integer", "minimum": 0} for mode in MODE_ORDER}

JOINED_ARTIFACT_SCHEMA: dict[str, object] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "https://nearmiss.dev/schema/private-fars-joined-outcomes.schema.json",
    "title": "Private NearMiss FARS joined-outcome artifact",
    "type": "object",
    "additionalProperties": False,
    "required": [
        "schema_version",
        "artifact_type",
        "crash_normalization",
        "crash_provenance",
        "join_policy",
        "person_join",
        "records",
    ],
    "$defs": {
        **_OUTCOME_DEFS,
        "mode_array": {
            "type": "array",
            "uniqueItems": True,
            "items": {"type": "string", "enum": _MODE_ENUM},
        },
        "mode_counts": {
            "type": "object",
            "additionalProperties": False,
            "required": _MODE_ENUM,
            "properties": _MODE_COUNT_PROPERTIES,
        },
        "mode_summary": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "source_record_id",
                "involved_modes",
                "fatality_modes",
                "involved_person_count_by_mode",
                "fatality_count_by_mode",
            ],
            "properties": {
                "source_record_id": {
                    "type": "string",
                    "pattern": "^2024:[1-9][0-9]*$",
                },
                "involved_modes": {"$ref": "#/$defs/mode_array"},
                "fatality_modes": {"$ref": "#/$defs/mode_array"},
                "involved_person_count_by_mode": {"$ref": "#/$defs/mode_counts"},
                "fatality_count_by_mode": {"$ref": "#/$defs/mode_counts"},
            },
        },
        "person_join": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "mapping_version",
                "dataset_year",
                "input_sha256",
                "accident_sha256",
                "person_sha256",
                "accident_member",
                "person_member",
                "records_read",
                "records_accepted",
                "cases_joined",
                "records_excluded_with_rejected_crash",
                "cases_excluded_with_rejected_crash",
                "rejection_reasons",
            ],
            "properties": {
                "mapping_version": {"const": PERSON_MODE_MAPPING_VERSION},
                "dataset_year": {"const": 2024},
                "input_sha256": {"$ref": "#/$defs/sha256"},
                "accident_sha256": {"$ref": "#/$defs/sha256"},
                "person_sha256": {"$ref": "#/$defs/sha256"},
                "accident_member": {"$ref": "#/$defs/member_descriptor"},
                "person_member": {"$ref": "#/$defs/member_descriptor"},
                "records_read": {"type": "integer", "minimum": 1},
                "records_accepted": {"type": "integer", "minimum": 1},
                "cases_joined": {"type": "integer", "minimum": 1},
                "records_excluded_with_rejected_crash": {
                    "type": "integer",
                    "minimum": 0,
                },
                "cases_excluded_with_rejected_crash": {
                    "type": "integer",
                    "minimum": 0,
                },
                "rejection_reasons": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {"parent_crash_rejected": {"type": "integer", "minimum": 1}},
                },
            },
        },
        "member_descriptor": {
            "type": "object",
            "additionalProperties": False,
            "required": ["archive_path", "name", "uncompressed_size", "crc32", "sha256"],
            "properties": {
                "archive_path": {"type": "string", "minLength": 1},
                "name": {"type": "string", "minLength": 1, "maxLength": 12},
                "uncompressed_size": {"type": "integer", "minimum": 1},
                "crc32": {"type": "string", "pattern": "^[0-9a-f]{8}$"},
                "sha256": {"$ref": "#/$defs/sha256"},
            },
        },
        "join_policy": {
            "type": "object",
            "additionalProperties": False,
            "required": ["allow_mode_regression", "allow_release_regression"],
            "properties": {
                "allow_mode_regression": {"type": "boolean"},
                "allow_release_regression": {"type": "boolean"},
            },
        },
        "joined_record": {
            "type": "object",
            "additionalProperties": False,
            "required": ["outcome", "mode_summary"],
            "properties": {
                "outcome": {"$ref": "#/$defs/outcome"},
                "mode_summary": {"$ref": "#/$defs/mode_summary"},
            },
        },
    },
    "properties": {
        "schema_version": {"const": JOINED_ARTIFACT_SCHEMA_VERSION},
        "artifact_type": {"const": JOINED_ARTIFACT_TYPE},
        "crash_normalization": {"$ref": "#/$defs/normalization"},
        "crash_provenance": {"$ref": "#/$defs/provenance"},
        "join_policy": {"$ref": "#/$defs/join_policy"},
        "person_join": {"$ref": "#/$defs/person_join"},
        "records": {
            "type": "array",
            "minItems": 1,
            "maxItems": 36297,
            "items": {"$ref": "#/$defs/joined_record"},
        },
    },
}

_VALIDATOR = Draft202012Validator(JOINED_ARTIFACT_SCHEMA, format_checker=FormatChecker())


def _schema_error(artifact: Mapping[str, object]) -> None:
    errors = sorted(_VALIDATOR.iter_errors(artifact), key=lambda error: list(error.absolute_path))
    if errors:
        error = errors[0]
        path = "/".join(str(part) for part in error.absolute_path) or "(root)"
        raise ValueError(f"invalid private joined artifact at {path}: {error.message}")


def _validate_summary(summary: Mapping[str, object], outcome: Mapping[str, object]) -> int:
    involved = cast(Mapping[str, int], summary["involved_person_count_by_mode"])
    fatal = cast(Mapping[str, int], summary["fatality_count_by_mode"])
    involved_modes = cast(list[str], summary["involved_modes"])
    fatality_modes = cast(list[str], summary["fatality_modes"])
    expected_involved = [mode for mode in MODE_ORDER if involved[mode] > 0]
    expected_fatal = [mode for mode in MODE_ORDER if fatal[mode] > 0]
    if involved_modes != expected_involved or fatality_modes != expected_fatal:
        raise ValueError("private joined artifact mode arrays do not match canonical counts")
    if any(fatal[mode] > involved[mode] for mode in MODE_ORDER):
        raise ValueError("private joined artifact fatal mode count exceeds involved count")
    involved_total = sum(involved.values())
    if involved_total < 1:
        raise ValueError("private joined artifact requires an involved person")
    if sum(fatal.values()) != outcome["fatality_count"]:
        raise ValueError("private joined artifact fatal mode counts do not match outcome")
    return involved_total


def _validate_crash_contract(
    crash_normalization: Mapping[str, object],
    crash_provenance: Mapping[str, object],
    records: list[Mapping[str, object]],
) -> None:
    base_artifact: dict[str, object] = {
        "schema_version": "1.0.0",
        "artifact_type": "nearmiss.official_outcomes",
        "normalization": copy.deepcopy(dict(crash_normalization)),
        "provenance": copy.deepcopy(dict(crash_provenance)),
        "outcomes": [
            copy.deepcopy(dict(cast(Mapping[str, object], row["outcome"]))) for row in records
        ],
    }
    try:
        validate_outcome_artifact(base_artifact, expected_source_id="fars")
    except ValueError as exc:
        raise ValueError("private joined artifact crash contract is invalid") from exc
    if crash_normalization["allow_year_regression"] is not False:
        raise ValueError("private joined artifact must not authorize year regression")
    if not cast(str, crash_normalization["distribution_url"]).casefold().endswith(".zip"):
        raise ValueError("private joined artifact distribution must be a ZIP")
    if crash_provenance["release_status"] not in {"preliminary", "final"}:
        raise ValueError("private joined artifact release status is unsupported")


def _validate_member_descriptors(provenance: Mapping[str, object]) -> None:
    descriptors: list[FarsMemberDescriptor] = []
    for key in ("accident_member", "person_member"):
        value = cast(Mapping[str, object], provenance[key])
        try:
            descriptors.append(
                FarsMemberDescriptor(
                    archive_path=cast(str, value["archive_path"]),
                    name=cast(str, value["name"]),
                    uncompressed_size=cast(int, value["uncompressed_size"]),
                    crc32=cast(str, value["crc32"]),
                    sha256=cast(str, value["sha256"]),
                )
            )
        except (TypeError, ValueError) as exc:
            raise ValueError("private joined artifact member descriptor is invalid") from exc
    accident_member, person_member = descriptors
    if (
        accident_member.name.casefold() != "accident.csv"
        or person_member.name.casefold() != "person.csv"
        or accident_member.sha256 != provenance["accident_sha256"]
        or person_member.sha256 != provenance["person_sha256"]
        or accident_member.archive_path == person_member.archive_path
    ):
        raise ValueError("private joined artifact member descriptors are inconsistent")


def _validate_cross_accounting(
    provenance: Mapping[str, object],
    crash_provenance: Mapping[str, object],
    *,
    record_count: int,
    accepted_people: int,
) -> None:
    if provenance["cases_joined"] != record_count:
        raise ValueError("private joined artifact cases_joined does not match records")
    if provenance["records_accepted"] != accepted_people:
        raise ValueError("private joined artifact accepted person count does not match summaries")
    excluded = cast(int, provenance["records_excluded_with_rejected_crash"])
    if provenance["records_accepted"] + excluded != provenance["records_read"]:
        raise ValueError("private joined artifact person accounting does not cover records_read")
    reasons = cast(Mapping[str, int], provenance["rejection_reasons"])
    expected_reasons = {"parent_crash_rejected": excluded} if excluded else {}
    if reasons != expected_reasons:
        raise ValueError("private joined artifact rejection reasons do not match exclusions")
    excluded_cases = cast(int, provenance["cases_excluded_with_rejected_crash"])
    if excluded_cases > excluded:
        raise ValueError("private joined artifact excluded cases exceed excluded person records")
    if crash_provenance["input_sha256"] != provenance["input_sha256"]:
        raise ValueError("private joined artifact crash/person input digests do not match")
    _validate_member_descriptors(provenance)
    if crash_provenance["records_accepted"] != provenance["cases_joined"]:
        raise ValueError("private joined artifact crash/person accepted accounting differs")
    if provenance["cases_joined"] + excluded_cases != crash_provenance["records_read"]:
        raise ValueError("private joined artifact crash/person case accounting differs")
    rejected = sum(cast(Mapping[str, int], crash_provenance["rejection_reasons"]).values())
    if rejected != excluded_cases:
        raise ValueError("private joined artifact crash/person rejection accounting differs")


def validate_joined_outcome_artifact(artifact: Mapping[str, object]) -> None:
    """Fail closed if a private joined artifact is structurally or relationally invalid."""
    _schema_error(artifact)
    crash_normalization = cast(Mapping[str, object], artifact["crash_normalization"])
    crash_provenance = cast(Mapping[str, object], artifact["crash_provenance"])
    provenance = cast(Mapping[str, object], artifact["person_join"])
    records = cast(list[Mapping[str, object]], artifact["records"])
    _validate_crash_contract(crash_normalization, crash_provenance, records)
    source_ids: set[str] = set()
    outcome_ids: set[str] = set()
    accepted_people = 0
    order: list[tuple[str, str]] = []
    for record in records:
        outcome = cast(Mapping[str, object], record["outcome"])
        summary = cast(Mapping[str, object], record["mode_summary"])
        source_id = cast(str, outcome["source_record_id"])
        outcome_id = cast(str, outcome["id"])
        if summary["source_record_id"] != source_id:
            raise ValueError("private joined artifact outcome and mode IDs do not match")
        if source_id in source_ids or outcome_id in outcome_ids:
            raise ValueError("private joined artifact outcome identities must be unique")
        source_ids.add(source_id)
        outcome_ids.add(outcome_id)
        accepted_people += _validate_summary(summary, outcome)
        order.append((cast(str, outcome["occurred_on"]), source_id))
    if order != sorted(order):
        raise ValueError("private joined artifact records are not canonically ordered")
    _validate_cross_accounting(
        provenance,
        crash_provenance,
        record_count=len(records),
        accepted_people=accepted_people,
    )


def build_joined_outcome_artifact(
    outcomes: Iterable[Mapping[str, object]],
    summaries: Iterable[FarsModeSummary],
    person_provenance: PersonJoinProvenance,
    crash_provenance: OutcomeProvenance,
    *,
    distribution_url: str,
    max_invalid_fraction: float = 0.05,
    allow_record_regression: bool = False,
    allow_mode_regression: bool = False,
    allow_release_regression: bool = False,
    allow_year_regression: bool = False,
) -> dict[str, object]:
    """Pair canonical outcomes and mode summaries in a deterministic private artifact."""
    outcome_values = list(outcomes)
    summary_values = list(summaries)
    outcome_source_ids = [str(outcome["source_record_id"]) for outcome in outcome_values]
    summary_source_ids = [summary.source_record_id for summary in summary_values]
    if len(outcome_source_ids) != len(set(outcome_source_ids)):
        raise ValueError("private joined artifact contains duplicate outcome source IDs")
    if len(summary_source_ids) != len(set(summary_source_ids)):
        raise ValueError("private joined artifact contains duplicate summary source IDs")
    if len(outcome_source_ids) != len(summary_source_ids) or set(outcome_source_ids) != set(
        summary_source_ids
    ):
        raise ValueError("private joined artifact requires one mode summary per outcome")
    outcome_values.sort(key=lambda outcome: (outcome["occurred_on"], outcome["source_record_id"]))
    base_artifact = build_outcome_artifact(
        outcome_values,
        crash_provenance,
        expected_year=2024,
        distribution_url=distribution_url,
        max_invalid_fraction=max_invalid_fraction,
        allow_record_regression=allow_record_regression,
        allow_year_regression=allow_year_regression,
    )
    outcome_by_id = {
        str(outcome["source_record_id"]): copy.deepcopy(dict(outcome)) for outcome in outcome_values
    }
    summary_by_id = {summary.source_record_id: summary.as_dict() for summary in summary_values}
    if (
        len(outcome_by_id) != len(outcome_values)
        or len(summary_by_id) != len(summary_values)
        or len(outcome_by_id) != len(summary_by_id)
        or set(outcome_by_id) != set(summary_by_id)
    ):
        raise ValueError("private joined artifact requires one mode summary per outcome")
    records = [
        {"outcome": outcome_by_id[source_id], "mode_summary": summary_by_id[source_id]}
        for source_id in outcome_by_id
    ]
    records.sort(
        key=lambda record: (
            cast(Mapping[str, object], record["outcome"])["occurred_on"],
            cast(Mapping[str, object], record["outcome"])["source_record_id"],
        )
    )
    artifact: dict[str, object] = {
        "schema_version": JOINED_ARTIFACT_SCHEMA_VERSION,
        "artifact_type": JOINED_ARTIFACT_TYPE,
        "crash_normalization": base_artifact["normalization"],
        "crash_provenance": base_artifact["provenance"],
        "join_policy": {
            "allow_mode_regression": allow_mode_regression,
            "allow_release_regression": allow_release_regression,
        },
        "person_join": person_provenance.as_dict(),
        "records": records,
    }
    validate_joined_outcome_artifact(artifact)
    return artifact


def canonical_joined_outcome_artifact_bytes(artifact: Mapping[str, object]) -> bytes:
    """Serialize a valid private joined artifact as deterministic UTF-8 JSON."""
    validate_joined_outcome_artifact(artifact)
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
