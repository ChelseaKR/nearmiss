"""Getis-Ord Gi* local hotspot statistic.

Gi* answers a sharper question than "where are there more reports": it finds
where high values *cluster* beyond what spatial structure alone would produce.
We run it on the exposure-normalized **rate**, not the raw count, so a cluster
is "hot because dangerous," not "hot because busy." A binary distance-band
weight (including the focal segment itself, as Gi* requires) is used; the result
is a z-score per segment.

Reference: Getis & Ord (1992); Ord & Getis (1995).
"""

from __future__ import annotations

import math

from ..geometry import haversine_m


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

    z: dict[str, float] = {}
    for i in ids:
        w_sum = 0.0
        w2_sum = 0.0
        wx_sum = 0.0
        ci = centroids[i]
        for j in ids:
            cj = centroids[j]
            d = haversine_m(ci[0], ci[1], cj[0], cj[1])
            w = 1.0 if d <= band_m else 0.0
            w_sum += w
            w2_sum += w * w
            wx_sum += w * values[j]
        numerator = wx_sum - mean * w_sum
        denom = s * math.sqrt(max(0.0, (n * w2_sum - w_sum * w_sum) / (n - 1)))
        z[i] = numerator / denom if denom != 0.0 else 0.0
    return z
