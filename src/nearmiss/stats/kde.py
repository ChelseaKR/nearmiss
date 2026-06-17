"""Kernel density estimation of report intensity.

A raw KDE surface looks authoritative and is easy to misread, so its output is
always labeled as **report intensity**, not danger, unless it has been
exposure-normalized. KDE here operates on the private report points but emits
only an aggregate surface and a peak cell (a grid-cell centre, never an
individual report location).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from ..geometry import haversine_m


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

    cells: list[KdeCell] = []
    peak: KdeCell | None = None
    for gi in range(grid):
        for gj in range(grid):
            clat = lat_min + (lat_max - lat_min) * (gi + 0.5) / grid
            clon = lon_min + (lon_max - lon_min) * (gj + 0.5) / grid
            intensity = 0.0
            for plat, plon in points:
                d = haversine_m(clat, clon, plat, plon)
                intensity += math.exp(-0.5 * (d / bandwidth_m) ** 2)
            cell = KdeCell(lat=clat, lon=clon, intensity=intensity)
            cells.append(cell)
            if peak is None or intensity > peak.intensity:
                peak = cell
    return KdeResult(cells=tuple(cells), peak=peak, bandwidth_m=bandwidth_m)
