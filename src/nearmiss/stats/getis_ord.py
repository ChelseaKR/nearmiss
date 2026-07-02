"""Getis-Ord Gi* local hotspot statistic.

Gi* answers a sharper question than "where are there more reports": it finds
where high values *cluster* beyond what spatial structure alone would produce.
We run it on the exposure-normalized **rate**, not the raw count, so a cluster
is "hot because dangerous," not "hot because busy." A binary distance-band
weight (including the focal segment itself, as Gi* requires) is used; the result
is a z-score per segment.

Uses spatial indexing to accelerate the all-pairs distance computation: instead
of computing haversine distances for all segment pairs, we query a spatial index
to find candidates within the band, then compute exact distances only for those.
Results are identical to brute-force Gi*.

Reference: Getis & Ord (1992); Ord & Getis (1995).
"""

from __future__ import annotations

import math

from ..geometry import haversine_m, project, projection_margin_m
from ..spatial_index import SpatialIndex


def two_sided_p(z: float) -> float:
    """Two-sided p-value of a z-score under the standard normal."""
    return math.erfc(abs(z) / math.sqrt(2.0))


def benjamini_hochberg(pvalues: dict[str, float], alpha: float) -> set[str]:
    """Return the set of keys rejected by the Benjamini-Hochberg FDR procedure.

    Controls the false-discovery rate at ``alpha`` across all tested segments,
    so a "significant" hotspot is not just one of many independent z > 1.96
    coincidences. Reference: Benjamini & Hochberg (1995).
    """
    m = len(pvalues)
    if m == 0:
        return set()
    ordered = sorted(pvalues.items(), key=lambda kv: kv[1])
    threshold_rank = 0
    for rank, (_, p) in enumerate(ordered, start=1):
        if p <= (rank / m) * alpha:
            threshold_rank = rank
    return {ordered[i][0] for i in range(threshold_rank)}


def _build_spatial_index_metric(
    centroids: dict[str, tuple[float, float]], band_m: float, lat0: float, lon0: float
) -> SpatialIndex:
    """Build a spatial index of centroids, projected to local metres, for neighbor queries.

    ``SpatialIndex.cell_size_m`` is a metric cell size, so the points it indexes
    must be in metres too — indexing raw (lon, lat) degrees under a metres-valued
    cell size is a unit mismatch: the "cells" wouldn't be band_m wide in any real
    sense. Projecting about a shared reference point (as snap.py and dedupe.py
    do) keeps the index metric everywhere the pipeline runs.
    """
    index = SpatialIndex(cell_size_m=max(band_m, 1.0))
    for seg_id, (lat, lon) in centroids.items():
        x, y = project(lat, lon, lat0, lon0)
        index.add(seg_id, x, y)
    index.finalize()
    return index


def getis_ord_star(
    values: dict[str, float],
    centroids: dict[str, tuple[float, float]],
    band_m: float,
) -> dict[str, float]:
    """Return a Gi* z-score per segment id (positive = hot cluster)."""
    ids = list(values.keys())
    n = len(ids)
    if n < 3:
        return dict.fromkeys(ids, 0.0)

    xs = [values[s] for s in ids]
    mean = sum(xs) / n
    variance = sum(x * x for x in xs) / n - mean * mean
    s = math.sqrt(variance) if variance > 0 else 0.0
    if s == 0.0:
        return dict.fromkeys(ids, 0.0)

    # Build spatial index for neighbor queries, projected to local metres about
    # the mean of the centroids (an arbitrary but stable reference point — only
    # the *candidate set* it produces matters; the actual weight below is
    # decided by an exact haversine distance, so the reference choice cannot
    # change the result, only the index's effectiveness at pruning).
    lat0 = sum(c[0] for c in centroids.values()) / len(centroids)
    lon0 = sum(c[1] for c in centroids.values()) / len(centroids)
    index = _build_spatial_index_metric(centroids, band_m, lat0, lon0)
    # Margin absorbs the equirectangular projection's residual error (see
    # projection_margin_m) so the index never under-counts a true in-band
    # neighbor; the exact `d <= band_m` haversine check below is still what
    # decides membership.
    search_radius_m = band_m + projection_margin_m(band_m)

    z: dict[str, float] = {}
    for i in ids:
        w_sum = 0.0
        w2_sum = 0.0
        wx_sum = 0.0
        ci = centroids[i]
        # Query neighbors within band_m (plus margin) using the spatial index.
        cix, ciy = project(ci[0], ci[1], lat0, lon0)
        candidates = index.neighbors_in_radius(cix, ciy, search_radius_m)
        candidate_ids = {cand_id for cand_id, _, _ in candidates}
        for j in ids:
            if j in candidate_ids:
                cj = centroids[j]
                d = haversine_m(ci[0], ci[1], cj[0], cj[1])
                w = 1.0 if d <= band_m else 0.0
            else:
                w = 0.0
            w_sum += w
            w2_sum += w * w
            wx_sum += w * values[j]
        numerator = wx_sum - mean * w_sum
        denom = s * math.sqrt(max(0.0, (n * w2_sum - w_sum * w_sum) / (n - 1)))
        z[i] = numerator / denom if denom != 0.0 else 0.0
    return z
