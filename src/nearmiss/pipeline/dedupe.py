"""Deduplication: collapse reports that describe the same event.

Two reports are treated as duplicates when they are close in space and time and
either share a pseudonymous reporter token or describe the same hazard type.
The earliest report (by timestamp, then id) is kept, so the result is
deterministic.

Uses spatial bucketing to accelerate the all-pairs comparison: reports are first
grouped by (spatial cell, time window), then compared only within their buckets.
Results are identical to brute-force deduplication.
"""

from __future__ import annotations

from ..config import Config
from ..geometry import haversine_m
from ..models import Report
from ..spatial_index import SpatialIndex
from ..util import parse_ts


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

    # Build a spatial index to group reports by cell.
    # Use a rough heuristic: 1 degree ≈ 111 km at the equator.
    # Cell size in degrees ≈ dedupe_distance_m / 111,000
    cell_size_deg = max(config.dedupe_distance_m / 111_000.0, 0.0001)
    index = SpatialIndex(cell_size_m=cell_size_deg)
    for r in ordered:
        # Index reports using lon/lat as (x, y) in degrees.
        index.add(r.id, r.lon, r.lat)
    index.finalize()

    kept: list[Report] = []
    removed: list[str] = []
    for r in ordered:
        # Query neighborhood of reports that might be duplicates.
        candidates = index.cells_in_neighborhood(r.lon, r.lat)
        candidate_ids = {cand_id for cand_id, _, _ in candidates}
        # Check only against already-kept reports that are in the candidate set.
        if any(_is_duplicate(r, k, config) for k in kept if k.id in candidate_ids):
            removed.append(r.id)
        else:
            kept.append(r)
    return kept, removed
