"""The OSM street fetcher emits a streets.geojson the pipeline can load.

A small Overpass-shaped sample of two crossing ways exercises the conversion and
the intersection split, and the result is fed straight to loaders.load_streets to
prove it is directly consumable (the real contract that matters).
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

from nearmiss.loaders import load_streets

ROOT = Path(__file__).resolve().parents[1]


def _load_tool() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "fetch_osm_streets", ROOT / "tools" / "fetch_osm_streets.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


fos = _load_tool()

# Two ways that cross at (-123.39, 48.42): a shared node = an intersection.
SAMPLE = {
    "elements": [
        {
            "type": "way",
            "id": 1,
            "tags": {"highway": "residential", "name": "Main St"},
            "geometry": [
                {"lon": -123.40, "lat": 48.42},
                {"lon": -123.39, "lat": 48.42},
                {"lon": -123.38, "lat": 48.42},
            ],
        },
        {
            "type": "way",
            "id": 2,
            "tags": {"highway": "tertiary", "name": "Cross St"},
            "geometry": [
                {"lon": -123.39, "lat": 48.41},
                {"lon": -123.39, "lat": 48.42},
                {"lon": -123.39, "lat": 48.43},
            ],
        },
    ]
}


def test_splits_each_way_at_the_shared_intersection() -> None:
    ways = fos.parse_ways(SAMPLE)
    assert len(ways) == 2
    streets = fos.build_streets(ways, split=True)
    # Each way splits into two blocks at the shared node -> four segments.
    assert len(streets["features"]) == 4
    ids = {f["properties"]["segment_id"] for f in streets["features"]}
    assert ids == {"osm-w1-1", "osm-w1-2", "osm-w2-1", "osm-w2-2"}
    names = {f["properties"]["name"] for f in streets["features"]}
    assert names == {"Main St", "Cross St"}


def test_no_split_keeps_whole_ways() -> None:
    ways = fos.parse_ways(SAMPLE)
    streets = fos.build_streets(ways, split=False)
    assert len(streets["features"]) == 2


def test_output_is_loadable_by_the_pipeline(tmp_path: Path) -> None:
    ways = fos.parse_ways(SAMPLE)
    streets = fos.build_streets(ways, split=True)
    path = tmp_path / "streets.geojson"
    path.write_text(json.dumps(streets), encoding="utf-8")
    segments = load_streets(path)
    assert len(segments) == 4
    # Coordinates round-trip as (lat, lon) pairs with >= 2 vertices.
    for seg in segments:
        assert len(seg.coords) >= 2
        assert seg.name in {"Main St", "Cross St"}


def test_unnamed_way_gets_a_fallback_name() -> None:
    sample = {
        "elements": [
            {
                "type": "way",
                "id": 9,
                "tags": {"highway": "cycleway"},
                "geometry": [{"lon": -123.4, "lat": 48.4}, {"lon": -123.39, "lat": 48.4}],
            }
        ]
    }
    streets = fos.build_streets(fos.parse_ways(sample), split=True)
    assert streets["features"][0]["properties"]["name"] == "unnamed cycleway"
