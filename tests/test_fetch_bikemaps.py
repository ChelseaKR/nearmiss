"""The BikeMaps real-data bridge maps real records onto the intake contract.

These tests use a small BikeMaps-shaped sample (no network) and assert that every
emitted report validates against schema/report.schema.json and that the
vocabulary crosswalk is faithful. The live fetch path is exercised separately;
here we pin the transform that turns real BikeMaps GeoJSON into intake reports.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType
from typing import Any

import jsonschema

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads((ROOT / "schema" / "report.schema.json").read_text(encoding="utf-8"))


def _load_tool() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "fetch_bikemaps", ROOT / "tools" / "fetch_bikemaps.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


fb = _load_tool()


def _feature(lon: float, lat: float, props: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [lon, lat]},
        "properties": props,
    }


SAMPLE = {
    "nearmiss": [
        _feature(
            -123.365,
            48.428,
            {"pk": 1, "date": "2023-05-01T17:30:00Z", "incident_with": "Vehicle, passing"},
        ),
        _feature(
            -123.366,
            48.429,
            {"pk": 2, "date": "2023-06-11T08:05:00Z", "incident_with": "Vehicle, open door"},
        ),
        _feature(
            -123.364,
            48.427,
            {"pk": 3, "date": "2023-07-01T12:00:00", "incident_with": "Pedestrian"},
        ),
    ],
    "collision": [
        _feature(
            -123.360,
            48.430,
            {
                "pk": 4,
                "date": "2023-08-02T09:00:00Z",
                "incident_with": "Vehicle, head on",
                "injury": "Injury, hospitalized",
            },
        ),
        _feature(
            -123.361,
            48.431,
            {
                "pk": 5,
                "date": "2023-08-03T09:00:00Z",
                "incident_with": "Vehicle, rear end",
                "injury": "No injury",
            },
        ),
    ],
    "hazard": [
        _feature(
            -123.362,
            48.432,
            {"pk": 6, "date": "2023-09-09T10:00:00Z", "p_type": "Road or path issue"},
        ),
    ],
}


def test_every_mapped_report_is_schema_valid() -> None:
    reports, counts = fb.collect(SAMPLE, bbox=None, utc_offset="-07:00")
    assert counts == {"nearmiss": 3, "collision": 2, "hazard": 1}
    validator = jsonschema.Draft202012Validator(SCHEMA)
    for r in reports:
        errors = list(validator.iter_errors(r))
        assert not errors, errors


def test_crosswalk_is_faithful() -> None:
    reports, _ = fb.collect(SAMPLE, bbox=None, utc_offset="-07:00")
    by_id = {r["occurred_at"]: r for r in reports}
    # passing -> close_pass; open door -> dooring; pedestrian -> other (honest fallback).
    assert by_id["2023-05-01T17:30:00Z"]["hazard_type"] == "close_pass"
    assert by_id["2023-06-11T08:05:00Z"]["hazard_type"] == "dooring"
    # A collision with hospitalization is "serious"; a no-injury collision is still "minor".
    assert by_id["2023-08-02T09:00:00Z"]["severity"] == "serious"
    assert by_id["2023-08-03T09:00:00Z"]["severity"] == "minor"
    # Near misses and hazards never claim a collision severity.
    assert by_id["2023-09-09T10:00:00Z"]["severity"] == "near_miss"
    # A naive timestamp gets the configured offset; tz-aware ones pass through.
    assert by_id["2023-07-01T12:00:00-07:00"]["mode"] == "cyclist"


def test_ids_are_stable_and_deterministic() -> None:
    a, _ = fb.collect(SAMPLE, bbox=None, utc_offset="-07:00")
    b, _ = fb.collect(SAMPLE, bbox=None, utc_offset="-07:00")
    assert [r["id"] for r in a] == [r["id"] for r in b]


def test_bbox_filters_out_of_range_features() -> None:
    sample = {
        "nearmiss": [
            _feature(-123.365, 48.428, {"pk": 1, "date": "2023-05-01T17:30:00Z"}),
            _feature(-100.0, 40.0, {"pk": 2, "date": "2023-05-01T17:30:00Z"}),  # far away
        ]
    }
    reports, counts = fb.collect(sample, bbox=(-123.46, 48.40, -123.28, 48.50), utc_offset="-07:00")
    assert counts["nearmiss"] == 1
    assert reports[0]["location"]["lon"] == -123.365
