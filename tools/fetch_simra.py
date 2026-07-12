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

This is a thin CLI over the ``SimRaAdapter`` in ``nearmiss.adapters.simra`` (the
second ``SourceAdapter`` implementation, EXP-04 — this tool was previously an
orphaned, unmerged branch; it is now a manifest + adapter module like BikeMaps).
The incident-code crosswalk lives as declarative data in
``src/nearmiss/adapters/crosswalks/simra.toml``.

Usage:
    python tools/fetch_simra.py --dir path/to/SimRa/Berlin_2023_03 --out reports.json
    python tools/fetch_simra.py --dir path/to/SimRa --city berlin --out reports.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from nearmiss.adapters.simra import CITY_BBOX, collect, in_bbox, map_incident, parse_incidents

__all__ = [
    "CITY_BBOX",
    "collect",
    "in_bbox",
    "main",
    "map_incident",
    "parse_args",
    "parse_incidents",
]


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
