#!/usr/bin/env python3
"""Generate the deterministic, synthetic Davis test fixtures — a full street grid.

The streets are a downtown-Davis-style grid: lettered avenues (A–E) run
north-south, numbered streets (1st–5th) run east-west, and every block between
two intersections is a segment, so the map reads like a real street network.

Only TWELVE of the blocks carry exposure data and reports — those are the
analyzed segments. The rest of the grid is published as **context** with no
exposure (shown gray on the map); having no denominator, they are excluded from
the rates, the Getis-Ord statistic, and the bias analysis, so the known-answer
results are unchanged:

  * seg-06 ("5th St (C–D)") is the planted hotspot: low exposure, many reports ->
    the highest rate and the centre of a significant Getis-Ord cluster along the
    5th St corridor (seg-05/06/07) and its cross streets (seg-02/10).
  * seg-03 ("3rd St (B–C)") is the busy decoy: high exposure with the MOST raw
    reports, but a low rate -> not near the top once normalized.

Run from the repo root:  python tools/make_fixtures.py
Outputs are committed; tests read the static files, so test runs need no RNG.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from itertools import pairwise
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "tests" / "fixtures" / "davis"


def ordinal(n: int) -> str:
    suffix = "th" if 11 <= n % 100 <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


# A full-city lattice ~3.5 km across: 20 lettered avenues (A–T) run north-south,
# 20 numbered streets (1st–20th) run east-west. The twelve analyzed blocks sit in
# the centre; the rest of the grid is published as no-exposure context.
AVE = [chr(ord("A") + j) for j in range(20)]  # A..T
ST = [ordinal(i) for i in range(1, 21)]  # 1st..20th
LON = {a: -121.7460 + j * 0.0020 for j, a in enumerate(AVE)}
LAT = {s: 38.5430 + i * 0.0016 for i, s in enumerate(ST)}

# segment_id -> (name, exposure, {hazard_type: count}). These twelve blocks carry
# data; every other block in the grid is published as no-exposure context.
DATA: dict[str, tuple[str, float, dict[str, int]]] = {
    "seg-06": (
        "5th St (C–D)",
        300.0,
        {"close_pass": 4, "dooring": 1, "surface_hazard": 1},
    ),  # HOTSPOT
    "seg-05": ("5th St (B–C)", 400.0, {"close_pass": 6}),  # cluster
    "seg-07": ("5th St (D–E)", 400.0, {"close_pass": 6}),  # cluster
    "seg-02": ("C St (4th–5th)", 400.0, {"close_pass": 6}),  # cluster cross street
    "seg-10": ("D St (4th–5th)", 400.0, {"close_pass": 6}),  # cluster cross street
    "seg-03": (
        "3rd St (B–C)",
        8000.0,
        {"close_pass": 12, "surface_hazard": 5, "debris": 3},
    ),  # BUSY decoy
    "seg-01": ("B St (1st–2nd)", 1500.0, {"close_pass": 4}),  # published but uncertain
    "seg-04": ("D St (1st–2nd)", 1500.0, {"close_pass": 1}),  # withheld (k-anonymity)
    "seg-08": ("A St (1st–2nd)", 1500.0, {"close_pass": 1}),  # withheld
    "seg-11": ("A St (4th–5th)", 1500.0, {"close_pass": 1}),  # withheld
    "seg-09": ("1st St (A–B)", 1500.0, {}),  # zero reports
    "seg-12": ("2nd St (D–E)", 1500.0, {}),  # zero reports
}

MODES = ["cyclist", "cyclist", "cyclist", "pedestrian", "scooter"]
SEVERITIES = ["near_miss", "near_miss", "near_miss", "minor", "serious"]


def grid_blocks() -> dict[str, tuple[tuple[float, float], tuple[float, float]]]:
    """Every block in the lattice -> name: ((lat0, lon0), (lat1, lon1))."""
    blocks: dict[str, tuple[tuple[float, float], tuple[float, float]]] = {}
    for s in ST:  # east-west streets
        for a, b in pairwise(AVE):
            blocks[f"{s} St ({a}–{b})"] = ((LAT[s], LON[a]), (LAT[s], LON[b]))
    for a in AVE:  # north-south avenues
        for s0, s1 in pairwise(ST):
            blocks[f"{a} St ({s0}–{s1})"] = ((LAT[s0], LON[a]), (LAT[s1], LON[a]))
    return blocks


def point_on(
    p0: tuple[float, float], p1: tuple[float, float], t: float, perp: float
) -> tuple[float, float]:
    lat = p0[0] + t * (p1[0] - p0[0])
    lon = p0[1] + t * (p1[1] - p0[1])
    if p0[0] == p1[0]:  # east-west -> offset latitude
        lat += perp
    else:  # north-south -> offset longitude
        lon += perp
    return round(lat, 6), round(lon, 6)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    blocks = grid_blocks()
    name_to_data_id = {name: sid for sid, (name, _, _) in DATA.items()}
    for name in name_to_data_id:
        assert name in blocks, f"data block not in grid: {name}"

    # Assign ids: the twelve data blocks keep theirs; the rest become context
    # segments seg-13.. in name order (deterministic).
    segments: dict[str, tuple[str, tuple[float, float], tuple[float, float]]] = {}
    for sid, (name, _, _) in DATA.items():
        segments[sid] = (name, blocks[name][0], blocks[name][1])
    n = 13
    for name in sorted(blocks):
        if name in name_to_data_id:
            continue
        segments[f"seg-{n:02d}"] = (name, blocks[name][0], blocks[name][1])
        n += 1

    streets = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {
                    "type": "LineString",
                    "coordinates": [
                        [segments[sid][1][1], segments[sid][1][0]],
                        [segments[sid][2][1], segments[sid][2][0]],
                    ],
                },
                "properties": {"segment_id": sid, "name": segments[sid][0]},
            }
            for sid in sorted(segments)
        ],
    }
    exposure = {
        "segments": [
            {
                "segment_id": sid,
                "estimate": DATA[sid][1],
                "source": "synthetic_bike_count",
                "date": "2026-05-01",
            }
            for sid in sorted(DATA)
        ]
    }

    t0 = datetime(2026, 6, 10, 7, 0, 0, tzinfo=timezone(timedelta(hours=-7)))
    reports: list[dict[str, object]] = []
    i = 0
    first_hot: dict[str, object] | None = None
    low_acc_done = False
    for sid in sorted(DATA):
        _, _, hazards = DATA[sid]
        p0, p1 = segments[sid][1], segments[sid][2]
        for hazard, k in sorted(hazards.items()):
            for j in range(k):
                i += 1
                t = 0.3 + 0.4 * ((j + 0.5) / max(k, 1))
                perp = 0.00003 if i % 2 == 0 else -0.00003
                lat, lon = point_on(p0, p1, t, perp)
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
    snapped = sum(sum(h.values()) for _, _, h in DATA.values())
    print(
        f"wrote {len(segments)} grid segments ({len(DATA)} with data), "
        f"{len(reports)} reports to {OUT}"
    )
    print(f"  expected: snapped≈{snapped}, duplicates_removed=1, unsnapped=1")


if __name__ == "__main__":
    main()
