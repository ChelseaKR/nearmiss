"""Pure-Python planar geometry for a city-scale analysis.

Coordinates are projected to local metres with an equirectangular approximation
about a reference latitude. For a single city this is accurate to well within
the precision the analysis needs, and it avoids any native geospatial
dependency, so the pipeline runs anywhere Python runs. The approximation and its
limits are documented in ``docs/METHODOLOGY.md``.
"""

from __future__ import annotations

import math

_M_PER_DEG_LAT = 110_540.0
_M_PER_DEG_LON_EQ = 111_320.0


def project(lat: float, lon: float, lat0: float, lon0: float) -> tuple[float, float]:
    """Project (lat, lon) to local metres (x east, y north) about (lat0, lon0)."""
    x = (lon - lon0) * _M_PER_DEG_LON_EQ * math.cos(math.radians(lat0))
    y = (lat - lat0) * _M_PER_DEG_LAT
    return x, y


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in metres (used for reference / sanity checks)."""
    r = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def _point_seg_dist_xy(px: float, py: float, ax: float, ay: float, bx: float, by: float) -> float:
    """Distance from point P to segment AB, all in projected metres."""
    dx, dy = bx - ax, by - ay
    if dx == 0.0 and dy == 0.0:
        return math.hypot(px - ax, py - ay)
    t = ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    cx, cy = ax + t * dx, ay + t * dy
    return math.hypot(px - cx, py - cy)


def point_to_polyline_m(
    lat: float,
    lon: float,
    coords: tuple[tuple[float, float], ...],
    lat0: float,
    lon0: float,
) -> float:
    """Minimum distance in metres from a point to a polyline (a street segment)."""
    px, py = project(lat, lon, lat0, lon0)
    best = math.inf
    for i in range(len(coords) - 1):
        ax, ay = project(coords[i][0], coords[i][1], lat0, lon0)
        bx, by = project(coords[i + 1][0], coords[i + 1][1], lat0, lon0)
        d = _point_seg_dist_xy(px, py, ax, ay, bx, by)
        if d < best:
            best = d
    return best


def projection_margin_m(radius_m: float) -> float:
    """Safety margin (metres) to pad a metric search radius built on ``project()``.

    ``project()`` scales longitude by ``cos(lat0)`` at a single reference latitude,
    not each point's own latitude, so distances between points far from ``lat0``
    are systematically over- or under-stated relative to the true great-circle
    (haversine) distance. For any real deployment (a single city, spanning at
    most a couple of degrees of latitude from its reference point) that residual
    error is well under 1%, but a fixed spatial-index search radius must still be
    padded by more than the worst case so it can never under-count true
    candidates — the earlier "raw degrees, fixed 3x3 window" bug in dedupe.py is
    exactly what under-counting looks like. 10% plus a flat floor comfortably
    covers city-scale deployments while costing only a few extra candidates.
    """
    return radius_m * 0.10 + 5.0


def polyline_centroid(coords: tuple[tuple[float, float], ...]) -> tuple[float, float]:
    """Length-weighted centroid (lat, lon) of a polyline."""
    if len(coords) == 1:
        return coords[0]
    total = 0.0
    cx = cy = 0.0
    for i in range(len(coords) - 1):
        (la, lo), (lb, lob) = coords[i], coords[i + 1]
        seg_len = haversine_m(la, lo, lb, lob)
        mx, my = (la + lb) / 2.0, (lo + lob) / 2.0
        cx += mx * seg_len
        cy += my * seg_len
        total += seg_len
    if total == 0.0:
        return coords[0]
    return cx / total, cy / total
