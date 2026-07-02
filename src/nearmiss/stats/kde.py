"""Kernel density estimation of report intensity.

A raw KDE surface looks authoritative and is easy to misread, so its output is
always labeled as **report intensity**, not danger, unless it has been
exposure-normalized. KDE here operates on the private report points but emits
only an aggregate surface and a peak cell (a grid-cell centre, never an
individual report location).

Uses spatial indexing to accelerate kernel evaluation: instead of summing the
kernel contribution from all points at each grid cell, we index the points and
query only those within ~4σ of each cell (beyond which the Gaussian weight is
below ~3e-4 of its peak). Results match a brute-force KDE using the same 4σ
truncation to within floating-point precision.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from ..geometry import haversine_m, project, projection_margin_m
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

    # Build spatial index of points, projected to local metres, for neighbor
    # queries. SpatialIndex.cell_size_m is a metric cell size; indexing raw
    # (lon, lat) degrees under it would be a unit mismatch (a "cell" would not
    # actually be bandwidth_m wide), so project about the mean of the points
    # first — as the rest of the pipeline does (see snap.py, dedupe.py).
    lat0 = sum(lats) / len(lats)
    lon0 = sum(lons) / len(lons)
    index = SpatialIndex(cell_size_m=max(bandwidth_m, 1.0))
    for i, (plat, plon) in enumerate(points):
        x, y = project(plat, plon, lat0, lon0)
        index.add(str(i), x, y)
    index.finalize()

    # Evaluate KDE at grid cells, using spatial index to prune point queries.
    # The kernel contribution is e^(-0.5*(d/bw)^2). At d=4*bw, this is ~0.0003,
    # so we only evaluate points within ~4*bw (4 sigma). The index query radius
    # carries a margin (see projection_margin_m) to absorb the projection's
    # residual error so it never under-counts a true within-4-sigma point; the
    # exact haversine distance and the `d <= sigma_radius_m` check below are
    # what actually decide the 4-sigma cutoff.
    sigma_radius_m = 4.0 * bandwidth_m
    search_radius_m = sigma_radius_m + projection_margin_m(sigma_radius_m)

    cells: list[KdeCell] = []
    peak: KdeCell | None = None
    for gi in range(grid):
        for gj in range(grid):
            clat = lat_min + (lat_max - lat_min) * (gi + 0.5) / grid
            clon = lon_min + (lon_max - lon_min) * (gj + 0.5) / grid
            cx, cy = project(clat, clon, lat0, lon0)
            # Query nearby points.
            nearby = index.neighbors_in_radius(cx, cy, search_radius_m)
            intensity = 0.0
            for point_id, _x, _y in nearby:
                # Convert point_id back to index to get the original point.
                pidx = int(point_id)
                plat_orig, plon_orig = points[pidx]
                d = haversine_m(clat, clon, plat_orig, plon_orig)
                if d <= sigma_radius_m:
                    intensity += math.exp(-0.5 * (d / bandwidth_m) ** 2)
            cell = KdeCell(lat=clat, lon=clon, intensity=intensity)
            cells.append(cell)
            if peak is None or intensity > peak.intensity:
                peak = cell
    return KdeResult(cells=tuple(cells), peak=peak, bandwidth_m=bandwidth_m)
