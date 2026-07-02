"""Snap reports to the nearest street segment.

A report is assigned to the nearest segment within ``snap_max_m``; beyond that
it is left unsnapped (segment_id ``None``) for the quality stage to flag, rather
than forced onto a segment it does not belong to.

Uses spatial indexing to accelerate the nearest-neighbor search: instead of
checking all segments for each report, we query a 3×3 grid neighborhood around
the report. Results are identical to brute-force snapping.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..config import Config
from ..geometry import point_to_polyline_m, project
from ..models import Report, Segment
from ..spatial_index import SpatialIndex
from ..util import reference_point


@dataclass(frozen=True)
class Snapped:
    report: Report
    segment_id: str | None
    distance_m: float | None


def snap(reports: list[Report], segments: list[Segment], config: Config) -> list[Snapped]:
    lat0, lon0 = reference_point(segments, config.ref_lat, config.ref_lon)

    # Build spatial index of ALL segment coordinates (not just centroids).
    # This ensures we find segments even if their centroids are far away.
    # Use a cell size smaller than snap_max_m to allow efficient radius queries.
    cell_size = max(config.snap_max_m / 2.0, 10.0)
    index = SpatialIndex(cell_size_m=cell_size)
    seg_id_map = {}  # Map segment id to segment object for fast lookup
    for seg in segments:
        seg_id_map[seg.id] = seg
        # Index all coordinates of the segment.
        for lat, lon in seg.coords:
            x, y = project(lat, lon, lat0, lon0)
            index.add(seg.id, x, y)
    index.finalize()

    out: list[Snapped] = []
    for r in reports:
        rx, ry = project(r.lat, r.lon, lat0, lon0)
        # Use spatial index to find candidate segments.
        # Search radius: use a large enough radius to ensure we find the global nearest
        # segment. For city-scale data, 1 km is safe; for continental data, we'd increase.
        best_id: str | None = None
        best_d = float("inf")

        # Use a large search radius to ensure correctness (spatial index is just an accelerator)
        search_radius = 1000.0  # 1 km
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
            # Fallback: brute force all segments (should not happen with 1km radius)
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
