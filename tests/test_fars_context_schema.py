"""Machine-readable private FARS context schema and privacy-contract tests."""

from __future__ import annotations

import copy
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from nearmiss.adapters.fars import FARS_MAPPING_VERSION
from nearmiss.adapters.fars_joined import PERSON_MODE_MAPPING_VERSION
from nearmiss.config import Config
from nearmiss.fars_context import (
    _build_parsed_fars_context,
    canonical_parsed_network_sha256,
    fars_context_contract_descriptor,
)
from nearmiss.fars_context_schema import (
    FARS_CONTEXT_ARTIFACT_SCHEMA,
    validate_fars_context_schema,
)
from nearmiss.models import Segment

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schema" / "private-fars-context.schema.json"
LAT, LON = 38.54, -121.74


def _artifact() -> dict[str, Any]:
    segment = Segment("main", "Main", ((LAT - 0.01, LON), (LAT + 0.01, LON)))
    records = [
        {
            "outcome": {
                "source_record_id": f"2024:{index}",
                "occurred_on": "2024-06-15",
                "occurred_time_local": "12:00",
                "location": {"lat": LAT, "lon": LON},
            },
            "mode_summary": {
                "source_record_id": f"2024:{index}",
                "involved_modes": ["pedestrian"],
            },
        }
        for index in range(1, 6)
    ]
    source = {
        "source_id": "fars-joined",
        "dataset_year": 2024,
        "release_status": "final",
        "attempt_id": "schema-test",
        "raw_sha256": "a" * 64,
        "normalized_sha256": "b" * 64,
        "accident_sha256": "c" * 64,
        "person_sha256": "d" * 64,
        "crash_mapping_version": FARS_MAPPING_VERSION,
        "person_mapping_version": PERSON_MODE_MAPPING_VERSION,
        "crash_records_read": 5,
        "crash_records_accepted": 5,
        "crash_records_rejected": 0,
        "person_records_read": 5,
        "person_records_accepted": 5,
        "person_records_excluded": 0,
        "cases_joined": 5,
        "cases_excluded": 0,
    }
    inputs = {
        "config_raw_sha256": "e" * 64,
        "config_raw_byte_count": 100,
        "network_raw_sha256": "f" * 64,
        "network_raw_byte_count": 200,
        "network_canonical_sha256": canonical_parsed_network_sha256([segment]),
        "network_segment_count": 1,
        "network_coordinate_count": 2,
    }
    config = Config(
        city="schema-city",
        streets_path=Path("streets.geojson"),
        reports_path=Path("reports.json"),
        exposure_path=Path("exposure.json"),
        raw_dir=Path("private/raw"),
        out_dir=Path("private/out"),
        ref_lat=LAT,
        ref_lon=LON,
        min_publish_n=5,
        window_start="2024-01-01",
        window_end="2024-12-31",
    )
    return _build_parsed_fars_context(
        records,
        [segment],
        config,
        source_lineage=source,
        input_lineage=inputs,
        fars_snap_max_m=25.0,
        ambiguity_margin_m=5.0,
    )


def test_repository_schema_is_object_identical_to_embedded_contract() -> None:
    assert json.loads(SCHEMA_PATH.read_text(encoding="utf-8")) == FARS_CONTEXT_ARTIFACT_SCHEMA


def test_embedded_contract_is_valid_draft_2020_12_schema() -> None:
    Draft202012Validator.check_schema(FARS_CONTEXT_ARTIFACT_SCHEMA)


def test_schema_caps_are_derived_from_the_runtime_contract() -> None:
    caps = fars_context_contract_descriptor()["caps"]
    assert isinstance(caps, dict)
    properties = FARS_CONTEXT_ARTIFACT_SCHEMA["properties"]
    assert isinstance(properties, dict)
    inputs = properties["input_lineage"]["properties"]
    source = properties["source_lineage"]["properties"]
    accounting = properties["accounting"]["properties"]
    assert inputs["config_raw_byte_count"]["maximum"] == caps["max_config_bytes"]
    assert inputs["network_raw_byte_count"]["maximum"] == caps["max_network_bytes"]
    assert inputs["network_segment_count"]["maximum"] == caps["max_segments"]
    assert inputs["network_coordinate_count"]["maximum"] == caps["max_coordinates"]
    assert source["crash_records_read"]["maximum"] == caps["max_crash_source_records"]
    assert source["person_records_read"]["maximum"] == caps["max_person_source_records"]
    assert accounting["positive_candidate_cell_count"]["maximum"] == caps["max_cells"]
    assert accounting["crash_contribution_total"]["maximum"] == caps["max_contributions"]


