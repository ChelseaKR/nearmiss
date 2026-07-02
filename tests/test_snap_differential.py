"""Differential tests: snap() vs. an independent brute-force oracle.

Two related risks were flagged for the spatial-indexing branch (FIX-12):

1. snap() used a hardcoded ``search_radius = 1000.0`` decoupled from the
   configurable ``config.snap_max_m``, with no validation bounding
   ``snap_max_m`` below it. The fix derives the search radius from
   ``snap_max_m`` (with a margin and a 1km floor) instead.

2. While constructing a regression case for (1), a deeper and more general bug
   surfaced: the spatial index only stores discrete (x, y) samples, so a
   segment digitized as just two far-apart vertices (a straight, sparsely
   vertexed road — common in real street data) was invisible to a report near
   its *middle*, even though the true point-to-polyline distance there is
   small. This reproduced even at the *default* snap_max_m (25m), whenever a
   closer decoy segment was also present (so the empty-candidate brute-force
   fallback never triggered). The fix densifies segment sampling
   (``_densify_segment_xy``) so no point on any segment is far from an indexed
   sample, and separately, ``SpatialIndex.neighbors_in_radius`` had a latent
   bug where a multi-point id's first-visited (and possibly out-of-range)
   instance would shadow a later, in-range instance of the *same* id; both are
   fixed at their source (pipeline/snap.py and spatial_index.py).

These tests cover both: a differential fuzz test against a brute-force nearest
-segment oracle (including snap_max_m > 1km), and the concrete long-segment
regression that exposed the deeper bug.
"""

from __future__ import annotations

import random
from pathlib import Path

from nearmiss.config import Config
from nearmiss.geometry import point_to_polyline_m
from nearmiss.models import Report, Segment
from nearmiss.pipeline.snap import snap

LAT0, LON0 = 34.05, -118.25


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


def _report(id_: str, lat: float, lon: float) -> Report:
    return Report(
        id=id_,
        occurred_at="2024-01-01T00:00:00Z",
        lat=lat,
        lon=lon,
        mode="cyclist",
        hazard_type="close_pass",
        severity="near_miss",
    )


def _brute_force_snap(
    reports: list[Report], segments: list[Segment], config: Config
) -> list[tuple[str | None, float | None]]:
    """O(reports x segments) oracle: check every segment for every report."""
    lats = [c[0] for s in segments for c in s.coords]
    lons = [c[1] for s in segments for c in s.coords]
    lat0, lon0 = sum(lats) / len(lats), sum(lons) / len(lons)

    out: list[tuple[str | None, float | None]] = []
    for r in reports:
        best_id: str | None = None
        best_d = float("inf")
        for seg in segments:
            d = point_to_polyline_m(r.lat, r.lon, seg.coords, lat0, lon0)
            if d < best_d:
                best_d, best_id = d, seg.id
        if best_id is None:
            out.append((None, None))
        elif best_d <= config.snap_max_m:
            out.append((best_id, best_d))
        else:
            out.append((None, best_d))
    return out


def test_snap_reproduces_the_long_sparse_segment_miss() -> None:
    """Concrete regression: a segment digitized as just two endpoints ~18km
    apart passes within ~5.5m of a report near its middle, but a closer
    (~115m) decoy segment is also present. Both the default snap_max_m (25m)
    and a > 1km snap_max_m (1500m) must correctly snap to the true nearest
    segment, not the decoy."""
    long_seg = Segment(id="long", name="long", coords=((34.0, -118.35), (34.0, -118.15)))
    decoy = Segment(id="decoy", name="decoy", coords=((34.001, -118.2505), (34.0011, -118.2504)))
    r = _report("r1", 34.00005, -118.25)

    for snap_max_m in (25.0, 1500.0):
        config = _config(snap_max_m=snap_max_m)
        out = snap([r], [long_seg, decoy], config)
        assert out[0].segment_id == "long", f"snap_max_m={snap_max_m}: got {out[0].segment_id!r}"
        assert out[0].distance_m is not None
        assert out[0].distance_m < 6.0


def test_snap_matches_brute_force_including_snap_max_m_above_1km() -> None:
    """Randomized differential test: random segments and reports at ~34 degrees
    latitude, including configs with snap_max_m > 1km (the specific risk
    flagged for the old hardcoded 1km search radius), and a mix of short and
    long (sparsely-vertexed) segments. 150 trials x ~15 segments x 20 reports."""
    rng = random.Random(4242)
    trials = 150
    mismatches = 0
    total_reports = 0

    for t in range(trials):
        segments: list[Segment] = []
        for k in range(15):
            slat = LAT0 + rng.uniform(-0.05, 0.05)
            slon = LON0 + rng.uniform(-0.05, 0.05)
            if rng.random() < 0.3:
                # A long, sparsely-vertexed segment: just two endpoints, far apart.
                dlat = 0.15 * rng.uniform(-1, 1)
                dlon = 0.15 * rng.uniform(-1, 1)
                coords = ((slat, slon), (slat + dlat, slon + dlon))
            else:
                # A short, ordinary city-block-scale segment.
                dlat = rng.uniform(-0.001, 0.001)
                dlon = rng.uniform(-0.001, 0.001)
                coords = ((slat, slon), (slat + dlat, slon + dlon))
            segments.append(Segment(id=f"{t}-seg{k}", name="seg", coords=coords))

        reports = [
            _report(f"{t}-r{i}", LAT0 + rng.uniform(-0.06, 0.06), LON0 + rng.uniform(-0.06, 0.06))
            for i in range(20)
        ]

        snap_max_m = rng.choice([25.0, 50.0, 250.0, 1200.0, 2500.0])
        config = _config(snap_max_m=snap_max_m)

        actual = [(s.segment_id, s.distance_m) for s in snap(reports, segments, config)]
        expected = _brute_force_snap(reports, segments, config)

        total_reports += len(reports)
        for (a_id, a_d), (e_id, e_d) in zip(actual, expected, strict=True):
            if a_id != e_id or (a_d is not None and e_d is not None and abs(a_d - e_d) > 1e-6):
                mismatches += 1

    assert mismatches == 0, f"{mismatches}/{total_reports} report-trials mismatched the oracle"
