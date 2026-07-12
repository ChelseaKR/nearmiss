"""The pipeline recovers the known dedupe / snap / quality answers in the fixtures."""

from __future__ import annotations

import dataclasses

from nearmiss.config import Config
from nearmiss.engine import AnalysisBundle, load_city
from nearmiss.pipeline import run


def test_stage_summary_matches_known_fixture(bundle: AnalysisBundle) -> None:
    assert bundle.summary == {
        "reports_in": 59,
        "out_of_window": 0,  # the demo window spans every fixture timestamp
        "duplicates_removed": 1,  # exactly the one planted duplicate
        "snapped": 57,
        "unsnapped": 1,  # exactly the one planted far-away report
    }


def test_records_outside_window_are_dropped_and_counted(config: Config) -> None:
    # The davis fixtures all fall on 2026-06-10/11. A window that ends before them
    # drops every report and counts each removal in the summary.
    city = load_city(config)
    narrow = dataclasses.replace(config, window_start="2020-01-01", window_end="2020-12-31")
    records, summary = run(city.reports, city.segments, narrow)
    assert records == []
    assert summary["out_of_window"] == summary["reports_in"] == len(city.reports)


def test_window_keeps_only_in_range_reports(config: Config) -> None:
    # A window that admits only 2026-06-10 excludes the reports that spilled to
    # 2026-06-11; the kept + dropped counts partition every incoming report.
    city = load_city(config)
    day = dataclasses.replace(config, window_start="2026-06-10", window_end="2026-06-10")
    _, summary = run(city.reports, city.segments, day)
    kept = summary["reports_in"] - summary["out_of_window"]
    assert 0 < kept < summary["reports_in"]
    assert summary["out_of_window"] > 0


def test_no_window_configured_drops_nothing(config: Config) -> None:
    city = load_city(config)
    none_win = dataclasses.replace(config, window_start=None, window_end=None)
    _, summary = run(city.reports, city.segments, none_win)
    assert summary["out_of_window"] == 0


def test_exactly_one_unsnapped_record(bundle: AnalysisBundle) -> None:
    unsnapped = [r for r in bundle.records if r.segment_id is None]
    assert len(unsnapped) == 1
    assert "unsnapped" in unsnapped[0].quality_flags


def test_low_accuracy_report_is_flagged(bundle: AnalysisBundle) -> None:
    assert any("low_accuracy" in r.quality_flags for r in bundle.records)
