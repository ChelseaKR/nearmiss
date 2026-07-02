"""Differential tests: getis_ord_star() vs. an independent brute-force oracle.

The spatial-indexing branch (FIX-12) built the Gi* neighbor index with
``cell_size_m=max(band_m, 1000.0)`` (a metric cell size) but inserted raw
(lon, lat) *degrees* as (x, y) — a unit mismatch. For typical city-scale
inputs this happened to be self-correcting (the oversized "metre" cell size
applied to tiny degree coordinates meant every point landed in one of a
handful of cells, so the index degraded to an unaccelerated full scan rather
than an incorrect one) — but it was accidentally correct, not correctly
built, and nothing proved it stayed correct outside that lucky regime. The fix
projects centroids to local metres (as the rest of the pipeline does) before
indexing. These tests prove, at a non-trivial latitude (~34 degrees, not the
equator), that z-scores from the indexed implementation exactly match a
brute-force (no spatial index) reference over many random layouts.
"""

from __future__ import annotations

import math
import random

from nearmiss.geometry import haversine_m
from nearmiss.stats.getis_ord import getis_ord_star

LAT0, LON0 = 34.05, -118.25


def _brute_force_getis_ord(
    values: dict[str, float], centroids: dict[str, tuple[float, float]], band_m: float
) -> dict[str, float]:
    """O(n^2) oracle with no spatial index at all — a direct transcription of
    the documented Gi* formula, independent of getis_ord.py's indexing code."""
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
        w_sum = w2_sum = wx_sum = 0.0
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


def test_getis_ord_matches_brute_force_at_la_latitude() -> None:
    """Randomized differential test: 300 trials x 30 segments, scattered over a
    city-sized area at ~34 degrees latitude, with a band_m comparable to the
    segment spacing so in/out-of-band membership is genuinely contested."""
    rng = random.Random(2026)
    trials = 300
    n_segments = 30
    band_m = 300.0

    max_abs_diff = 0.0
    for t in range(trials):
        ids = [f"s{t}-{k}" for k in range(n_segments)]
        centroids = {
            i: (LAT0 + rng.uniform(-0.02, 0.02), LON0 + rng.uniform(-0.02, 0.02)) for i in ids
        }
        values = {i: rng.uniform(0.0, 20.0) for i in ids}

        actual = getis_ord_star(values, centroids, band_m)
        expected = _brute_force_getis_ord(values, centroids, band_m)

        assert actual.keys() == expected.keys()
        for i in ids:
            max_abs_diff = max(max_abs_diff, abs(actual[i] - expected[i]))

    # Both implementations decide band membership with the same exact
    # haversine `d <= band_m` check, so they should match to floating-point
    # noise, not just approximately.
    assert max_abs_diff < 1e-9, f"max |actual - expected| z-score diff was {max_abs_diff}"