@pytest.mark.parametrize("field", ["city_key", "cell_segment_id"])
def test_standalone_schema_rejects_unpaired_surrogate_text(field: str) -> None:
    artifact = _artifact()
    if field == "city_key":
        artifact["city_key"] = "\ud800"
    else:
        artifact["cells"][0]["segment_id"] = "\ud800"

    assert not Draft202012Validator(FARS_CONTEXT_ARTIFACT_SCHEMA).is_valid(artifact)


def test_current_private_context_artifact_passes_machine_and_semantic_validation() -> None:
    validate_fars_context_schema(_artifact())


def test_runtime_validator_applies_semantic_accounting_after_json_schema() -> None:
    artifact = _artifact()
    artifact["accounting"]["records_outside_window"] = 1
    with pytest.raises(ValueError, match="window accounting equation"):
        validate_fars_context_schema(artifact)


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(
            lambda artifact: artifact.__setitem__("overall", {"crash_count": 5}),
            id="top-overall",
        ),
        pytest.param(
            lambda artifact: artifact.__setitem__("suppressed_cells", {"secret-segment": 1}),
            id="top-suppressed-map",
        ),
        pytest.param(
            lambda artifact: artifact["cells"][0].__setitem__("fatality_count", 5),
            id="cell-fatality",
        ),
        pytest.param(
            lambda artifact: artifact["cells"][0].__setitem__("suppressed", False),
            id="cell-suppressed-key",
        ),
        pytest.param(
            lambda artifact: artifact["cells"][0].__setitem__("source_record_id", "2024:1"),
            id="cell-source-record-id",
        ),
        pytest.param(
            lambda artifact: artifact.__setitem__("visibility", "public"),
            id="public-visibility",
        ),
        pytest.param(lambda artifact: artifact.__setitem__("caveat", "context"), id="weak-caveat"),
        pytest.param(
            lambda artifact: artifact["cells"][0].__setitem__("involved_mode", "all_crashes"),
            id="unsupported-mode",
        ),
        pytest.param(
            lambda artifact: artifact["cells"][0].__setitem__("crash_count", 4),
            id="below-k",
        ),
        pytest.param(
            lambda artifact: artifact["input_lineage"].__setitem__(
                "network_raw_byte_count", 64 * 1024 * 1024 + 1
            ),
            id="input-cap",
        ),
        pytest.param(
            lambda artifact: artifact["method"]["window"].__setitem__(
                "effective_start_inclusive", "2023-12-31"
            ),
            id="wrong-date-year",
        ),
        pytest.param(
            lambda artifact: artifact["method"]["time"]["order"].reverse(),
            id="wrong-time-order",
        ),
        pytest.param(
            lambda artifact: artifact["method"]["snap"]["point_snap"]["caps"].__setitem__(
                "unbounded", 1
            ),
            id="point-snap-extra-cap",
        ),
        pytest.param(
            lambda artifact: artifact["method"]["snap"].__setitem__("reference_lat", None),
            id="configured-reference-missing-latitude",
        ),
        pytest.param(
            lambda artifact: artifact["cells"][0].__setitem__("segment_id", "\x00"),
            id="control-only-segment-id",
        ),
    ],
)
def test_schema_rejects_privacy_shape_enum_order_and_cap_mutations(
    mutate: Callable[[dict[str, Any]], None],
) -> None:
    artifact = copy.deepcopy(_artifact())
    mutate(artifact)

    with pytest.raises(ValueError, match="invalid private FARS context artifact"):
        validate_fars_context_schema(artifact)


def test_every_declared_object_shape_is_closed() -> None:
    pending: list[object] = [FARS_CONTEXT_ARTIFACT_SCHEMA]
    while pending:
        value = pending.pop()
        if isinstance(value, dict):
            if value.get("type") == "object":
                assert value.get("additionalProperties") is False
            pending.extend(value.values())
        elif isinstance(value, list):
            pending.extend(value)


def test_cell_contract_is_mode_only_and_contains_no_private_residual_dimensions() -> None:
    properties = FARS_CONTEXT_ARTIFACT_SCHEMA["properties"]
    assert isinstance(properties, dict)
    cells = properties["cells"]
    assert isinstance(cells, dict)
    item = cells["items"]
    assert isinstance(item, dict)
    assert set(item["properties"]) == {
        "segment_id",
        "part_of_day",
        "involved_mode",
        "crash_count",
    }
    encoded = json.dumps(item, sort_keys=True)
    for forbidden in ("overall", "fatality", "source_record_id", "suppressed_segment"):
        assert forbidden not in encoded
