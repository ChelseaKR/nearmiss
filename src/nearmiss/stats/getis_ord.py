"""Getis-Ord Gi* local hotspot statistic.

Gi* answers a sharper question than "where are there more reports": it finds
where high values *cluster* beyond what spatial structure alone would produce.
We run it on the exposure-normalized **rate**, not the raw count, so a cluster
is "hot because dangerous," not "hot because busy." A binary weight (including
the focal segment itself, as Gi* requires) is used; the result is a z-score
per segment.

Neighbors are decided **on the street network**, not by straight-line
distance: this function takes a precomputed neighbor map (see
``nearmiss.network.SegmentGraph.neighbors_within``) instead of centroids and a
distance band, so two segments on opposite sides of a river or freeway with no
connecting street cannot be counted as neighbors just because their centroids
happen to be close as the crow flies.

Reference: Getis & Ord (1992); Ord & Getis (1995).
"""

from __future__ import annotations

import math


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


def getis_ord_star(
    values: dict[str, float],
    neighbor_ids: dict[str, set[str]],
) -> dict[str, float]:
    """Return a Gi* z-score per segment id (positive = hot cluster).

    ``neighbor_ids[i]`` is the set of segment ids treated as segment ``i``'s
    Gi* neighborhood, built from **street-network** adjacency/distance (see
    ``nearmiss.network.SegmentGraph.neighbors_within``) rather than
    straight-line distance. It need not include ``i`` itself — this function
    adds it if missing, since Gi* always includes the focal segment in its own
    neighborhood. Ids with no usable rate (absent from ``values``) are ignored
    even if listed as a neighbor, matching how the caller restricts ``values``
    to rate-bearing segments before calling this function.
    """
    ids = list(values.keys())
    ids_set = set(ids)
    n = len(ids)
    if n < 3:
        return dict.fromkeys(ids, 0.0)

    xs = [values[s] for s in ids]
    mean = sum(xs) / n
    # Two-pass (population) variance. The one-pass E[x^2] - E[x]^2 form is
    # algebraically identical but catastrophically cancellation-prone: when the
    # values share a large common offset (e.g. all near 1e8 with tiny spread),
    # sum(x*x)/n and mean*mean are two huge, nearly equal numbers whose
    # difference loses almost all significant digits and can even go negative,
    # collapsing s to 0.0 and silently zeroing every z-score. Summing the
    # centered deviations keeps the magnitudes at the scale of the true spread,
    # so the statistic stays finite and sane. Same semantics (population
    # variance) as before, so the exact-value tests in test_stats_numerics.py
    # (z = ±sqrt(3), ±sqrt(2)) are unchanged.
    variance = sum((x - mean) ** 2 for x in xs) / n
    s = math.sqrt(variance) if variance > 0 else 0.0
    if s == 0.0:
        return dict.fromkeys(ids, 0.0)

    z: dict[str, float] = {}
    for i in ids:
        neighbors = (neighbor_ids.get(i, set()) | {i}) & ids_set
        # Binary weights (1.0 for a neighbor, 0.0 otherwise): w*w == w, so the
        # sum-of-squares term collapses to the same neighbor count.
        w_sum = float(len(neighbors))
        w2_sum = w_sum
        wx_sum = sum(values[j] for j in neighbors)
        numerator = wx_sum - mean * w_sum
        denom = s * math.sqrt(max(0.0, (n * w2_sum - w_sum * w_sum) / (n - 1)))
        z[i] = numerator / denom if denom != 0.0 else 0.0
    return z
