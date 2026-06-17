"""Exposure: attach a denominator to every segment (hard rule #1).

Counts confound danger with traffic. Before any rate is computed, each segment
is matched to an exposure estimate — observed counts, a demand model, or an
imported exposure layer — and that estimate carries its source and date. A
segment with no exposure is marked ``exposure_unknown`` downstream, never given
a fabricated denominator.
"""

from __future__ import annotations

from .models import Exposure


def attach_exposure(
    segment_ids: list[str], exposure_map: dict[str, Exposure]
) -> dict[str, Exposure | None]:
    """Map each segment id to its exposure, or None when none is available."""
    return {sid: exposure_map.get(sid) for sid in segment_ids}


def coverage(attached: dict[str, Exposure | None]) -> float:
    """Fraction of segments that have an exposure denominator (0..1)."""
    if not attached:
        return 0.0
    have = sum(1 for v in attached.values() if v is not None)
    return have / len(attached)
