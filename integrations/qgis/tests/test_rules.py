# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import json
from pathlib import Path

import pytest
from nearmiss_honest import rules

SAMPLE_DIR = Path(__file__).resolve().parent.parent / "nearmiss_honest" / "sample_data"


def _load(name: str) -> dict:
    return json.loads((SAMPLE_DIR / name).read_text(encoding="utf-8"))


@pytest.fixture(params=["davis.geojson", "riverside.geojson"])
def dataset(request):
    return _load(request.param)


# --- bundled sample data is itself invariant-clean --------------------------


def test_bundled_sample_datasets_pass_verification(dataset):
    assert rules.verify_dataset(dataset) == []


def test_davis_sample_has_both_known_and_unknown_exposure():
    # Davis is the larger demo dataset and is expected to exercise both the
    # rated and exposure-unknown rendering paths; Riverside is a smaller demo
    # that happens to have full exposure coverage for all its segments.
    rates = [f["properties"].get("rate") for f in _load("davis.geojson")["features"]]
    assert any(r is not None for r in rates), "expected at least one rated feature"
    assert any(r is None for r in rates), "expected at least one exposure-unknown feature"


# --- significance_marker -----------------------------------------------------


def test_significance_marker_hot_spot():
    props = {"getis_ord_z": 2.5, "getis_ord_significant": True}
    result = rules.significance_marker(props)
    assert result["pattern"] == rules.PATTERN_SIGNIFICANT_HOT
    assert result["significant"] is True
    assert "hot" in result["label"]


def test_significance_marker_cold_spot():
    props = {"getis_ord_z": -2.5, "getis_ord_significant": True}
    result = rules.significance_marker(props)
    assert result["pattern"] == rules.PATTERN_SIGNIFICANT_COLD
    assert "cold" in result["label"]


def test_significance_marker_not_significant():
    props = {"getis_ord_z": 0.3, "getis_ord_significant": False}
    result = rules.significance_marker(props)
    assert result["pattern"] == rules.PATTERN_NOT_SIGNIFICANT
    assert result["significant"] is False


def test_significance_marker_unknown_when_exposure_unknown():
    props = {"getis_ord_z": None, "getis_ord_significant": None}
    result = rules.significance_marker(props)
    assert result["pattern"] == rules.PATTERN_UNKNOWN
    assert result["significant"] is None
    assert "not evaluated" in result["label"]


# --- rate_class / compute_rate_breaks: unknown is never coerced to a number -


def test_rate_class_null_rate_is_always_unknown_class_regardless_of_breaks():
    props = {"rate": None}
    assert rules.rate_class(props, breaks=[1.0, 2.0, 3.0]) == rules.UNKNOWN_CLASS
    assert rules.rate_class(props, breaks=[]) == rules.UNKNOWN_CLASS


def test_rate_class_buckets_into_correct_break():
    breaks = [1.0, 2.0, 3.0]
    assert rules.rate_class({"rate": 0.5}, breaks) == "class_0"
    assert rules.rate_class({"rate": 1.0}, breaks) == "class_0"
    assert rules.rate_class({"rate": 1.5}, breaks) == "class_1"
    assert rules.rate_class({"rate": 3.5}, breaks) == "class_3"


def test_compute_rate_breaks_excludes_null_rate_features():
    features = [
        {"properties": {"rate": 1.0}},
        {"properties": {"rate": 2.0}},
        {"properties": {"rate": None}},  # exposure unknown — must not affect breaks
        {"properties": {"rate": 3.0}},
    ]
    breaks = rules.compute_rate_breaks(features, n_classes=3)
    assert breaks, "expected non-empty breaks from the 3 rated features"
    assert all(b is not None for b in breaks)


def test_compute_rate_breaks_empty_when_all_unknown():
    features = [{"properties": {"rate": None}}, {"properties": {"rate": None}}]
    assert rules.compute_rate_breaks(features) == []


# --- confidence_text: honest 'unknown' text, never a bare number ------------


def test_confidence_text_unknown_never_shows_a_number():
    props = {"rate": None, "confidence_label": "exposure_unknown"}
    text = rules.confidence_text(props)
    assert text == "rate: exposure unknown"
    assert "None" not in text


