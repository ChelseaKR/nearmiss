#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Build the per-segment exposure denominator (``exposure.json``) by snapping
real bicycle/pedestrian count observations onto the street segments.

Exposure is the third and hardest real-city input (see docs/REAL-DATA.md) and the
one that distinguishes this project from a dot-map: without a denominator, a
"rate" is just a count. This tool turns point count observations — e.g. the
California Active Transportation (AT) Count Dataset on the state open-data portal,
or SACOG's regional bike/ped counts — into the per-segment exposure the pipeline
needs, using the **same snapping** the pipeline uses for reports (so a counter
lands on the same segment a near-miss at that spot would).

Honest by default: a segment with no nearby count gets **no** exposure and is
published as ``exposure unknown`` downstream — never a fabricated denominator
(hard rule #1). ``--model-fallback`` will, only if you ask, fill uncovered
segments with a clearly-labeled flat prior; that is a weak placeholder and is
documented as such. Prefer real counts.

Inputs:
  * ``--streets streets.geojson`` — the segments (from tools/fetch_osm_streets.py).
  * ``--counts FILE`` — count observations as GeoJSON points (``--count-field``
    in properties) or CSV (``--lat-field``/``--lon-field``/``--count-field``).

Usage:
    python tools/build_exposure.py --streets streets.geojson --counts at_counts.csv \\
        --count-field count --source "CA AT Count Dataset 2025" --date 2025-01-01 \\
        --out exposure.json

Stdlib only, but it reuses the installed nearmiss geometry for snapping so the
result is consistent with the pipeline.
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
from pathlib import Path
from typing import Any

from nearmiss.geometry import point_to_polyline_m
from nearmiss.loaders import load_streets
from nearmiss.util import reference_point


def _to_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def read_counts(
    path: Path, count_field: str, lat_field: str, lon_field: str
) -> list[tuple[float, float, float]]:
    """Return [(lat, lon, count), ...] from a GeoJSON points file or a CSV."""
    text = path.read_text(encoding="utf-8")
    obs: list[tuple[float, float, float]] = []

    stripped = text.lstrip()
    if stripped.startswith("{"):
        data = json.loads(text)
        for feat in data.get("features", []):
            geom = feat.get("geometry", {}) or {}
            if geom.get("type") != "Point":
                continue
            coords = geom.get("coordinates", [])
            if len(coords) < 2:
                continue
            props = feat.get("properties", {}) or {}
            count = _to_float(props.get(count_field))
            if count is None or count <= 0:
                continue
            obs.append((float(coords[1]), float(coords[0]), count))
        return obs

    reader = csv.DictReader(text.splitlines())
    for row in reader:
        lat = _to_float(row.get(lat_field))
        lon = _to_float(row.get(lon_field))
        count = _to_float(row.get(count_field))
        if lat is None or lon is None or count is None or count <= 0:
            continue
        obs.append((lat, lon, count))
    return obs


def nearest_segment(
    lat: float,
    lon: float,
    segments: list[Any],
    lat0: float,
    lon0: float,
    max_snap_m: float,
) -> str | None:
    best_id: str | None = None
    best_d = float("inf")
    for seg in segments:
        d = point_to_polyline_m(lat, lon, seg.coords, lat0, lon0)
        if d < best_d:
            best_d, best_id = d, seg.id
    return best_id if best_d <= max_snap_m else None


def assign(
    segments: list[Any],
    obs: list[tuple[float, float, float]],
    max_snap_m: float,
    aggregate: str,
) -> tuple[dict[str, float], int]:
    """Snap each observation to a segment and aggregate per-segment counts."""
    lat0, lon0 = reference_point((c for s in segments for c in s.coords), None, None)
    buckets: dict[str, list[float]] = {}
    unsnapped = 0
    for lat, lon, count in obs:
        sid = nearest_segment(lat, lon, segments, lat0, lon0, max_snap_m)
        if sid is None:
            unsnapped += 1
            continue
        buckets.setdefault(sid, []).append(count)
    reducer = {"sum": sum, "mean": statistics.mean, "max": max}[aggregate]
    estimates = {sid: float(reducer(vals)) for sid, vals in buckets.items()}
    return estimates, unsnapped


def build_exposure(
    segments: list[Any],
    estimates: dict[str, float],
    source: str,
    date: str,
    model_fallback: bool,
    fallback_estimate: float | None,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for sid, est in estimates.items():
        rows.append({"segment_id": sid, "estimate": est, "source": source, "date": date})

    if model_fallback:
        prior = fallback_estimate
        if prior is None:
            prior = statistics.median(estimates.values()) if estimates else 0.0
        covered = set(estimates)
        for seg in segments:
            if seg.id not in covered and prior > 0:
                rows.append(
                    {
                        "segment_id": seg.id,
                        "estimate": float(prior),
                        # Distinct, honest label so the data card can flag it.
                        "source": f"modeled_flat_prior ({source})",
                        "date": date,
                    }
                )
    return {"segments": rows}


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--streets", required=True, help="streets.geojson (the segments).")
    p.add_argument("--counts", required=True, help="Count observations: GeoJSON points or CSV.")
    p.add_argument("--count-field", default="count", help="Property/column holding the count.")
    p.add_argument("--lat-field", default="lat", help="CSV latitude column (CSV only).")
    p.add_argument("--lon-field", default="lon", help="CSV longitude column (CSV only).")
    p.add_argument("--source", default="bike_counts", help="Exposure source label.")
    p.add_argument("--date", default="", help="As-of date (ISO) for the exposure figures.")
    p.add_argument("--max-snap-m", type=float, default=30.0, help="Max counter->segment distance.")
    p.add_argument(
        "--aggregate",
        choices=["sum", "mean", "max"],
        default="sum",
        help="How to combine multiple counters on one segment (default sum).",
    )
    p.add_argument(
        "--model-fallback",
        action="store_true",
        help="Fill uncovered segments with a labeled flat prior (weak; opt-in).",
    )
    p.add_argument(
        "--fallback-estimate",
        type=float,
        default=None,
        help="Prior value for --model-fallback (default: median of observed counts).",
    )
    p.add_argument("--out", default="-", help="Output exposure.json ('-' for stdout).")
    return p.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    segments = load_streets(Path(args.streets))
    obs = read_counts(Path(args.counts), args.count_field, args.lat_field, args.lon_field)
    if not obs:
        print("build_exposure: no usable count observations in --counts.", file=sys.stderr)
        return 1

    estimates, unsnapped = assign(segments, obs, args.max_snap_m, args.aggregate)
    exposure = build_exposure(
        segments, estimates, args.source, args.date, args.model_fallback, args.fallback_estimate
    )

    text = json.dumps(exposure, ensure_ascii=False, indent=2)
    if args.out == "-":
        print(text)
    else:
        with Path(args.out).open("w", encoding="utf-8") as fh:
            fh.write(text + "\n")

    covered = len(estimates)
    where = "stdout" if args.out == "-" else args.out
    rest = ", rest modeled" if args.model_fallback else ", rest 'exposure unknown'"
    print(
        f"build_exposure: {len(obs)} counts ({unsnapped} unsnapped) -> "
        f"{covered}/{len(segments)} segments with real exposure{rest} -> {where}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
