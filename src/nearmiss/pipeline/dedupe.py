"""Deduplication: collapse reports that describe the same event.

Two reports are treated as duplicates when they are close in space and time and
either share a pseudonymous reporter token or describe the same hazard type.
The earliest report (by timestamp, then id) is kept, so the result is
deterministic.
"""

from __future__ import annotations

from ..config import Config
from ..geometry import haversine_m
from ..models import Report
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


def dedupe(reports: list[Report], config: Config) -> tuple[list[Report], list[str]]:
    """Return (kept_reports, removed_ids), deterministically."""
    ordered = sorted(reports, key=lambda r: (r.occurred_at, r.id))
    kept: list[Report] = []
    removed: list[str] = []
    for r in ordered:
        if any(_is_duplicate(r, k, config) for k in kept):
            removed.append(r.id)
        else:
            kept.append(r)
    return kept, removed
