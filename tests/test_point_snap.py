from __future__ import annotations

import math
import random

import pytest

from nearmiss.geometry import point_to_polyline_m
from nearmiss.models import Segment
from nearmiss.point_snap import SnapPoint, snap_points_to_segments

LAT0, LON0 = 38.54, -121.74


def _vertical(segment_id: str, lon_offset: float) -> Segment:
    return Segment(
        id=segment_id,
        name=segment_id,
        coords=((LAT0 - 0.01, LON0 + lon_offset), (LAT0 + 0.01, LON0 + lon_offset)),
    )


def test_unique_nearest_returns_exact_nearest_and_runner_up_distances() -> None:
    point = SnapPoint("official-1", LAT0, LON0)
    near = _vertical("near", 0.0001)
    far = _vertical("far", 0.001)

    result = snap_points_to_segments(
        [point],
        [far, near],
        max_distance_m=25.0,
        ambiguity_margin_m=5.0,
        ref_lat=LAT0,
        ref_lon=LON0,
    )[0]

    assert result.status == "snapped"
    assert result.segment_id == "near"
    assert result.competing_segment_ids == ()
    assert result.distance_m == pytest.approx(
        point_to_polyline_m(point.lat, point.lon, near.coords, LAT0, LON0)
    )
    assert result.runner_up_distance_m == pytest.approx(
        point_to_polyline_m(point.lat, point.lon, far.coords, LAT0, LON0)
    )


def test_near_tie_is_explicit_and_never_lexicographically_assigned() -> None:
    point = SnapPoint("official-1", LAT0, LON0)
    # Symmetric geometry creates a true tie. Reverse lexical/input order to
    # prove that stable sorting is representational, not a hidden assignment.
    west = _vertical("z-west", -0.0001)
    east = _vertical("a-east", 0.0001)

    result = snap_points_to_segments(
        [point],
        [west, east],
        max_distance_m=25.0,
        ambiguity_margin_m=0.0,
        ref_lat=LAT0,
        ref_lon=LON0,
    )[0]

    assert result.status == "ambiguous"
    assert result.segment_id is None
    assert result.distance_m == pytest.approx(result.runner_up_distance_m)
    assert result.competing_segment_ids == ("a-east", "z-west")


def test_configured_uniqueness_margin_marks_a_near_but_non_equal_runner_up_ambiguous() -> None:
    point = SnapPoint("official-1", LAT0, LON0)
    nearest = _vertical("nearest", 0.00010)
    runner_up = _vertical("runner-up", 0.00013)
    third = _vertical("third", 0.00014)

    ambiguous = snap_points_to_segments(
        [point],
        [runner_up, third, nearest],
        max_distance_m=25.0,
        ambiguity_margin_m=5.0,
        ref_lat=LAT0,
        ref_lon=LON0,
    )[0]
    unique = snap_points_to_segments(
        [point],
        [runner_up, third, nearest],
        max_distance_m=25.0,
        ambiguity_margin_m=1.0,
        ref_lat=LAT0,
        ref_lon=LON0,
    )[0]

    assert ambiguous.status == "ambiguous"
    assert ambiguous.segment_id is None
    assert ambiguous.competing_segment_ids == ("nearest", "runner-up", "third")
    assert unique.status == "snapped"
    assert unique.segment_id == "nearest"


def test_unsnapped_outside_the_bounded_neighborhood_has_no_distance_diagnostics() -> None:
    point = SnapPoint("outside", LAT0, LON0)
    near = _vertical("near", 0.01)
    far = _vertical("far", 0.02)

    result = snap_points_to_segments(
        [point],
        [far, near],
        max_distance_m=25.0,
        ambiguity_margin_m=5.0,
        ref_lat=LAT0,
        ref_lon=LON0,
    )[0]

    assert result.status == "unsnapped"
    assert result.segment_id is None
    assert result.distance_m is None
    assert result.runner_up_distance_m is None


def test_empty_segment_set_is_an_explicit_unsnapped_result() -> None:
    result = snap_points_to_segments(
        [SnapPoint("p", LAT0, LON0)],
        [],
        max_distance_m=25.0,
        ambiguity_margin_m=5.0,
    )[0]

    assert result.status == "unsnapped"
    assert result.segment_id is None
    assert result.distance_m is None
    assert result.runner_up_distance_m is None


def test_long_sparse_segment_is_found_near_its_midpoint() -> None:
    point = SnapPoint("official-1", 34.00005, -118.25)
    long_segment = Segment(id="long", name="long", coords=((34.0, -118.35), (34.0, -118.15)))
    decoy = Segment(id="decoy", name="decoy", coords=((34.001, -118.2505), (34.0011, -118.2504)))

    result = snap_points_to_segments(
        [point],
        [decoy, long_segment],
        max_distance_m=25.0,
        ambiguity_margin_m=5.0,
        ref_lat=34.05,
        ref_lon=-118.25,
    )[0]

    assert result.status == "snapped"
    assert result.segment_id == "long"
    assert result.distance_m is not None and result.distance_m < 6.0


