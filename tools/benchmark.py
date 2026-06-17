#!/usr/bin/env python3
"""Performance benchmark for the nearmiss pipeline + statistics.

Generates a city-scale synthetic dataset in memory and times the pipeline,
the exposure-normalized statistics (including the O(M^2) Getis-Ord step), and
the GeoJSON build. Deterministic generation, no RNG. Run:
    python tools/benchmark.py [n_segments] [n_reports]
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

from nearmiss import pipeline
from nearmiss.config import Config
from nearmiss.models import Exposure, Report, Segment
from nearmiss.publish import build_geojson
from nearmiss.stats import analyze

BASE_LAT = 38.5
BASE_LON = -121.7


def _config() -> Config:
    return Config(
        city="bench",
        streets_path=Path("x"),
        reports_path=Path("x"),
        exposure_path=Path("x"),
        raw_dir=Path("/tmp/nm-bench-raw"),
        out_dir=Path("/tmp/nm-bench-pub"),
    )


def _segments(m: int) -> list[Segment]:
    cols = max(1, int(m**0.5))
    out: list[Segment] = []
    for n in range(m):
        row, col = divmod(n, cols)
        lat = BASE_LAT + row * 0.0025
        lon = BASE_LON + col * 0.0030
        out.append(
            Segment(
                id=f"seg-{n}", name=f"Street {n}", coords=((lat, lon - 0.0008), (lat, lon + 0.0008))
            )
        )
    return out


def _exposure(segs: list[Segment]) -> dict[str, Exposure]:
    return {
        s.id: Exposure(s.id, 100.0 + (i % 50) * 30.0, "synthetic", "2026-05-01")
        for i, s in enumerate(segs)
    }


def _reports(n: int, segs: list[Segment]) -> list[Report]:
    out: list[Report] = []
    for i in range(n):
        s = segs[i % len(segs)]
        lat = s.coords[0][0] + 0.00003
        # Spread reports along the segment by report index so within-segment
        # reports are distinct (not collapsed by dedupe).
        lon = (s.coords[0][1] + s.coords[1][1]) / 2 + ((i // len(segs)) - 10) * 0.00006
        # Distinct timestamps per report (h:m:s derived from i) -> no dedupe.
        h, mn, sc = (i // 3600) % 24, (i // 60) % 60, i % 60
        out.append(
            Report(
                id=f"00000000-0000-4000-8000-{i:012x}",
                occurred_at=f"2026-06-01T{h:02d}:{mn:02d}:{sc:02d}-07:00",
                lat=round(lat, 6),
                lon=round(lon, 6),
                mode="cyclist",
                hazard_type="close_pass",
                severity="near_miss",
            )
        )
    return out


def main() -> None:
    m = int(sys.argv[1]) if len(sys.argv) > 1 else 300
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 6000
    config = _config()
    segs = _segments(m)
    exposure = _exposure(segs)
    reports = _reports(n, segs)

    print(f"benchmark: {m} segments, {n} reports")

    t0 = time.perf_counter()
    records, _summary = pipeline.run(reports, segs, config)
    t1 = time.perf_counter()
    result = analyze(records, reports, segs, exposure, config)
    t2 = time.perf_counter()
    geojson = build_geojson(result.segments, segs)
    t3 = time.perf_counter()

    print(f"  pipeline (dedupe/geocode/snap/classify/quality): {t1 - t0:7.3f} s")
    print(f"  statistics (rates+CIs, bias, KDE, Getis-Ord):     {t2 - t1:7.3f} s")
    print(f"  build geojson:                                    {t3 - t2:7.3f} s")
    print(f"  TOTAL:                                            {t3 - t0:7.3f} s")
    print(f"  throughput: {n / (t3 - t0):,.0f} reports/s; features: {len(geojson['features'])}")


if __name__ == "__main__":
    main()
