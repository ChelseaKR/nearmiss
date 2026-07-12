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
from ..network import SegmentGraph
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
    count_by_id = {s.segment_id: s.report_count for s in stats}
    for sid, unit in coarse_of.items():
        exp = attached.get(sid)
        if is_usable(exp):
            assert exp is not None
            # "Every rate has a denominator": a segment's count may enter a coarse
            # unit's numerator only when its exposure enters the denominator —
            # mirroring the primary analysis, which never rates a count that has no
            # usable exposure. Mixing an exposure-less count into a rated unit
            # would silently inflate the coarse rate.
            counts[unit] = counts.get(unit, 0) + count_by_id.get(sid, 0)
            exposures[unit] = exposures.get(unit, 0.0) + exp.estimate

    coarse_rate: dict[str, float] = {
        str(unit): counts[unit] / exposures[unit] * config.rate_per
        for unit in exposures
        if exposures[unit] > 0
    }
    # Gi* + FDR on the coarse rates, mirroring the primary analysis. Coarse
    # units are Gi* neighbors when any of their member segments are
    # STREET-NETWORK neighbors within the band (FIX-02) — never straight-line
    # centroid distance, so units across a river/freeway stay non-adjacent.
    graph = SegmentGraph.build(segments, node_snap_m=config.gi_node_snap_m)
    fine_neighbors = graph.neighbors_within(config.gi_band_m)
    coarse_neighbors: dict[str, set[str]] = {}
    for sid, unit in coarse_of.items():
        u = str(unit)
        coarse_neighbors.setdefault(u, set())
        for nb_sid in fine_neighbors.get(sid, ()):
            nb_unit = coarse_of.get(nb_sid)
            if nb_unit is not None and str(nb_unit) != u:
                coarse_neighbors[u].add(str(nb_unit))
    z = getis_ord_star(coarse_rate, coarse_neighbors)
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


def to_metadata(stability: RankStability) -> dict[str, object]:
    """A JSON-serializable view of the MAUP rank-stability artifact (RR-05).

    Only unit *counts*, a segment id, ranks, and boolean/scalar summaries — never
    a coordinate or a forbidden key — so it is safe to embed in the published
    metadata sidecar.
    """
    return {
        "basis": "greedy nearest-neighbour re-segmentation to a coarser partition",
        "fine_units": stability.fine_units,
        "coarse_units": stability.coarse_units,
        "k": stability.k,
        "top_hotspot_segment": stability.top_hotspot_id,
        "top_hotspot_survives": stability.top_hotspot_survives,
        "top_hotspot_coarse_rank": stability.top_hotspot_coarse_rank,
        "top_hotspot_still_significant": stability.top_hotspot_still_significant,
        "topk_overlap": stability.topk_overlap,
    }
