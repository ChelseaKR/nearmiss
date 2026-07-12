"""Aggregate clean records to per-segment counts and hazard breakdowns."""

from __future__ import annotations

from dataclasses import dataclass, field

from ..models import CleanRecord

# Raw pipeline quality flags that mark a report as low-confidence for the primary
# published rate (vague location -> low_accuracy, snap beyond tolerance -> far_snap).
# Records carrying either are counted for the all-records sensitivity rate but
# excluded from the primary rate. Defined here (not in stats/__init__) so both the
# aggregator and analyze() can share it without a circular import.
_LOW_CONFIDENCE_RAW = frozenset(("low_accuracy", "far_snap"))


@dataclass
class SegmentAgg:
    segment_id: str
    count: int = 0
    # Count of only the high-confidence records (no low_accuracy / far_snap flag);
    # this feeds the PRIMARY published rate. ``count`` remains the all-records total.
    count_primary: int = 0
    hazard_breakdown: dict[str, int] = field(default_factory=dict)
    quality_flags: set[str] = field(default_factory=set)


def aggregate(records: list[CleanRecord]) -> dict[str, SegmentAgg]:
    """Group snapped records by segment. Unsnapped records are excluded.

    ``count`` is the all-records total; ``count_primary`` counts only records
    without a low-confidence flag (``low_accuracy`` / ``far_snap``) and is the
    basis for the primary published rate.
    """
    out: dict[str, SegmentAgg] = {}
    for r in records:
        if r.segment_id is None:
            continue
        agg = out.setdefault(r.segment_id, SegmentAgg(segment_id=r.segment_id))
        agg.count += 1
        if not (set(r.quality_flags) & _LOW_CONFIDENCE_RAW):
            agg.count_primary += 1
        agg.hazard_breakdown[r.hazard_type] = agg.hazard_breakdown.get(r.hazard_type, 0) + 1
        agg.quality_flags.update(r.quality_flags)
    return out
