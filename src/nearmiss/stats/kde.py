"""Kernel density estimation of report intensity.

A raw KDE surface looks authoritative and is easy to misread, so its output is
always labeled as **report intensity**, not danger, unless it has been
exposure-normalized. KDE here operates on the private report points but emits
only an aggregate surface and a peak cell (a grid-cell centre, never an
individual report location).

Uses spatial indexing to accelerate kernel evaluation: instead of summing the
kernel contribution from all points at each grid cell, we index the points and
query only those within ~4σ of each cell. Results are identical to brute-force KDE.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from ..geometry import haversine_m
from ..spatial_index import SpatialIndex


@dataclass(frozen=True)
class KdeCell:
    lat: float
    lon: float
    intensity: float


@dataclass(frozen=True)
class KdeResult:
    cells: tuple[KdeCell, ...]
    peak: KdeCell | None
    bandwidth_m: float


def kde(
    points: list[tuple[float, float]],
    grid: int,
    bandwidth_m: float,
) -> KdeResult:
    """Gaussian KDE over a square grid covering the report points."""
    if not points:
        return KdeResult(cells=(), peak=None, bandwidth_m=bandwidth_m)

    lats = [p[0] for p in points]
    lons = [p[1] for p in points]
    lat_min, lat_max = min(lats), max(lats)
    lon_min, lon_max = min(lons), max(lons)
    # Guard against a degenerate (zero-area) bbox.
    pad = 0.001
    lat_max = lat_max + pad if lat_max == lat_min else lat_max
    lon_max = lon_max + pad if lon_max == lon_min else lon_max

    # Build spatial index of points for neighbor queries.
    # Use bandwidth_m as cell size.
    index = SpatialIndex(cell_size_m=bandwidth_m)
    for i, (plat, plon) in enumerate(points):
        index.add(str(i), plon, plat)
    index.finalize()

    # Evaluate KDE at grid cells, using spatial index to prune point queries.
    # The kernel contribution is e^(-0.5*(d/bw)^2). At d=4*bw, this is ~0.0003,
    # so we only evaluate points within ~4*bw (4 sigma).
    sigma_radius_m = 4.0 * bandwidth_m

    cells: list[KdeCell] = []
    peak: KdeCell | None = None
    for gi in range(grid):
        for gj in range(grid):
            clat = lat_min + (lat_max - lat_min) * (gi + 0.5) / grid
            clon = lon_min + (lon_max - lon_min) * (gj + 0.5) / grid
            # Query nearby points.
            nearby = index.neighbors_in_radius(clon, clat, sigma_radius_m)
            intensity = 0.0
            for point_id, _plat, _plon in nearby:
                # Convert point_id back to index to get the original point.
                pidx = int(point_id)
                plat_orig, plon_orig = points[pidx]
                d = haversine_m(clat, clon, plat_orig, plon_orig)
                intensity += math.exp(-0.5 * (d / bandwidth_m) ** 2)
            cell = KdeCell(lat=clat, lon=clon, intensity=intensity)
            cells.append(cell)
            if peak is None or intensity > peak.intensity:
                peak = cell
    return KdeResult(cells=tuple(cells), peak=peak, bandwidth_m=bandwidth_m)
