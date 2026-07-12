"""Adversarial and deterministic tests for official-outcome artifacts."""

from __future__ import annotations

import copy
import json
import uuid
from pathlib import Path
from typing import Any, cast

import pytest
from jsonschema import Draft202012Validator

from nearmiss.adapters.fars import FARS_MAPPING_VERSION, FarsAdapter
from nearmiss.outcome_artifacts import (
    OUTCOME_ARTIFACT_SCHEMA,
    build_outcome_artifact,
    canonical_outcome_artifact_bytes,
    validate_outcome_artifact,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "fars" / "accident.csv"
SCHEMA_PATH = ROOT / "schema" / "official-outcome-artifact.schema.json"
DISTRIBUTION_URL = (
    "https://static.nhtsa.gov/nhtsa/downloads/FARS/2023/National/FARS2023NationalCSV.zip"
)


def _artifact(
    *, max_invalid_fraction: float = 0.34, allow_record_regression: bool = False
) -> dict[str, object]:
    outcomes, provenance = FarsAdapter().parse(FIXTURE, release_status="final")
    return build_outcome_artifact(
        outcomes,
        provenance,
        expected_year=2023,
        distribution_url=DISTRIBUTION_URL,
        max_invalid_fraction=max_invalid_fraction,
        allow_record_regression=allow_record_regression,
    )


def _normalization(artifact: dict[str, object]) -> dict[str, Any]:
    return cast(dict[str, Any], artifact["normalization"])


def _provenance(artifact: dict[str, object]) -> dict[str, Any]:
    return cast(dict[str, Any], artifact["provenance"])


def _outcomes(artifact: dict[str, object]) -> list[dict[str, Any]]:
    return cast(list[dict[str, Any]], artifact["outcomes"])


def test_public_schema_is_valid_and_matches_installed_runtime_contract() -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    assert schema == OUTCOME_ARTIFACT_SCHEMA


def test_build_is_stable_traceable_and_contains_no_run_timestamp() -> None:
    first = _artifact()
    second = _artifact()
    assert first == second
    assert _normalization(first) == {
        "adapter_id": "fars",
        "adapter_version": FARS_MAPPING_VERSION,
        "expected_year": 2023,
        "distribution_url": DISTRIBUTION_URL,
        "max_invalid_fraction": 0.34,
        "allow_record_regression": False,
        "allow_year_regression": False,
    }
    assert _provenance(first)["input_sha256"]
    assert all("involved_modes" not in outcome for outcome in _outcomes(first))
    assert "timestamp" not in canonical_outcome_artifact_bytes(first).decode()


def test_canonical_bytes_are_sorted_compact_and_newline_terminated() -> None:
    artifact = _artifact()
    payload = canonical_outcome_artifact_bytes(artifact)
    assert payload == canonical_outcome_artifact_bytes(copy.deepcopy(artifact))
    assert payload.endswith(b"\n")
    assert b"\n" not in payload[:-1]
    assert payload.startswith(b'{"artifact_type":"nearmiss.official_outcomes"')
    assert json.loads(payload) == artifact


def test_builder_detaches_nested_outcomes_from_caller_mutation() -> None:
    outcomes, provenance = FarsAdapter().parse(FIXTURE, release_status="final")
    artifact = build_outcome_artifact(
        outcomes,
        provenance,
        expected_year=2023,
        distribution_url=DISTRIBUTION_URL,
        max_invalid_fraction=0.34,
    )
    cast(dict[str, object], outcomes[0]["location"])["lat"] = 0
    assert cast(dict[str, Any], _outcomes(artifact)[0]["location"])["lat"] != 0


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda value: value.update(outcomes=[]), "non-empty"),
        (
            lambda value: _outcomes(value)[1].update(id=_outcomes(value)[0]["id"]),
            "IDs must be unique",
        ),
        (
            lambda value: _outcomes(value)[0].update(id=str(uuid.uuid4())),
            "derived from its FARS source identity",
        ),
        (
            lambda value: _outcomes(value)[1].update(
                source_record_id=_outcomes(value)[0]["source_record_id"]
            ),
            "source_record_id values must be unique",
        ),
        (
            lambda value: _outcomes(value)[0].update(source_record_id="not-an-identity"),
            "source_record_id",
        ),
        (
            lambda value: _outcomes(value)[0].update(source_record_id="2022:100001"),
            "expected_year:positive-digits",
        ),
        (lambda value: _outcomes(value).reverse(), "must be ordered"),
        (
            lambda value: _provenance(value).update(records_accepted=1),
            "accepted count",
        ),
        (
            lambda value: _provenance(value).update(dataset_years=[2022, 2023]),
            "dataset_years",
        ),
        (lambda value: _provenance(value).pop("input_sha256"), "input_sha256"),
        (
            lambda value: _normalization(value).update(distribution_url="http://example.test/a"),
            "distribution_url",
        ),
        (
            lambda value: _normalization(value).update(
                distribution_url=(
                    "https://static.nhtsa.gov/nhtsa/downloads/FARS/2022/National/data.zip"
                )
            ),
            "release year",
        ),
        (
            lambda value: _normalization(value).update(max_invalid_fraction=float("nan")),
            "max_invalid_fraction",
        ),
        (
            lambda value: _outcomes(value)[0].update(involved_modes=["pedestrian"]),
            "involved_modes",
        ),
        (
            lambda value: _outcomes(value)[0].update(occurred_on="2022-01-01"),
            "expected_year",
        ),
        (lambda value: value.update(generated_at="2026-07-12T00:00:00Z"), "generated_at"),
        (
            lambda value: _normalization(value).update(adapter_version="99.0.0"),
            "adapter_version",
        ),
        (
            lambda value: _provenance(value).update(release_status="final\nsecret"),
            "release_status",
        ),
    ],
    ids=[
        "empty",
        "duplicate-id",
        "arbitrary-id",
        "duplicate-source-record-id",
        "invalid-source-record-id-shape",
        "wrong-source-record-year",
        "unsorted",
        "accepted-count",
        "dataset-years",
        "missing-input-hash",
        "insecure-url",
        "wrong-distribution-year",
        "nan-threshold",
        "unsupported-modes",
        "wrong-outcome-year",
        "timestamp-field",
        "unsupported-adapter-version",
        "unsafe-release-status",
    ],
)
def test_validation_rejects_adversarial_mutations(mutate: Any, message: str) -> None:
    artifact = _artifact()
    mutate(artifact)
    with pytest.raises(ValueError, match=message):
        validate_outcome_artifact(artifact)