def test_far_point_never_degrades_to_a_full_network_distance_scan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import nearmiss.point_snap as point_snap

    segments = [
        Segment(
            id=f"segment-{index:04d}",
            name="far",
            coords=((LAT0, LON0 + index * 0.00001), (LAT0 + 0.0001, LON0 + index * 0.00001)),
        )
        for index in range(2_000)
    ]
    calls = 0

    def counted_distance(
        lat: float,
        lon: float,
        coords: tuple[tuple[float, float], ...],
        lat0: float,
        lon0: float,
    ) -> float:
        nonlocal calls
        calls += 1
        return point_to_polyline_m(lat, lon, coords, lat0, lon0)

    monkeypatch.setattr(point_snap, "point_to_polyline_m", counted_distance)
    result = point_snap.snap_points_to_segments(
        [point_snap.SnapPoint("outside", LAT0 + 5.0, LON0 + 5.0)],
        segments,
        max_distance_m=25.0,
        ambiguity_margin_m=5.0,
        ref_lat=LAT0,
        ref_lon=LON0,
    )[0]

    assert result.status == "unsnapped"
    assert result.distance_m is None
    assert calls == 0


def test_results_are_independent_of_point_and_segment_iterable_order() -> None:
    points = [
        SnapPoint("b", LAT0, LON0 + 0.001),
        SnapPoint("a", LAT0, LON0),
    ]
    segments = [_vertical("right", 0.001), _vertical("left", 0.0)]

    forward = snap_points_to_segments(
        points,
        segments,
        max_distance_m=25.0,
        ambiguity_margin_m=1.0,
        ref_lat=LAT0,
        ref_lon=LON0,
    )
    reversed_inputs = snap_points_to_segments(
        reversed(points),
        reversed(segments),
        max_distance_m=25.0,
        ambiguity_margin_m=1.0,
        ref_lat=LAT0,
        ref_lon=LON0,
    )

    assert forward == reversed_inputs
    assert [result.point_id for result in forward] == ["a", "b"]


@pytest.mark.parametrize(
    ("point", "max_distance_m", "ambiguity_margin_m"),
    [
        (SnapPoint("p", math.nan, LON0), 25.0, 5.0),
        (SnapPoint("p", 91.0, LON0), 25.0, 5.0),
        (SnapPoint("p", LAT0, 181.0), 25.0, 5.0),
        (SnapPoint("p", LAT0, LON0), math.inf, 5.0),
        (SnapPoint("p", LAT0, LON0), -1.0, 5.0),
        (SnapPoint("p", LAT0, LON0), 25.0, -1.0),
        (SnapPoint("p", LAT0, LON0), 100_001.0, 5.0),
    ],
)
def test_numeric_inputs_are_finite_and_bounded(
    point: SnapPoint, max_distance_m: float, ambiguity_margin_m: float
) -> None:
    with pytest.raises(ValueError):
        snap_points_to_segments(
            [point],
            [_vertical("segment", 0.0)],
            max_distance_m=max_distance_m,
            ambiguity_margin_m=ambiguity_margin_m,
        )


def test_reference_coordinates_must_be_supplied_as_a_valid_pair() -> None:
    point = SnapPoint("p", LAT0, LON0)
    segment = _vertical("segment", 0.0)

    with pytest.raises(ValueError, match="provided together"):
        snap_points_to_segments(
            [point],
            [segment],
            max_distance_m=25.0,
            ambiguity_margin_m=5.0,
            ref_lat=LAT0,
        )
    with pytest.raises(ValueError, match="ref_lat"):
        snap_points_to_segments(
            [point],
            [segment],
            max_distance_m=25.0,
            ambiguity_margin_m=5.0,
            ref_lat=math.nan,
            ref_lon=LON0,
        )


def test_duplicate_stable_ids_and_invalid_segment_geometry_are_rejected() -> None:
    with pytest.raises(ValueError, match="duplicate point id"):
        snap_points_to_segments(
            [SnapPoint("same", LAT0, LON0), SnapPoint("same", LAT0, LON0)],
            [_vertical("segment", 0.0)],
            max_distance_m=25.0,
            ambiguity_margin_m=5.0,
        )
    with pytest.raises(ValueError, match="duplicate segment id"):
        snap_points_to_segments(
            [SnapPoint("p", LAT0, LON0)],
            [_vertical("same", 0.0), _vertical("same", 0.001)],
            max_distance_m=25.0,
            ambiguity_margin_m=5.0,
        )
    with pytest.raises(ValueError, match="at least two"):
        snap_points_to_segments(
            [SnapPoint("p", LAT0, LON0)],
            [Segment("bad", "bad", ((LAT0, LON0),))],
            max_distance_m=25.0,
            ambiguity_margin_m=5.0,
        )