def test_confidence_text_includes_ci_and_n():
    props = {
        "rate": 2.5,
        "rate_ci_low": 1.1,
        "rate_ci_high": 4.2,
        "n": 7,
        "confidence_label": "uncertain",
    }
    text = rules.confidence_text(props)
    assert "2.5" in text
    assert "1.1" in text and "4.2" in text
    assert "n=7" in text
    assert "uncertain" in text


# --- tooltip_html: every risk-carrying field is stated as text --------------


def test_tooltip_html_states_exposure_unknown_as_text_not_zero():
    props = {
        "name": "Test St",
        "segment_id": "seg-99",
        "report_count": 3,
        "exposure_estimate": None,
        "exposure_source": None,
        "exposure_date": None,
        "rate": None,
        "confidence_label": "exposure_unknown",
        "getis_ord_z": None,
        "getis_ord_significant": None,
        "quality_flags": ["exposure_unknown"],
    }
    html = rules.tooltip_html(props)
    assert "exposure: unknown" in html
    assert "rate: exposure unknown" in html
    assert ">0<" not in html  # never silently renders unknown as a zero
    assert "not evaluated" in html


def test_tooltip_html_escapes_html_in_name():
    props = {"name": "<script>alert(1)</script>", "report_count": 0, "quality_flags": []}
    html = rules.tooltip_html(props)
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_tooltip_html_states_report_count_is_not_danger():
    props = {"name": "Foo", "report_count": 12, "quality_flags": []}
    html = rules.tooltip_html(props)
    assert "volume, not danger" in html


# --- verify_feature / verify_dataset invariants ------------------------------


def test_verify_feature_flags_rate_without_ci():
    props = {
        "segment_id": "seg-x",
        "exposure_estimate": 100,
        "rate": 1.5,
        "rate_ci_low": None,
        "rate_ci_high": None,
        "confidence_label": "certain",
        "getis_ord_z": 1.0,
        "getis_ord_significant": True,
    }
    problems = rules.verify_feature(props)
    assert any("confidence interval" in p for p in problems)


def test_verify_feature_flags_rate_present_with_null_exposure():
    props = {
        "segment_id": "seg-y",
        "exposure_estimate": None,
        "rate": 1.5,
        "rate_ci_low": 1.0,
        "rate_ci_high": 2.0,
        "confidence_label": "exposure_unknown",
        "getis_ord_z": None,
        "getis_ord_significant": None,
    }
    problems = rules.verify_feature(props)
    assert any("HR1 violation" in p for p in problems)


def test_verify_feature_flags_unrecognized_confidence_label():
    props = {
        "segment_id": "seg-z",
        "exposure_estimate": None,
        "rate": None,
        "rate_ci_low": None,
        "rate_ci_high": None,
        "confidence_label": "very_safe",
        "getis_ord_z": None,
        "getis_ord_significant": None,
    }
    problems = rules.verify_feature(props)
    assert any("closed vocabulary" in p for p in problems)


def test_verify_feature_flags_unrecognized_quality_flag():
    props = {
        "segment_id": "seg-w",
        "exposure_estimate": None,
        "rate": None,
        "rate_ci_low": None,
        "rate_ci_high": None,
        "confidence_label": "exposure_unknown",
        "getis_ord_z": None,
        "getis_ord_significant": None,
        "quality_flags": ["dangerous"],
    }
    problems = rules.verify_feature(props)
    assert any("unrecognized flag" in p for p in problems)


def test_verify_feature_clean_feature_has_no_problems():
    props = {
        "segment_id": "seg-clean",
        "exposure_estimate": 500,
        "rate": 1.2,
        "rate_ci_low": 0.5,
        "rate_ci_high": 2.5,
        "confidence_label": "certain",
        "getis_ord_z": 1.8,
        "getis_ord_significant": False,
        "quality_flags": [],
    }
    assert rules.verify_feature(props) == []


def test_verify_dataset_flags_missing_metadata():
    problems = rules.verify_dataset({"features": []})
    assert any("metadata" in p for p in problems)


def test_verify_dataset_flags_empty_features():
    metadata = {
        "schema_version": "1.0.0",
        "significance": "x",
        "privacy": "y",
        "exposure_unit": "trips",
    }
    problems = rules.verify_dataset({"metadata": metadata, "features": []})
    assert any("no features" in p for p in problems)
