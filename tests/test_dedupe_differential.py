"""Differential tests: indexed dedupe() vs. an independent brute-force oracle.

The spatial-indexing branch (FIX-12) built dedupe()'s SpatialIndex in raw
lon/lat *degrees*, with a fixed 3x3 cells_in_neighborhood() window. A degree of
longitude is ~111km at the equator but shrinks by cos(latitude), so a "cell"
that is one degree-fraction wide is not a fixed physical size once you leave
the equator — at any real-world latitude, two points can be within
dedupe_distance_m of each other in true distance while landing more than one
cell apart in longitude, and the fixed window silently misses them. The fixed
dedupe() now projects to local metres and uses a radius-aware neighborhood
query (see pipeline/dedupe.py); these tests prove, at LA's latitude (~34
degrees, matching the bug report's reproduction), that its output is always
identical to a brute-force (no spatial index at all) reference implementation.
"""

from __future__ import annotations

import math
import random
from datetime import UTC, datetime
from pathlib import Path

from nearmiss.config import Config
from nearmiss.geometry import haversine_m
from nearmiss.models import Report
from nearmiss.pipeline.dedupe import dedupe

LA_LAT, LA_LON = 34.0522, -118.2437


def _config(**overrides: object) -> Config:
    base: dict[str, object] = {
        "city": "Test",
        "streets_path": Path("unused"),
        "reports_path": Path("unused"),
        "exposure_path": Path("unused"),
        "raw_dir": Path("unused"),
        "out_dir": Path("unused"),
    }
    base.update(overrides)
    return Config(**base)  # type: ignore[arg-type]


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=UTC).isoformat()


def _offset(lat: float, lon: float, bearing_deg: float, dist_m: float) -> tuple[float, float]:
    """Move (lat, lon) by ~dist_m metres along bearing_deg.

    Approximate — it only needs to be roughly right, because every trial's
    pass/fail decision below is made from the *actual* haversine distance
    between the resulting points, not from this offset's target distance.
    """
    bearing = math.radians(bearing_deg)
    m_per_deg_lat = 110_540.0
    m_per_deg_lon = 111_320.0 * math.cos(math.radians(lat))
    dlat = (dist_m * math.cos(bearing)) / m_per_deg_lat
    dlon = (dist_m * math.sin(bearing)) / m_per_deg_lon if m_per_deg_lon else 0.0
    return lat + dlat, lon + dlon


def _report(
    id_: str, lat: float, lon: float, ts: float, token: str, hazard: str = "close_pass"
) -> Report:
    return Report(
        id=id_,
        occurred_at=_iso(ts),
        lat=lat,
        lon=lon,
        mode="cyclist",
        hazard_type=hazard,
        severity="near_miss",
        reporter_token=token,
    )


def _brute_force_is_duplicate(a: Report, b: Report, config: Config) -> bool:
    """Independent reimplementation of the documented dedupe predicate.

    Written from dedupe.py's module docstring, not by reusing its internals,
    so this oracle cannot share a latent bug with the code under test.
    """
    if haversine_m(a.lat, a.lon, b.lat, b.lon) > config.dedupe_distance_m:
        return False
    ta = datetime.fromisoformat(a.occurred_at).timestamp()
    tb = datetime.fromisoformat(b.occurred_at).timestamp()
    if abs(ta - tb) > config.dedupe_window_s:
        return False
    if a.reporter_token and b.reporter_token:
        return a.reporter_token == b.reporter_token
    return a.hazard_type == b.hazard_type and a.mode == b.mode


def _brute_force_dedupe(reports: list[Report], config: Config) -> tuple[set[str], set[str]]:
    """O(n^2) oracle: every report checked against every already-kept report."""
    ordered = sorted(
        reports, key=lambda r: (datetime.fromisoformat(r.occurred_at).timestamp(), r.id)
    )
    kept: list[Report] = []
    removed: set[str] = set()
    for r in ordered:
        if any(_brute_force_is_duplicate(r, k, config) for k in kept):
            removed.add(r.id)
        else:
            kept.append(r)
    return {r.id for r in kept}, removed


