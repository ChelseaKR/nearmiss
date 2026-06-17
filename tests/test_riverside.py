"""A second city (Riverside) proves the engine generalizes by config alone."""

from __future__ import annotations

import json
from pathlib import Path

from nearmiss.config import load_config
from nearmiss.engine import build_analysis
from nearmiss.publish import build_geojson

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "riverside-demo.toml"


def test_riverside_runs_and_recovers_its_hotspot() -> None:
    bundle = build_analysis(load_config(CONFIG))
    assert bundle.summary["snapped"] == 20
    ranked = sorted(
        (s for s in bundle.result.segments if s.rate is not None and s.publishable),
        key=lambda s: s.rate or 0.0,
        reverse=True,
    )
    # rs-3 is the planted high-rate segment (low exposure, many reports).
    assert ranked[0].segment_id == "rs-3"


def _props(geojson: dict[str, object]) -> list[dict[str, object]]:
    feats = geojson["features"]
    assert isinstance(feats, list)
    out: list[dict[str, object]] = []
    for f in feats:
        assert isinstance(f, dict)
        p = f["properties"]
        assert isinstance(p, dict)
        out.append(p)
    return out


def test_riverside_publishes_with_k_anonymity() -> None:
    bundle = build_analysis(load_config(CONFIG))
    props = _props(build_geojson(bundle.result.segments, bundle.segments))
    ids = {p["segment_id"] for p in props}
    # rs-4 has n=1 -> withheld; no published segment has 0 < report_count < 3.
    assert "rs-4" not in ids
    for p in props:
        rc = p["report_count"]
        assert isinstance(rc, int)
        assert rc == 0 or rc >= 3


def test_riverside_uses_a_different_id_scheme_from_davis() -> None:
    bundle = build_analysis(load_config(CONFIG))
    ids = {s.id for s in bundle.segments}
    assert all(i.startswith("rs-") for i in ids)  # not "seg-*" — distinct city


def test_riverside_geojson_is_valid_geojson() -> None:
    gj = json.loads((ROOT / "data/published/riverside.geojson").read_text(encoding="utf-8"))
    assert gj["type"] == "FeatureCollection"
    assert gj["metadata"]["city"] == "Riverside"
