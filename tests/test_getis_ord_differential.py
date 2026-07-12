"""Differential tests: getis_ord_star() vs. an independent brute-force oracle.

FIX-02 replaced the straight-line centroid distance band with a precomputed,
network-topology neighbor map (built by ``nearmiss.network.SegmentGraph`` and
tested independently in ``tests/test_network.py``). This file now isolates the
*other* half of Gi* correctness: given an arbitrary neighbor map (regardless of
how it was built), is the weighted z-score arithmetic right? So these tests
generate random neighbor structures directly — no geometry involved — and
compare ``getis_ord_star`` against a direct, independent transcription of the
documented Gi* formula.

(The previous incarnation of this file caught a real bug: the spatial-indexing
branch (FIX-12) built the old haversine-based neighbor index with a metric
cell_size_m but inserted raw (lon, lat) *degrees* as (x, y) — a unit mismatch
that only happened to be self-correcting near the equator. That geometry/
projection concern now lives entirely in ``nearmiss.network``, so its
regression coverage moved to ``tests/test_network.py``, which builds graphs at
a non-trivial ~34 degree latitude.)
"""

from __future__ import annotations

import math
import random

from nearmiss.stats.getis_ord import getis_ord_star


def _brute_force_getis_ord(
    values: dict[str, float], neighbor_ids: dict[str, set[str]]
) -> dict[str, float]:
    """Independent transcription of the documented Gi* formula.

    Builds the same binary weight matrix as ``getis_ord_star`` (a neighbor
    map, with the focal segment always included in its own neighborhood) but
    accumulates the weighted sums with an explicit double loop instead of a
    set comprehension, so a bug shared between the two implementations is
    unlikely to be identical by construction.
    """
    ids = list(values.keys())
    ids_set = set(ids)
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
        allowed = neighbor_ids.get(i, set()) | {i}
        w_sum = w2_sum = wx_sum = 0.0
        for j in ids:
            w = 1.0 if j in allowed and j in ids_set else 0.0
            w_sum += w
            w2_sum += w * w
            wx_sum += w * values[j]
        numerator = wx_sum - mean * w_sum
        denom = s * math.sqrt(max(0.0, (n * w2_sum - w_sum * w_sum) / (n - 1)))
        z[i] = numerator / denom if denom != 0.0 else 0.0
    return z


def test_getis_ord_matches_brute_force_over_random_neighbor_graphs() -> None:
    """Randomized differential test: 300 trials x 30 segments, with a random
    (not necessarily symmetric, not necessarily complete) neighbor structure
    per trial — the network graph could hand back any subset."""
    rng = random.Random(2026)
    trials = 300
    n_segments = 30

    max_abs_diff = 0.0
    for t in range(trials):
        ids = [f"s{t}-{k}" for k in range(n_segments)]
        values = {i: rng.uniform(0.0, 20.0) for i in ids}
        # Each segment gets a random handful of neighbors (possibly none,
        # possibly itself, possibly asymmetric — getis_ord_star must not
        # assume symmetry or self-inclusion; it enforces the latter itself).
        neighbor_ids = {i: set(rng.sample(ids, k=rng.randint(0, 6))) for i in ids}

        actual = getis_ord_star(values, neighbor_ids)
        expected = _brute_force_getis_ord(values, neighbor_ids)

        assert actual.keys() == expected.keys()
        for i in ids:
            max_abs_diff = max(max_abs_diff, abs(actual[i] - expected[i]))

    assert max_abs_diff < 1e-9, f"max |actual - expected| z-score diff was {max_abs_diff}"


def test_getis_ord_always_includes_the_focal_segment() -> None:
    """Even an empty neighbor set must still test the segment against itself
    (Gi* requires the focal unit in its own neighborhood)."""
    values = {"a": 10.0, "b": 1.0, "c": 1.0, "d": 1.0}
    neighbor_ids: dict[str, set[str]] = {"a": set(), "b": set(), "c": set(), "d": set()}
    z = getis_ord_star(values, neighbor_ids)
    # With no cross-segment neighbors, each segment is only compared to
    # itself: w_sum == 1 for all, so denom's (n*w2_sum - w_sum^2) term is
    # n - 1 for every segment, and z reduces to (x_i - mean) / (s * sqrt(1)).
    mean = sum(values.values()) / 4
    variance = sum(v * v for v in values.values()) / 4 - mean * mean
    s = math.sqrt(variance)
    for i, x in values.items():
        assert math.isclose(z[i], (x - mean) / s, rel_tol=1e-9)
