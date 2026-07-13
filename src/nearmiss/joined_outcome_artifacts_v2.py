# SPDX-License-Identifier: Apache-2.0
"""Closed, fixed-year v2 artifacts for strict FARS accident/person joins."""

from __future__ import annotations

import copy
import json
import re
from collections.abc import Iterable, Mapping
from typing import Any, cast

from jsonschema import Draft202012Validator, FormatChecker

from .adapters.fars import FARS_MAPPING_VERSION
from .adapters.fars_joined import (
    MODE_ORDER,
    FarsMemberDescriptor,
    FarsModeSummary,
    PersonJoinProvenance,
    collect_joined,
    read_pinned_joined_export_bytes_for_contract,
)
from .adapters.outcomes import OutcomeProvenance
from .fars_national_context import FARS_2024_STATE_CODES
from .fars_year_contracts import (
    FARS_ACCIDENT_ROW_CAP,
    FARS_PERSON_ROW_CAP,
    FARS_YEAR_CONTRACT_HISTORY,
    SUPPORTED_FARS_YEARS,
    FarsYearContract,
    fars_year_contract_descriptor,
    fars_year_contract_from_descriptor,
    fars_year_contract_revision,
)
from .outcome_artifacts import (
    OUTCOME_ARTIFACT_SCHEMA,
    build_outcome_artifact,
    validate_outcome_artifact,
)

JOINED_ARTIFACT_V2_SCHEMA_VERSION = "2.0.0"
JOINED_ARTIFACT_V2_TYPE = "nearmiss.private.fars_joined_outcomes.v2"
JOINED_ARTIFACT_V2_MAX_INVALID_FRACTION = 0.05

_OUTCOME_DEFS = cast(Mapping[str, object], OUTCOME_ARTIFACT_SCHEMA["$defs"])
_MODE_ENUM = list(MODE_ORDER)
_MODE_COUNTS = {mode: {"type": "integer", "minimum": 0} for mode in MODE_ORDER}
_CONTRACT_FIELDS = tuple(fars_year_contract_descriptor(FARS_YEAR_CONTRACT_HISTORY[2020][0]))


def _registered_contracts() -> tuple[FarsYearContract, ...]:
    return tuple(
        contract for history in FARS_YEAR_CONTRACT_HISTORY.values() for contract in history
    )


def _contract_definition_name(contract: FarsYearContract) -> str:
    return f"source_contract_{contract.year}_r{contract.revision}"


def _contract_definition(contract: FarsYearContract) -> dict[str, object]:
    descriptor = fars_year_contract_descriptor(contract)
    return {
        "type": "object",
        "additionalProperties": False,
        "required": list(_CONTRACT_FIELDS),
        "properties": {key: {"const": value} for key, value in descriptor.items()},
    }


def _outcome_definition() -> dict[str, object]:
    definition = copy.deepcopy(cast(dict[str, object], _OUTCOME_DEFS["outcome"]))
    required = cast(list[str], definition["required"])
    if "state_code" not in required:
        required.append("state_code")
    properties = cast(dict[str, object], definition["properties"])
    properties["source_record_id"] = {
        "type": "string",
        "pattern": "^202[0-4]:[1-9][0-9]*$",
    }
    properties["occurred_on"] = {
        "type": "string",
        "format": "date",
        "pattern": "^202[0-4]-",
    }
    properties["state_code"] = {"type": "string", "enum": list(FARS_2024_STATE_CODES)}
    return definition


def _normalization_definition() -> dict[str, object]:
    definition = copy.deepcopy(cast(dict[str, object], _OUTCOME_DEFS["normalization"]))
    properties = cast(dict[str, object], definition["properties"])
    properties["adapter_version"] = {
        "type": "string",
        "enum": sorted({contract.crash_mapping_version for contract in _registered_contracts()}),
    }
    properties["max_invalid_fraction"] = {"const": JOINED_ARTIFACT_V2_MAX_INVALID_FRACTION}
    properties["allow_record_regression"] = {"const": False}
    properties["allow_year_regression"] = {"const": False}
    return definition


