"""Loaders turn boring input files into models, and reject malformed input cleanly.

Every malformed-input path is surfaced as a typed :class:`NearmissError` with a
clear message (no raw traceback), never as an unhandled crash — the data-integrity
boundary the loaders exist to enforce.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from nearmiss.errors import NearmissError
from nearmiss.loaders import (
    load_exposure,
    load_reports,
    load_streets,
    reports_from_dicts,
)
from nearmiss.models import Exposure, Segment


def _write(path: Path, payload: object) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


# --------------------------------------------------------------------------- #
# _read_json error surface (via the public loaders that call it)
# --------------------------------------------------------------------------- #
def test_invalid_json_is_a_clean_error(tmp_path: Path) -> None:
    p = tmp_path / "broken.json"
    p.write_text("{ this is not json", encoding="utf-8")
    with pytest.raises(NearmissError, match="invalid JSON"):
        load_reports(p)


def test_unreadable_path_is_a_clean_error(tmp_path: Path) -> None:
    # A directory is readable as a path but not as a file: read_text raises
    # IsADirectoryError (an OSError that is NOT FileNotFoundError), exercising
    # the generic-OSError branch rather than the not-found branch.
    with pytest.raises(NearmissError, match="could not read"):
        load_reports(tmp_path)


# --------------------------------------------------------------------------- #
# load_streets
# --------------------------------------------------------------------------- #
def test_load_streets_happy_path_swaps_lonlat_to_latlon(tmp_path: Path) -> None:
    fc = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                # GeoJSON positions are [lon, lat]; the model stores (lat, lon).
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[-121.74, 38.54], [-121.73, 38.55]],
                },
                "properties": {"segment_id": "seg-1"},  # no name -> falls back to id
            }
        ],
    }
    segs = load_streets(_write(tmp_path / "streets.geojson", fc))
    assert segs == [Segment(id="seg-1", name="seg-1", coords=((38.54, -121.74), (38.55, -121.73)))]


def test_load_streets_rejects_non_object_geojson(tmp_path: Path) -> None:
    with pytest.raises(NearmissError, match="expected a GeoJSON object"):
        load_streets(_write(tmp_path / "streets.geojson", [1, 2, 3]))


def test_load_streets_skips_non_linestrings_then_errors_when_empty(tmp_path: Path) -> None:
    # A Point feature is silently skipped (not a LineString); with no LineStrings
    # left, the loader refuses to return an empty street network.
    fc = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [-121.7, 38.5]},
                "properties": {"segment_id": "ignored"},
            }
        ],
    }
    with pytest.raises(NearmissError, match="no LineString segments"):
        load_streets(_write(tmp_path / "streets.geojson", fc))


# --------------------------------------------------------------------------- #
# load_exposure
# --------------------------------------------------------------------------- #
def test_load_exposure_happy_path_keyed_by_segment_id(tmp_path: Path) -> None:
    payload = {
        "segments": [
            {"segment_id": "s1", "estimate": 100.0, "source": "counts", "date": "2026-01-01"}
        ]
    }
    out = load_exposure(_write(tmp_path / "exp.json", payload))
    assert out == {"s1": Exposure("s1", 100.0, "counts", "2026-01-01")}


def test_load_exposure_accepts_a_bare_list(tmp_path: Path) -> None:
    rows = [{"segment_id": "s2", "estimate": 5, "source": "x", "date": "2026-01-02"}]
    out = load_exposure(_write(tmp_path / "exp.json", rows))
    assert set(out) == {"s2"}
    assert out["s2"].estimate == 5.0  # coerced to float


def test_load_exposure_rejects_non_list_rows(tmp_path: Path) -> None:
    with pytest.raises(NearmissError, match="expected exposure rows"):
        load_exposure(_write(tmp_path / "exp.json", {"segments": "oops"}))


def test_load_exposure_rejects_malformed_row(tmp_path: Path) -> None:
    # estimate is non-numeric -> float() raises ValueError, caught and re-raised
    # as a NearmissError naming the offending file.
    payload = {
        "segments": [{"segment_id": "s1", "estimate": "not-a-number", "source": "x", "date": "d"}]
    }
    with pytest.raises(NearmissError, match="malformed exposure row"):
        load_exposure(_write(tmp_path / "exp.json", payload))


def test_load_exposure_rejects_row_missing_required_key(tmp_path: Path) -> None:
    payload = {"segments": [{"segment_id": "s1", "estimate": 1.0, "source": "x"}]}  # no date
    with pytest.raises(NearmissError, match="malformed exposure row"):
        load_exposure(_write(tmp_path / "exp.json", payload))


# --------------------------------------------------------------------------- #
# load_reports  (raw dicts, NOT yet schema-validated)
# --------------------------------------------------------------------------- #
def test_load_reports_accepts_wrapper_and_bare_list(tmp_path: Path) -> None:
    one = {"id": "a", "mode": "cyclist"}
    wrapped = load_reports(_write(tmp_path / "w.json", {"reports": [one]}))
    bare = load_reports(_write(tmp_path / "b.json", [one]))
    assert wrapped == [one] == bare
    # Each row is a fresh dict copy, not an alias into the parsed structure.
    assert wrapped[0] is not one


def test_load_reports_rejects_non_list_rows(tmp_path: Path) -> None:
    with pytest.raises(NearmissError, match="expected a list of reports"):
        load_reports(_write(tmp_path / "r.json", {"reports": 42}))


def test_reports_from_dicts_builds_report_models() -> None:
    rows: list[dict[str, object]] = [
        {
            "id": "00000000-0000-4000-8000-000000000001",
            "occurred_at": "2026-06-10T07:20:00-07:00",
            "location": {"lat": 38.5, "lon": -121.7, "accuracy_m": 8.0},
            "mode": "cyclist",
            "hazard_type": "close_pass",
            "severity": "near_miss",
        }
    ]
    reports = reports_from_dicts(rows)
    assert len(reports) == 1
    assert reports[0].lat == 38.5
    assert reports[0].lon == -121.7
    assert reports[0].accuracy_m == 8.0
