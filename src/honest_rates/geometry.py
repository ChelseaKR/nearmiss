"""Pure-Python planar geometry for city-scale (or smaller) spatial statistics.

Coordinates are projected to local metres with an equirectangular approximation
about a reference latitude. Over a metro-area extent this is accurate to well
within the precision a hotspot analysis needs, and it avoids any native
geospatial dependency, so this library runs anywhere Python runs.
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


def projection_margin_m(radius_m: float) -> float:
    """Safety margin (metres) to pad a metric search radius built on ``project()``.

    ``project()`` scales longitude by ``cos(lat0)`` at a single reference latitude,
    not each point's own latitude, so distances between points far from ``lat0``
    are systematically over- or under-stated relative to the true great-circle
    (haversine) distance. For any real deployment (a single metro area, spanning
    at most a couple of degrees of latitude from its reference point) that
    residual error is well under 1%, but a fixed spatial-index search radius must
    still be padded by more than the worst case so it can never under-count true
    candidates. 10% plus a flat floor comfortably covers metro-scale extents
    while costing only a few extra candidates.
    """
    return radius_m * 0.10 + 5.0
