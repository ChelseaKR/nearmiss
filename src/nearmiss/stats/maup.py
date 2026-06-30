"""MAUP rank-stability sensitivity (RR-05).

The unit of analysis is a street segment (a block between intersections), and
blocks are an arbitrary areal unit — the **modifiable areal unit problem**
(MAUP): a hotspot drawn at one granularity can dissolve at another. The
[limitations](../../docs/LIMITATIONS.md) page names this as the skeptic's
strongest live attack and an "honest place to push." This module answers it with
a reproducible artifact instead of only a caveat: it **re-segments the network**
to a coarser partition, recomputes the exposure-normalized rate ranking and the
Getis-Ord Gi* significance on the coarser units, and reports whether the top
hotspot **survives**.

The re-segmentation is a deterministic greedy nearest-neighbour pairing: process
segments in a fixed order (by id) and pair each not-yet-assigned segment with its
nearest not-yet-assigned neighbour by centroid distance (ties broken by id),
producing coarser units that are each a pair of adjacent blocks (with at most one
leftover singleton). This changes both MAUP axes at once — the **scale** (units
roughly halve in number and double in size) and the **zoning** (block boundaries
move) — so a hotspot that is merely an artifact of where the lines were drawn
should not survive it.

Reference: Openshaw (1984); *The modifiable areal unit problem in traffic
safety* (J. Traffic & Transportation Engineering, 2016).
"""

from __future__ import annotations

from dataclasses import dataclass

from ..config import Config
from ..exposure import attach_exposure, is_usable
from ..geometry import haversine_m, polyline_centroid
from ..models import Exposure, Segment, SegmentStats
from .getis_ord import benjamini_hochberg, getis_ord_star, two_sided_p


@dataclass(frozen=True)
class RankStability:
    """The MAUP rank-stability result for one re-segmentation."""

    fine_units: int
    coarse_units: int
    k: int
    top_hotspot_id: str | None
    top_hotspot_survives: bool
    top_hotspot_coarse_rank: int | None
    top_hotspot_still_significant: bool
    topk_overlap: float


def _pair_segments(segments: list[Segment]) -> dict[str, int]:
    """Greedy nearest-neighbour pairing → a map of segment_id → coarse-unit index.

    Deterministic: segments are processed sorted by id, and ties in distance are
    broken by id. Each coarse unit is a pair of the nearest two unassigned
    segments (or a lone singleton at the end).
    """
    centroids = {s.id: polyline_centroid(s.coords) for s in segments}
    order = sorted(centroids)
    assigned: dict[str, int] = {}
    unit = 0
    for sid in order:
        if sid in assigned:
            continue
        ci = centroids[sid]
        best: str | None = None
        best_d = float("inf")
        for other in order:
            if other == sid or other in assigned:
                continue
            d = haversine_m(ci[0], ci[1], *centroids[other])
            if d < best_d or (d == best_d and best is not None and other < best):
                best_d = d
                best = other
        assigned[sid] = unit
        if best is not None:
            assigned[best] = unit
        unit += 1
    return assigned


def rank_stability(
    stats: list[SegmentStats],
    segments: list[Segment],
    exposure_map: dict[str, Exposure],
    config: Config,
    k: int = 5,
) -> RankStability:
    """Re-segment the network and report whether the top hotspots survive.

    Returns a :class:`RankStability`. ``top_hotspot_survives`` is True when the
    coarse unit that contains the finest-grained top-rate hotspot is itself the
    top-ranked coarse unit by rate *and* remains a significant Gi* cluster after
    the same Benjamini-Hochberg FDR control used in the primary analysis.
    """
    seg_by_id = {s.id: s for s in segments}
    coarse_of = _pair_segments(segments)

    # Fine top-k hotspots: publishable, rated, highest rate first (the brief's order).
    fine_ranked = sorted(
        (s for s in stats if s.rate is not None and s.publishable),
        key=lambda s: s.rate or 0.0,
        reverse=True,
    )
    fine_top = [s.segment_id for s in fine_ranked[:k]]
    top_hotspot_id = fine_top[0] if fine_top else None

    # Coarse aggregates: sum counts and (usable) exposure per coarse unit.
    attached = attach_exposure([s.id for s in segments], exposure_map)
    counts: dict[int, int] = {}
    exposures: dict[int, float] = {}
    lat_sum: dict[int, float] = {}
    lon_sum: dict[int, float] = {}
    members: dict[int, int] = {}
    count_by_id = {s.segment_id: s.report_count for s in stats}
    for sid, unit in coarse_of.items():
        counts[unit] = counts.get(unit, 0) + count_by_id.get(sid, 0)
        exp = attached.get(sid)
        if is_usable(exp):
            assert exp is not None
            exposures[unit] = exposures.get(unit, 0.0) + exp.estimate
        cy, cx = polyline_centroid(seg_by_id[sid].coords)
        lat_sum[unit] = lat_sum.get(unit, 0.0) + cy
        lon_sum[unit] = lon_sum.get(unit, 0.0) + cx
        members[unit] = members.get(unit, 0) + 1

    coarse_rate: dict[str, float] = {
        str(unit): counts[unit] / exposures[unit] * config.rate_per
        for unit in exposures
        if exposures[unit] > 0
    }
    coarse_centroid = {
        str(unit): (lat_sum[unit] / members[unit], lon_sum[unit] / members[unit])
        for unit in members
    }

    # Gi* + FDR on the coarse rates, mirroring the primary analysis.
    z = getis_ord_star(coarse_rate, {u: coarse_centroid[u] for u in coarse_rate}, config.gi_band_m)
    rejected = benjamini_hochberg({u: two_sided_p(zi) for u, zi in z.items()}, config.fdr_alpha)
    coarse_significant = {u for u in rejected if z.get(u, 0.0) > 0.0}

    coarse_ranked = sorted(coarse_rate, key=lambda u: coarse_rate[u], reverse=True)
    coarse_top = coarse_ranked[:k]

    # Does the top hotspot's coarse unit lead the coarse ranking and stay significant?
    survives = False
    coarse_rank: int | None = None
    still_sig = False
    if top_hotspot_id is not None:
        hot_unit = str(coarse_of[top_hotspot_id])
        if hot_unit in coarse_rate:
            coarse_rank = coarse_ranked.index(hot_unit) + 1
            still_sig = hot_unit in coarse_significant
            survives = coarse_rank == 1 and still_sig

    # Top-k overlap (Jaccard) between the coarse units of the fine top-k and the
    # coarse top-k — a scalar summary of how stable the ranking is to re-segmenting.
    fine_top_units = {str(coarse_of[s]) for s in fine_top if str(coarse_of[s]) in coarse_rate}
    coarse_top_units = set(coarse_top)
    union = fine_top_units | coarse_top_units
    overlap = len(fine_top_units & coarse_top_units) / len(union) if union else 0.0

    return RankStability(
        fine_units=len(segments),
        coarse_units=len(set(coarse_of.values())),
        k=k,
        top_hotspot_id=top_hotspot_id,
        top_hotspot_survives=survives,
        top_hotspot_coarse_rank=coarse_rank,
        top_hotspot_still_significant=still_sig,
        topk_overlap=round(overlap, 4),
    )