def test_randomized_results_match_a_brute_force_nearest_two_oracle() -> None:
    rng = random.Random(2107)
    for trial in range(30):
        segments = []
        for index in range(12):
            lat = LAT0 + rng.uniform(-0.015, 0.015)
            lon = LON0 + rng.uniform(-0.015, 0.015)
            segments.append(
                Segment(
                    id=f"s-{index}",
                    name="segment",
                    coords=((lat, lon), (lat + rng.uniform(-0.003, 0.003), lon + 0.002)),
                )
            )
        point = SnapPoint(f"p-{trial}", LAT0, LON0)
        actual = snap_points_to_segments(
            [point],
            segments,
            max_distance_m=500.0,
            ambiguity_margin_m=10.0,
            ref_lat=LAT0,
            ref_lon=LON0,
        )[0]

        expected = sorted(
            (point_to_polyline_m(point.lat, point.lon, s.coords, LAT0, LON0), s.id)
            for s in segments
        )
        nearest_distance, nearest_id = expected[0]
        runner_up_distance = expected[1][0]
        expected_status = (
            "unsnapped"
            if nearest_distance > 500.0
            else "ambiguous"
            if runner_up_distance - nearest_distance <= 10.0
            else "snapped"
        )

        assert actual.status == expected_status
        assert actual.segment_id == (nearest_id if expected_status == "snapped" else None)
        if nearest_distance <= 500.0:
            # Every segment capable of changing an assignment is guaranteed to
            # be in the bounded query, so in-range nearest and ambiguous
            # runner-up distances match the global brute-force oracle.
            assert actual.distance_m == pytest.approx(nearest_distance)
            if expected_status == "ambiguous":
                assert actual.runner_up_distance_m == pytest.approx(runner_up_distance)


def test_decision_tolerance_stabilizes_distance_and_ambiguity_boundaries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import nearmiss.point_snap as point_snap

    values = iter((25.0000005, 40.0))
    monkeypatch.setattr(point_snap, "point_to_polyline_m", lambda *_args: next(values))
    result = point_snap.snap_points_to_segments(
        [point_snap.SnapPoint("p", LAT0, LON0)],
        [_vertical("near", 0.0), _vertical("far", 0.0001)],
        max_distance_m=25.0,
        ambiguity_margin_m=5.0,
        ref_lat=LAT0,
        ref_lon=LON0,
    )[0]
    assert result.status == "snapped"

    values = iter((10.0, 15.0000005))
    result = point_snap.snap_points_to_segments(
        [point_snap.SnapPoint("p", LAT0, LON0)],
        [_vertical("near", 0.0), _vertical("far", 0.0001)],
        max_distance_m=25.0,
        ambiguity_margin_m=5.0,
        ref_lat=LAT0,
        ref_lon=LON0,
    )[0]
    assert result.status == "ambiguous"


def test_values_beyond_decision_tolerance_do_not_cross_boundaries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import nearmiss.point_snap as point_snap

    values = iter((25.000002, 40.0))
    monkeypatch.setattr(point_snap, "point_to_polyline_m", lambda *_args: next(values))
    result = point_snap.snap_points_to_segments(
        [point_snap.SnapPoint("p", LAT0, LON0)],
        [_vertical("near", 0.0), _vertical("far", 0.0001)],
        max_distance_m=25.0,
        ambiguity_margin_m=5.0,
        ref_lat=LAT0,
        ref_lon=LON0,
    )[0]
    assert result.status == "unsnapped"

    values = iter((10.0, 15.000002))
    result = point_snap.snap_points_to_segments(
        [point_snap.SnapPoint("p", LAT0, LON0)],
        [_vertical("near", 0.0), _vertical("far", 0.0001)],
        max_distance_m=25.0,
        ambiguity_margin_m=5.0,
        ref_lat=LAT0,
        ref_lon=LON0,
    )[0]
    assert result.status == "snapped"


def test_input_and_densified_index_limits_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import nearmiss.point_snap as point_snap

    monkeypatch.setattr(point_snap, "_MAX_POINTS", 1)
    with pytest.raises(ValueError, match="point input"):
        point_snap.snap_points_to_segments(
            [point_snap.SnapPoint("a", LAT0, LON0), point_snap.SnapPoint("b", LAT0, LON0)],
            [_vertical("s", 0.0)],
            max_distance_m=25.0,
            ambiguity_margin_m=5.0,
        )
    monkeypatch.setattr(point_snap, "_MAX_POINTS", 100_000)
    monkeypatch.setattr(point_snap, "_MAX_INDEX_SAMPLES", 1)
    with pytest.raises(ValueError, match="densified segment index"):
        point_snap.snap_points_to_segments(
            [point_snap.SnapPoint("a", LAT0, LON0)],
            [_vertical("s", 0.0)],
            max_distance_m=25.0,
            ambiguity_margin_m=5.0,
        )


def test_cross_dateline_edge_is_rejected_as_non_city_geometry() -> None:
    segment = Segment(
        id="dateline",
        name="dateline",
        coords=((0.0, 179.999), (0.0, -179.999)),
    )
    with pytest.raises(ValueError, match="dateline wrapping is unsupported"):
        snap_points_to_segments(
            [SnapPoint("p", 0.0, 180.0)],
            [segment],
            max_distance_m=25.0,
            ambiguity_margin_m=5.0,
            ref_lat=0.0,
            ref_lon=0.0,
        )