def _crash_provenance_definition() -> dict[str, object]:
    definition = copy.deepcopy(cast(dict[str, object], _OUTCOME_DEFS["provenance"]))
    properties = cast(dict[str, dict[str, object]], definition["properties"])
    properties["records_read"]["maximum"] = FARS_ACCIDENT_ROW_CAP
    properties["records_accepted"]["maximum"] = FARS_ACCIDENT_ROW_CAP
    return definition


def _year_branch(contract: FarsYearContract) -> dict[str, object]:
    year = contract.year
    identity = f"^{year}:[1-9][0-9]*$"
    return {
        "properties": {
            "source_contract": {"$ref": f"#/$defs/{_contract_definition_name(contract)}"},
            "crash_normalization": {
                "properties": {
                    "adapter_version": {"const": contract.crash_mapping_version},
                    "expected_year": {"const": year},
                    "distribution_url": {"const": contract.distribution_url},
                }
            },
            "crash_provenance": {
                "properties": {
                    "dataset_years": {"const": [year]},
                    "release_status": {"const": contract.release_stage},
                    "input_sha256": {"const": contract.raw_sha256},
                }
            },
            "person_join": {
                "properties": {
                    "mapping_version": {"const": contract.person_mapping_version},
                    "dataset_year": {"const": year},
                    "input_sha256": {"const": contract.raw_sha256},
                    "semantic_regime_id": {"const": contract.semantic_regime_id},
                }
            },
            "records": {
                "items": {
                    "properties": {
                        "outcome": {
                            "properties": {
                                "source_record_id": {"pattern": identity},
                                "occurred_on": {"pattern": f"^{year}-"},
                            }
                        },
                        "mode_summary": {"properties": {"source_record_id": {"pattern": identity}}},
                        "jurisdiction": {
                            "properties": {
                                "source_record_id": {"pattern": identity},
                                "state_code_system": {"const": contract.state_code_system},
                                "county_code_system": {"const": contract.county_code_system},
                            }
                        },
                    }
                }
            },
        }
    }


