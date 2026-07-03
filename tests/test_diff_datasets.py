"""diff_datasets attributes every hotspot appearance/disappearance to a cause.

Each test constructs two tiny GeoJSON + metadata vintages that isolate one
attribution class (new reports, revised exposure, a method-key change, a
threshold change via min_publish_n, and suppression), runs the tool, and asserts
the machine-readable JSON classifies the segment correctly. A final test proves
the standing reporting-decline caveat appears verbatim in the markdown and that
the tool never claims a hazard was "resolved".
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def _load_tool() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "diff_datasets", ROOT / "tools" / "diff_datasets.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


dd = _load_tool()


# --- fixtures ---------------------------------------------------------------


def _seg(
    sid: str,
    *,
    significant: bool,
    n: int = 5,
    z: float = 0.0,
    exposure: float = 1000.0,
    source: str = "synthetic_bike_count",
    date: str = "2026-01-01",
    name: str | None = None,
) -> dict[str, Any]:
    return {
        "type": "Feature",
        "geometry": {"type": "LineString", "coordinates": [[0, 0], [0, 1]]},
        "properties": {
            "segment_id": sid,
            "name": name or f"Seg {sid}",
            "getis_ord_significant": significant,
            "getis_ord_z": z,
            "n": n,
            "report_count": n,
            "exposure_estimate": exposure,
            "exposure_source": source,
            "exposure_date": date,
            "rate": round(n / exposure * 1000, 4),
        },
    }


def _geojson(segments: list[dict[str, Any]], version: str) -> dict[str, Any]:
    return {
        "type": "FeatureCollection",
        "metadata": {"city": "Test", "dataset_version": version},
        "features": segments,
    }


DEFAULT_METHODS: dict[str, Any] = {
    "confidence_z": 1.96,
    "fdr_alpha": 0.05,
    "getis_ord_band_m": 300.0,
    "kde_bandwidth_m": 150.0,
    "min_publish_n": 3,
    "rate_per": 1000.0,
    "significance": "Getis-Ord Gi* on the exposure-normalized rate, BH FDR",
    "small_n": 5,
}


def _meta(version: str, **method_overrides: Any) -> dict[str, Any]:
    methods = dict(DEFAULT_METHODS)
    methods.update(method_overrides)
    return {"dataset_version": version, "methods": methods}


def _write(tmp_path: Path, name: str, obj: dict[str, Any]) -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(obj), encoding="utf-8")
    return path


def _run(
    tmp_path: Path,
    old_geo: dict[str, Any],
    new_geo: dict[str, Any],
    old_meta: dict[str, Any] | None,
    new_meta: dict[str, Any] | None,
    slug: str = "test",
) -> dict[str, Any]:
    old_gp = _write(tmp_path, "old.geojson", old_geo)
    new_gp = _write(tmp_path, "new.geojson", new_geo)
    argv = [str(old_gp), str(new_gp), "--out-dir", str(tmp_path / "changes"), "--slug", slug]
    if old_meta is not None:
        argv += ["--old-meta", str(_write(tmp_path, "old.metadata.json", old_meta))]
    if new_meta is not None:
        argv += ["--new-meta", str(_write(tmp_path, "new.metadata.json", new_meta))]
    assert dd.main(argv) == 0
    reports = list((tmp_path / "changes").glob("*.json"))
    assert len(reports) == 1
    data: dict[str, Any] = json.loads(reports[0].read_text(encoding="utf-8"))
    return data


def _record(report: dict[str, Any], sid: str) -> dict[str, Any]:
    match = [r for r in report["changes"] if r["segment_id"] == sid]
    assert match, f"no change record for {sid}: {report['changes']}"
    rec: dict[str, Any] = match[0]
    return rec


# --- attribution classes ----------------------------------------------------


def test_new_reports(tmp_path: Path) -> None:
    """A published segment gains reports and becomes a hotspot -> new_reports."""
    old = _geojson([_seg("seg-01", significant=False, n=3, z=1.0)], "v1")
    new = _geojson([_seg("seg-01", significant=True, n=12, z=3.5)], "v2")
    report = _run(tmp_path, old, new, _meta("v1"), _meta("v2"))
    rec = _record(report, "seg-01")
    assert rec["change"] == "appeared"
    assert rec["cause"] == "new_reports"


def test_revised_exposure(tmp_path: Path) -> None:
    """Exposure changes, report count constant, hotspot flips -> revised_exposure."""
    old = _geojson([_seg("seg-02", significant=True, n=6, exposure=800.0)], "v1")
    new = _geojson([_seg("seg-02", significant=False, n=6, exposure=5000.0)], "v2")
    report = _run(tmp_path, old, new, _meta("v1"), _meta("v2"))
    rec = _record(report, "seg-02")
    assert rec["change"] == "disappeared"
    assert rec["cause"] == "revised_exposure"


def test_method_key_change(tmp_path: Path) -> None:
    """A modelling key differs -> method_change wins precedence."""
    old = _geojson([_seg("seg-03", significant=True, n=6)], "v1")
    new = _geojson([_seg("seg-03", significant=False, n=6)], "v2")
    new_meta = _meta("v2", getis_ord_band_m=500.0)
    report = _run(tmp_path, old, new, _meta("v1"), new_meta)
    rec = _record(report, "seg-03")
    assert rec["cause"] == "method_change"
    assert "getis_ord_band_m" in report["method_changes"]


def test_threshold_change_min_publish_n(tmp_path: Path) -> None:
    """min_publish_n lowered so a withheld segment appears -> threshold_change."""
    # seg-04 is withheld in v1 (absent) and published+significant in v2.
    old = _geojson([_seg("seg-99", significant=False, n=4)], "v1")
    new = _geojson(
        [_seg("seg-99", significant=False, n=4), _seg("seg-04", significant=True, n=2, z=3.0)],
        "v2",
    )
    old_meta = _meta("v1", min_publish_n=5)
    new_meta = _meta("v2", min_publish_n=1)
    report = _run(tmp_path, old, new, old_meta, new_meta)
    rec = _record(report, "seg-04")
    assert rec["change"] == "appeared"
    assert rec["cause"] == "threshold_change"


def test_suppression(tmp_path: Path) -> None:
    """A hotspot is withheld under a raised min_publish_n -> suppression."""
    old = _geojson([_seg("seg-05", significant=True, n=4, z=3.0)], "v1")
    new = _geojson([], "v2")  # seg-05 withheld -> absent
    old_meta = _meta("v1", min_publish_n=3)
    new_meta = _meta("v2", min_publish_n=5)
    report = _run(tmp_path, old, new, old_meta, new_meta)
    rec = _record(report, "seg-05")
    assert rec["change"] == "withdrawn"
    assert rec["cause"] == "suppression"


def test_recomputation(tmp_path: Path) -> None:
    """Same inputs, significance flips from a neighbourhood effect -> recomputation."""
    old = _geojson([_seg("seg-06", significant=False, n=6, z=1.5)], "v1")
    new = _geojson([_seg("seg-06", significant=True, n=6, z=2.4)], "v2")
    report = _run(tmp_path, old, new, _meta("v1"), _meta("v2"))
    rec = _record(report, "seg-06")
    assert rec["cause"] == "recomputation"


# --- degradation & summary --------------------------------------------------


def test_counts_only_without_metadata(tmp_path: Path) -> None:
    """Without sidecars, attribution degrades to counts and flags it."""
    old = _geojson([_seg("seg-07", significant=False, n=3)], "v1")
    new = _geojson([_seg("seg-07", significant=True, n=15, z=3.0)], "v2")
    report = _run(tmp_path, old, new, None, None)
    assert report["metadata_available"] is False
    rec = _record(report, "seg-07")
    assert rec["cause"] == "new_reports"


def test_persisted_not_in_changes(tmp_path: Path) -> None:
    old = _geojson([_seg("seg-08", significant=True, n=6)], "v1")
    new = _geojson([_seg("seg-08", significant=True, n=7)], "v2")
    report = _run(tmp_path, old, new, _meta("v1"), _meta("v2"))
    assert report["summary"]["persisted"] == 1
    assert report["changes"] == []


# --- wording discipline -----------------------------------------------------


def test_markdown_contains_caveat_and_never_resolved(tmp_path: Path) -> None:
    old = _geojson([_seg("seg-09", significant=True, n=6)], "v1")
    new = _geojson([_seg("seg-09", significant=False, n=6, exposure=9000.0)], "v2")
    _run(tmp_path, old, new, _meta("v1"), _meta("v2"), slug="davis")
    md = next((tmp_path / "changes").glob("*.md")).read_text(encoding="utf-8")
    assert dd.CAVEAT in md
    assert "a hazard was fixed" in md.lower()
    assert "resolved" not in md.replace(dd.CAVEAT, "").lower()


def test_deterministic_ordering(tmp_path: Path) -> None:
    old = _geojson(
        [_seg("seg-03", significant=True, n=6), _seg("seg-01", significant=True, n=6)],
        "v1",
    )
    new = _geojson(
        [
            _seg("seg-03", significant=False, n=6, exposure=9000.0),
            _seg("seg-01", significant=False, n=6, exposure=9000.0),
        ],
        "v1",
    )
    report = _run(tmp_path, old, new, _meta("v1"), _meta("v1"))
    ids = [r["segment_id"] for r in report["changes"]]
    assert ids == sorted(ids)
