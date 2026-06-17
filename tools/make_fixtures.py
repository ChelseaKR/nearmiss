#!/usr/bin/env python3
"""Generate the deterministic, synthetic test fixtures for nearmiss.

The fixtures encode KNOWN ANSWERS so the pipeline and statistics can be tested
against ground truth (see tests/README.md):

  * seg-06 is the planted hotspot: LOW exposure, MANY reports -> highest rate,
    and the centre of a local cluster so Getis-Ord Gi* should flag it.
  * seg-03 is the "busy but not dangerous" decoy: HIGH exposure with the MOST
    raw reports, but a LOW rate -> must NOT rank near the top once normalized.

Run from the repo root:  python tools/make_fixtures.py
Outputs are committed; tests read the static files, so test runs need no RNG.
"""

from __future__ import annotations

import json
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "tests" / "fixtures" / "davis"

BASE_LAT = 38.5449
BASE_LON = -121.7405
ROW_STEP = 0.0025  # ~276 m north
COL_STEP = 0.0030  # ~260 m east
HALF_LEN = 0.0008  # half segment length in lon degrees (~70 m)

# segment -> (exposure, {hazard_type: count}).
# Rates (count / exposure * 1000): seg-06 = 20 (hotspot), its band neighbours
# seg-02/05/07/10 = 15 (the elevated cluster), seg-03 = 2.5 (busy decoy, most raw
# reports but low rate), everything else ~<=1.3. This makes seg-06 both the
# highest rate AND the uniquely Getis-Ord-significant segment.
PLAN: dict[str, tuple[float, dict[str, int]]] = {
    "seg-06": (300.0, {"close_pass": 4, "dooring": 1, "surface_hazard": 1}),  # HOTSPOT, rate 20
    "seg-02": (400.0, {"close_pass": 6}),  # cluster, rate 15
    "seg-05": (400.0, {"close_pass": 6}),  # cluster, rate 15
    "seg-07": (400.0, {"close_pass": 6}),  # cluster, rate 15
    "seg-10": (400.0, {"close_pass": 6}),  # cluster, rate 15
    "seg-03": (8000.0, {"close_pass": 12, "surface_hazard": 5, "debris": 3}),  # BUSY decoy
    "seg-01": (1500.0, {"close_pass": 4}),  # published but uncertain (3 <= n < small_n)
    "seg-04": (1500.0, {"close_pass": 1}),  # withheld (n < min_publish_n)
    "seg-08": (1500.0, {"close_pass": 1}),  # withheld
    "seg-09": (1500.0, {}),
    "seg-11": (1500.0, {"close_pass": 1}),  # withheld
    "seg-12": (1500.0, {}),
}

MODES = ["cyclist", "cyclist", "cyclist", "pedestrian", "scooter"]
SEVERITIES = ["near_miss", "near_miss", "near_miss", "minor", "serious"]


def seg_rowcol(n: int) -> tuple[int, int]:
    return (n - 1) // 4, (n - 1) % 4


def seg_centroid(seg_id: str) -> tuple[float, float]:
    n = int(seg_id.split("-")[1])
    row, col = seg_rowcol(n)
    return BASE_LAT + row * ROW_STEP, BASE_LON + col * COL_STEP


def seg_coords(seg_id: str) -> list[list[float]]:
    lat, lon = seg_centroid(seg_id)
    # GeoJSON order is [lon, lat].
    return [[lon - HALF_LEN, lat], [lon + HALF_LEN, lat]]


def uid(i: int) -> str:
    return f"00000000-0000-4000-8000-{i:012x}"


def main() -> None:
    rng = random.Random(7)
    OUT.mkdir(parents=True, exist_ok=True)

    # --- streets.geojson ---
    streets = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "LineString", "coordinates": seg_coords(f"seg-{n:02d}")},
                "properties": {"segment_id": f"seg-{n:02d}", "name": f"Street {f'seg-{n:02d}'}"},
            }
            for n in range(1, 13)
        ],
    }

    # --- exposure.json ---
    exposure = {
        "segments": [
            {
                "segment_id": sid,
                "estimate": PLAN[sid][0],
                "source": "synthetic_bike_count",
                "date": "2026-05-01",
            }
            for sid in sorted(PLAN)
        ]
    }

    # --- reports.json ---
    t0 = datetime(2026, 6, 10, 7, 0, 0, tzinfo=timezone(timedelta(hours=-7)))
    reports: list[dict[str, object]] = []
    i = 0
    first_hot_report: dict[str, object] | None = None
    low_acc_done = False

    # Reports are spaced 20 minutes apart, comfortably beyond the 600 s dedupe
    # window, so distinct same-segment reports are NOT collapsed — only the one
    # deliberately planted duplicate (below) is.
    for sid in sorted(PLAN):
        lat, lon = seg_centroid(sid)
        _, hazards = PLAN[sid]
        for hazard, k in sorted(hazards.items()):
            for _ in range(k):
                i += 1
                rlat = lat + rng.uniform(-0.00006, 0.00006)
                rlon = lon + rng.uniform(-0.0006, 0.0006)
                location: dict[str, object] = {"lat": round(rlat, 6), "lon": round(rlon, 6)}
                rec: dict[str, object] = {
                    "schema_version": "1.0.0",
                    "id": uid(i),
                    "occurred_at": (t0 + timedelta(minutes=20 * i)).isoformat(),
                    "location": location,
                    "mode": MODES[i % len(MODES)],
                    "hazard_type": hazard,
                    "severity": SEVERITIES[i % len(SEVERITIES)],
                }
                # Give the first seg-06 report a reporter token (for the dedupe test).
                if sid == "seg-06" and first_hot_report is None:
                    rec["reporter_token"] = "reporter-hot-001"
                    first_hot_report = rec
                # One low-accuracy report on seg-01 (for the quality-flag test).
                if sid == "seg-01" and not low_acc_done:
                    location["accuracy_m"] = 60.0
                    low_acc_done = True
                reports.append(rec)

    # Duplicate of the first seg-06 report: same reporter, same place, +30s -> deduped.
    assert first_hot_report is not None
    i += 1
    dup = dict(first_hot_report)
    dup["id"] = uid(i)
    base_dt = datetime.fromisoformat(str(first_hot_report["occurred_at"]))
    dup["occurred_at"] = (base_dt + timedelta(seconds=30)).isoformat()
    loc = first_hot_report["location"]
    assert isinstance(loc, dict)
    dup["location"] = dict(loc)
    reports.append(dup)

    # One unsnapped report far from any segment (for the unsnapped/quality test).
    i += 1
    reports.append(
        {
            "schema_version": "1.0.0",
            "id": uid(i),
            "occurred_at": (t0 + timedelta(minutes=20 * i)).isoformat(),
            "location": {"lat": round(BASE_LAT - 0.01, 6), "lon": round(BASE_LON - 0.01, 6)},
            "mode": "cyclist",
            "hazard_type": "close_pass",
            "severity": "near_miss",
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
    snapped_total = sum(sum(h.values()) for _, h in PLAN.values())
    print(f"wrote {len(streets['features'])} segments, {len(reports)} reports to {OUT}")
    print(f"  expected: snapped≈{snapped_total}, duplicates_removed=1, unsnapped=1")


if __name__ == "__main__":
    main()
