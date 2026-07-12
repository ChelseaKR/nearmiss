"""Contract tests for the private FARS joined-outcome artifact."""

from __future__ import annotations

import copy
import json
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import pytest
from jsonschema import Draft202012Validator

from nearmiss.adapters.fars import FarsAdapter, read_export_bytes
from nearmiss.adapters.fars_joined import (
    FarsMemberDescriptor,
    FarsModeSummary,
    PersonJoinProvenance,
)
from nearmiss.joined_outcome_artifacts import (
    JOINED_ARTIFACT_SCHEMA,
    build_joined_outcome_artifact,
    canonical_joined_outcome_artifact_bytes,
    validate_joined_outcome_artifact,
)

ROOT = Path(__file__).resolve().parents[1]
ACCIDENT = (
    (ROOT / "tests" / "fixtures" / "fars" / "accident.csv")
    .read_bytes()
    .replace(b",2023,", b",2024,")
)
URL = "https://static.nhtsa.gov/nhtsa/downloads/FARS/2024/National/FARS2024.zip"


def _inputs() -> tuple[list[dict[str, Any]], list[Any], Any, Any]:
    outcomes, crash = FarsAdapter().parse(read_export_bytes(ACCIDENT), release_status="final")
    crash = replace(crash, input_sha256="a" * 64)
    zeroes = {
        "motor_vehicle_occupant": 0,
        "motorcyclist": 0,
        "pedalcyclist": 0,
        "pedestrian": 0,
        "other_road_user": 0,
        "unknown": 0,
    }
    summaries = [
        FarsModeSummary(
            source_record_id="2024:100001",
            involved_modes=("motor_vehicle_occupant", "pedestrian"),
            fatality_modes=("motor_vehicle_occupant",),
            involved_person_count_by_mode={
                **zeroes,
                "motor_vehicle_occupant": 1,
                "pedestrian": 1,
            },
            fatality_count_by_mode={**zeroes, "motor_vehicle_occupant": 1},
        ),
        FarsModeSummary(
            source_record_id="2024:100002",
            involved_modes=("motorcyclist", "pedalcyclist"),
            fatality_modes=("motorcyclist", "pedalcyclist"),
            involved_person_count_by_mode={**zeroes, "motorcyclist": 1, "pedalcyclist": 1},
            fatality_count_by_mode={**zeroes, "motorcyclist": 1, "pedalcyclist": 1},
        ),
    ]
    accident_member = FarsMemberDescriptor(
        archive_path="FARS/accident.csv",
        name="accident.csv",
        uncompressed_size=len(ACCIDENT),
        crc32="12345678",
        sha256="b" * 64,
    )
    person_member = FarsMemberDescriptor(
        archive_path="FARS/person.csv",
        name="person.csv",
        uncompressed_size=100,
        crc32="87654321",
        sha256="c" * 64,
    )
    provenance = PersonJoinProvenance(
        mapping_version="1.0.0",
        dataset_year=2024,
        input_sha256="a" * 64,
        accident_sha256="b" * 64,
        person_sha256="c" * 64,
        accident_member=accident_member,
        person_member=person_member,
        records_read=5,
        records_accepted=4,
        cases_joined=2,
        records_excluded_with_rejected_crash=1,
        cases_excluded_with_rejected_crash=1,
        rejection_reasons={"parent_crash_rejected": 1},
    )
    return outcomes, summaries, crash, provenance


def _build(outcomes: Any, summaries: Any, crash: Any, person: Any) -> dict[str, object]:
    return build_joined_outcome_artifact(
        outcomes,
        summaries,
        person,
        crash,
        distribution_url=URL,
        max_invalid_fraction=0.34,
    )


def _artifact() -> dict[str, object]:
    outcomes, summaries, crash, person = _inputs()
    return _build(outcomes, summaries, crash, person)


def _records(artifact: dict[str, object]) -> list[dict[str, Any]]:
    return cast(list[dict[str, Any]], artifact["records"])


def _join(artifact: dict[str, object]) -> dict[str, Any]:
    return cast(dict[str, Any], artifact["person_join"])


def _crash(artifact: dict[str, object]) -> dict[str, Any]:
    return cast(dict[str, Any], artifact["crash_provenance"])


def _normalization(artifact: dict[str, object]) -> dict[str, Any]:
    return cast(dict[str, Any], artifact["crash_normalization"])


def _tamper_fatal_reconciliation(artifact: dict[str, object]) -> None:
    summary = _records(artifact)[0]["mode_summary"]
    summary["fatality_modes"] = ["motor_vehicle_occupant", "pedestrian"]
    summary["fatality_count_by_mode"]["pedestrian"] = 1


def test_schema_is_valid_and_builds_one_to_one_private_records() -> None:
    Draft202012Validator.check_schema(JOINED_ARTIFACT_SCHEMA)
    schema_path = ROOT / "schema" / "private-fars-joined-outcomes.schema.json"
    assert json.loads(schema_path.read_text(encoding="utf-8")) == JOINED_ARTIFACT_SCHEMA
    artifact = _artifact()
    assert artifact["artifact_type"] == "nearmiss.private.fars_joined_outcomes"
    assert len(_records(artifact)) == 2
    for record in _records(artifact):
        assert record["outcome"]["source_record_id"] == record["mode_summary"]["source_record_id"]
        assert set(record["outcome"]).isdisjoint(
            {"involved_modes", "fatality_modes", "fatality_count_by_mode"}
        )
    assert _join(artifact)["dataset_year"] == 2024
    assert _join(artifact)["mapping_version"] == "1.0.0"
    assert len(_join(artifact)["input_sha256"]) == 64
    assert len(_join(artifact)["accident_sha256"]) == 64
    assert len(_join(artifact)["person_sha256"]) == 64
    assert artifact["crash_normalization"] == {
        "adapter_id": "fars",
        "adapter_version": "1.0.0",
        "expected_year": 2024,
        "distribution_url": URL,
        "max_invalid_fraction": 0.34,
        "allow_record_regression": False,
        "allow_year_regression": False,
    }
    assert _crash(artifact)["release_status"] == "final"
    assert _crash(artifact)["records_read"] == 3
    assert _crash(artifact)["records_accepted"] == 2


