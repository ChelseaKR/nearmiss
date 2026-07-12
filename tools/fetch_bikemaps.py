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

This is a thin CLI over the ``BikeMapsAdapter`` in ``nearmiss.adapters.bikemaps``
(the first ``SourceAdapter`` implementation, EXP-04). The field crosswalk lives
as declarative data in ``src/nearmiss/adapters/crosswalks/bikemaps.toml``, not
in this file — see ``docs/REAL-DATA.md`` for the crosswalk table and
``src/nearmiss/adapters/base.py`` for the adapter contract.

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
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
from pathlib import Path

from nearmiss.adapters.bikemaps import (
    BASE_URL,
    CITY_BBOX,
    ENDPOINTS,
    collect,
    fetch_geojson,
    hazard_from_incident_with,
    in_bbox,
    map_feature,
    severity_from_injury,
)

__all__ = [
    "BASE_URL",
    "CITY_BBOX",
    "ENDPOINTS",
    "collect",
    "fetch_geojson",
    "hazard_from_incident_with",
    "in_bbox",
    "main",
    "map_feature",
    "parse_args",
    "severity_from_injury",
]


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
    features_by_kind: dict[str, list[dict]] = {}

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
