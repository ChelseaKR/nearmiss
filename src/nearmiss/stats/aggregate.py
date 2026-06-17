"""Aggregate clean records to per-segment counts and hazard breakdowns."""

from __future__ import annotations

from dataclasses import dataclass, field

from ..models import CleanRecord


@dataclass
class SegmentAgg:
    segment_id: str
    count: int = 0
    hazard_breakdown: dict[str, int] = field(default_factory=dict)
    quality_flags: set[str] = field(default_factory=set)


def aggregate(records: list[CleanRecord]) -> dict[str, SegmentAgg]:
    """Group snapped records by segment. Unsnapped records are excluded."""
    out: dict[str, SegmentAgg] = {}
    for r in records:
        if r.segment_id is None:
            continue
        agg = out.setdefault(r.segment_id, SegmentAgg(segment_id=r.segment_id))
        agg.count += 1
        agg.hazard_breakdown[r.hazard_type] = agg.hazard_breakdown.get(r.hazard_type, 0) + 1
        agg.quality_flags.update(r.quality_flags)
    return out