def _schema() -> dict[str, object]:
    contracts = _registered_contracts()
    definitions: dict[str, object] = {
        "sha256": copy.deepcopy(_OUTCOME_DEFS["sha256"]),
        "normalization": _normalization_definition(),
        "provenance": _crash_provenance_definition(),
        "location": copy.deepcopy(_OUTCOME_DEFS["location"]),
        "outcome": _outcome_definition(),
        "mode_array": {
            "type": "array",
            "uniqueItems": True,
            "items": {"type": "string", "enum": _MODE_ENUM},
        },
        "mode_counts": {
            "type": "object",
            "additionalProperties": False,
            "required": _MODE_ENUM,
            "properties": _MODE_COUNTS,
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
                    "pattern": "^202[0-4]:[1-9][0-9]*$",
                },
                "involved_modes": {"$ref": "#/$defs/mode_array"},
                "fatality_modes": {"$ref": "#/$defs/mode_array"},
                "involved_person_count_by_mode": {"$ref": "#/$defs/mode_counts"},
                "fatality_count_by_mode": {"$ref": "#/$defs/mode_counts"},
            },
        },
        "jurisdiction": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "source_record_id",
                "state_code",
                "state_code_system",
                "county_code",
                "county_status",
                "county_code_system",
            ],
            "properties": {
                "source_record_id": {
                    "type": "string",
                    "pattern": "^202[0-4]:[1-9][0-9]*$",
                },
                "state_code": {"type": "string", "enum": list(FARS_2024_STATE_CODES)},
                "state_code_system": {"type": "string", "minLength": 1},
                "county_code": {"type": "string", "pattern": "^[0-9]{3}$"},
                "county_status": {
                    "type": "string",
                    "enum": [
                        "reported",
                        "not_applicable",
                        "other",
                        "not_reported",
                        "unknown",
                    ],
                },
                "county_code_system": {"type": "string", "minLength": 1},
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
        "person_join": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "mapping_version",
                "semantic_regime_id",
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
                "mapping_version": {
                    "type": "string",
                    "enum": sorted({contract.person_mapping_version for contract in contracts}),
                },
                "semantic_regime_id": {
                    "type": "string",
                    "enum": sorted({contract.semantic_regime_id for contract in contracts}),
                },
                "dataset_year": {
                    "type": "integer",
                    "enum": list(SUPPORTED_FARS_YEARS),
                },
                "input_sha256": {"$ref": "#/$defs/sha256"},
                "accident_sha256": {"$ref": "#/$defs/sha256"},
                "person_sha256": {"$ref": "#/$defs/sha256"},
                "accident_member": {"$ref": "#/$defs/member_descriptor"},
                "person_member": {"$ref": "#/$defs/member_descriptor"},
                "records_read": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": FARS_PERSON_ROW_CAP,
                },
                "records_accepted": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": FARS_PERSON_ROW_CAP,
                },
                "cases_joined": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": FARS_ACCIDENT_ROW_CAP,
                },
                "records_excluded_with_rejected_crash": {
                    "type": "integer",
                    "minimum": 0,
                    "maximum": FARS_PERSON_ROW_CAP,
                },
                "cases_excluded_with_rejected_crash": {
                    "type": "integer",
                    "minimum": 0,
                    "maximum": FARS_ACCIDENT_ROW_CAP,
                },
                "rejection_reasons": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {"parent_crash_rejected": {"type": "integer", "minimum": 1}},
                },
            },
        },
        "join_policy": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "allow_record_regression",
                "allow_mode_regression",
                "allow_release_regression",
                "allow_year_regression",
            ],
            "properties": {
                "allow_record_regression": {"const": False},
                "allow_mode_regression": {"const": False},
                "allow_release_regression": {"const": False},
                "allow_year_regression": {"const": False},
            },
        },
        "joined_record": {
            "type": "object",
            "additionalProperties": False,
            "required": ["outcome", "mode_summary", "jurisdiction"],
            "properties": {
                "outcome": {"$ref": "#/$defs/outcome"},
                "mode_summary": {"$ref": "#/$defs/mode_summary"},
                "jurisdiction": {"$ref": "#/$defs/jurisdiction"},
            },
        },
        "source_contract": {
            "oneOf": [
                {"$ref": f"#/$defs/{_contract_definition_name(contract)}"} for contract in contracts
            ]
        },
    }
    for contract in contracts:
        definitions[_contract_definition_name(contract)] = _contract_definition(contract)

    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://nearmiss.dev/schema/private-fars-joined-outcomes-v2.schema.json",
        "title": "Private NearMiss fixed-year FARS joined-outcome artifact v2",
        "type": "object",
        "additionalProperties": False,
        "required": [
            "schema_version",
            "artifact_type",
            "source_contract",
            "crash_normalization",
            "crash_provenance",
            "join_policy",
            "person_join",
            "records",
        ],
        "oneOf": [_year_branch(contract) for contract in contracts],
        "$defs": definitions,
        "properties": {
            "schema_version": {"const": JOINED_ARTIFACT_V2_SCHEMA_VERSION},
            "artifact_type": {"const": JOINED_ARTIFACT_V2_TYPE},
            "source_contract": {"$ref": "#/$defs/source_contract"},
            "crash_normalization": {"$ref": "#/$defs/normalization"},
            "crash_provenance": {"$ref": "#/$defs/provenance"},
            "join_policy": {"$ref": "#/$defs/join_policy"},
            "person_join": {"$ref": "#/$defs/person_join"},
            "records": {
                "type": "array",
                "minItems": 1,
                "maxItems": FARS_ACCIDENT_ROW_CAP,
                "items": {"$ref": "#/$defs/joined_record"},
            },
        },
    }


