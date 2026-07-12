"""Deterministic, report-independent point-to-street-segment snapping.

This module is intentionally separate from :mod:`nearmiss.pipeline.snap`.
Official outcome locations are not contributor ``Report`` objects, and routing
them through the report pipeline would invent provenance that does not exist.

The nearest segment is assigned only when it is within ``max_distance_m`` and
is separated from the runner-up by more than ``ambiguity_margin_m``.  Exact and
near ties are therefore explicit results, never lexicographic assignments.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass
from itertools import pairwise
from typing import Literal

from .geometry import point_to_polyline_m, project
from .models import Segment
from .spatial_index import SpatialIndex

PointSnapStatus = Literal["snapped", "ambiguous", "unsnapped"]
POINT_SNAP_METHOD_VERSION = "1.0.0"

# Dense index samples make long, two-vertex road segments discoverable near
# their midpoint.  A query padded by half this step contains every polyline
# whose true projected distance is within the unpadded radius.
_DENSIFY_STEP_M = 200.0
_INDEX_EPSILON_M = 1e-6

# Decision comparisons include one micrometre of deterministic tolerance for
# projection/IEEE-754 roundoff.  Context artifacts must pin this algorithm
# version rather than silently changing the tolerance.
DECISION_TOLERANCE_M = 1e-6

# These are operational guardrails, not methodological thresholds.  They
# reject accidental degree/metre mix-ups and non-finite values before a radius
# query can allocate an effectively unbounded grid neighborhood.
_MAX_DISTANCE_M = 100_000.0
_MAX_ID_LENGTH = 512
_MAX_POINTS = 100_000
_MAX_SEGMENTS = 250_000
_MAX_TOTAL_COORDINATES = 2_000_000
_MAX_PROJECTED_EDGE_M = 100_000.0
_MAX_INDEX_SAMPLES = 2_000_000


def point_snap_method_descriptor() -> dict[str, object]:
    """Return the closed method/cap contract used by snap execution.

    Returning a fresh mapping prevents callers from mutating module state.
    Every value comes from the constants used below, so a reviewed behavior or
    safety-cap change necessarily changes downstream context method hashes.
    """

    return {
        "version": POINT_SNAP_METHOD_VERSION,
        "decision_tolerance_m": DECISION_TOLERANCE_M,
        "densification_step_m": _DENSIFY_STEP_M,
        "index_epsilon_m": _INDEX_EPSILON_M,
        "index_padding_rule": "half_densification_step_plus_index_epsilon",
        "decision_radius_rule": "max_distance_plus_ambiguity_margin_plus_decision_tolerance",
        "distance_rule": "nearest_distance_lte_max_distance_plus_decision_tolerance",
        "ambiguity_rule": ("runner_up_minus_nearest_lte_ambiguity_margin_plus_decision_tolerance"),
        "caps": {
            "max_distance_m": _MAX_DISTANCE_M,
            "max_id_length": _MAX_ID_LENGTH,
            "max_points": _MAX_POINTS,
            "max_segments": _MAX_SEGMENTS,
            "max_total_coordinates": _MAX_TOTAL_COORDINATES,
            "max_projected_edge_m": _MAX_PROJECTED_EDGE_M,
            "max_index_samples": _MAX_INDEX_SAMPLES,
        },
    }


@dataclass(frozen=True)
class SnapPoint:
    """A stable public/official point identifier and WGS84 location."""

    id: str
    lat: float
    lon: float


@dataclass(frozen=True)
class PointSnapResult:
    """Sensitive, ephemeral decision result for one precise input point.

    ``segment_id`` is populated only for an unambiguous in-range match.
    The point ID, segment IDs, and distance diagnostics are row-level location
    derivatives: callers must aggregate and discard them, never publish or
    persist them as evidence.  The distances are
    exact among locally indexed candidates; both are ``None`` when no segment
    can affect the snap decision, and the runner-up is ``None`` when there is
    only one local candidate.  ``competing_segment_ids`` is populated only for
    ambiguous results and contains every segment in the configured ambiguity
    band, sorted by stable segment id.
    """

    point_id: str
    status: PointSnapStatus
    segment_id: str | None
    nearest_distance_m: float | None
    runner_up_distance_m: float | None
    competing_segment_ids: tuple[str, ...] = ()

    @property
    def distance_m(self) -> float | None:
        """Concise alias for callers that only need the nearest distance."""

        return self.nearest_distance_m


def _validate_id(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{label} must be a string")
    if not value or value != value.strip():
        raise ValueError(f"{label} must be non-empty and have no surrounding whitespace")
    if len(value) > _MAX_ID_LENGTH:
        raise ValueError(f"{label} must be at most {_MAX_ID_LENGTH} characters")
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise ValueError(f"{label} must not contain control characters")
    return value


def _validate_number(value: object, label: str, low: float, high: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{label} must be a number")
    number = float(value)
    if not math.isfinite(number) or not low <= number <= high:
        raise ValueError(f"{label} must be finite and in [{low}, {high}]")
    return number


def _validate_nonnegative_distance(value: object, label: str) -> float:
    return _validate_number(value, label, 0.0, _MAX_DISTANCE_M)


def _materialize_points(points: Iterable[SnapPoint]) -> list[SnapPoint]:
    point_list: list[SnapPoint] = []
    for point in points:
        if len(point_list) >= _MAX_POINTS:
            raise ValueError("point input exceeds its safety limit")
        point_list.append(point)
    return point_list


def _materialize_segments(segments: Iterable[Segment]) -> list[Segment]:
    segment_list: list[Segment] = []
    for segment in segments:
        if len(segment_list) >= _MAX_SEGMENTS:
            raise ValueError("segment input exceeds its safety limit")
        segment_list.append(segment)
    return segment_list


def _validate_points(points: list[SnapPoint]) -> None:
    seen_points: set[str] = set()
    for point in points:
        if not isinstance(point, SnapPoint):
            raise TypeError("points must contain SnapPoint values")
        point_id = _validate_id(point.id, "point id")
        if point_id in seen_points:
            raise ValueError(f"duplicate point id: {point_id!r}")
        seen_points.add(point_id)
        _validate_number(point.lat, f"point {point_id!r} latitude", -90.0, 90.0)
        _validate_number(point.lon, f"point {point_id!r} longitude", -180.0, 180.0)


def _validate_coordinate(coordinate: object, segment_id: str, index: int) -> None:
    if not isinstance(coordinate, tuple) or len(coordinate) != 2:
        raise TypeError(f"segment {segment_id!r} coordinate {index} must be a (lat, lon) tuple")
    _validate_number(
        coordinate[0], f"segment {segment_id!r} coordinate {index} latitude", -90.0, 90.0
    )
    _validate_number(
        coordinate[1], f"segment {segment_id!r} coordinate {index} longitude", -180.0, 180.0
    )


def _validate_segments(segments: list[Segment]) -> None:
    seen_segments: set[str] = set()
    total_coordinates = 0
    for segment in segments:
        if not isinstance(segment, Segment):
            raise TypeError("segments must contain Segment values")
        segment_id = _validate_id(segment.id, "segment id")
        if segment_id in seen_segments:
            raise ValueError(f"duplicate segment id: {segment_id!r}")
        seen_segments.add(segment_id)
        if len(segment.coords) < 2:
            raise ValueError(f"segment {segment_id!r} must have at least two coordinates")
        total_coordinates += len(segment.coords)
        if total_coordinates > _MAX_TOTAL_COORDINATES:
            raise ValueError("segment coordinates exceed their safety limit")
        for index, coordinate in enumerate(segment.coords):
            _validate_coordinate(coordinate, segment_id, index)


def _validate_inputs(
    points: Iterable[SnapPoint], segments: Iterable[Segment]
) -> tuple[list[SnapPoint], list[Segment]]:
    point_list = _materialize_points(points)
    segment_list = _materialize_segments(segments)
    _validate_points(point_list)
    _validate_segments(segment_list)

    return sorted(point_list, key=lambda point: point.id), sorted(
        segment_list, key=lambda segment: segment.id
    )


def _reference_point(
    segments: list[Segment], ref_lat: float | None, ref_lon: float | None
) -> tuple[float, float]:
    if (ref_lat is None) != (ref_lon is None):
        raise ValueError("ref_lat and ref_lon must be provided together")
    if ref_lat is not None and ref_lon is not None:
        return (
            _validate_number(ref_lat, "ref_lat", -90.0, 90.0),
            _validate_number(ref_lon, "ref_lon", -180.0, 180.0),
        )

    coordinates = [coordinate for segment in segments for coordinate in segment.coords]
    # Empty segment sets produce only ``unsnapped`` results and need no actual
    # projection.  A neutral finite reference keeps the control flow uniform.
    if not coordinates:
        return 0.0, 0.0
    return (
        math.fsum(coordinate[0] for coordinate in coordinates) / len(coordinates),
        math.fsum(coordinate[1] for coordinate in coordinates) / len(coordinates),
    )


def _densify_xy(coords_xy: list[tuple[float, float]]) -> Iterable[tuple[float, float]]:
    yield coords_xy[0]
    for (ax, ay), (bx, by) in pairwise(coords_xy):
        length = math.hypot(bx - ax, by - ay)
        if length > _MAX_PROJECTED_EDGE_M:
            raise ValueError(
                "segment edge exceeds the city-scale safety limit; dateline wrapping is unsupported"
            )
        divisions = max(1, math.ceil(length / _DENSIFY_STEP_M))
        for division in range(1, divisions + 1):
            fraction = division / divisions
            yield ax + fraction * (bx - ax), ay + fraction * (by - ay)


def _build_index(
    segments: list[Segment], lat0: float, lon0: float, decision_radius_m: float
) -> tuple[SpatialIndex, dict[str, Segment]]:
    cell_size_m = max(10.0, decision_radius_m / 2.0)
    index = SpatialIndex(cell_size_m=cell_size_m)
    by_id: dict[str, Segment] = {}
    sample_count = 0
    for segment in segments:
        by_id[segment.id] = segment
        projected = [project(lat, lon, lat0, lon0) for lat, lon in segment.coords]
        for x, y in _densify_xy(projected):
            sample_count += 1
            if sample_count > _MAX_INDEX_SAMPLES:
                raise ValueError("densified segment index exceeds its safety limit")
            index.add(segment.id, x, y)
    index.finalize()
    return index, by_id


def _distances(
    point: SnapPoint,
    segment_ids: Iterable[str],
    segments: dict[str, Segment],
    lat0: float,
    lon0: float,
) -> list[tuple[float, str]]:
    return sorted(
        (
            point_to_polyline_m(point.lat, point.lon, segments[segment_id].coords, lat0, lon0),
            segment_id,
        )
        for segment_id in segment_ids
    )


def _local_distances(
    point: SnapPoint,
    index: SpatialIndex,
    segments: dict[str, Segment],
    decision_radius_m: float,
    lat0: float,
    lon0: float,
) -> list[tuple[float, str]]:
    """Return exact distances for the bounded snap-decision neighborhood.

    The radius includes the assignment threshold, ambiguity margin, and the
    maximum distance to a dense index sample.  It therefore contains every
    segment that can affect the decision without ever degrading to a national
    full-network scan for points outside a covered city.
    """

    px, py = project(point.lat, point.lon, lat0, lon0)
    padding = _DENSIFY_STEP_M / 2.0 + _INDEX_EPSILON_M
    nearby = index.neighbors_in_radius(px, py, decision_radius_m + padding)
    candidate_ids = {segment_id for segment_id, _, _ in nearby}
    return _distances(point, candidate_ids, segments, lat0, lon0)


def snap_points_to_segments(
    points: Iterable[SnapPoint],
    segments: Iterable[Segment],
    *,
    max_distance_m: float,
    ambiguity_margin_m: float,
    ref_lat: float | None = None,
    ref_lon: float | None = None,
) -> list[PointSnapResult]:
    """Snap stable points to uniquely nearest segments, sorted by point id.

    A point is ``snapped`` only when its nearest segment is in range and its
    distance advantage over the runner-up is *greater than* the configured
    ambiguity margin.  With only one segment there is no competing geometry,
    so an in-range point is unambiguous.  Inputs and results are independent of
    iterable order.
    """

    max_distance = _validate_nonnegative_distance(max_distance_m, "max_distance_m")
    ambiguity_margin = _validate_nonnegative_distance(ambiguity_margin_m, "ambiguity_margin_m")
    point_list, segment_list = _validate_inputs(points, segments)
    lat0, lon0 = _reference_point(segment_list, ref_lat, ref_lon)

    if not segment_list:
        return [PointSnapResult(point.id, "unsnapped", None, None, None) for point in point_list]

    decision_radius = max_distance + ambiguity_margin + DECISION_TOLERANCE_M
    index, segments_by_id = _build_index(segment_list, lat0, lon0, decision_radius)
    results: list[PointSnapResult] = []

    for point in point_list:
        ranked = _local_distances(point, index, segments_by_id, decision_radius, lat0, lon0)
        if not ranked:
            results.append(PointSnapResult(point.id, "unsnapped", None, None, None))
            continue
        nearest_distance, nearest_id = ranked[0]
        runner_up_distance = ranked[1][0] if len(ranked) > 1 else None

        if nearest_distance > max_distance + DECISION_TOLERANCE_M:
            results.append(
                PointSnapResult(point.id, "unsnapped", None, nearest_distance, runner_up_distance)
            )
            continue

        competitors = tuple(
            sorted(
                segment_id
                for distance, segment_id in ranked
                if distance - nearest_distance <= ambiguity_margin + DECISION_TOLERANCE_M
            )
        )
        if len(competitors) > 1:
            results.append(
                PointSnapResult(
                    point.id,
                    "ambiguous",
                    None,
                    nearest_distance,
                    runner_up_distance,
                    competitors,
                )
            )
        else:
            results.append(
                PointSnapResult(
                    point.id, "snapped", nearest_id, nearest_distance, runner_up_distance
                )
            )

    return results


__all__ = [
    "DECISION_TOLERANCE_M",
    "POINT_SNAP_METHOD_VERSION",
    "PointSnapResult",
    "PointSnapStatus",
    "SnapPoint",
    "point_snap_method_descriptor",
    "snap_points_to_segments",
]
