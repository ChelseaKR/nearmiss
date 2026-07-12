"""Getis-Ord Gi* local hotspot statistic, with FDR control.

Gi* answers a sharper question than "where are there more events": it finds
where high values *cluster* beyond what spatial structure alone would produce.
Run it on the exposure-normalized **rate** (see :mod:`honest_rates.rates`),
not the raw count, so a cluster is "hot because dangerous," not "hot because
busy." A binary weight (including the focal unit itself, as Gi* requires) is
used; the result is a z-score per unit, and :func:`benjamini_hochberg`
controls the false-discovery rate across the many simultaneous per-unit tests.

The core statistic takes a **precomputed neighbor map**, so the caller decides
what "neighbor" means for its domain: nearmiss feeds it street-network
adjacency/distance (``nearmiss.network.SegmentGraph.neighbors_within``), so
two street segments on opposite sides of a river or freeway with no connecting
street are never neighbors just because their centroids are close as the crow
flies. Standalone consumers without a network graph can build a plain
straight-line distance-band neighborhood with :func:`band_neighbors` —
honestly cruder, and documented as such.

Reference: Getis & Ord (1992); Ord & Getis (1995); Benjamini & Hochberg (1995).
"""

from __future__ import annotations

import math

from .geometry import haversine_m, project, projection_margin_m
from .spatial_index import SpatialIndex


def two_sided_p(z: float) -> float:
    """Two-sided p-value of a z-score under the standard normal."""
    return math.erfc(abs(z) / math.sqrt(2.0))


def benjamini_hochberg(pvalues: dict[str, float], alpha: float) -> set[str]:
    """Benjamini-Hochberg FDR control: return the ids whose p-values are rejected.

    Controls the expected fraction of false discoveries among the rejections at
    ``alpha`` across ``len(pvalues)`` simultaneous tests.
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


def band_neighbors(
    centroids: dict[str, tuple[float, float]],
    band_m: float,
) -> dict[str, set[str]]:
    """A straight-line distance-band neighbor map for :func:`getis_ord_star`.

    Two units are neighbors when their (lat, lon) centroids lie within
    ``band_m`` metres of each other (great-circle distance). This is the
    honest fallback for consumers without a real network topology: a Euclidean
    band can treat two units separated by a river, freeway, or fence line as
    neighbors, which network-aware weights would not — say so in your methods
    note if you publish results built on it.

    A spatial index (projected to local metres about the centroid cloud's
    mean) prunes the candidate set; exact haversine distance decides
    membership, so the projection cannot change the answer.
    """
    if not centroids:
        return {}
    lat0 = sum(c[0] for c in centroids.values()) / len(centroids)
    lon0 = sum(c[1] for c in centroids.values()) / len(centroids)
    index = SpatialIndex(cell_size_m=max(band_m, 1.0))
    for unit_id, (lat, lon) in centroids.items():
        x, y = project(lat, lon, lat0, lon0)
        index.add(unit_id, x, y)
    index.finalize()
    # Margin absorbs the equirectangular projection's residual error (see
    # projection_margin_m) so the index never under-counts a true in-band
    # neighbor; the exact `d <= band_m` haversine check below still decides.
    search_radius_m = band_m + projection_margin_m(band_m)

    neighbors: dict[str, set[str]] = {}
    for i, (lat_i, lon_i) in centroids.items():
        xi, yi = project(lat_i, lon_i, lat0, lon0)
        candidates = index.neighbors_in_radius(xi, yi, search_radius_m)
        neighbors[i] = {
            cand_id
            for cand_id, _, _ in candidates
            if cand_id != i
            and haversine_m(lat_i, lon_i, centroids[cand_id][0], centroids[cand_id][1]) <= band_m
        }
    return neighbors


def getis_ord_star(
    values: dict[str, float],
    neighbor_ids: dict[str, set[str]],
) -> dict[str, float]:
    """Return a Gi* z-score per unit id (positive = hot cluster).

    ``values`` is any per-unit numeric value (typically an exposure-normalized
    rate from :func:`honest_rates.rates.rate_with_ci`), keyed by a stable
    string id. ``neighbor_ids[i]`` is the set of ids treated as unit ``i``'s
    Gi* neighborhood — from a real network topology when you have one, or from
    :func:`band_neighbors` when you don't. It need not include ``i`` itself —
    this function adds it, since Gi* always includes the focal unit in its own
    neighborhood. Ids with no usable value (absent from ``values``) are
    ignored even if listed as a neighbor.
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
    # so the statistic stays finite and sane.
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
