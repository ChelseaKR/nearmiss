"""The pipeline: a sequence of pure, recorded transforms.

    dedupe -> geocode -> snap -> classify -> quality

Each report becomes a :class:`~nearmiss.models.CleanRecord`. The pipeline keeps
no hidden state; given the same reports and config it produces the same records
every run (determinability / reproducibility).
"""

from __future__ import annotations

from ..config import Config
from ..models import CleanRecord, Report, Segment
from .classify import classify
from .dedupe import dedupe
from .geocode import geocode
from .quality import quality_flags
from .snap import snap

__all__ = ["classify", "dedupe", "geocode", "quality_flags", "run", "snap"]


def run(
    reports: list[Report], segments: list[Segment], config: Config
) -> tuple[list[CleanRecord], dict[str, int]]:
    """Run the full pipeline; return (clean_records, stage_summary)."""
    in_window, out_of_window = _apply_window(reports, config)
    deduped, removed = dedupe(in_window, config)
    geocoded = geocode(deduped, config)
    snapped = snap(geocoded, segments, config)

    records: list[CleanRecord] = []
    for s in snapped:
        records.append(
            CleanRecord(
                report_id=s.report.id,
                occurred_at=s.report.occurred_at,
                segment_id=s.segment_id,
                hazard_type=classify(s.report),
                severity=s.report.severity,
                mode=s.report.mode,
                snapped_distance_m=(round(s.distance_m, 2) if s.distance_m is not None else None),
                quality_flags=quality_flags(s.report, s.segment_id, s.distance_m, config),
            )
        )

    summary = {
        "reports_in": len(reports),
        "out_of_window": len(out_of_window),
        "duplicates_removed": len(removed),
        "snapped": sum(1 for r in records if r.segment_id is not None),
        "unsnapped": sum(1 for r in records if r.segment_id is None),
    }
    return records, summary


def _report_date(occurred_at: str) -> str:
    """The calendar date (YYYY-MM-DD) an ISO-8601 timestamp falls on.

    The window is stated in whole dates, so compare on the date prefix. Timestamps
    are ISO-8601, so the leading 10 characters are the date; this keeps the
    comparison a pure string compare (no timezone normalization surprises) and
    matches how the window itself is stored.
    """
    return occurred_at[:10]


def _apply_window(reports: list[Report], config: Config) -> tuple[list[Report], list[Report]]:
    """Split reports into (inside, outside) the configured analysis window.

    Bounds are inclusive ISO-8601 dates; either may be unset (open-ended on that
    side). With no window configured, every report is inside and nothing is
    dropped, so pipelines without a window behave exactly as before.
    """
    if config.window_start is None and config.window_end is None:
        return reports, []
    inside: list[Report] = []
    outside: list[Report] = []
    for r in reports:
        d = _report_date(r.occurred_at)
        before = config.window_start is not None and d < config.window_start
        after = config.window_end is not None and d > config.window_end
        (outside if before or after else inside).append(r)
    return inside, outside
