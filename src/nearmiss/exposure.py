"""Exposure: attach a denominator to every segment (hard rule #1).

Counts confound danger with traffic. Before any rate is computed, each segment
is matched to an exposure estimate — observed counts, a demand model, or an
imported exposure layer — and that estimate carries its source and date. A
segment with no *usable* exposure is marked ``exposure_unknown`` downstream,
never given a fabricated denominator.
"""

from __future__ import annotations

from .models import Exposure


def is_usable(exp: Exposure | None) -> bool:
    """An exposure is usable as a denominator only if it is present and positive."""
    return exp is not None and exp.estimate > 0


def attach_exposure(
    segment_ids: list[str], exposure_map: dict[str, Exposure]
) -> dict[str, Exposure | None]:
    """Map each segment id to its exposure, or None when none is available."""
    return {sid: exposure_map.get(sid) for sid in segment_ids}


def coverage(attached: dict[str, Exposure | None]) -> float:
    """Fraction of segments with a USABLE exposure denominator (0..1).

    Counts only exposures that actually yield a rate (present and positive), so
    the published ``exposure_coverage`` can never overstate how many segments are
    exposure-normalized — it matches the per-segment ``exposure_unknown`` gate.
    """
    if not attached:
        return 0.0
    have = sum(1 for v in attached.values() if is_usable(v))
    return have / len(attached)
