"""Time-of-day, day-of-week, and weather-correlation breakdowns.

This module answers "*when* are hazards reported?" without ever pretending a
count is a rate it is not. The breakdowns here are **report-volume**
distributions, not exposure-normalized rates: there is no time-of-day or
weather-conditioned exposure denominator, so a busy commute hour collecting many
reports is exactly the kind of volume-is-not-danger artifact this project exists
to refuse (hard rule #1). Every output is therefore labeled as report volume and
carries a small-sample caveat (hard rule #2), and the whole breakdown is
withheld below the k-anonymity floor (hard rule #4).

Privacy: these are **city-wide aggregates** only — never a per-segment,
per-hour cell, which could re-identify a contributor's routine. No per-report
timestamp is ever emitted; only counts within coarse buckets are.

The weather hook joins each report's date to a supplied open weather record (see
``tools/fetch_weather.py`` for the Open-Meteo fetcher) and reports how reports
distribute across wet and dry days *relative to how common those days are* — an
honest association, explicitly not a weather risk rate.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from ..config import Config
from ..errors import NearmissError
from ..models import CleanRecord

# Coarse, commute-aware parts of the day. Ordered; each maps an hour range
# [start, end] inclusive. Robust to small samples in a way 24 hourly bins are not.
_PARTS_OF_DAY: tuple[tuple[str, int, int], ...] = (
    ("overnight", 0, 5),  # 00:00–05:59
    ("am_peak", 6, 9),  # 06:00–09:59 morning commute
    ("midday", 10, 15),  # 10:00–15:59
    ("pm_peak", 16, 19),  # 16:00–19:59 evening commute
    ("evening", 20, 23),  # 20:00–23:59
)

_WEEKDAY_NAMES: tuple[str, ...] = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def _part_of_day(hour: int) -> str:
    for name, lo, hi in _PARTS_OF_DAY:
        if lo <= hour <= hi:
            return name
    return "overnight"  # pragma: no cover - hours are always 0..23


def _parse_hour_weekday(occurred_at: str) -> tuple[int, int] | None:
    """Return (hour, weekday) in the report's own local offset, or None if unparseable.

    The hour is the local wall-clock hour the contributor experienced — that is
    the meaningful "time of day", so we deliberately keep the submitted offset
    rather than converting to UTC.
    """
    try:
        dt = datetime.fromisoformat(occurred_at)
    except (ValueError, TypeError):
        return None
    return dt.hour, dt.weekday()


@dataclass(frozen=True)
class WeatherDay:
    """One day of open weather, keyed by ISO date (YYYY-MM-DD)."""

    date: str
    wet: bool
    condition: str
    precip_mm: float | None = None


@dataclass(frozen=True)
class WeatherRecord:
    """A loaded weather dataset: per-date conditions plus its provenance label."""

    source: str
    days: dict[str, WeatherDay]


def _wet_from_row(row: Mapping[str, object]) -> bool:
    """Decide wet/dry from an explicit flag or precipitation amount."""
    if "wet" in row:
        return bool(row["wet"])
    precip = row.get("precip_mm")
    try:
        return precip is not None and float(precip) > 0.0  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return False


def load_weather(path: Path) -> WeatherRecord:
    """Load an open/supplied weather dataset keyed by ISO date.

    Accepts the shape ``tools/fetch_weather.py`` emits:
    ``{"source": str, "daily": [{"date","precip_mm"|"wet","condition"}, ...]}``
    (a bare list of day rows is also accepted). A day is "wet" when an explicit
    ``wet`` flag says so, or when ``precip_mm > 0``.
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise NearmissError(f"weather file not found: {path}") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise NearmissError(f"could not read weather {path}: {exc}") from exc

    if isinstance(data, dict):
        source = str(data.get("source", "supplied weather record"))
        rows = data.get("daily", data.get("days", []))
    else:
        source = "supplied weather record"
        rows = data
    if not isinstance(rows, list):
        raise NearmissError(f"{path}: expected weather day rows or a {{'daily': [...]}} object")

    days: dict[str, WeatherDay] = {}
    try:
        for row in rows:
            date = str(row["date"])[:10]
            precip = row.get("precip_mm")
            days[date] = WeatherDay(
                date=date,
                wet=_wet_from_row(row),
                condition=str(row.get("condition", "wet" if _wet_from_row(row) else "dry")),
                precip_mm=(float(precip) if precip is not None else None),
            )
    except (KeyError, TypeError, ValueError) as exc:
        raise NearmissError(f"{path}: malformed weather row ({exc})") from exc
    return WeatherRecord(source=source, days=days)


