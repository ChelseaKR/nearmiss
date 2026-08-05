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
    reports, counts, _terms = fb.collect(SAMPLE, bbox=None, utc_offset="-07:00")
    assert counts == {"nearmiss": 3, "collision": 2, "hazard": 1}
    validator = jsonschema.Draft202012Validator(SCHEMA)
    for r in reports:
        errors = list(validator.iter_errors(r))
        assert not errors, errors


def test_crosswalk_is_faithful() -> None:
    reports, _, _ = fb.collect(SAMPLE, bbox=None, utc_offset="-07:00")
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
    a, _, _ = fb.collect(SAMPLE, bbox=None, utc_offset="-07:00")
    b, _, _ = fb.collect(SAMPLE, bbox=None, utc_offset="-07:00")
    assert [r["id"] for r in a] == [r["id"] for r in b]


def test_bbox_filters_out_of_range_features() -> None:
    sample = {
        "nearmiss": [
            _feature(-123.365, 48.428, {"pk": 1, "date": "2023-05-01T17:30:00Z"}),
            _feature(-100.0, 40.0, {"pk": 2, "date": "2023-05-01T17:30:00Z"}),  # far away
        ]
    }
    reports, counts, _terms = fb.collect(
        sample, bbox=(-123.46, 48.40, -123.28, 48.50), utc_offset="-07:00"
    )
    assert counts["nearmiss"] == 1
    assert reports[0]["location"]["lon"] == -123.365


def test_source_terms_recover_what_the_closed_enum_discards() -> None:
    """The unmapped conflict geometry must stay recoverable beside the report.

    BikeMaps' live near-miss extract (6,222 reports, fetched 2026-08-04) falls to
    `other` for 76.6% of the corpus, and 4,768 of those name a specific geometry
    at source -- side, head on, turning right/left, angle, rear end. `hazard_type`
    is a closed enum with no member for any of them, so the crosswalk is right to
    decline; dropping the term entirely is what would cost the analysis the
    difference between a right-hook corner and a rear-end corridor.
    """
    geometry_only = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [-123.35, 48.47]},
                "properties": {
                    "pk": 90001,
                    "date": "2026-03-01T08:00:00Z",
                    "incident_with": "Vehicle, turning right",
                },
            },
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [-123.36, 48.46]},
                "properties": {
                    "pk": 90002,
                    "date": "2026-03-02T08:00:00Z",
                    "incident_with": "Vehicle, passing",
                },
            },
        ],
    }
    reports, _counts, terms = fb.collect(
        {"nearmiss": geometry_only["features"]}, bbox=None, utc_offset="+00:00"
    )
    assert len(reports) == 2
    by_id = {r["id"]: r for r in reports}

    # The right-hook report has no enum member, so it is `other` -- and the term survives.
    hook = next(r for r in reports if terms[r["id"]] == "Vehicle, turning right")
    assert hook["hazard_type"] == "other"
    assert terms[hook["id"]] == "Vehicle, turning right"

    # A report the crosswalk *can* map keeps both its enum value and its source term.
    passing = next(r for r in reports if terms[r["id"]] == "Vehicle, passing")
    assert passing["hazard_type"] == "close_pass"

    # The terms never leak into the schema-validated payload.
    validator = jsonschema.Draft202012Validator(SCHEMA)
    for report in by_id.values():
        assert "source_term" not in report
        assert "source_terms" not in report
        validator.validate(report)


def test_source_terms_are_keyed_by_report_id() -> None:
    """A sidecar nothing can join back is not a sidecar."""
    reports, _counts, terms = fb.collect(SAMPLE, bbox=None, utc_offset="-07:00")
    assert terms, "sample should yield at least one source term"
    assert set(terms) <= {r["id"] for r in reports}
