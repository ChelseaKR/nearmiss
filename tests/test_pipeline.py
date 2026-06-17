"""The pipeline recovers the known dedupe / snap / quality answers in the fixtures."""

from __future__ import annotations

from nearmiss.engine import AnalysisBundle


def test_stage_summary_matches_known_fixture(bundle: AnalysisBundle) -> None:
    assert bundle.summary == {
        "reports_in": 57,
        "duplicates_removed": 1,  # exactly the one planted duplicate
        "snapped": 55,
        "unsnapped": 1,  # exactly the one planted far-away report
    }


def test_exactly_one_unsnapped_record(bundle: AnalysisBundle) -> None:
    unsnapped = [r for r in bundle.records if r.segment_id is None]
    assert len(unsnapped) == 1
    assert "unsnapped" in unsnapped[0].quality_flags


def test_low_accuracy_report_is_flagged(bundle: AnalysisBundle) -> None:
    assert any("low_accuracy" in r.quality_flags for r in bundle.records)
