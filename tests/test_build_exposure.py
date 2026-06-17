"""The exposure builder snaps real counts onto segments, honestly.

Counts are snapped with the same geometry the pipeline uses for reports; segments
with no nearby count get no exposure (published as 'exposure unknown') unless the
opt-in modeled fallback is requested. The output is fed to loaders.load_exposure
to prove it is directly consumable.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

from nearmiss.loaders import load_exposure, load_streets
from nearmiss.models import Segment

ROOT = Path(__file__).resolve().parents[1]


def _load_tool() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "build_exposure", ROOT / "tools" / "build_exposure.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


be = _load_tool()

STREETS = {
    "type": "FeatureCollection",
    "features": [
        {
            "type": "Feature",
            "geometry": {"type": "LineString", "coordinates": [[-123.40, 48.42], [-123.39, 48.42]]},
            "properties": {"segment_id": "A", "name": "Main St"},
        },
        {
            "type": "Feature",
            "geometry": {"type": "LineString", "coordinates": [[-123.39, 48.41], [-123.39, 48.43]]},
            "properties": {"segment_id": "B", "name": "Cross St"},
        },
        {
            "type": "Feature",
            "geometry": {"type": "LineString", "coordinates": [[-123.50, 48.50], [-123.49, 48.50]]},
            "properties": {"segment_id": "C", "name": "Far St"},
        },
    ],
}


def _segments(tmp_path: Path) -> list[Segment]:
    path = tmp_path / "streets.geojson"
    path.write_text(json.dumps(STREETS), encoding="utf-8")
    return load_streets(path)


def test_counts_snap_to_segments_and_aggregate(tmp_path: Path) -> None:
    segments = _segments(tmp_path)
    obs = [
        (48.4200, -123.395, 100.0),  # on Main St (A)
        (48.4150, -123.390, 50.0),  # on Cross St (B)
        (40.0, -100.0, 999.0),  # nowhere near -> unsnapped
    ]
    estimates, unsnapped = be.assign(segments, obs, max_snap_m=50.0, aggregate="sum")
    assert unsnapped == 1
    assert round(estimates["A"]) == 100
    assert round(estimates["B"]) == 50
    assert "C" not in estimates  # no count near Far St


def test_default_leaves_uncovered_segments_unknown(tmp_path: Path) -> None:
    segments = _segments(tmp_path)
    estimates = {"A": 100.0}
    exposure = be.build_exposure(
        segments,
        estimates,
        source="ca_at",
        date="2025-01-01",
        model_fallback=False,
        fallback_estimate=None,
    )
    ids = {r["segment_id"] for r in exposure["segments"]}
    assert ids == {"A"}  # B and C are NOT fabricated


def test_model_fallback_is_labeled_and_opt_in(tmp_path: Path) -> None:
    segments = _segments(tmp_path)
    estimates = {"A": 100.0, "B": 50.0}
    exposure = be.build_exposure(
        segments,
        estimates,
        source="ca_at",
        date="2025-01-01",
        model_fallback=True,
        fallback_estimate=None,
    )
    by_id = {r["segment_id"]: r for r in exposure["segments"]}
    assert set(by_id) == {"A", "B", "C"}
    # The fallback (median of 100, 50 = 75) is applied to C and clearly labeled.
    assert by_id["C"]["estimate"] == 75.0
    assert "modeled" in by_id["C"]["source"]
    assert by_id["A"]["source"] == "ca_at"  # real ones keep their real source


def test_output_is_loadable_by_the_pipeline(tmp_path: Path) -> None:
    segments = _segments(tmp_path)
    exposure = be.build_exposure(
        segments,
        {"A": 100.0},
        source="ca_at",
        date="2025-01-01",
        model_fallback=False,
        fallback_estimate=None,
    )
    path = tmp_path / "exposure.json"
    path.write_text(json.dumps(exposure), encoding="utf-8")
    loaded = load_exposure(path)
    assert loaded["A"].estimate == 100.0
    assert loaded["A"].source == "ca_at"


def test_reads_csv_and_geojson_counts(tmp_path: Path) -> None:
    csv_path = tmp_path / "counts.csv"
    csv_path.write_text("lat,lon,count\n48.4200,-123.395,100\n", encoding="utf-8")
    csv_obs = be.read_counts(csv_path, "count", "lat", "lon")
    assert csv_obs == [(48.42, -123.395, 100.0)]

    gj_path = tmp_path / "counts.geojson"
    gj_path.write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "geometry": {"type": "Point", "coordinates": [-123.395, 48.42]},
                        "properties": {"count": 100},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    gj_obs = be.read_counts(gj_path, "count", "lat", "lon")
    assert gj_obs == [(48.42, -123.395, 100.0)]
