"""Getis-Ord Gi* local hotspot statistic, with FDR control.

Gi* answers a sharper question than "where are there more events": it finds
where high values *cluster* beyond what spatial structure alone would produce.
Run it on the exposure-normalized **rate** (see :mod:`honest_rates.rates`),
not the raw count, so a cluster is "hot because dangerous," not "hot because
busy." A binary weight (including the focal unit itself, as Gi* requires) is
used; the result is a z-score per unit, and :func:`benjamini_hochberg`
controls the false-discovery rate across the many simultaneous per-unit tests.

**Gi\\* stops being a local statistic when a unit's neighborhood is a
singleton.** With binary weights and a neighborhood of just the focal unit,
``w_sum == w2_sum == 1``, so the denominator collapses::

    denom = s * sqrt((n*1 - 1*1) / (n - 1)) = s * sqrt((n-1)/(n-1)) = s
    z     = (x_i - mean) / s

— a plain **global** z-score of one unit against the whole value set, emitted
through the Gi\\* code path where nothing downstream can tell it apart from a
real cluster. :func:`singleton_neighborhoods` reports exactly which units this
happened to, so a caller can label or suppress them rather than publish a
global z-score wearing a local statistic's name (nearmiss issue #193).

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
import random
from collections.abc import Iterable

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


def _effective_neighbors(
    unit_id: str,
    neighbor_ids: dict[str, set[str]],
    ids_set: set[str],
) -> set[str]:
    """The neighborhood Gi* actually weights for ``unit_id``.

    Gi* always includes the focal unit in its own neighborhood, and a listed
    neighbor with no usable value (absent from ``values``) contributes nothing,
    so the *effective* neighborhood is the listed set plus the focal unit,
    intersected with the ids that have values. Both :func:`getis_ord_star` and
    :func:`singleton_neighborhoods` go through here so the two can never
    disagree about what a unit's neighborhood was.
    """
    return (neighbor_ids.get(unit_id, set()) | {unit_id}) & ids_set


def singleton_neighborhoods(
    values: dict[str, float],
    neighbor_ids: dict[str, set[str]],
) -> frozenset[str]:
    """Ids whose *effective* Gi* neighborhood is the unit alone.

    For these units the statistic :func:`getis_ord_star` returns is not a
    cluster statistic at all — the binary-weight algebra collapses it to the
    global z-score ``(x_i - mean) / s`` (see the module docstring). Treat the
    result as a degeneracy label: suppress the unit's significance, flag it, or
    both, but do not publish its z as evidence of a local cluster.

    "Effective" is the operative word, and it is why this takes ``values``
    rather than only the neighbor map. Three different situations land here:

    1. a genuine graph island, with no adjacent unit at all;
    2. a unit whose listed neighbors are all unreachable under the caller's own
       distance rule (for a street network, ``nearmiss.network`` weights an edge
       by half of each segment's length, so a segment longer than twice the band
       can never reach one — the case that dominated on real data); and
    3. a unit with real, reachable neighbors none of which has a usable value —
       structurally connected, arithmetically alone.

    Only (1) is visible in the neighbor map by itself. Deciding degeneracy on
    the raw map would miss (3) entirely.
    """
    ids_set = set(values.keys())
    return frozenset(
        unit_id
        for unit_id in ids_set
        if len(_effective_neighbors(unit_id, neighbor_ids, ids_set)) <= 1
    )


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

    A unit left with only itself gets a number back like any other, but that
    number is a **global** z-score, not a cluster statistic — call
    :func:`singleton_neighborhoods` alongside this to find out which units that
    happened to. This function does not suppress them on its own: the caller
    owns the publication decision, and silently returning ``0.0`` would be a
    different lie.
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
        neighbors = _effective_neighbors(i, neighbor_ids, ids_set)
        # Binary weights (1.0 for a neighbor, 0.0 otherwise): w*w == w, so the
        # sum-of-squares term collapses to the same neighbor count.
        w_sum = float(len(neighbors))
        w2_sum = w_sum
        wx_sum = sum(values[j] for j in neighbors)
        numerator = wx_sum - mean * w_sum
        denom = s * math.sqrt(max(0.0, (n * w2_sum - w_sum * w_sum) / (n - 1)))
        z[i] = numerator / denom if denom != 0.0 else 0.0
    return z


def conditional_permutation_p(
    values: dict[str, float],
    neighbor_ids: dict[str, set[str]],
    unit_ids: Iterable[str],
    permutations: int,
    seed: int,
) -> dict[str, float]:
    """Pseudo p-values for Gi\\* from a conditional-permutation reference.

    :func:`getis_ord_star` reads its z-score against the asymptotic normal
    reference, which is an approximation. Sparse, skewed values over small
    neighborhoods are exactly where that approximation is least comfortable, so
    this asks the same question empirically instead: hold unit ``i``'s own value
    fixed, redistribute the other values at random across the other units,
    recompute Gi\\*, and see how extreme the observed statistic is in that
    reference distribution. This is the conditional-permutation scheme standard
    for local spatial statistics (Anselin 1995).

    With binary weights only the neighborhood *sum* varies, and the value
    multiset (so the global mean and standard deviation Gi\\* divides by) is
    unchanged by permuting labels. One replicate therefore costs a draw of
    ``k - 1`` values without replacement from the other ``n - 1`` units, where
    ``k`` is the size of unit ``i``'s effective neighborhood.

    The returned value is the **two-sided pseudo p-value**
    ``(1 + #{|G*_perm| >= |G*_obs|}) / (permutations + 1)``. The ``+1`` in both
    places counts the observed arrangement as one of its own reference
    draws, which keeps the statistic valid rather than allowing an impossible
    ``p = 0`` (North, Curtis & Sham 2002).

    ``unit_ids`` selects which units to test: a caller testing only the units it
    publishes a claim about pays only for those. Units whose effective
    neighborhood is a singleton are **omitted from the result** entirely, because
    Gi\\* there is a global z-score and not a cluster statistic (see
    :func:`singleton_neighborhoods`); so are units absent from ``values``. A
    caller must therefore read a missing id as "not tested", never as "passed".

    Deterministic: the reference draws for unit ``i`` come from a generator
    seeded with ``seed`` and the unit id, so the result does not depend on
    iteration order and does not change between runs.
    """
    if permutations < 1:
        raise ValueError("permutations must be at least 1")
    ids = list(values.keys())
    ids_set = set(ids)
    n = len(ids)
    if n < 3:
        return {}
    xs = [values[s] for s in ids]
    mean = sum(xs) / n
    variance = sum((x - mean) ** 2 for x in xs) / n
    s = math.sqrt(variance) if variance > 0 else 0.0
    if s == 0.0:
        return {}

    out: dict[str, float] = {}
    for unit_id in unit_ids:
        if unit_id not in ids_set:
            continue
        neighbors = _effective_neighbors(unit_id, neighbor_ids, ids_set)
        k = len(neighbors)
        if k <= 1:
            continue
        w_sum = float(k)
        denom = s * math.sqrt(max(0.0, (n * w_sum - w_sum * w_sum) / (n - 1)))
        if denom == 0.0:
            continue
        observed = abs((sum(values[j] for j in neighbors) - mean * w_sum) / denom)
        pool = [values[j] for j in ids if j != unit_id]
        focal = values[unit_id]
        rng = random.Random(f"{seed}:{unit_id}")
        at_least_as_extreme = 0
        for _ in range(permutations):
            drawn = focal + sum(rng.sample(pool, k - 1))
            if abs((drawn - mean * w_sum) / denom) >= observed:
                at_least_as_extreme += 1
        out[unit_id] = (1 + at_least_as_extreme) / (permutations + 1)
    return out
