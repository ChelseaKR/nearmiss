"""Quality flags: mark uncertainty instead of dropping data.

A report with poor location accuracy, or one that could not be snapped to a
segment, is flagged and carried forward rather than discarded — degradability
and failure transparency. Flags travel with the record so downstream stages and
consumers can see exactly why a record is uncertain.
"""

from __future__ import annotations

from ..config import Config
from ..models import Report


def quality_flags(
    report: Report, segment_id: str | None, distance_m: float | None, config: Config
) -> tuple[str, ...]:
    flags: list[str] = []
    if segment_id is None:
        flags.append("unsnapped")
    if report.accuracy_m is not None and report.accuracy_m > config.snap_max_m:
        flags.append("low_accuracy")
    if segment_id is not None and distance_m is not None and distance_m > config.snap_max_m * 0.6:
        flags.append("far_snap")
    return tuple(flags)