def test_invalid_fraction_is_enforced_at_build_and_validation_boundaries() -> None:
    outcomes, provenance = FarsAdapter().parse(FIXTURE, release_status="final")
    with pytest.raises(ValueError, match="invalid fraction"):
        build_outcome_artifact(
            outcomes,
            provenance,
            expected_year=2023,
            distribution_url=DISTRIBUTION_URL,
        )

    artifact = _artifact()
    _normalization(artifact)["max_invalid_fraction"] = 0.32
    with pytest.raises(ValueError, match="invalid fraction"):
        validate_outcome_artifact(artifact)


def test_expected_source_id_is_checked_for_consumers() -> None:
    with pytest.raises(ValueError, match="does not match"):
        validate_outcome_artifact(_artifact(), expected_source_id="other")


def test_official_outcome_contract_is_enforced_inside_artifact() -> None:
    artifact = _artifact()
    _outcomes(artifact)[0]["location"] = {"lat": 999, "lon": -121}
    with pytest.raises(ValueError, match="location"):
        validate_outcome_artifact(artifact)


@pytest.mark.parametrize("coordinate", [float("nan"), float("inf"), float("-inf")])
@pytest.mark.parametrize("axis", ["lat", "lon"])
def test_nonfinite_coordinates_are_rejected(axis: str, coordinate: float) -> None:
    artifact = _artifact()
    location = cast(dict[str, float], _outcomes(artifact)[0]["location"])
    location[axis] = coordinate
    with pytest.raises(ValueError):
        validate_outcome_artifact(artifact)


@pytest.mark.parametrize(
    "url",
    [
        "https://evil.test/nhtsa/downloads/FARS/2023/data.zip",
        "https://static.nhtsa.gov.evil.test/nhtsa/downloads/FARS/2023/data.zip",
        "https://static.nhtsa.gov:443/nhtsa/downloads/FARS/2023/data.zip",
        "https://static.nhtsa.gov:bad/nhtsa/downloads/FARS/2023/data.zip",
        "https://static.nhtsa.gov/nhtsa/downloads/FARS/2023/data.zip?token=secret",
    ],
)
def test_builder_rejects_malicious_distribution_urls(url: str) -> None:
    outcomes, provenance = FarsAdapter().parse(FIXTURE, release_status="final")
    with pytest.raises(ValueError, match="FARS distribution URL"):
        build_outcome_artifact(
            outcomes,
            provenance,
            expected_year=2023,
            distribution_url=url,
            max_invalid_fraction=0.34,
        )
