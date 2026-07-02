"""Unit tests for SpatialIndex, including a multi-point-per-id regression.

``neighbors_in_radius`` used to mark an id as "seen" the moment it visited
*any* instance of that id, before checking whether that instance was actually
within the radius. For an id added at a single (x, y) — every current caller
except pipeline/snap.py — this is harmless. But pipeline/snap.py adds every
vertex of a segment under that segment's shared id, and the fixed cell-scan
order can visit a far-away (out-of-range) vertex before a much closer
(in-range) one of the same segment. The far vertex would fail the distance
check but still "use up" the id, silently hiding the close vertex — and with
it, the whole segment — from the query result.
"""

from __future__ import annotations

from nearmiss.spatial_index import SpatialIndex


def test_neighbors_in_radius_finds_a_close_instance_even_if_a_far_one_is_visited_first() -> None:
    # cell_size=100 keeps the scan window (cell_radius = int(2000/100)+1 = 21)
    # wide enough to visit a far-away instance of "seg" before the close one,
    # reproducing the shadowing bug regardless of iteration order specifics.
    index = SpatialIndex(cell_size_m=100.0)
    # Two instances of the SAME id: one far away (outside the query radius),
    # one close (inside it).
    index.add("seg", -1900.0, -1900.0)  # far: dist ~2687m, outside radius
    index.add("seg", 5.0, 5.0)  # close: dist ~7m, inside radius
    index.finalize()

    result = index.neighbors_in_radius(0.0, 0.0, radius_m=2000.0)

    ids = {item_id for item_id, _, _ in result}
    assert "seg" in ids, "the close instance must not be shadowed by the far one"
    # Exactly one entry per id, and it must be the in-range instance.
    matches = [item for item in result if item[0] == "seg"]
    assert len(matches) == 1
    _, x, y = matches[0]
    assert (x, y) == (5.0, 5.0)


def test_neighbors_in_radius_excludes_an_id_with_no_instance_in_range() -> None:
    index = SpatialIndex(cell_size_m=100.0)
    index.add("far-only", -1900.0, -1900.0)
    index.finalize()

    result = index.neighbors_in_radius(0.0, 0.0, radius_m=200.0)
    assert result == []


def test_neighbors_in_radius_matches_brute_force_for_multi_point_ids() -> None:
    """Differential check against a plain O(n) brute-force scan, for ids with
    several instances each (the snap.py usage pattern) and query points/radii
    chosen so some ids have only far instances, some only close, and some
    both."""
    import math
    import random

    rng = random.Random(11)
    index = SpatialIndex(cell_size_m=50.0)
    points: list[tuple[str, float, float]] = []
    for seg_id in range(20):
        n_instances = rng.randint(1, 6)
        for _ in range(n_instances):
            x = rng.uniform(-3000, 3000)
            y = rng.uniform(-3000, 3000)
            points.append((f"seg-{seg_id}", x, y))
            index.add(f"seg-{seg_id}", x, y)
    index.finalize()

    for _ in range(200):
        qx, qy = rng.uniform(-3000, 3000), rng.uniform(-3000, 3000)
        radius = rng.uniform(50, 1500)

        actual_ids = {item_id for item_id, _, _ in index.neighbors_in_radius(qx, qy, radius)}
        expected_ids = {item_id for item_id, x, y in points if math.hypot(x - qx, y - qy) <= radius}
        assert actual_ids == expected_ids
