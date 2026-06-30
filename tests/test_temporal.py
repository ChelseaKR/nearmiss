"""Time-of-day / day-of-week / weather-correlation breakdown tests.

These guard the statistical-honesty contract for the temporal feature: the
output is report VOLUME (never a rate), it is withheld below the k-anonymity
floor, peaks are only read above the small-sample cutoff, and the published
metadata view leaks no forbidden key or per-report timestamp.
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest

from nearmiss.config import Config, load_config
from nearmiss.engine import AnalysisBundle
from nearmiss.models import CleanRecord
from nearmiss.publish import _FORBIDDEN_KEYS
from nearmiss.stats.temporal import load_weather, temporal_breakdown, to_metadata

ROOT = Path(__file__).resolve().parents[1]
WEATHER_FIXTURE = ROOT / "tests" / "fixtures" / "davis" / "weather.json"


def _rec(occurred_at: str, segment_id: str | None = "seg-01") -> CleanRecord:
    return CleanRecord(
        report_id="r-" + occurred_at,
        occurred_at=occurred_at,
        segment_id=segment_id,
        hazard_type="close_pass",
        severity="near_miss",
        mode="cyclist",
        snapped_distance_m=1.0,
    )


def test_breakdown_buckets_hours_weekdays_and_parts(config: Config) -> None:
    # 2026-06-10 is a Wednesday; spread reports across parts of the day.
    records = [
        _rec("2026-06-10T02:00:00-07:00"),  # overnight
        _rec("2026-06-10T07:00:00-07:00"),  # am_peak
        _rec("2026-06-10T08:00:00-07:00"),  # am_peak
        _rec("2026-06-10T12:00:00-07:00"),  # midday
        _rec("2026-06-10T17:00:00-07:00"),  # pm_peak
        _rec("2026-06-10T22:00:00-07:00"),  # evening
    ]
    tb = temporal_breakdown(records, config)
    assert not tb.suppressed
    assert tb.total_timed == 6
    assert tb.by_part_of_day["am_peak"] == 2
    assert tb.by_weekday == {"Wed": 6}
    assert tb.by_hour[8] == 1
    # Part order is commute-aware (overnight..evening), not insertion order.
    assert list(tb.by_part_of_day) == ["overnight", "am_peak", "midday", "pm_peak", "evening"]
    assert tb.peak_part_of_day == "am_peak"
    assert tb.peak_weekday == "Wed"


def test_withheld_below_kanonymity_floor(config: Config) -> None:
    cfg = dataclasses.replace(config, min_publish_n=3)
    tb = temporal_breakdown([_rec("2026-06-10T08:00:00-07:00")], cfg)
    assert tb.suppressed is True
    assert tb.by_hour == {}
    assert tb.peak_hour is None
    # The metadata view must say it was withheld and carry no counts.
    md = to_metadata(tb)
    assert md["suppressed_low_count"] is True
    assert "by_hour" not in md


def test_small_sample_suppresses_peaks_but_not_counts(config: Config) -> None:
    cfg = dataclasses.replace(config, min_publish_n=2, small_n=5)
    records = [_rec("2026-06-10T08:00:00-07:00"), _rec("2026-06-10T09:00:00-07:00")]
    tb = temporal_breakdown(records, cfg)
    assert not tb.suppressed
    assert tb.small_sample is True
    assert tb.peak_hour is None  # too few to claim a peak
    assert tb.by_part_of_day["am_peak"] == 2  # but the counts are still shown


def test_unparseable_timestamps_are_counted_not_crashed(config: Config) -> None:
    records = [
        _rec("not-a-date"),
        _rec("2026-06-10T08:00:00-07:00"),
        _rec("2026-06-10T09:00:00-07:00"),
        _rec("2026-06-10T10:00:00-07:00"),
    ]
    tb = temporal_breakdown(records, config)
    assert tb.unparseable == 1
    assert tb.total_timed == 3


def test_metadata_view_leaks_no_forbidden_key(config: Config) -> None:
    records = [_rec(f"2026-06-10T{h:02d}:00:00-07:00") for h in range(6)]
    tb = temporal_breakdown(records, config)
    text = json.dumps(to_metadata(tb))
    for key in _FORBIDDEN_KEYS:
        assert f'"{key}"' not in text, f"temporal metadata leaked forbidden key {key}"


def test_load_weather_fixture_and_wet_inference() -> None:
    rec = load_weather(WEATHER_FIXTURE)
    assert "2026-06-09" in rec.days
    assert rec.days["2026-06-09"].wet is True
    assert rec.days["2026-06-10"].wet is False
    assert rec.source.startswith("Synthetic")


def test_load_weather_infers_wet_from_precip(tmp_path: Path) -> None:
    p = tmp_path / "w.json"
    p.write_text(
        json.dumps([{"date": "2026-06-10", "precip_mm": 2.0}, {"date": "2026-06-11"}]),
        encoding="utf-8",
    )
    rec = load_weather(p)
    assert rec.days["2026-06-10"].wet is True
    assert rec.days["2026-06-11"].wet is False


def test_weather_correlation_reports_share_vs_baseline(config: Config) -> None:
    rec = load_weather(WEATHER_FIXTURE)
    # 4 reports on a dry day (06-10), 2 on a wet day (06-09).
    records = [_rec("2026-06-10T08:00:00-07:00") for _ in range(4)]
    records += [_rec("2026-06-09T08:00:00-07:00") for _ in range(2)]
    tb = temporal_breakdown(records, config, rec.days, rec.source)
    w = tb.weather
    assert w is not None
    assert w.matched == 6
    assert w.wet_reports == 2
    assert w.dry_reports == 4
    assert w.report_wet_share == pytest.approx(2 / 6)
    # Fixture has 3 wet days out of 7.
    assert w.baseline_wet_share == pytest.approx(3 / 7)
    assert w.source == rec.source
    assert w.by_condition  # populated
    # Honest framing: an association, never a risk rate.
    assert "not a weather risk rate" in w.caveat


def test_engine_bundle_carries_temporal(bundle: AnalysisBundle) -> None:
    tb = bundle.result.temporal
    assert tb.total_timed > 0
    assert not tb.suppressed
    # The Davis fixture is densest at midday; weekdays are Wed/Thu.
    assert tb.peak_weekday in {"Wed", "Thu"}


def test_weather_via_config_path_demo(config: Config) -> None:
    cfg = dataclasses.replace(config, weather_path=WEATHER_FIXTURE)
    from nearmiss.engine import build_analysis

    tb = build_analysis(cfg).result.temporal
    assert tb.weather is not None
    assert tb.weather.matched > 0


def test_demo_configs_load_without_weather_by_default() -> None:
    # Weather is strictly optional: the committed demo runs with no weather wired.
    cfg = load_config(ROOT / "config" / "davis-demo.toml")
    assert cfg.weather_path is None
