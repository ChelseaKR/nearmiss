"""Geometry sanity: projection, haversine, and point-to-polyline distance."""

from __future__ import annotations

import math

from nearmiss.geometry import haversine_m, point_to_polyline_m, polyline_centroid, project


def test_project_origin_is_zero() -> None:
    x, y = project(38.5, -121.7, 38.5, -121.7)
    assert abs(x) < 1e-9 and abs(y) < 1e-9


def test_haversine_known_distance() -> None:
    # One degree of latitude is ~111 km.
    d = haversine_m(38.0, -121.0, 39.0, -121.0)
    assert 110_000 < d < 112_000


def test_point_on_segment_is_close() -> None:
    seg = ((38.5, -121.701), (38.5, -121.699))  # short E-W line through -121.700
    d = point_to_polyline_m(38.5, -121.700, seg, 38.5, -121.700)
    assert d < 1.0


def test_point_off_segment_distance() -> None:
    seg = ((38.5, -121.701), (38.5, -121.699))
    # ~0.0009 deg north of the line ≈ ~100 m.
    d = point_to_polyline_m(38.5009, -121.700, seg, 38.5, -121.700)
    assert 80 < d < 120


def test_centroid_midpoint() -> None:
    lat, lon = polyline_centroid(((38.0, -121.0), (38.0, -121.002)))
    assert abs(lat - 38.0) < 1e-9
    assert math.isclose(lon, -121.001, abs_tol=1e-6)