@dataclass(frozen=True)
class WeatherCorrelation:
    """How reports distribute across wet vs dry days, vs how common those days are.

    This is an *association*, never a weather risk rate: wet days usually carry
    far fewer riders, so fewer reports on wet days can mean less cycling, not
    less danger. ``baseline_wet_share`` (the share of *days* that were wet in the
    weather record) is the honest yardstick the report share is read against.
    """

    source: str
    matched: int  # reports with a weather day on their date
    unmatched: int  # reports whose date had no weather record
    wet_reports: int
    dry_reports: int
    report_wet_share: float | None  # share of matched reports that fell on wet days
    baseline_wet_share: float | None  # share of weather-record days that were wet
    by_condition: dict[str, int] = field(default_factory=dict)

    @property
    def caveat(self) -> str:
        return (
            "Association only, not a weather risk rate: wet days typically carry far fewer "
            "riders, so a report share is read against how common wet days are "
            "(baseline_wet_share), and neither is exposure-normalized."
        )


@dataclass(frozen=True)
class TemporalBreakdown:
    """City-wide report-volume distribution over time, with small-sample caveats."""

    total_timed: int  # reports with a parseable timestamp
    unparseable: int  # reports whose timestamp could not be read
    suppressed: bool  # withheld for k-anonymity (total_timed below the floor)
    by_hour: dict[int, int] = field(default_factory=dict)
    by_weekday: dict[str, int] = field(default_factory=dict)
    by_part_of_day: dict[str, int] = field(default_factory=dict)
    peak_hour: int | None = None
    peak_part_of_day: str | None = None
    peak_weekday: str | None = None
    small_sample: bool = False  # too few to read peaks confidently
    weather: WeatherCorrelation | None = None

    @property
    def basis(self) -> str:
        return (
            "Report volume by time of day and day of week (city-wide aggregate). NOT an "
            "exposure-normalized rate: it reflects when people report, which tracks when they "
            "ride. Treat as a lead, not a risk ranking."
        )


def _correlate_weather(
    dates: list[str], weather: Mapping[str, WeatherDay]
) -> WeatherCorrelation | None:
    if not weather:
        return None
    # The source label is supplied separately by the loader/caller; default here.
    source = "supplied weather record"
    matched = wet = dry = 0
    by_condition: dict[str, int] = {}
    for d in dates:
        day = weather.get(d)
        if day is None:
            continue
        matched += 1
        by_condition[day.condition] = by_condition.get(day.condition, 0) + 1
        if day.wet:
            wet += 1
        else:
            dry += 1
    unmatched = len(dates) - matched
    report_wet_share = (wet / matched) if matched else None
    wet_days = sum(1 for day in weather.values() if day.wet)
    baseline_wet_share = (wet_days / len(weather)) if weather else None
    return WeatherCorrelation(
        source=source,
        matched=matched,
        unmatched=unmatched,
        wet_reports=wet,
        dry_reports=dry,
        report_wet_share=report_wet_share,
        baseline_wet_share=baseline_wet_share,
        by_condition=dict(sorted(by_condition.items())),
    )