JOINED_OUTCOME_ARTIFACT_V2_SCHEMA = _schema()
_VALIDATOR = Draft202012Validator(
    JOINED_OUTCOME_ARTIFACT_V2_SCHEMA,
    format_checker=FormatChecker(),
)


def _schema_error(artifact: Mapping[str, object]) -> None:
    errors = sorted(_VALIDATOR.iter_errors(artifact), key=lambda error: list(error.absolute_path))
    if errors:
        first = errors[0]
        path = "/".join(str(part) for part in first.absolute_path) or "(root)"
        raise ValueError(f"invalid private joined v2 artifact at {path}: {first.message}")


def _resolve_contract(source_contract: Mapping[str, object]) -> FarsYearContract:
    try:
        return fars_year_contract_from_descriptor(source_contract)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "private joined v2 source contract is not a recorded immutable revision"
        ) from exc


def _validate_member_descriptors(person: Mapping[str, object], contract: FarsYearContract) -> None:
    descriptors: list[FarsMemberDescriptor] = []
    for key in ("accident_member", "person_member"):
        value = cast(Mapping[str, object], person[key])
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
            raise ValueError("private joined v2 member descriptor is invalid") from exc
    accident, person_member = descriptors
    if (
        accident.name.casefold() != contract.accident_member
        or person_member.name.casefold() != contract.person_member
        or accident.archive_path == person_member.archive_path
        or accident.sha256 != person["accident_sha256"]
        or person_member.sha256 != person["person_sha256"]
    ):
        raise ValueError("private joined v2 member descriptors are inconsistent")


def _validate_mapping_versions(
    normalization: Mapping[str, object],
    person: Mapping[str, object],
    contract: FarsYearContract,
) -> None:
    if (
        normalization["adapter_version"] != contract.crash_mapping_version
        or person["mapping_version"] != contract.person_mapping_version
    ):
        raise ValueError(
            "private joined v2 mapping versions do not match the immutable source contract"
        )


def _validate_record(
    record: Mapping[str, object], contract: FarsYearContract
) -> tuple[str, str, int]:
    outcome = cast(Mapping[str, object], record["outcome"])
    summary = cast(Mapping[str, object], record["mode_summary"])
    jurisdiction = cast(Mapping[str, object], record["jurisdiction"])
    source_id = cast(str, outcome["source_record_id"])
    identity = re.fullmatch(rf"{contract.year}:([1-9][0-9]*)", source_id, re.ASCII)
    if identity is None or not cast(str, outcome["occurred_on"]).startswith(f"{contract.year}-"):
        raise ValueError("private joined v2 record identity or date does not match its year")
    if summary["source_record_id"] != source_id or jurisdiction["source_record_id"] != source_id:
        raise ValueError("private joined v2 sibling source identities do not match")
    if (
        jurisdiction["state_code"] != outcome["state_code"]
        or jurisdiction["state_code_system"] != contract.state_code_system
        or jurisdiction["county_code_system"] != contract.county_code_system
    ):
        raise ValueError(
            "private joined v2 jurisdiction does not match its outcome or code systems"
        )
    county_code = cast(str, jurisdiction["county_code"])
    expected_status = {
        "000": "not_applicable",
        "997": "other",
        "998": "not_reported",
        "999": "unknown",
    }.get(county_code, "reported")
    if jurisdiction["county_status"] != expected_status:
        raise ValueError("private joined v2 county status is inconsistent")

    involved = cast(Mapping[str, int], summary["involved_person_count_by_mode"])
    fatal = cast(Mapping[str, int], summary["fatality_count_by_mode"])
    expected_involved = [mode for mode in MODE_ORDER if involved[mode] > 0]
    expected_fatal = [mode for mode in MODE_ORDER if fatal[mode] > 0]
    if (
        summary["involved_modes"] != expected_involved
        or summary["fatality_modes"] != expected_fatal
    ):
        raise ValueError("private joined v2 mode arrays do not match canonical counts")
    if any(fatal[mode] > involved[mode] for mode in MODE_ORDER):
        raise ValueError("private joined v2 fatal mode count exceeds involved count")
    if sum(fatal.values()) != outcome["fatality_count"]:
        raise ValueError("private joined v2 fatal mode counts do not match outcome")
    involved_total = sum(involved.values())
    if involved_total < 1:
        raise ValueError("private joined v2 record requires an involved person")
    return cast(str, outcome["occurred_on"]), source_id, involved_total


