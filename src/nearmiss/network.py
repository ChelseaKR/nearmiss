"""Street-network topology: the segment adjacency graph behind Gi* neighbors.

METHODOLOGY §8.2 documents (and, until this module, only *aspired to*) neighbors
"defined on the street network ... not naive straight-line distance." This module
builds that graph directly from the same ``Segment`` polylines the pipeline
already snaps reports to: ``tools/fetch_osm_streets.py`` splits OSM ways at real
intersections, so two segments that share an endpoint genuinely meet at a
junction, and that shared-endpoint relation *is* the network adjacency — no
separate street-centerline fetch is needed.

Two segments are adjacent when an endpoint of one lands within ``node_snap_m``
of an endpoint of the other (a tolerance, not exact equality, because
independently-sourced street data can carry sub-metre float/rounding jitter
even at a shared real-world intersection). The edge weight approximates the
network distance between the two segments' *centroids* — half of each
segment's own length — since ``geometry.polyline_centroid`` sits at a
length-weighted midpoint and the segments only actually connect at the shared
endpoint.

``SegmentGraph.neighbors_within`` runs a band-bounded Dijkstra from every
segment (pure Python, a heap — no native graph dependency, keeping the
project's ADR-0003 "runs anywhere Python runs" stance) and returns, per
segment, the set of segment ids reachable by network distance <= band_m,
always including the segment itself (Gi* requires the focal unit in its own
neighborhood). A segment with no adjacent segment (an island — a real
possibility in sparse or disconnected network extracts) simply has no
reachable neighbors beyond itself; that is the correct, honest answer, not a
special case to work around.

Reference: the shared-endpoint construction mirrors how
``tools/fetch_osm_streets.py`` itself identifies intersections (``_node_key``,
``intersection_nodes``) — segment endpoints are principled network nodes, not
arbitrary geometry.
"""

from __future__ import annotations

import heapq
import math
from dataclasses import dataclass, field

from .geometry import haversine_m, project, projection_margin_m
from .models import Segment
from .spatial_index import SpatialIndex

# Two segment endpoints within this many metres are treated as meeting at the
# same network node (real intersection). Generous enough to absorb float/
# rounding jitter in independently-sourced street data, tight enough not to
# fuse two genuinely distinct intersections a short block apart.
DEFAULT_NODE_SNAP_M = 5.0


_Coords = tuple[tuple[float, float], ...]
_Endpoints = tuple[tuple[float, float], tuple[float, float]]


def _endpoints(coords: _Coords) -> _Endpoints:
    return coords[0], coords[-1]


def _length_m(coords: _Coords) -> float:
    total = 0.0
    for i in range(len(coords) - 1):
        (la, lo), (lb, lob) = coords[i], coords[i + 1]
        total += haversine_m(la, lo, lb, lob)
    return total


def _reference_point(endpoints: dict[str, _Endpoints]) -> tuple[float, float]:
    """Mean of all endpoint coordinates — a stable, arbitrary local-metres
    projection reference point (only the candidate set it produces for the
    spatial index matters; adjacency itself is decided by an exact haversine
    check, so the reference choice cannot change the result)."""
    all_pts = [pt for eps in endpoints.values() for pt in eps]
    lat0 = sum(p[0] for p in all_pts) / len(all_pts)
    lon0 = sum(p[1] for p in all_pts) / len(all_pts)
    return lat0, lon0


def _endpoint_index(
    endpoints: dict[str, _Endpoints], lat0: float, lon0: float, node_snap_m: float
) -> SpatialIndex:
    """Spatial index of every segment's endpoints, projected to local metres
    (SpatialIndex.cell_size_m is metric, so raw lon/lat degrees would be a
    unit mismatch — the FIX-12 bug class this project has already hit once)."""
    index = SpatialIndex(cell_size_m=max(node_snap_m, 1.0))
    for sid, (a, b) in endpoints.items():
        ax, ay = project(a[0], a[1], lat0, lon0)
        index.add(sid, ax, ay)
        if b != a:
            bx, by = project(b[0], b[1], lat0, lon0)
            index.add(sid, bx, by)
    index.finalize()
    return index


