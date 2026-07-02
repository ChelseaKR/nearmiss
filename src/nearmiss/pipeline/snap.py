"""Snap reports to the nearest street segment.

A report is assigned to the nearest segment within ``snap_max_m``; beyond that
it is left unsnapped (segment_id ``None``) for the quality stage to flag, rather
than forced onto a segment it does not belong to.

Uses spatial indexing to accelerate the nearest-neighbor search: instead of
checking all segments for each report, we query a radius neighborhood around
the report. Results are identical to brute-force snapping.

The index only stores discrete (x, y) samples, not continuous geometry, so a
segment digitized as just two far-apart vertices (a straight rural road, say)
would be invisible to a report near its *midpoint* even though the true
point-to-polyline distance there is small: neither endpoint is a nearby
sample. ``_densify_segment_xy`` closes that gap by adding extra samples along
any edge longer than ``_DENSIFY_STEP_M``, so every point on every segment has
an indexed sample within half that step of it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from itertools import pairwise

from ..config import Config
from ..geometry import point_to_polyline_m, project
from ..models import Report, Segment
from ..spatial_index import SpatialIndex
from ..util import reference_point

# Extra samples are added along any segment edge longer than this, so a
# sparsely-vertexed (e.g. two-point) segment can still be found by a report
# near its middle. 200m is a large margin below the search radius (at least a
# 1km floor, or 4x snap_max_m — see `search_radius` below), so it adds
# negligible index size for ordinary short city-block segments while still
# guaranteeing every point on every segment is within 100m of some sample.
_DENSIFY_STEP_M = 200.0


def _densify_segment_xy(
    coords_xy: list[tuple[float, float]], step_m: float
) -> list[tuple[float, float]]:
    """Add extra points along each edge longer than ``step_m``.

    Operates on already-projected (x, y) metres so the interpolation is a
    plain straight-line lerp; for city-scale segments this is well within the
    precision the pipeline needs (see geometry.py's module docstring).
    """
    if step_m <= 0 or len(coords_xy) < 2:
        return list(coords_xy)
    out: list[tuple[float, float]] = [coords_xy[0]]
    for (ax, ay), (bx, by) in pairwise(coords_xy):
        length = math.hypot(bx - ax, by - ay)
        steps = int(length // step_m)
        for k in range(1, steps + 1):
            t = (k * step_m) / length
            out.append((ax + t * (bx - ax), ay + t * (by - ay)))
        out.append((bx, by))
    return out


@dataclass(frozen=True)
class Snapped:
    report: Report
    segment_id: str | None
    distance_m: float | None


def snap(reports: list[Report], segments: list[Segment], config: Config) -> list[Snapped]:
    lat0, lon0 = reference_point(
        (c for s in segments for c in s.coords), config.ref_lat, config.ref_lon
    )

    # Build spatial index of ALL segment coordinates (not just centroids).
    # This ensures we find segments even if their centroids are far away.
    # Use a cell size smaller than snap_max_m to allow efficient radius queries.
    cell_size = max(config.snap_max_m / 2.0, 10.0)
    index = SpatialIndex(cell_size_m=cell_size)
    seg_id_map = {}  # Map segment id to segment object for fast lookup
    for seg in segments:
        seg_id_map[seg.id] = seg
        # Index all coordinates of the segment, densified so a long,
        # sparsely-vertexed segment (e.g. two endpoints and nothing else) is
        # still discoverable by a report near its middle.
        xy = [project(lat, lon, lat0, lon0) for lat, lon in seg.coords]
        for x, y in _densify_segment_xy(xy, _DENSIFY_STEP_M):
            index.add(seg.id, x, y)
    index.finalize()

    out: list[Snapped] = []
    for r in reports:
        rx, ry = project(r.lat, r.lon, lat0, lon0)
        # Use spatial index to find candidate segments.
        # Search radius: derived from config.snap_max_m (not a bare constant), with a
        # 4x margin and a 1 km floor. A fixed 1 km radius decoupled from the
        # configurable threshold would silently under-search for any city config
        # that sets snap_max_m above 1 km — the empty-candidate fallback below
        # still catches a *totally* empty neighborhood, but coupling the radius to
        # snap_max_m keeps the fast path correct without leaning on that fallback.
        best_id: str | None = None
        best_d = float("inf")

        search_radius = max(1000.0, config.snap_max_m * 4.0)
        candidates_raw = index.neighbors_in_radius(rx, ry, search_radius)
        candidate_ids = {cand_id for cand_id, _, _ in candidates_raw}

        # Evaluate candidates found by spatial index
        if candidate_ids:
            for seg_id in sorted(candidate_ids):  # Sort for determinism
                seg = seg_id_map[seg_id]
                d = point_to_polyline_m(r.lat, r.lon, seg.coords, lat0, lon0)
                if d < best_d:
                    best_d, best_id = d, seg.id
        else:
            # Fallback: brute force all segments (should not happen with search_radius)
            for seg_id in sorted(seg_id_map.keys()):
                seg = seg_id_map[seg_id]
                d = point_to_polyline_m(r.lat, r.lon, seg.coords, lat0, lon0)
                if d < best_d:
                    best_d, best_id = d, seg.id

        if best_id is None:
            out.append(Snapped(r, None, None))
        elif best_d <= config.snap_max_m:
            out.append(Snapped(r, best_id, best_d))
        else:
            out.append(Snapped(r, None, best_d))
    return out