def _validate_accounting(
    records: list[Mapping[str, object]],
    crash: Mapping[str, object],
    person: Mapping[str, object],
    *,
    accepted_people: int,
) -> None:
    if person["cases_joined"] != len(records):
        raise ValueError("private joined v2 cases_joined does not match records")
    if person["records_accepted"] != accepted_people:
        raise ValueError("private joined v2 accepted person count does not match records")
    excluded_records = cast(int, person["records_excluded_with_rejected_crash"])
    if person["records_accepted"] + excluded_records != person["records_read"]:
        raise ValueError("private joined v2 person accounting does not cover records_read")
    reasons = cast(Mapping[str, int], person["rejection_reasons"])
    if reasons != ({"parent_crash_rejected": excluded_records} if excluded_records else {}):
        raise ValueError("private joined v2 person rejection reasons are inconsistent")
    excluded_cases = cast(int, person["cases_excluded_with_rejected_crash"])
    if excluded_cases > excluded_records:
        raise ValueError("private joined v2 excluded cases exceed excluded person records")
    if crash["records_accepted"] != len(records):
        raise ValueError("private joined v2 crash accepted count does not match records")
    if len(records) + excluded_cases != crash["records_read"]:
        raise ValueError("private joined v2 crash/person case accounting differs")
    if crash["records_read"] > FARS_ACCIDENT_ROW_CAP:
        raise ValueError("private joined v2 crash records exceed the annual row cap")
    rejected = sum(cast(Mapping[str, int], crash["rejection_reasons"]).values())
    if rejected != excluded_cases:
        raise ValueError("private joined v2 crash rejection accounting differs")


def validate_joined_outcome_artifact_v2(artifact: Mapping[str, object]) -> None:
    """Validate structure and cross-fields; this does not prove source replay."""
    _schema_error(artifact)
    source_contract = cast(Mapping[str, object], artifact["source_contract"])
    contract = _resolve_contract(source_contract)
    normalization = cast(Mapping[str, object], artifact["crash_normalization"])
    crash = cast(Mapping[str, object], artifact["crash_provenance"])
    person = cast(Mapping[str, object], artifact["person_join"])
    policy = cast(Mapping[str, object], artifact["join_policy"])
    records = cast(list[Mapping[str, object]], artifact["records"])

    base = {
        "schema_version": "1.0.0",
        "artifact_type": "nearmiss.official_outcomes",
        "normalization": copy.deepcopy(dict(normalization)),
        "provenance": copy.deepcopy(dict(crash)),
        "outcomes": [
            copy.deepcopy(dict(cast(Mapping[str, object], row["outcome"]))) for row in records
        ],
    }
    cast(dict[str, object], base["normalization"])["adapter_version"] = FARS_MAPPING_VERSION
    try:
        validate_outcome_artifact(base, expected_source_id="fars")
    except ValueError as exc:
        raise ValueError("private joined v2 crash contract is invalid") from exc
    if (
        normalization["expected_year"] != contract.year
        or normalization["distribution_url"] != contract.distribution_url
        or normalization["max_invalid_fraction"] != JOINED_ARTIFACT_V2_MAX_INVALID_FRACTION
        or normalization["allow_record_regression"] is not False
        or normalization["allow_year_regression"] is not False
        or crash["dataset_years"] != [contract.year]
        or crash["release_status"] != contract.release_stage
        or crash["input_sha256"] != contract.raw_sha256
        or person["dataset_year"] != contract.year
        or person["input_sha256"] != contract.raw_sha256
        or person["semantic_regime_id"] != contract.semantic_regime_id
        or policy["allow_record_regression"] is not False
        or policy["allow_mode_regression"] is not False
        or policy["allow_release_regression"] is not False
        or policy["allow_year_regression"] is not False
    ):
        raise ValueError("private joined v2 metadata does not match its immutable source contract")
    _validate_member_descriptors(person, contract)
    _validate_mapping_versions(normalization, person, contract)
    if crash["input_sha256"] != person["input_sha256"]:
        raise ValueError("private joined v2 crash/person input digests do not match")

    source_ids: set[str] = set()
    outcome_ids: set[str] = set()
    order: list[tuple[str, str]] = []
    accepted_people = 0
    for record in records:
        occurred_on, source_id, involved = _validate_record(record, contract)
        outcome_id = cast(str, cast(Mapping[str, object], record["outcome"])["id"])
        if source_id in source_ids or outcome_id in outcome_ids:
            raise ValueError("private joined v2 record identities must be unique")
        source_ids.add(source_id)
        outcome_ids.add(outcome_id)
        order.append((occurred_on, source_id))
        accepted_people += involved
    if order != sorted(order):
        raise ValueError("private joined v2 records are not canonically ordered")
    _validate_accounting(records, crash, person, accepted_people=accepted_people)


