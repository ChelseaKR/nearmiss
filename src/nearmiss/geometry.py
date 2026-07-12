"""Pure-Python planar geometry for a city-scale analysis.

Coordinates are projected to local metres with an equirectangular approximation
about a reference latitude. For a single city this is accurate to well within
the precision the analysis needs, and it avoids any native geospatial
dependency, so the pipeline runs anywhere Python runs. The approximation and its
limits are documented in ``docs/METHODOLOGY.md``.

``project``, ``haversine_m``, and ``projection_margin_m`` are generic (no
street, segment, or nearmiss-specific concept in them) and now live in the
standalone `honest_rates
<https://github.com/ChelseaKR/nearmiss/tree/main/src/honest_rates>`_ library
(roadmap item EXP-08); they are re-exported here under nearmiss's historical
import path. ``point_to_polyline_m`` and ``polyline_centroid`` are
street-segment-specific (they operate on a polyline of street-segment
vertices) and stay local to nearmiss.
"""

from __future__ import annotations

import math

from honest_rates.geometry import haversine_m, project, projection_margin_m

__all__ = [
    "haversine_m",
    "point_to_polyline_m",
    "polyline_centroid",
    "project",
    "projection_margin_m",
]


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
