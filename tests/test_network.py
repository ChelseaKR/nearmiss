"""Tests for nearmiss.network.SegmentGraph: street-network adjacency and
network-distance neighbor queries — the FIX-02 replacement for straight-line
centroid distance in Getis-Ord Gi*.

The central claim under test: two segments can be close as the crow flies but
NOT network neighbors if nothing connects them (a river, a freeway, a missing
link in the extract), and SegmentGraph must say so even though a straight-line
distance band would not.
"""

from __future__ import annotations

import math
import random

from nearmiss.models import Segment
from nearmiss.network import SegmentGraph
from nearmiss.stats.getis_ord import getis_ord_star

# A non-trivial latitude (not the equator), matching the discipline the old
# getis_ord differential test used — this is exactly where a raw-degrees /
# metric unit mismatch (the FIX-12 bug class) would show up.
LAT0, LON0 = 34.05, -118.25
_M_PER_DEG_LAT = 110_540.0
_M_PER_DEG_LON = 111_320.0 * math.cos(math.radians(LAT0))


def _seg(sid: str, coords: list[tuple[float, float]]) -> Segment:
    return Segment(id=sid, name=sid, coords=tuple(coords))


def _offset(lat: float, lon: float, dx_m: float, dy_m: float) -> tuple[float, float]:
    """Move (lat, lon) by (dx_m east, dy_m north)."""
    return (lat + dy_m / _M_PER_DEG_LAT, lon + dx_m / _M_PER_DEG_LON)


def test_two_segments_sharing_an_endpoint_are_adjacent() -> None:
    a = _seg("a", [(LAT0, LON0), _offset(LAT0, LON0, 0, 100)])
    b = _seg("b", [_offset(LAT0, LON0, 0, 100), _offset(LAT0, LON0, 100, 100)])
    graph = SegmentGraph.build([a, b])
    assert not graph.isolated
    neighbors = graph.neighbors_within(1000.0)
    assert "b" in neighbors["a"]
    assert "a" in neighbors["b"]


def test_two_far_apart_segments_are_not_adjacent() -> None:
    a = _seg("a", [(LAT0, LON0), _offset(LAT0, LON0, 0, 100)])
    b = _seg("b", [_offset(LAT0, LON0, 5000, 5000), _offset(LAT0, LON0, 5100, 5000)])
    graph = SegmentGraph.build([a, b])
    assert graph.isolated == {"a", "b"}
    neighbors = graph.neighbors_within(1000.0)
    assert neighbors["a"] == {"a"}
    assert neighbors["b"] == {"b"}


def test_barrier_disagrees_with_straight_line_distance() -> None:
    """The exact scenario the ideation doc asks for: two parallel streets a
    short straight-line distance apart with NO connecting edge (a river or
    freeway between them) — a Euclidean distance band would treat them as
    neighbors; the network graph must not.

    Layout (metres east/north of LAT0, LON0):
        north street:  n1 (0,50) -------- n2 (80,50)
        south street:  s1 (0,0)  -------- s2 (80,0)
    n1/n2 and s1/s2 are each single segments; nothing connects the north
    street to the south street, even though they are only 50m apart —
    well within a typical gi_band_m of 300m.
    """
    north = _seg("north", [_offset(LAT0, LON0, 0, 50), _offset(LAT0, LON0, 80, 50)])
    south = _seg("south", [_offset(LAT0, LON0, 0, 0), _offset(LAT0, LON0, 80, 0)])
    graph = SegmentGraph.build([north, south])

    # Straight-line (centroid-to-centroid) distance is ~50m — well inside a
    # 300m band, so a Euclidean weights matrix WOULD call these neighbors.
    straight_line_m = 50.0
    band_m = 300.0
    assert straight_line_m <= band_m

    # The network graph disagrees: no shared endpoint, no edge, no path.
    assert graph.isolated == {"north", "south"}
    neighbors = graph.neighbors_within(band_m)
    assert neighbors["north"] == {"north"}
    assert neighbors["south"] == {"south"}


def test_barrier_fixture_changes_the_published_gi_star_answer() -> None:
    """End-to-end: planting a hotspot on one side of the barrier, Gi* run with
    network weights must NOT let the isolated opposite-side segment inflate or
    dilute the result the way a straight-line band would.

    Six segments: three in a connected "hot" corridor (h1-h2-h3, all high
    rate) and three in a connected "cold" corridor (c1-c2-c3, all low rate),
    the two corridors close together in straight-line terms but on opposite
    sides of an unconnected barrier.
    """
    # Hot corridor: h1 - h2 - h3, chained (h2 shares an endpoint with both).
    h1 = _seg("h1", [_offset(LAT0, LON0, 0, 100), _offset(LAT0, LON0, 80, 100)])
    h2 = _seg("h2", [_offset(LAT0, LON0, 80, 100), _offset(LAT0, LON0, 160, 100)])
    h3 = _seg("h3", [_offset(LAT0, LON0, 160, 100), _offset(LAT0, LON0, 240, 100)])
    # Cold corridor, 50m south of the hot one (well within a 300m band) but
    # with NO connecting segment across the gap.
    c1 = _seg("c1", [_offset(LAT0, LON0, 0, 50), _offset(LAT0, LON0, 80, 50)])
    c2 = _seg("c2", [_offset(LAT0, LON0, 80, 50), _offset(LAT0, LON0, 160, 50)])
    c3 = _seg("c3", [_offset(LAT0, LON0, 160, 50), _offset(LAT0, LON0, 240, 50)])
    segments = [h1, h2, h3, c1, c2, c3]

    values = {"h1": 20.0, "h2": 20.0, "h3": 20.0, "c1": 1.0, "c2": 1.0, "c3": 1.0}
    band_m = 300.0

    graph = SegmentGraph.build(segments)
    network_neighbors = graph.neighbors_within(band_m)
    network_z = getis_ord_star(values, network_neighbors)

    # A straight-line-distance weights matrix (the pre-FIX-02 behavior),
    # computed directly here so this test does not depend on removed code:
    # centroids are ~50m apart across the barrier, well inside band_m, so
    # EVERY segment would be everyone's neighbor.
    straight_line_neighbors = {sid: set(values.keys()) for sid in values}
    straight_line_z = getis_ord_star(values, straight_line_neighbors)

    # Under network weights, the hot corridor is an isolated cluster from the
    # cold one: h1's z is driven only by h1/h2/h3 (all high), so it is a much
    # stronger, cleanly significant hotspot than under the straight-line
    # matrix, where the cold segments on the other side of the barrier drag
    # the neighborhood average down and dilute it.
    assert network_z["h1"] > straight_line_z["h1"]
    assert network_z["c1"] < straight_line_z["c1"]

    # And the two answers are genuinely different, not coincidentally equal.
    for sid in values:
        assert network_z[sid] != straight_line_z[sid]


