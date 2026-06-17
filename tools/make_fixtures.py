#!/usr/bin/env python3
"""Generate the deterministic, synthetic Davis test fixtures — a connected grid.

The streets form a downtown-Davis-style grid: lettered avenues (A, B, C, …) run
north-south by longitude, numbered/named streets (3rd, 5th, …) run east-west by
latitude, and each segment is a block between two intersections. So the network
actually connects and renders like a street map rather than a row of dashes.

The fixtures encode KNOWN ANSWERS (see tests/README.md):
  * seg-06 ("5th St (C–D)") is the planted hotspot: LOW exposure, MANY reports ->
    the highest rate and the centre of a significant Getis-Ord cluster along the
    5th St corridor (seg-05/06/07) and its cross streets (seg-02/10).
  * seg-03 ("3rd St (B–C)") is the busy decoy: HIGH exposure with the MOST raw
    reports, but a LOW rate -> not near the top once normalized.

Run from the repo root:  python tools/make_fixtures.py
Outputs are committed; tests read the static files, so test runs need no RNG.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "tests" / "fixtures" / "davis"

# North-south avenues (longitude) and east-west streets (latitude).
LON = {
    "A": -121.7460,
    "B": -121.7440,
    "C": -121.7420,
    "D": -121.7400,
    "E": -121.7380,
    "F": -121.7360,
}
LAT = {
    "Russell": 38.5410,
    "1st": 38.5430,
    "2nd": 38.5445,
    "3rd": 38.5460,
    "4th": 38.5475,
    "5th": 38.5490,
    "8th": 38.5535,
    "Covell": 38.5560,
}

# segment_id -> (name, (lat0, lon0), (lat1, lon1)). Each is a block between two
# intersections; the 5th St corridor and its cross streets connect at shared nodes.
SEGMENTS: dict[str, tuple[str, tuple[float, float], tuple[float, float]]] = {
    "seg-01": ("B St (1st–2nd)", (LAT["1st"], LON["B"]), (LAT["2nd"], LON["B"])),
    "seg-02": ("C St (4th–5th)", (LAT["4th"], LON["C"]), (LAT["5th"], LON["C"])),
    "seg-03": ("3rd St (B–C)", (LAT["3rd"], LON["B"]), (LAT["3rd"], LON["C"])),
    "seg-04": ("D St (1st–2nd)", (LAT["1st"], LON["D"]), (LAT["2nd"], LON["D"])),
    "seg-05": ("5th St (B–C)", (LAT["5th"], LON["B"]), (LAT["5th"], LON["C"])),
    "seg-06": ("5th St (C–D)", (LAT["5th"], LON["C"]), (LAT["5th"], LON["D"])),
    "seg-07": ("5th St (D–E)", (LAT["5th"], LON["D"]), (LAT["5th"], LON["E"])),
    "seg-08": ("F St (2nd–3rd)", (LAT["2nd"], LON["F"]), (LAT["3rd"], LON["F"])),
    "seg-09": ("8th St (B–C)", (LAT["8th"], LON["B"]), (LAT["8th"], LON["C"])),
    "seg-10": ("D St (4th–5th)", (LAT["4th"], LON["D"]), (LAT["5th"], LON["D"])),
    "seg-11": ("Anderson Rd (5th–8th)", (LAT["5th"], LON["F"]), (LAT["8th"], LON["F"])),
    "seg-12": ("Covell Blvd (E–F)", (LAT["Covell"], LON["E"]), (LAT["Covell"], LON["F"])),
}

# segment_id -> (exposure, {hazard_type: count}).
PLAN: dict[str, tuple[float, dict[str, int]]] = {
    "seg-06": (300.0, {"close_pass": 4, "dooring": 1, "surface_hazard": 1}),  # HOTSPOT, rate 20
    "seg-02": (400.0, {"close_pass": 6}),  # cluster, rate 15
    "seg-05": (400.0, {"close_pass": 6}),  # cluster, rate 15
    "seg-07": (400.0, {"close_pass": 6}),  # cluster, rate 15
    "seg-10": (400.0, {"close_pass": 6}),  # cluster, rate 15
    "seg-03": (
        8000.0,
        {"close_pass": 12, "surface_hazard": 5, "debris": 3},
    ),  # BUSY decoy, rate 2.5
    "seg-01": (1500.0, {"close_pass": 4}),  # published but uncertain (3 <= n < small_n)
    "seg-04": (1500.0, {"close_pass": 1}),  # withheld (n < min_publish_n)
    "seg-08": (1500.0, {"close_pass": 1}),  # withheld
    "seg-09": (1500.0, {}),
    "seg-11": (1500.0, {"close_pass": 1}),  # withheld
    "seg-12": (1500.0, {}),
}

MODES = ["cyclist", "cyclist", "cyclist", "pedestrian", "scooter"]
SEVERITIES = ["near_miss", "near_miss", "near_miss", "minor", "serious"]


def point_on(seg_id: str, t: float, perp: float) -> tuple[float, float]:
    """A point at fraction t along the segment, offset ~perp degrees cross-track."""
    (lat0, lon0), (lat1, lon1) = SEGMENTS[seg_id][1], SEGMENTS[seg_id][2]
    lat = lat0 + t * (lat1 - lat0)
    lon = lon0 + t * (lon1 - lon0)
    if lat0 == lat1:  # east-west block -> offset latitude
        lat += perp
    else:  # north-south block -> offset longitude
        lon += perp
    return round(lat, 6), round(lon, 6)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)

    streets = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {
                    "type": "LineString",
                    "coordinates": [
                        [SEGMENTS[s][1][1], SEGMENTS[s][1][0]],
                        [SEGMENTS[s][2][1], SEGMENTS[s][2][0]],
                    ],
                },
                "properties": {"segment_id": s, "name": SEGMENTS[s][0]},
            }
            for s in sorted(SEGMENTS)
        ],
    }
    exposure = {
        "segments": [
            {
                "segment_id": s,
                "estimate": PLAN[s][0],
                "source": "synthetic_bike_count",
                "date": "2026-05-01",
            }
            for s in sorted(PLAN)
        ]
    }

    t0 = datetime(2026, 6, 10, 7, 0, 0, tzinfo=timezone(timedelta(hours=-7)))
    reports: list[dict[str, object]] = []
    i = 0
    first_hot: dict[str, object] | None = None
    low_acc_done = False

    for sid in sorted(PLAN):
        _, hazards = PLAN[sid]
        for hazard, k in sorted(hazards.items()):
            for j in range(k):
                i += 1
                # Spread reports through the middle 30–70% of the block; tiny
                # cross-track offset so they snap but distinct positions remain.
                t = 0.3 + 0.4 * ((j + 0.5) / max(k, 1))
                perp = 0.00003 if i % 2 == 0 else -0.00003
                lat, lon = point_on(sid, t, perp)
                location: dict[str, object] = {"lat": lat, "lon": lon}
                rec: dict[str, object] = {
                    "schema_version": "1.0.0",
                    "id": f"00000000-0000-4000-8000-{i:012x}",
                    "occurred_at": (t0 + timedelta(minutes=20 * i)).isoformat(),
                    "location": location,
                    "mode": MODES[i % len(MODES)],
                    "hazard_type": hazard,
                    "severity": SEVERITIES[i % len(SEVERITIES)],
                }
                if sid == "seg-06" and first_hot is None:
                    rec["reporter_token"] = "reporter-hot-001"
                    first_hot = rec
                if sid == "seg-01" and not low_acc_done:
                    location["accuracy_m"] = 60.0
                    low_acc_done = True
                reports.append(rec)

    # Planted duplicate of the first seg-06 report (same place, +30s) -> deduped.
    assert first_hot is not None
    i += 1
    dup = dict(first_hot)
    dup["id"] = f"00000000-0000-4000-8000-{i:012x}"
    base_dt = datetime.fromisoformat(str(first_hot["occurred_at"]))
    dup["occurred_at"] = (base_dt + timedelta(seconds=30)).isoformat()
    loc = first_hot["location"]
    assert isinstance(loc, dict)
    dup["location"] = dict(loc)
    reports.append(dup)

    # One unsnapped report far from any segment.
    i += 1
    reports.append(
        {
            "schema_version": "1.0.0",
            "id": f"00000000-0000-4000-8000-{i:012x}",
            "occurred_at": (t0 + timedelta(minutes=20 * i)).isoformat(),
            "location": {"lat": round(LAT["1st"] - 0.01, 6), "lon": round(LON["A"] - 0.01, 6)},
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
    snapped = sum(sum(h.values()) for _, h in PLAN.values())
    print(f"wrote {len(SEGMENTS)} segments, {len(reports)} reports to {OUT}")
    print(f"  expected: snapped≈{snapped}, duplicates_removed=1, unsnapped=1")


if __name__ == "__main__":
    main()
