"""Differential tests: kde() vs. an independent brute-force oracle.

The spatial-indexing branch (FIX-12) built the KDE point index with
``cell_size_m=bandwidth_m`` (a metric cell size) but inserted raw (lon, lat)
*degrees* as (x, y) — the same unit mismatch as getis_ord.py. As with Gi*, for
typical city-scale inputs and bandwidths this degraded to an unaccelerated
full scan with no 4-sigma truncation at all (rather than a wrong answer), but
that was luck, not correctness by design. The fix projects points and grid
cells to local metres before indexing, and makes the documented 4-sigma
truncation an explicit, exact check rather than an implicit side effect of a
broken radius filter. These tests prove, at a non-trivial latitude (~34
degrees), that the indexed implementation's grid intensities match a
brute-force (no spatial index) reference applying the same 4-sigma cutoff.
"""

from __future__ import annotations

import math
import random

from nearmiss.geometry import haversine_m
from nearmiss.stats.kde import KdeCell, KdeResult, kde

LAT0, LON0 = 34.05, -118.25


def _brute_force_kde(points: list[tuple[float, float]], grid: int, bandwidth_m: float) -> KdeResult:
    """No-index oracle using the same documented 4-sigma truncation as kde()."""
    lats = [p[0] for p in points]
    lons = [p[1] for p in points]
    lat_min, lat_max = min(lats), max(lats)
    lon_min, lon_max = min(lons), max(lons)
    pad = 0.001
    lat_max = lat_max + pad if lat_max == lat_min else lat_max
    lon_max = lon_max + pad if lon_max == lon_min else lon_max

    sigma_radius_m = 4.0 * bandwidth_m
    cells: list[KdeCell] = []
    peak: KdeCell | None = None
    for gi in range(grid):
        for gj in range(grid):
            clat = lat_min + (lat_max - lat_min) * (gi + 0.5) / grid
            clon = lon_min + (lon_max - lon_min) * (gj + 0.5) / grid
            intensity = 0.0
            for plat, plon in points:
                d = haversine_m(clat, clon, plat, plon)
                if d <= sigma_radius_m:
                    intensity += math.exp(-0.5 * (d / bandwidth_m) ** 2)
            cell = KdeCell(lat=clat, lon=clon, intensity=intensity)
            cells.append(cell)
            if peak is None or intensity > peak.intensity:
                peak = cell
    return KdeResult(cells=tuple(cells), peak=peak, bandwidth_m=bandwidth_m)


def test_kde_matches_brute_force_at_la_latitude() -> None:
    """Randomized differential test: 40 trials x 60 points over a city-sized
    area at ~34 degrees latitude, with a bandwidth small relative to the area
    so the 4-sigma truncation actually prunes most points per cell."""
    rng = random.Random(7)
    trials = 40
    n_points = 60
    grid = 12
    bandwidth_m = 120.0

    max_rel_diff = 0.0
    for _ in range(trials):
        points = [
            (LAT0 + rng.uniform(-0.01, 0.01), LON0 + rng.uniform(-0.01, 0.01))
            for _ in range(n_points)
        ]

        actual = kde(points, grid, bandwidth_m)
        expected = _brute_force_kde(points, grid, bandwidth_m)

        assert len(actual.cells) == len(expected.cells)
        for a_cell, e_cell in zip(actual.cells, expected.cells, strict=True):
            assert a_cell.lat == e_cell.lat
            assert a_cell.lon == e_cell.lon
            denom = max(e_cell.intensity, 1e-12)
            rel_diff = abs(a_cell.intensity - e_cell.intensity) / denom
            max_rel_diff = max(max_rel_diff, rel_diff)

        assert actual.peak is not None and expected.peak is not None
        assert actual.peak.lat == expected.peak.lat
        assert actual.peak.lon == expected.peak.lon

    # Both implementations apply the same exact 4-sigma cutoff on the same
    # haversine distance, so intensities should match to floating-point
    # summation noise (order of summation can differ), not just approximately.
    assert max_rel_diff < 1e-6, f"max relative intensity diff was {max_rel_diff}"
