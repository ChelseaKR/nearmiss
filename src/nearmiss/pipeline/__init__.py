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
    deduped, removed = dedupe(reports, config)
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
        "duplicates_removed": len(removed),
        "snapped": sum(1 for r in records if r.segment_id is not None),
        "unsnapped": sum(1 for r in records if r.segment_id is None),
    }
    return records, summary
