#!/usr/bin/env python3
"""Generate a SECOND synthetic demo city (Riverside, CA) — proving config-over-code.

Same engine, a different city, with its own planted hotspot. Deterministic (no
RNG): report offsets are fixed by index. Run from the repo root:
    python tools/make_riverside.py
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "tests" / "fixtures" / "riverside"

BASE_LAT = 33.9533
BASE_LON = -117.3962
ROW_STEP = 0.0025
COL_STEP = 0.0030
HALF = 0.0008

NAMES = {
    "rs-1": "Main St (5th–6th)",
    "rs-2": "Market St (5th–6th)",
    "rs-3": "University Ave (Market–Lemon)",  # HOTSPOT
    "rs-4": "Mission Inn Ave (Main–Market)",
    "rs-5": "7th St (Market–Lemon)",
    "rs-6": "Lemon St (University–10th)",
}
# segment -> (exposure, {hazard_type: count})
PLAN = {
    "rs-3": (250.0, {"close_pass": 6, "dooring": 2}),  # HOTSPOT, rate 32
    "rs-2": (800.0, {"close_pass": 4}),  # cluster neighbour, rate 5
    "rs-6": (800.0, {"close_pass": 4}),  # cluster neighbour, rate 5
    "rs-1": (1500.0, {"close_pass": 3}),  # published, uncertain (n=3)
    "rs-4": (1500.0, {"close_pass": 1}),  # withheld (n < min_publish_n)
    "rs-5": (1500.0, {}),  # zero reports
}
MODES = ["cyclist", "pedestrian", "cyclist", "scooter"]
SEVERITIES = ["near_miss", "minor", "near_miss", "serious"]


def rowcol(n: int) -> tuple[int, int]:
    return (n - 1) // 3, (n - 1) % 3


def centroid(sid: str) -> tuple[float, float]:
    row, col = rowcol(int(sid.split("-")[1]))
    return BASE_LAT + row * ROW_STEP, BASE_LON + col * COL_STEP


def coords(sid: str) -> list[list[float]]:
    lat, lon = centroid(sid)
    return [[lon - HALF, lat], [lon + HALF, lat]]


def uid(i: int) -> str:
    return f"00000000-0000-4000-8000-{i:012x}"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    streets = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "LineString", "coordinates": coords(f"rs-{n}")},
                "properties": {"segment_id": f"rs-{n}", "name": NAMES[f"rs-{n}"]},
            }
            for n in range(1, 7)
        ],
    }
    exposure_rows = [
        {
            "segment_id": sid,
            "estimate": PLAN[sid][0],
            "source": "synthetic_count",
            "date": "2026-05-01",
            "tier": "observed",
        }
        for sid in sorted(PLAN)
    ]
    # FIX-04: rs-1 also gets a corroborating modeled reading, lower than the
    # observed count, so the published dataset carries one real multi-source
    # disagreement example (METHODOLOGY §3.1) without moving rs-1's own rate.
    for row in exposure_rows:
        if row["segment_id"] == "rs-1":
            row["sources"] = [
                {
                    "estimate": 1200.0,
                    "source": "synthetic_demand_model",
                    "date": "2026-04-15",
                    "tier": "modeled",
                }
            ]
    exposure = {"segments": exposure_rows}
    t0 = datetime(2026, 6, 1, 8, 0, 0, tzinfo=timezone(timedelta(hours=-7)))
    reports: list[dict[str, object]] = []
    i = 0
    for sid in sorted(PLAN):
        lat, lon = centroid(sid)
        _, hazards = PLAN[sid]
        for hazard, k in sorted(hazards.items()):
            for j in range(k):
                i += 1
                # Fixed, deterministic offsets within the segment, ~3 m cross-track.
                rlat = round(lat + 0.00003, 6)
                rlon = round(lon + (j - k / 2) * 0.0002, 6)
                reports.append(
                    {
                        "schema_version": "1.0.0",
                        "id": uid(i),
                        "occurred_at": (t0 + timedelta(minutes=20 * i)).isoformat(),
                        "location": {"lat": rlat, "lon": rlon},
                        "mode": MODES[i % len(MODES)],
                        "hazard_type": hazard,
                        "severity": SEVERITIES[i % len(SEVERITIES)],
                    }
                )
    (OUT / "streets.geojson").write_text(
        json.dumps(streets, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (OUT / "exposure.json").write_text(
        json.dumps(exposure, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (OUT / "reports.json").write_text(
        json.dumps({"reports": reports}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"wrote 6 segments, {len(reports)} reports to {OUT}")


if __name__ == "__main__":
    main()