def test_dedupe_reproduces_the_reported_la_boundary_miss() -> None:
    """Concrete regression: two points 12.47m apart (below the 15m threshold),
    same reporter_token, 5s apart, at LA's latitude. The buggy fixed-window
    index missed this pair because it landed >1 longitude cell apart even
    though it is well within dedupe_distance_m in true distance."""
    config = _config(dedupe_distance_m=15.0, dedupe_window_s=600)
    lat, lon = LA_LAT, LA_LON
    lat2, lon2 = _offset(lat, lon, bearing_deg=90.0, dist_m=12.47)
    assert haversine_m(lat, lon, lat2, lon2) < 15.0

    a = _report("a", lat, lon, 1_700_000_000.0, "tok-1")
    b = _report("b", lat2, lon2, 1_700_000_005.0, "tok-1")

    kept, removed = dedupe([a, b], config)
    assert [r.id for r in kept] == ["a"]
    assert removed == ["b"]


def test_dedupe_matches_brute_force_over_5000_boundary_pairs() -> None:
    """5,000-trial randomized differential test at LA's latitude, matching the
    scale that originally caught the bug (13/5000 true duplicates silently
    kept). Every trial's actual dedupe() result must exactly match the
    brute-force oracle; zero mismatches are allowed."""
    rng = random.Random(20260702)
    config = _config(dedupe_distance_m=15.0, dedupe_window_s=600)

    mismatches = 0
    trials = 5000
    for i in range(trials):
        base_lat = LA_LAT + rng.uniform(-0.05, 0.05)
        base_lon = LA_LON + rng.uniform(-0.05, 0.05)
        bearing = rng.uniform(0.0, 360.0)
        # Spread across, and straddling, the dedupe threshold (0 - 30m vs. a
        # 15m default), which is exactly where a boundary bug would show up.
        dist = rng.uniform(0.0, 30.0)
        lat_b, lon_b = _offset(base_lat, base_lon, bearing, dist)

        token = f"tok-{i}"
        a = _report(f"{i}-a", base_lat, base_lon, 1_700_000_000.0, token)
        b = _report(f"{i}-b", lat_b, lon_b, 1_700_000_000.0 + rng.uniform(-5, 5), token)

        expected_kept, expected_removed = _brute_force_dedupe([a, b], config)
        actual_kept, actual_removed = dedupe([a, b], config)

        if {r.id for r in actual_kept} != expected_kept or set(actual_removed) != expected_removed:
            mismatches += 1

    assert mismatches == 0, f"{mismatches}/{trials} trials mismatched the brute-force oracle"


def test_dedupe_matches_brute_force_over_random_city_batches() -> None:
    """Broader-scale check: many-report batches (not just isolated pairs),
    scattered over a city-sized area at LA's latitude, with a mix of tokens,
    hazard types, and timestamps, so kept-report candidate sets grow the way
    they would in a real pipeline run. 200 trials x 40 reports = 8,000 report
    instances, each trial fully cross-checked against the brute-force oracle."""
    rng = random.Random(99)
    config = _config(dedupe_distance_m=15.0, dedupe_window_s=600)
    tokens = [f"tok-{k}" for k in range(6)]
    hazards = ["close_pass", "dooring", "surface_hazard", "sightline"]

    mismatches = 0
    trials = 200
    for t in range(trials):
        reports: list[Report] = []
        for i in range(40):
            lat = LA_LAT + rng.uniform(-0.03, 0.03)
            lon = LA_LON + rng.uniform(-0.03, 0.03)
            ts = 1_700_000_000.0 + rng.uniform(0, 1200)
            token = rng.choice(tokens)
            hazard = rng.choice(hazards)
            reports.append(_report(f"{t}-{i}", lat, lon, ts, token, hazard))

        expected_kept, expected_removed = _brute_force_dedupe(reports, config)
        actual_kept, actual_removed = dedupe(reports, config)

        if {r.id for r in actual_kept} != expected_kept or set(actual_removed) != expected_removed:
            mismatches += 1

    assert mismatches == 0, f"{mismatches}/{trials} batch trials mismatched the brute-force oracle"