def _project_joined_outcome_artifact_v2_without_source_authority(
    outcomes: Iterable[Mapping[str, object]],
    summaries: Iterable[FarsModeSummary],
    person_provenance: PersonJoinProvenance,
    crash_provenance: OutcomeProvenance,
    *,
    contract: FarsYearContract,
) -> dict[str, object]:
    """Project already-joined values without minting or asserting source authority.

    This private helper exists only to keep the deterministic projection and its
    invariant checks independently testable.  Only
    ``canonical_joined_outcome_artifact_v2_from_pinned_archive`` verifies and
    reads pinned raw bytes before calling this projection.
    """
    if not isinstance(contract, FarsYearContract):
        raise TypeError("private joined v2 builder requires an immutable year contract")
    descriptor = fars_year_contract_descriptor(contract)
    resolved = _resolve_contract(descriptor)
    if resolved != contract:
        raise ValueError("private joined v2 builder requires a recorded contract revision")
    outcome_values = [copy.deepcopy(dict(outcome)) for outcome in outcomes]
    summary_values = list(summaries)
    if len(outcome_values) > FARS_ACCIDENT_ROW_CAP or len(summary_values) > FARS_ACCIDENT_ROW_CAP:
        raise ValueError("private joined v2 records exceed the annual row cap")
    outcome_ids = [cast(str, value.get("source_record_id")) for value in outcome_values]
    summary_ids = [summary.source_record_id for summary in summary_values]
    if (
        len(outcome_ids) != len(set(outcome_ids))
        or len(summary_ids) != len(set(summary_ids))
        or len(outcome_ids) != len(summary_ids)
        or set(outcome_ids) != set(summary_ids)
    ):
        raise ValueError("private joined v2 requires one unique summary per outcome")
    if any(summary.jurisdiction is None for summary in summary_values):
        raise ValueError("private joined v2 requires jurisdiction for every record")
    if (
        person_provenance.dataset_year != contract.year
        or person_provenance.semantic_regime_id != contract.semantic_regime_id
    ):
        raise ValueError("private joined v2 strict person provenance does not match contract")

    outcome_values.sort(key=lambda value: (value["occurred_on"], value["source_record_id"]))
    base = build_outcome_artifact(
        outcome_values,
        crash_provenance,
        expected_year=contract.year,
        distribution_url=contract.distribution_url,
        adapter_version=contract.crash_mapping_version,
        max_invalid_fraction=JOINED_ARTIFACT_V2_MAX_INVALID_FRACTION,
        allow_record_regression=False,
        allow_year_regression=False,
    )
    outcome_by_id = {cast(str, value["source_record_id"]): value for value in outcome_values}
    summary_by_id = {summary.source_record_id: summary for summary in summary_values}
    records: list[dict[str, object]] = []
    for source_id, outcome in outcome_by_id.items():
        summary = summary_by_id[source_id]
        jurisdiction = cast(Any, summary.jurisdiction).as_dict()
        jurisdiction["state_code_system"] = contract.state_code_system
        records.append(
            {
                "outcome": outcome,
                "mode_summary": summary.as_dict(),
                "jurisdiction": jurisdiction,
            }
        )
    person = person_provenance.as_dict()
    person["semantic_regime_id"] = person_provenance.semantic_regime_id
    artifact: dict[str, object] = {
        "schema_version": JOINED_ARTIFACT_V2_SCHEMA_VERSION,
        "artifact_type": JOINED_ARTIFACT_V2_TYPE,
        "source_contract": descriptor,
        "crash_normalization": base["normalization"],
        "crash_provenance": base["provenance"],
        "join_policy": {
            "allow_record_regression": False,
            "allow_mode_regression": False,
            "allow_release_regression": False,
            "allow_year_regression": False,
        },
        "person_join": person,
        "records": records,
    }
    validate_joined_outcome_artifact_v2(artifact)
    return artifact


