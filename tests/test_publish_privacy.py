"""Publishing never leaks a precise raw report (hard rule #4)."""

from __future__ import annotations

import json

import pytest

from nearmiss.config import Config
from nearmiss.engine import AnalysisBundle, load_city
from nearmiss.errors import PrivacyError
from nearmiss.publish import (
    assert_metadata_clean,
    assert_published_clean,
    build_geojson,
    publish,
)


def _geojson(bundle: AnalysisBundle) -> dict[str, object]:
    return build_geojson(bundle.result.segments, bundle.segments)


def _features(geojson: dict[str, object]) -> list[dict[str, object]]:
    feats = geojson["features"]
    assert isinstance(feats, list)
    out: list[dict[str, object]] = []
    for f in feats:
        assert isinstance(f, dict)
        out.append(f)
    return out


def _props(feature: dict[str, object]) -> dict[str, object]:
    p = feature["properties"]
    assert isinstance(p, dict)
    return p


def test_no_forbidden_keys_in_published_features(bundle: AnalysisBundle) -> None:
    text = json.dumps(_geojson(bundle))
    for forbidden in (
        "reporter_token",
        "occurred_at",
        "accuracy_m",
        "heading_deg",
        "mode",
        "severity",
    ):
        assert f'"{forbidden}"' not in text
    assert "reporter-hot-001" not in text


def test_assert_published_clean_passes_for_real_output(
    bundle: AnalysisBundle, config: Config
) -> None:
    assert_published_clean(_geojson(bundle), load_city(config).reports, config.min_publish_n)


def test_assert_published_clean_catches_a_leak(bundle: AnalysisBundle, config: Config) -> None:
    leaky = _geojson(bundle)
    _props(_features(leaky)[0])["reporter_token"] = "reporter-hot-001"
    with pytest.raises(PrivacyError):
        assert_published_clean(leaky, load_city(config).reports, config.min_publish_n)


def test_assert_published_clean_catches_min_occupancy_violation(
    bundle: AnalysisBundle, config: Config
) -> None:
    leaky = _geojson(bundle)
    _props(_features(leaky)[0])["report_count"] = 1  # below min_publish_n
    with pytest.raises(PrivacyError):
        assert_published_clean(leaky, load_city(config).reports, config.min_publish_n)


def test_k_anonymity_no_low_count_segment_is_published(
    bundle: AnalysisBundle, config: Config
) -> None:
    for p in (_props(f) for f in _features(_geojson(bundle))):
        rc = p["report_count"]
        assert isinstance(rc, int)
        assert rc == 0 or rc >= config.min_publish_n
    # The three planted single-report segments are withheld entirely.
    published_ids = {_props(f)["segment_id"] for f in _features(_geojson(bundle))}
    assert {"seg-04", "seg-08", "seg-11"}.isdisjoint(published_ids)


def test_small_n_hazard_breakdown_is_suppressed(bundle: AnalysisBundle) -> None:
    props = {_props(f)["segment_id"]: _props(f) for f in _features(_geojson(bundle))}
    # seg-01 has n=4 (< small_n) -> breakdown suppressed; seg-06 has n=6 -> present.
    assert props["seg-01"]["hazard_breakdown"] == {}
    assert props["seg-06"]["hazard_breakdown"] != {}


def test_published_geojson_is_self_describing(config: Config, tmp_path: object) -> None:
    import dataclasses
    from pathlib import Path

    assert isinstance(tmp_path, Path)
    result = publish(dataclasses.replace(config, out_dir=tmp_path))
    gj = json.loads(result.geojson_path.read_text(encoding="utf-8"))
    meta = gj["metadata"]
    assert meta["dataset_version"] == "0.1.0"
    assert meta["schema_version"] == "1.0.0"
    assert meta["license"] == "Apache-2.0"
    # The embedded metadata must also be privacy-clean.
    assert_metadata_clean(meta, load_city(config).reports)


def test_metadata_carries_no_coordinate_and_passes_gate(
    bundle: AnalysisBundle, config: Config, tmp_path: object
) -> None:
    import dataclasses
    from pathlib import Path

    assert isinstance(tmp_path, Path)
    cfg = dataclasses.replace(config, out_dir=tmp_path)
    result = publish(cfg)
    meta = json.loads(result.metadata_path.read_text(encoding="utf-8"))
    # The report-intensity peak is a segment id, not a coordinate.
    assert isinstance(meta["report_intensity_peak_segment"], str)
    assert "kde_peak" not in meta
    # And the metadata passes its own privacy gate.
    assert_metadata_clean(meta, load_city(config).reports)
