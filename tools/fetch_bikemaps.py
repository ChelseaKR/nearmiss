#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Fetch real cycling near-miss / collision / hazard reports from BikeMaps.org
and emit them in the nearmiss *intake* format (``schema/report.schema.json``).

BikeMaps.org (https://bikemaps.org, SPARLab/BikeMaps) is a crowdsourced global
map of cycling collisions, near misses, hazards, and thefts. It is the closest
real-world analogue to nearmiss's own input: citizen-reported near misses, which
by definition never reach a police collision report. This tool is the bridge
from that real data to this pipeline — it does **not** invent data, it maps
BikeMaps' public records onto our intake contract so they can flow through the
same exposure-normalization, confidence-interval, and significance stages.

Two sources, same mapping:

  * ``--bbox W,S,E,N`` (or ``--city``) pulls live GeoJSON from the public
    endpoints (``/nearmiss.json``, ``/collisions.json``, ``/hazards.json``) and
    keeps the features inside the bounding box.
  * ``--from-file export.geojson`` reads a GeoJSON file you already have — e.g.
    BikeMaps' own admin "Export" (see their docs/query-and-export-data.md), or a
    saved API response — so this works with no network access at all.

What this tool does NOT do: it does not attach exposure denominators, rates, or
intervals (those are computed downstream, never claimed at intake), and it does
not fabricate the street network or bicycle-count exposure a full real-city run
also needs. See docs/REAL-DATA.md for the complete recipe and the honest gaps.

Usage:
    python tools/fetch_bikemaps.py --city victoria --out reports.json
    python tools/fetch_bikemaps.py --bbox -123.5,48.4,-123.3,48.5 --out reports.json
    python tools/fetch_bikemaps.py --from-file bikemaps-export.geojson --out reports.json

Stdlib only, to match the project's minimal-dependency stance.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any

BASE_URL = "https://bikemaps.org"

# Public GeoJSON endpoints (mapApp/urls.py, format_suffix_patterns allowed=['json']).
ENDPOINTS = {
    "nearmiss": "/nearmiss.json",
    "collision": "/collisions.json",
    "hazard": "/hazards.json",
}

# A few convenience bounding boxes (W, S, E, N) for cities where BikeMaps data is
# dense. Add your own; a bbox is all the pipeline needs to scope an extract.
CITY_BBOX = {
    "victoria": (-123.46, 48.40, -123.28, 48.50),  # Victoria, BC — BikeMaps' home, densest data
    "vancouver": (-123.27, 49.20, -123.02, 49.32),  # Vancouver, BC
    "davis": (-121.78, 38.53, -121.70, 38.57),  # Davis, CA — sparse; for parity with the demo
    "sacramento": (-121.56, 38.44, -121.36, 38.68),  # Sacramento, CA
}

# Stable namespace so the same BikeMaps record always yields the same report id
# (reproducibility). The id is derived only from the public record key, never
# from anything personal.
_NS = uuid.uuid5(uuid.NAMESPACE_URL, "https://bikemaps.org/")

# --- Crosswalk: BikeMaps vocabulary -> nearmiss intake enums -----------------
# Derived from SPARLab/BikeMaps mapApp/models/incident.py (INCIDENT_WITH_CHOICES,
# INJURY_CHOICES). Our intake hazard_type vocabulary is the closed set
# {close_pass, dooring, surface_hazard, sightline, signal, debris, other}; where
# BikeMaps draws a distinction we cannot represent, we fall back to "other"
# rather than overstate the conflict manner. The full crosswalk is in
# docs/REAL-DATA.md.
_INCIDENT_WITH_TO_HAZARD = {
    "Vehicle, passing": "close_pass",
    "Vehicle, open door": "dooring",
    "Pothole": "surface_hazard",
    "Curb": "surface_hazard",
    "Train Tracks": "surface_hazard",
    "Lane divider": "surface_hazard",
    "Roadway": "surface_hazard",
    "Sign/Post": "sightline",
}


def hazard_from_incident_with(value: str | None) -> str:
    if not value:
        return "other"
    if value in _INCIDENT_WITH_TO_HAZARD:
        return _INCIDENT_WITH_TO_HAZARD[value]
    # Any other motor-vehicle conflict (head on, side, angle, rear end, turning)
    # is a real car conflict but not specifically a close pass or dooring; we do
    # not have a generic "vehicle collision" type, so it is honestly "other".
    return "other"


def severity_from_injury(injury: str | None) -> str:
    """Collision severity from BikeMaps INJURY_CHOICES -> our {near_miss, minor,
    serious}. A collision always involved contact, so the floor is "minor"."""
    if not injury:
        return "minor"
    lowered = injury.lower()
    if "hospital" in lowered or "hospitalized" in lowered:
        return "serious"
    return "minor"


def _norm_datetime(value: str | None, utc_offset: str) -> str | None:
    """Return an RFC 3339 date-time with an explicit offset, or None if unusable.
    BikeMaps serializes tz-aware datetimes (usually trailing 'Z'); if a naive
    value slips through we append the configured offset rather than guess."""
    if not value:
        return None
    v = value.strip()
    if v.endswith("Z") or "+" in v[10:] or "-" in v[10:]:
        return v
    return v + utc_offset


def map_feature(feature: dict[str, Any], kind: str, utc_offset: str) -> dict[str, Any] | None:
    geom = feature.get("geometry") or {}
    coords = geom.get("coordinates")
    if geom.get("type") != "Point" or not isinstance(coords, list) or len(coords) < 2:
        return None
    lon, lat = float(coords[0]), float(coords[1])
    if not (-180 <= lon <= 180 and -90 <= lat <= 90):
        return None

    props = feature.get("properties") or {}
    occurred_at = _norm_datetime(props.get("date"), utc_offset)
    if occurred_at is None:
        return None

    if kind == "hazard":
        severity = "near_miss"
        hazard_type = "surface_hazard"
    elif kind == "collision":
        severity = severity_from_injury(props.get("injury"))
        hazard_type = hazard_from_incident_with(props.get("incident_with"))
    else:  # nearmiss
        severity = "near_miss"
        hazard_type = hazard_from_incident_with(props.get("incident_with"))

    pk = props.get("pk")
    key = f"{kind}:{pk}" if pk is not None else f"{kind}:{lat:.6f},{lon:.6f}:{occurred_at}"

    return {
        "schema_version": "1.0.0",
        "id": str(uuid.uuid5(_NS, key)),
        "occurred_at": occurred_at,
        "location": {"lat": lat, "lon": lon},
        "mode": "cyclist",  # BikeMaps reporters are cyclists; the other party is incident_with
        "hazard_type": hazard_type,
        "severity": severity,
    }


def in_bbox(feature: dict[str, Any], bbox: tuple[float, float, float, float]) -> bool:
    coords = (feature.get("geometry") or {}).get("coordinates")
    if not isinstance(coords, list) or len(coords) < 2:
        return False
    lon, lat = coords[0], coords[1]
    w, s, e, n = bbox
    return w <= lon <= e and s <= lat <= n


def fetch_geojson(url: str, timeout: float = 60.0) -> dict[str, Any]:
    req = urllib.request.Request(url, headers={"User-Agent": "nearmiss-fetch-bikemaps/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def collect(
    features_by_kind: dict[str, list[dict[str, Any]]],
    bbox: tuple[float, float, float, float] | None,
    utc_offset: str,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    reports: list[dict[str, Any]] = []
    counts: dict[str, int] = {}
    for kind, feats in features_by_kind.items():
        kept = 0
        for f in feats:
            if bbox is not None and not in_bbox(f, bbox):
                continue
            report = map_feature(f, kind, utc_offset)
            if report is not None:
                reports.append(report)
                kept += 1
        counts[kind] = kept
    return reports, counts


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument(
        "--city", choices=sorted(CITY_BBOX), help="Known city bounding box (live fetch)."
    )
    src.add_argument("--bbox", help="Bounding box W,S,E,N in degrees (live fetch).")
    src.add_argument(
        "--from-file",
        action="append",
        metavar="GEOJSON",
        help="Read a local BikeMaps GeoJSON export instead of the network (repeatable). "
        "Combine with --kind to label the file's incident type.",
    )
    p.add_argument(
        "--kind",
        choices=sorted(ENDPOINTS),
        default="nearmiss",
        help="Incident type to assume for --from-file inputs (default: nearmiss).",
    )
    p.add_argument(
        "--types",
        default="nearmiss,collision,hazard",
        help="Comma list of incident types to fetch live (default: all three).",
    )
    p.add_argument("--out", default="-", help="Output path for reports.json ('-' for stdout).")
    p.add_argument(
        "--utc-offset",
        default="+00:00",
        help="Offset to append to any naive timestamps (default +00:00). BikeMaps "
        "datetimes are normally tz-aware, so this is a fallback.",
    )
    p.add_argument("--base-url", default=BASE_URL, help=argparse.SUPPRESS)
    return p.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    bbox: tuple[float, float, float, float] | None = None
    features_by_kind: dict[str, list[dict[str, Any]]] = {}

    if args.from_file:
        for path in args.from_file:
            with Path(path).open(encoding="utf-8") as fh:
                gj = json.load(fh)
            features_by_kind.setdefault(args.kind, []).extend(gj.get("features", []))
    else:
        if args.city:
            bbox = CITY_BBOX[args.city]
        else:
            parts = [float(x) for x in args.bbox.split(",")]
            if len(parts) != 4:
                print("error: --bbox must be W,S,E,N", file=sys.stderr)
                return 2
            bbox = (parts[0], parts[1], parts[2], parts[3])
        for kind in [k.strip() for k in args.types.split(",") if k.strip()]:
            if kind not in ENDPOINTS:
                print(f"error: unknown type '{kind}'", file=sys.stderr)
                return 2
            url = args.base_url + ENDPOINTS[kind]
            try:
                gj = fetch_geojson(url)
            except (urllib.error.URLError, TimeoutError) as exc:  # pragma: no cover - network
                print(f"error: could not fetch {url}: {exc}", file=sys.stderr)
                print(
                    "hint: this host may be blocked by your network egress policy. "
                    "Use BikeMaps' admin GeoJSON export and pass it with --from-file.",
                    file=sys.stderr,
                )
                return 1
            features_by_kind.setdefault(kind, []).extend(gj.get("features", []))

    reports, counts = collect(features_by_kind, bbox, args.utc_offset)
    payload = {"reports": reports}
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.out == "-":
        print(text)
    else:
        with Path(args.out).open("w", encoding="utf-8") as fh:
            fh.write(text + "\n")

    summary = ", ".join(f"{k}={v}" for k, v in sorted(counts.items()))
    where = "stdout" if args.out == "-" else args.out
    print(
        f"fetch_bikemaps: wrote {len(reports)} reports to {where} ({summary or 'no features'})",
        file=sys.stderr,
    )
    if not reports:
        print(
            "fetch_bikemaps: no reports in range — widen the bbox or check the source.",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
