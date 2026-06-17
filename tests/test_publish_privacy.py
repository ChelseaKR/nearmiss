"""Publishing never leaks a precise raw report (hard rule #4)."""

from __future__ import annotations

import json

import pytest

from nearmiss.config import Config
from nearmiss.engine import AnalysisBundle, load_city
from nearmiss.errors import PrivacyError
from nearmiss.publish import assert_published_clean, build_geojson


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
    for forbidden in ("reporter_token", "occurred_at", "accuracy_m", "heading_deg"):
        assert forbidden not in text
    # The planted reporter token never appears anywhere in the public artifact.
    assert "reporter-hot-001" not in text


def test_assert_published_clean_passes_for_real_output(
    bundle: AnalysisBundle, config: Config
) -> None:
    assert_published_clean(_geojson(bundle), load_city(config).reports)


def test_assert_published_clean_catches_a_leak(bundle: AnalysisBundle, config: Config) -> None:
    leaky = _geojson(bundle)
    _props(_features(leaky)[0])["reporter_token"] = "reporter-hot-001"
    with pytest.raises(PrivacyError):
        assert_published_clean(leaky, load_city(config).reports)


def test_small_n_hazard_breakdown_is_suppressed(bundle: AnalysisBundle) -> None:
    props = {_props(f)["segment_id"]: _props(f) for f in _features(_geojson(bundle))}
    # seg-01 has n=2 (< small_n) -> breakdown suppressed; seg-06 has n=6 -> present.
    assert props["seg-01"]["hazard_breakdown"] == {}
    assert props["seg-06"]["hazard_breakdown"] != {}