def test_build_with_no_segments_is_empty_not_an_error() -> None:
    graph = SegmentGraph.build([])
    assert graph.adjacency == {}
    assert graph.isolated == frozenset()
    assert graph.neighbors_within(300.0) == {}


def test_endpoints_within_search_margin_but_beyond_node_snap_m_are_not_adjacent() -> None:
    """The spatial index is queried with a padded search radius (node_snap_m +
    projection_margin_m), matching getis_ord.py's own margin discipline, so it
    never under-counts a true candidate. But the padding only widens the
    CANDIDATE set — the actual adjacency decision is still the exact
    haversine `d <= node_snap_m` check. Two endpoints placed inside the padded
    radius but outside node_snap_m itself must NOT be treated as adjacent."""
    node_snap_m = 5.0
    # Comfortably inside the padded search radius (5 + 5*0.10 + 5 = 10.5m) but
    # outside the exact node_snap_m=5m tolerance.
    a = _seg("a", [(LAT0, LON0), _offset(LAT0, LON0, 0, 100)])
    b = _seg("b", [_offset(LAT0, LON0, 0, 107), _offset(LAT0, LON0, 100, 107)])
    graph = SegmentGraph.build([a, b], node_snap_m=node_snap_m)
    assert graph.isolated == {"a", "b"}


def test_isolated_segment_has_only_itself_as_a_neighbor() -> None:
    lonely = _seg("lonely", [(LAT0, LON0), _offset(LAT0, LON0, 0, 50)])
    graph = SegmentGraph.build([lonely])
    assert graph.isolated == {"lonely"}
    assert graph.neighbors_within(300.0) == {"lonely": {"lonely"}}


def test_multi_hop_network_distance_respects_the_band() -> None:
    """A chain of 5 segments, each 100m (so centroid spacing along the chain
    is ~100m): band_m=150 should reach 1 hop but not 2."""
    segs = []
    for i in range(5):
        a = _offset(LAT0, LON0, i * 100, 0)
        b = _offset(LAT0, LON0, (i + 1) * 100, 0)
        segs.append(_seg(f"s{i}", [a, b]))
    graph = SegmentGraph.build(segs)
    neighbors = graph.neighbors_within(150.0)
    # s2's immediate neighbors s1/s3 are ~100m away (half+half of equal
    # 100m segments); s0/s4 are ~200m away -> excluded at band_m=150.
    assert neighbors["s2"] == {"s1", "s2", "s3"}


def _brute_force_neighbors_within(graph: SegmentGraph, band_m: float) -> dict[str, set[str]]:
    """O(V*(V+E)) Bellman-Ford-style oracle: relax all edges |V|-1 times from
    every start node, independent of the heap-based Dijkstra in SegmentGraph."""
    result: dict[str, set[str]] = {}
    for start in graph.adjacency:
        dist = {start: 0.0}
        for _ in range(len(graph.adjacency)):
            changed = False
            for node, d in list(dist.items()):
                for neighbor, w in graph.adjacency.get(node, ()):
                    nd = d + w
                    if nd <= band_m and nd < dist.get(neighbor, math.inf):
                        dist[neighbor] = nd
                        changed = True
            if not changed:
                break
        result[start] = set(dist.keys())
    return result


def test_dijkstra_matches_a_brute_force_relaxation_oracle_on_random_grids() -> None:
    """Randomized differential test: build random small street grids at a
    non-trivial latitude and check the bounded-Dijkstra neighbor sets against
    an independent relaxation-based oracle."""
    rng = random.Random(2026)
    for trial in range(60):
        n = rng.randint(3, 12)
        segs = []
        # A random tree-ish chain plus some extra cross-links, so the graph
        # is connected but not just a straight line.
        placed: list[tuple[float, float]] = [(0.0, 0.0)]
        for _i in range(1, n):
            ox, oy = rng.choice(placed)
            dx, dy = rng.choice([(60, 0), (-60, 0), (0, 60), (0, -60)])
            placed.append((ox + dx, oy + dy))
        for i in range(1, n):
            a = _offset(LAT0, LON0, *placed[i - 1])
            b = _offset(LAT0, LON0, *placed[i])
            segs.append(_seg(f"g{trial}-{i}", [a, b]))

        graph = SegmentGraph.build(segs)
        band_m = rng.choice([50.0, 100.0, 200.0])
        actual = graph.neighbors_within(band_m)
        expected = _brute_force_neighbors_within(graph, band_m)
        assert actual == expected, f"trial {trial} band {band_m}: {actual} != {expected}"
