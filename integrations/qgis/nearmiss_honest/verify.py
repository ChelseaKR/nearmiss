# SPDX-License-Identifier: Apache-2.0
"""Standalone CLI to run the honest-symbology invariant checks on a GeoJSON
file, without opening QGIS.

    python -m nearmiss_honest.verify path/to/dataset.geojson

Exits non-zero if any violation is found, so it can also be dropped into a
contributor's own CI for a fork/derivative dataset. This is deliberately a
small, in-plugin check of the invariants the plugin's own symbology relies
on (see rules.py's module docstring) — not a substitute for the project's
own full HR1-HR5 conformance gate.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .rules import verify_dataset


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("geojson", type=Path, help="Path to a nearmiss published GeoJSON file")
    args = parser.parse_args(argv)

    try:
        data = json.loads(args.geojson.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"error: could not read/parse {args.geojson}: {exc}", file=sys.stderr)
        return 2

    problems = verify_dataset(data)
    if not problems:
        print(f"OK: {args.geojson} — no honest-symbology invariant violations found")
        return 0

    print(f"FAIL: {args.geojson} — {len(problems)} violation(s):", file=sys.stderr)
    for problem in problems:
        print(f"  - {problem}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