def test_build_and_canonical_bytes_are_stable_under_input_reordering() -> None:
    outcomes, summaries, crash, person = _inputs()
    first = _build(outcomes, summaries, crash, person)
    second = _build(reversed(outcomes), reversed(summaries), crash, person)
    assert first == second
    payload = canonical_joined_outcome_artifact_bytes(first)
    assert payload == canonical_joined_outcome_artifact_bytes(copy.deepcopy(first))
    assert payload.endswith(b"\n")
    assert b"\n" not in payload[:-1]
    assert json.loads(payload) == first
    assert b"generated_at" not in payload


def test_builder_requires_exactly_one_summary_per_outcome() -> None:
    outcomes, summaries, crash, person = _inputs()
    with pytest.raises(ValueError, match="one mode summary per outcome"):
        _build(outcomes, summaries[:-1], crash, person)
    with pytest.raises(ValueError, match="one mode summary per outcome"):
        _build(outcomes[:-1], summaries, crash, person)
    with pytest.raises(ValueError, match="duplicate outcome source IDs"):
        _build([*outcomes, outcomes[0]], summaries, crash, person)


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda value: _records(value)[0]["mode_summary"].update(source_record_id="2024:999999"),
            "outcome and mode IDs",
        ),
        (
            lambda value: _records(value)[1]["outcome"].update(
                id=_records(value)[0]["outcome"]["id"]
            ),
            "crash contract is invalid",
        ),
        (
            lambda value: _records(value)[0]["mode_summary"].update(
                involved_modes=["pedestrian", "motor_vehicle_occupant"]
            ),
            "mode arrays",
        ),
        (_tamper_fatal_reconciliation, "fatal mode counts"),
        (lambda value: _join(value).update(cases_joined=99), "cases_joined"),
        (lambda value: _join(value).update(records_accepted=99), "accepted person count"),
        (lambda value: _join(value).update(dataset_year=2023), "dataset_year"),
        (lambda value: _join(value).update(mapping_version="2.0.0"), "mapping_version"),
        (lambda value: _join(value).update(person_sha256="bad"), "person_sha256"),
        (
            lambda value: _crash(value).update(input_sha256="d" * 64),
            "input digests do not match",
        ),
        (
            lambda value: _normalization(value).update(allow_year_regression=True),
            "must not authorize year regression",
        ),
        (
            lambda value: _normalization(value).update(
                distribution_url=URL.removesuffix("FARS2024.zip") + "accident.csv"
            ),
            "distribution must be a ZIP",
        ),
        (
            lambda value: _crash(value).update(release_status="draft"),
            "release status is unsupported",
        ),
        (
            lambda value: _join(value).update(cases_excluded_with_rejected_crash=2),
            "excluded cases exceed",
        ),
        (
            lambda value: _records(value)[0]["outcome"]["location"].update(lat=float("nan")),
            "crash contract is invalid",
        ),
        (
            lambda value: _join(value).update(rejection_reasons={}),
            "rejection reasons",
        ),
        (lambda value: value.update(generated_at="2026-01-01T00:00:00Z"), "generated_at"),
    ],
    ids=[
        "id-mismatch",
        "duplicate-outcome-id",
        "mode-order",
        "fatal-reconciliation",
        "case-accounting",
        "person-accounting",
        "year",
        "mapping-version",
        "member-digest",
        "cross-input-digest",
        "year-override",
        "non-zip-distribution",
        "release-status",
        "excluded-cross-accounting",
        "nonfinite-coordinate",
        "rejection-accounting",
        "timestamp",
    ],
)
def test_validation_rejects_relational_and_schema_tampering(mutate: Any, message: str) -> None:
    artifact = _artifact()
    mutate(artifact)
    with pytest.raises(ValueError, match=message):
        validate_joined_outcome_artifact(artifact)


def test_joined_fields_cannot_be_smuggled_into_v1_outcomes() -> None:
    artifact = _artifact()
    _records(artifact)[0]["outcome"]["involved_modes"] = ["pedestrian"]
    with pytest.raises(ValueError, match="involved_modes"):
        validate_joined_outcome_artifact(artifact)


def test_mixed_case_member_names_preserve_the_core_descriptor_contract() -> None:
    artifact = _artifact()
    joined = _join(artifact)
    joined["accident_member"].update(archive_path="FARS/ACCIDENT.CSV", name="ACCIDENT.CSV")
    joined["person_member"].update(archive_path="FARS/Person.CsV", name="Person.CsV")
    validate_joined_outcome_artifact(artifact)


def test_unsafe_member_path_tampering_is_rejected() -> None:
    artifact = _artifact()
    _join(artifact)["accident_member"]["archive_path"] = "../../accident.csv"
    with pytest.raises(ValueError, match="member descriptor is invalid"):
        validate_joined_outcome_artifact(artifact)


def test_record_count_is_bounded_to_2024_crash_evidence() -> None:
    artifact = _artifact()
    artifact["records"] = _records(artifact) * 18149
    with pytest.raises(ValueError, match="too long"):
        validate_joined_outcome_artifact(artifact)