def _adjacent_pair_weights(
    endpoints: dict[str, _Endpoints],
    lengths: dict[str, float],
    index: SpatialIndex,
    lat0: float,
    lon0: float,
    node_snap_m: float,
) -> dict[frozenset[str], float]:
    """Unordered-pair -> approximate network distance, for every pair of
    segments that meet at a shared endpoint (within ``node_snap_m``).

    The index is queried with a padded search radius (``projection_margin_m``,
    the same margin discipline ``stats/getis_ord.py`` already used) so it never
    under-counts a true candidate; the padding only widens the CANDIDATE set —
    the actual adjacency decision is still the exact haversine ``d <=
    node_snap_m`` check below.
    """
    search_radius_m = node_snap_m + projection_margin_m(node_snap_m)
    pair_weight: dict[frozenset[str], float] = {}
    for sid, (a, b) in endpoints.items():
        for end_lat, end_lon in {a, b} if b != a else {a}:
            ex, ey = project(end_lat, end_lon, lat0, lon0)
            for cand_id, _, _ in index.neighbors_in_radius(ex, ey, search_radius_m):
                if cand_id == sid:
                    continue
                ca, cb = endpoints[cand_id]
                d = min(haversine_m(end_lat, end_lon, *ca), haversine_m(end_lat, end_lon, *cb))
                if d > node_snap_m:
                    continue
                key = frozenset((sid, cand_id))
                weight = lengths[sid] / 2.0 + lengths[cand_id] / 2.0
                if key not in pair_weight or weight < pair_weight[key]:
                    pair_weight[key] = weight
    return pair_weight


@dataclass
class SegmentGraph:
    """Adjacency graph over street segments, for network-distance neighbor queries.

    Nodes are segment ids. Two segments are adjacent (connected by an edge) if
    they meet at a shared endpoint within ``node_snap_m``. The edge weight is
    the approximate network distance between the two segments' centroids.
    """

    adjacency: dict[str, list[tuple[str, float]]] = field(default_factory=dict)
    # Segments with no adjacent segment at all — islands in the network extract.
    isolated: frozenset[str] = frozenset()

    @classmethod
    def build(
        cls, segments: list[Segment], node_snap_m: float = DEFAULT_NODE_SNAP_M
    ) -> SegmentGraph:
        """Build the adjacency graph from a list of street segments."""
        if not segments:
            return cls(adjacency={}, isolated=frozenset())

        lengths = {s.id: _length_m(s.coords) for s in segments}
        endpoints = {s.id: _endpoints(s.coords) for s in segments}
        lat0, lon0 = _reference_point(endpoints)
        index = _endpoint_index(endpoints, lat0, lon0, node_snap_m)
        pair_weight = _adjacent_pair_weights(endpoints, lengths, index, lat0, lon0, node_snap_m)

        adjacency: dict[str, list[tuple[str, float]]] = {s.id: [] for s in segments}
        for pair, weight in pair_weight.items():
            u, v = tuple(pair)
            adjacency[u].append((v, weight))
            adjacency[v].append((u, weight))
        for edges in adjacency.values():
            edges.sort(key=lambda e: e[0])  # determinism

        isolated = frozenset(sid for sid, edges in adjacency.items() if not edges)
        return cls(adjacency=adjacency, isolated=isolated)

    def _dijkstra_within(self, start: str, band_m: float) -> set[str]:
        """Segment ids reachable from ``start`` by network distance <= band_m.

        ``start`` is always a key of ``self.adjacency`` in practice — every
        segment passed to ``build()`` gets an (possibly empty) adjacency-list
        entry, including isolated ones — so there is no "unknown segment"
        branch to special-case here.
        """
        dist: dict[str, float] = {start: 0.0}
        heap: list[tuple[float, str]] = [(0.0, start)]
        visited: set[str] = set()
        while heap:
            d, node = heapq.heappop(heap)
            if node in visited:
                continue
            visited.add(node)
            for neighbor, w in self.adjacency.get(node, ()):
                nd = d + w
                if nd <= band_m and nd < dist.get(neighbor, math.inf):
                    dist[neighbor] = nd
                    heapq.heappush(heap, (nd, neighbor))
        return set(dist.keys())

    def neighbors_within(self, band_m: float) -> dict[str, set[str]]:
        """For every segment, the set of segment ids (including itself) within
        network distance ``band_m`` — the Gi* spatial-weights neighbor map.

        An isolated segment (no adjacent segment) maps to ``{itself}`` only:
        it has no honest network neighbors, so Gi* for it degenerates to
        comparing the segment to itself, which is the correct behavior for an
        island in the extract, not an error to hide.
        """
        return {sid: self._dijkstra_within(sid, band_m) for sid in self.adjacency}
