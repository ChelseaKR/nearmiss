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

from ..geometry import haversine_m
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


def _build_spatial_index_haversine(
    centroids: dict[str, tuple[float, float]], band_m: float
) -> SpatialIndex:
    """Build a spatial index of centroids for neighbor queries.

    For haversine distances, we use a simple heuristic: 1 degree ≈ 111 km at the
    equator. We index in (lon, lat) and use this as (x, y) for cell computation.
    """
    # Use band_m as cell_size: this gives ~0.5km cells for typical band_m (300m).
    index = SpatialIndex(cell_size_m=max(band_m, 1000.0))  # cell_size in metres
    for seg_id, (lat, lon) in centroids.items():
        index.add(seg_id, lon, lat)
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

    # Build spatial index for neighbor queries.
    index = _build_spatial_index_haversine(centroids, band_m)

    z: dict[str, float] = {}
    for i in ids:
        w_sum = 0.0
        w2_sum = 0.0
        wx_sum = 0.0
        ci = centroids[i]
        # Query neighbors within band_m using spatial index.
        candidates = index.neighbors_in_radius(ci[1], ci[0], band_m)
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
