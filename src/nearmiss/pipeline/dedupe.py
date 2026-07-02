"""Deduplication: collapse reports that describe the same event.

Two reports are treated as duplicates when they are close in space and time and
either share a pseudonymous reporter token or describe the same hazard type.
The earliest report (by timestamp, then id) is kept, so the result is
deterministic.

Uses spatial bucketing to accelerate the all-pairs comparison: reports are
projected to local metres (as the rest of the pipeline does — see
``geometry.project``) and indexed there, then a radius query around each report
narrows the comparison down to nearby, already-kept reports instead of all of
them. The exact spatial/temporal/identity test in ``_is_duplicate`` (using true
haversine distance) is still what decides duplication; the index only limits
which pairs get that exact test, and it is built with enough margin that it
never excludes a true duplicate. Results are identical to brute-force
deduplication.
"""

from __future__ import annotations

from ..config import Config
from ..geometry import haversine_m, project, projection_margin_m
from ..models import Report
from ..spatial_index import SpatialIndex
from ..util import parse_ts, reference_point


def _is_duplicate(a: Report, b: Report, config: Config) -> bool:
    dist = haversine_m(a.lat, a.lon, b.lat, b.lon)
    if dist > config.dedupe_distance_m:
        return False
    ta, tb = parse_ts(a.occurred_at), parse_ts(b.occurred_at)
    if ta is None or tb is None or abs(ta - tb) > config.dedupe_window_s:
        return False
    if a.reporter_token and b.reporter_token:
        return a.reporter_token == b.reporter_token
    return a.hazard_type == b.hazard_type and a.mode == b.mode


def _chrono_key(r: Report) -> tuple[float, str]:
    # Sort by parsed epoch (not the raw ISO string, which misorders across
    # timezone offsets), with the id as a stable tiebreaker.
    t = parse_ts(r.occurred_at)
    return (t if t is not None else float("inf"), r.id)


def dedupe(reports: list[Report], config: Config) -> tuple[list[Report], list[str]]:
    """Return (kept_reports, removed_ids), deterministically. Earliest is kept."""
    ordered = sorted(reports, key=_chrono_key)
    if not ordered:
        return [], []

    # Build the spatial index in local projected METRES, not raw lon/lat
    # degrees. A degree of longitude is ~111 km at the equator but shrinks by
    # cos(latitude) toward the poles, so a "cell" that is one degree-fraction
    # wide is not a fixed physical size once you leave the equator — at
    # anywhere but very low latitudes, two points can be within
    # dedupe_distance_m of each other in true distance while landing in
    # non-adjacent longitude cells. Projecting first (as snap.py already does)
    # keeps cell sizes, and therefore the neighborhood search, metric
    # everywhere the pipeline runs.
    lat0, lon0 = reference_point(((r.lat, r.lon) for r in ordered), config.ref_lat, config.ref_lon)

    cell_size_m = max(config.dedupe_distance_m, 1.0)
    index = SpatialIndex(cell_size_m=cell_size_m)
    projected: dict[str, tuple[float, float]] = {}
    for r in ordered:
        x, y = project(r.lat, r.lon, lat0, lon0)
        projected[r.id] = (x, y)
        index.add(r.id, x, y)
    index.finalize()

    # neighbors_in_radius (not a fixed-size window of cells) derives its own
    # cell-radius margin from the requested search radius, so it stays correct
    # regardless of how that radius compares to the cell size — this is the
    # same accessor snap.py and getis_ord.py use for radius-bounded queries.
    # A small extra margin on top of dedupe_distance_m absorbs the residual
    # error of the equirectangular projection (project() uses a single
    # reference latitude, so reports far from lat0/lon0 have a slightly
    # different true degrees-to-metres scale); the exact haversine check in
    # `_is_duplicate` remains the authority on whether a pair is a true
    # duplicate, so a generous margin only costs a few extra exact checks.
    search_radius_m = config.dedupe_distance_m + projection_margin_m(config.dedupe_distance_m)

    kept: list[Report] = []
    removed: list[str] = []
    for r in ordered:
        rx, ry = projected[r.id]
        candidates = index.neighbors_in_radius(rx, ry, search_radius_m)
        candidate_ids = {cand_id for cand_id, _, _ in candidates}
        # Check only against already-kept reports that are in the candidate set.
        if any(_is_duplicate(r, k, config) for k in kept if k.id in candidate_ids):
            removed.append(r.id)
        else:
            kept.append(r)
    return kept, removed