def temporal_breakdown(
    records: list[CleanRecord],
    config: Config,
    weather: Mapping[str, WeatherDay] | None = None,
    weather_source: str | None = None,
) -> TemporalBreakdown:
    """Build the city-wide temporal report-volume breakdown.

    Counts every clean record with a parseable timestamp (snapped or not — this
    is a temporal, not spatial, view). Withheld entirely below the k-anonymity
    floor; peaks are reported only above the small-sample cutoff.
    """
    by_hour: dict[int, int] = {}
    by_weekday: dict[str, int] = {}
    by_part: dict[str, int] = {}
    dates: list[str] = []
    unparseable = 0

    for r in records:
        hw = _parse_hour_weekday(r.occurred_at)
        if hw is None:
            unparseable += 1
            continue
        hour, weekday = hw
        by_hour[hour] = by_hour.get(hour, 0) + 1
        wname = _WEEKDAY_NAMES[weekday]
        by_weekday[wname] = by_weekday.get(wname, 0) + 1
        part = _part_of_day(hour)
        by_part[part] = by_part.get(part, 0) + 1
        dates.append(r.occurred_at[:10])

    total = sum(by_hour.values())

    # k-anonymity: a whole city-wide breakdown below the floor is withheld.
    if total < config.min_publish_n:
        return TemporalBreakdown(total_timed=total, unparseable=unparseable, suppressed=True)

    small_sample = total < config.small_n
    peak_hour = max(by_hour, key=lambda h: by_hour[h]) if by_hour and not small_sample else None
    peak_part = max(by_part, key=lambda p: by_part[p]) if by_part and not small_sample else None
    peak_weekday = (
        max(by_weekday, key=lambda w: by_weekday[w]) if by_weekday and not small_sample else None
    )

    corr = _correlate_weather(dates, weather) if weather else None
    if corr is not None and weather_source:
        corr = WeatherCorrelation(
            source=weather_source,
            matched=corr.matched,
            unmatched=corr.unmatched,
            wet_reports=corr.wet_reports,
            dry_reports=corr.dry_reports,
            report_wet_share=corr.report_wet_share,
            baseline_wet_share=corr.baseline_wet_share,
            by_condition=corr.by_condition,
        )

    # Order parts of day canonically (commute-aware), not by insertion.
    ordered_parts = {name: by_part[name] for name, _, _ in _PARTS_OF_DAY if name in by_part}
    ordered_days = {name: by_weekday[name] for name in _WEEKDAY_NAMES if name in by_weekday}

    return TemporalBreakdown(
        total_timed=total,
        unparseable=unparseable,
        suppressed=False,
        by_hour=dict(sorted(by_hour.items())),
        by_weekday=ordered_days,
        by_part_of_day=ordered_parts,
        peak_hour=peak_hour,
        peak_part_of_day=peak_part,
        peak_weekday=peak_weekday,
        small_sample=small_sample,
        weather=corr,
    )


def to_metadata(breakdown: TemporalBreakdown) -> dict[str, object]:
    """A privacy-safe, JSON-serializable view for the published metadata sidecar.

    Contains only city-wide counts within coarse buckets — never a per-report
    timestamp and never a forbidden key.
    """
    out: dict[str, object] = {
        "basis": breakdown.basis,
        "total_reports_timed": breakdown.total_timed,
        "suppressed_low_count": breakdown.suppressed,
    }
    if breakdown.suppressed:
        return out
    out["by_part_of_day"] = dict(breakdown.by_part_of_day)
    out["by_weekday"] = dict(breakdown.by_weekday)
    out["by_hour"] = {str(h): c for h, c in breakdown.by_hour.items()}
    out["peak_part_of_day"] = breakdown.peak_part_of_day
    out["peak_weekday"] = breakdown.peak_weekday
    out["small_sample_caveat"] = breakdown.small_sample
    if breakdown.weather is not None:
        w = breakdown.weather
        out["weather"] = {
            "source": w.source,
            "matched_reports": w.matched,
            "unmatched_reports": w.unmatched,
            "wet_reports": w.wet_reports,
            "dry_reports": w.dry_reports,
            "report_wet_share": w.report_wet_share,
            "baseline_wet_share": w.baseline_wet_share,
            "by_condition": dict(w.by_condition),
            "caveat": w.caveat,
        }
    return out