def _build_joined_outcome_artifact_v2_from_pinned_archive(
    raw_archive: bytes,
    *,
    contract: FarsYearContract,
) -> dict[str, object]:
    """Build a private projection after exact package and contract selection."""
    if not isinstance(raw_archive, bytes):
        raise TypeError("private joined v2 raw archive must be bytes")
    if len(raw_archive) != contract.raw_size_bytes:
        raise ValueError("FARS raw archive identity does not match the fixed-year contract")

    batch = read_pinned_joined_export_bytes_for_contract(raw_archive, contract=contract)
    if batch.year_contract != contract or batch.input_sha256 != contract.raw_sha256:
        raise ValueError("private joined v2 strict reader did not retain the pinned contract")
    outcomes, summaries, crash_provenance, person_provenance = collect_joined(
        batch,
        release_status=contract.release_stage,
    )
    if (
        crash_provenance.input_sha256 != batch.input_sha256
        or person_provenance.input_sha256 != batch.input_sha256
        or person_provenance.accident_member != batch.accident_member
        or person_provenance.person_member != batch.person_member
        or person_provenance.accident_sha256 != batch.accident_sha256
        or person_provenance.person_sha256 != batch.person_sha256
    ):
        raise ValueError("private joined v2 strict read provenance lost its source binding")
    return _project_joined_outcome_artifact_v2_without_source_authority(
        outcomes,
        summaries,
        person_provenance,
        crash_provenance,
        contract=contract,
    )


def canonical_joined_outcome_artifact_v2_from_pinned_archive(
    raw_archive: bytes,
    *,
    year: int,
    contract_revision: int,
) -> bytes:
    """Replay exact registered bytes and return the canonical authority artifact.

    This is the sole source-authority-producing v2 boundary. It resolves an
    explicit immutable contract revision, rejects a wrong byte length before
    hashing, performs the strict archive/member replay, validates the resulting
    projection, and serializes it canonically.
    """
    if not isinstance(raw_archive, bytes):
        raise TypeError("private joined v2 raw archive must be bytes")
    contract = fars_year_contract_revision(year, contract_revision)
    artifact = _build_joined_outcome_artifact_v2_from_pinned_archive(
        raw_archive,
        contract=contract,
    )
    return canonical_joined_outcome_artifact_v2_bytes(artifact)


def canonical_joined_outcome_artifact_v2_bytes(artifact: Mapping[str, object]) -> bytes:
    """Structurally validate and serialize; this does not confer source authority."""
    validate_joined_outcome_artifact_v2(artifact)
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
