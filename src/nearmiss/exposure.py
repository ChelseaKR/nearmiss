"""Exposure: attach a denominator to every segment (hard rule #1).

Counts confound danger with traffic. Before any rate is computed, each segment
is matched to an exposure estimate — observed counts, a demand model, or an
imported exposure layer — and that estimate carries its source, date, and trust
tier (METHODOLOGY §3.1). A segment with no *usable* exposure is marked
``exposure_unknown`` downstream, never given a fabricated denominator.
"""

from __future__ import annotations

from .models import Exposure
from .util import parse_ts


def is_usable(exp: Exposure | None, floor: float = 0.0) -> bool:
    """An exposure is usable as a denominator only if it is present and clears the
    exposure floor (METHODOLOGY §3.3): rates blow up as exposure -> 0, so an
    estimate at or below ``floor`` is treated the same as no estimate — published
    "exposure unknown" rather than a giant, meaningless rate. ``floor`` defaults to
    0.0, preserving the original "present and positive" behavior.
    """
    return exp is not None and exp.estimate > floor


def attach_exposure(
    segment_ids: list[str], exposure_map: dict[str, Exposure]
) -> dict[str, Exposure | None]:
    """Map each segment id to its exposure, or None when none is available."""
    return {sid: exposure_map.get(sid) for sid in segment_ids}


def coverage(attached: dict[str, Exposure | None], floor: float = 0.0) -> float:
    """Fraction of segments with a USABLE exposure denominator (0..1).

    Counts only exposures that actually yield a rate (present and above the
    exposure floor), so the published ``exposure_coverage`` can never overstate how
    many segments are exposure-normalized — it matches the per-segment
    ``exposure_unknown`` gate.
    """
    if not attached:
        return 0.0
    have = sum(1 for v in attached.values() if is_usable(v, floor))
    return have / len(attached)


def corroboration(exposure_map: dict[str, Exposure]) -> dict[str, float]:
    """Per-segment agreement ratio across all readings for a segment's exposure.

    METHODOLOGY §3.1: "When two or more sources cover the same segment they can
    corroborate the denominator; a large disagreement between, say, a count
    station and the exposure layer is itself a finding and is surfaced, not
    averaged away into a false consensus." For each segment whose ``Exposure``
    carries one or more additional ``sources`` beyond its primary reading, this
    returns ``min(estimates) / max(estimates)`` over the primary plus all
    corroborating readings with a positive estimate: ``1.0`` is perfect agreement,
    values near ``0`` flag a large cross-source disagreement. Segments with a
    single reading (no ``sources``) are omitted — there is nothing to corroborate.
    """
    out: dict[str, float] = {}
    for sid, exp in exposure_map.items():
        if not exp.sources:
            continue
        estimates = [exp.estimate] + [s.estimate for s in exp.sources]
        positive = [e for e in estimates if e > 0]
        if len(positive) < 2:
            continue
        out[sid] = min(positive) / max(positive)
    return out


def is_stale(exposure_date: str, reference_date: str, threshold_days: float) -> bool:
    """True when the exposure vintage and a reference (report/analysis-window) date
    are more than ``threshold_days`` apart — a temporal-alignment caveat
    (METHODOLOGY §3.2: "a rate whose exposure was measured in a different period
    than its reports has a temporal mismatch"). Unparseable dates are treated as
    "not stale" rather than raising — staleness is a soft caveat, not a hard error.
    """
    exp_ts = parse_ts(exposure_date)
    ref_ts = parse_ts(reference_date)
    if exp_ts is None or ref_ts is None:
        return False
    return abs(exp_ts - ref_ts) > threshold_days * 86400.0
