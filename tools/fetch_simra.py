#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Convert real SimRa bicycle near-miss data into the nearmiss *intake* format.

SimRa (https://github.com/simra-project/dataset, TU Berlin) is a crowdsourced,
openly-published dataset of **bicycle near-crashes** with GPS — the closest
real-world analogue to nearmiss's own input, and unusual in that the same source
also carries the *ride* GPS traces, which are a natural exposure denominator.

Each SimRa ride file has an incidents section (one annotated near-miss per row:
``lat,lon,ts,…,incident,…,scary,…``) then a divider then the ride GPS trace. This
tool reads a directory of such files and emits reports conforming to
``schema/report.schema.json`` — ready for ``nearmiss intake``. It does not touch
exposure or the street network (see docs/REAL-DATA.md); those are separate inputs,
though SimRa's ride traces can supply both.

Usage:
    python tools/fetch_simra.py --dir path/to/SimRa/Berlin_2023_03 --out reports.json
    python tools/fetch_simra.py --dir path/to/SimRa --city berlin --out reports.json

Stdlib only, to match the project's minimal-dependency stance.
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

DIVIDER = "========================="
_NS = uuid.uuid5(uuid.NAMESPACE_URL, "https://simra-project.github.io/")

# Convenience bounding boxes (W, S, E, N) for SimRa regions.
CITY_BBOX = {
    "berlin": (13.0, 52.30, 13.77, 52.70),
    "london": (-0.55, 51.28, 0.30, 51.70),
    "munich": (11.36, 48.06, 11.72, 48.25),
}

# SimRa incident enum -> nearmiss closed hazard vocabulary. SimRa's order is
# Close pass, pulling in/out, near left hook, near right hook, head-on,
# tailgating, near-dooring, dodging an obstacle, other. Where our vocabulary
# can't represent the distinction we fall back to "other" rather than overstate.
_INCIDENT_TO_HAZARD = {
    "1": "close_pass",
    "7": "dooring",  # near-dooring
    "8": "surface_hazard",  # dodging an obstacle
}


def hazard_from_code(code: str) -> str:
    return _INCIDENT_TO_HAZARD.get(code.strip(), "other")


def _iso_from_ts(ts: str) -> str | None:
    """SimRa timestamps are epoch milliseconds (UTC). Return RFC 3339 'Z' time."""
    try:
        ms = int(float(ts))
    except (TypeError, ValueError):
        return None
    if ms <= 0:
        return None
    return datetime.fromtimestamp(ms / 1000.0, tz=UTC).isoformat().replace("+00:00", "Z")


def parse_incidents(text: str) -> list[dict[str, str]]:
    """Return the annotated-incident rows (as dicts) from one SimRa ride file."""
    if DIVIDER not in text:
        return []
    head = text.split(DIVIDER)[0].splitlines()
    if len(head) < 2:
        return []
    cols = head[1].split(",")
    out: list[dict[str, str]] = []
    for line in head[2:]:
        if not line.strip():
            continue
        out.append(dict(zip(cols, line.split(","), strict=False)))
    return out


def in_bbox(lat: float, lon: float, bbox: tuple[float, float, float, float] | None) -> bool:
    if bbox is None:
        return True
    w, s, e, n = bbox
    return w <= lon <= e and s <= lat <= n


def map_incident(
    row: dict[str, str], source: str, bbox: tuple[float, float, float, float] | None
) -> dict[str, Any] | None:
    lat_s, lon_s, inc = row.get("lat", ""), row.get("lon", ""), row.get("incident", "")
    # An un-annotated row has empty coordinates and incident == -5.
    if not lat_s.strip() or not lon_s.strip() or inc.strip() in ("", "-5"):
        return None
    try:
        lat, lon = float(lat_s), float(lon_s)
    except ValueError:
        return None
    if not (-90 <= lat <= 90 and -180 <= lon <= 180) or not in_bbox(lat, lon, bbox):
        return None
    occurred_at = _iso_from_ts(row.get("ts", ""))
    if occurred_at is None:
        return None
    key = f"simra:{source}:{lat:.6f},{lon:.6f}:{row.get('ts', '')}"
    return {
        "schema_version": "1.0.0",
        "id": str(uuid.uuid5(_NS, key)),
        "occurred_at": occurred_at,
        "location": {"lat": lat, "lon": lon},
        "mode": "cyclist",  # SimRa reporters are cyclists
        "hazard_type": hazard_from_code(inc),
        "severity": "near_miss",  # SimRa records near-crashes, never verified collisions
    }


def collect(root: Path, bbox: tuple[float, float, float, float] | None) -> list[dict[str, Any]]:
    reports: list[dict[str, Any]] = []
    files = [p for p in root.rglob("*") if p.is_file() and p.name.startswith(("VM2_", "VM"))]
    for fp in files:
        try:
            text = fp.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for row in parse_incidents(text):
            rep = map_incident(row, fp.name, bbox)
            if rep is not None:
                reports.append(rep)
    return reports


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--dir", required=True, help="A SimRa region folder (or a parent of folders).")
    p.add_argument("--city", choices=sorted(CITY_BBOX), help="Restrict to a known city's bbox.")
    p.add_argument("--bbox", help="Bounding box W,S,E,N in degrees (overrides --city).")
    p.add_argument("--out", default="-", help="Output reports.json ('-' for stdout).")
    return p.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    bbox: tuple[float, float, float, float] | None = None
    if args.bbox:
        parts = [float(x) for x in args.bbox.split(",")]
        if len(parts) != 4:
            print("error: --bbox must be W,S,E,N", file=sys.stderr)
            return 2
        bbox = (parts[0], parts[1], parts[2], parts[3])
    elif args.city:
        bbox = CITY_BBOX[args.city]

    reports = collect(Path(args.dir), bbox)
    text = json.dumps({"reports": reports}, ensure_ascii=False, indent=2)
    if args.out == "-":
        print(text)
    else:
        Path(args.out).write_text(text + "\n", encoding="utf-8")

    where = "stdout" if args.out == "-" else args.out
    print(f"fetch_simra: wrote {len(reports)} real near-miss reports to {where}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
