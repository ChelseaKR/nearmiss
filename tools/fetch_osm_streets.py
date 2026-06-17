#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Fetch a real street network from OpenStreetMap (Overpass) and emit it as the
nearmiss ``streets.geojson`` the pipeline snaps reports to.

This is the second of the three real-city inputs (see docs/REAL-DATA.md): real
incidents come from BikeMaps (tools/fetch_bikemaps.py), the real road network
comes from here, and exposure remains the hard third input you must source.

It downloads cycling-relevant highways inside a bounding box and writes a
GeoJSON ``FeatureCollection`` of ``LineString`` features, each with a stable
``segment_id`` and a ``name`` — exactly what ``loaders.load_streets`` expects
([lon, lat] coordinates, >= 2 vertices per line).

By default each OSM way is **split at intersections** so a "segment" is a block
between cross streets (like the demo's "B St (1st–2nd)"), which is the right
granularity for snapping and for per-segment rates. A node shared by two or more
ways is treated as an intersection; pass ``--no-split`` to keep whole ways.

Two sources, same conversion:

  * ``--city`` / ``--bbox W,S,E,N`` queries the live Overpass API.
  * ``--from-file overpass.json`` reads a saved Overpass ``out geom`` JSON (or an
    Overpass GeoJSON), so it works with no network access.

Usage:
    python tools/fetch_osm_streets.py --city victoria --out streets.geojson
    python tools/fetch_osm_streets.py --bbox=-123.46,48.40,-123.28,48.50 --out streets.geojson
    python tools/fetch_osm_streets.py --from-file overpass.json --out streets.geojson

Stdlib only, to match the project's minimal-dependency stance.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

# Default Overpass mirror. Override with --base-url if your network blocks it.
OVERPASS_URL = "https://overpass-api.de/api/interpreter"

# Cycling-relevant highway classes. Motorways/trunk (no cycling) and service
# aisles/footways are excluded by default; override with --highway.
DEFAULT_HIGHWAYS = (
    "primary,secondary,tertiary,residential,unclassified,living_street,road,"
    "cycleway,primary_link,secondary_link,tertiary_link"
)

# Shared with tools/fetch_bikemaps.py — keep these in sync. (W, S, E, N)
CITY_BBOX = {
    "victoria": (-123.46, 48.40, -123.28, 48.50),
    "vancouver": (-123.27, 49.20, -123.02, 49.32),
    "davis": (-121.78, 38.53, -121.70, 38.57),
}

# Coordinate rounding for node identity. OSM ways at a junction share the exact
# same node, so identical coordinates mark a real intersection; 7 dp is ~1 cm.
_NODE_DP = 7


def build_query(bbox: tuple[float, float, float, float], highways: str, timeout: int = 90) -> str:
    w, s, e, n = bbox
    classes = "|".join(h.strip() for h in highways.split(",") if h.strip())
    # Overpass bbox order is (south, west, north, east).
    return (
        f'[out:json][timeout:{timeout}];way["highway"~"^({classes})$"]({s},{w},{n},{e});out geom;'
    )


def overpass_fetch(query: str, base_url: str, timeout: float = 180.0) -> dict[str, Any]:
    data = urllib.parse.urlencode({"data": query}).encode("utf-8")
    req = urllib.request.Request(
        base_url, data=data, headers={"User-Agent": "nearmiss-fetch-osm-streets/1.0"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _way_coords(element: dict[str, Any]) -> list[tuple[float, float]]:
    """Return a way's [(lon, lat), ...] from Overpass 'out geom' geometry."""
    geom = element.get("geometry")
    if not isinstance(geom, list):
        return []
    out: list[tuple[float, float]] = []
    for pt in geom:
        try:
            out.append((float(pt["lon"]), float(pt["lat"])))
        except (KeyError, TypeError, ValueError):
            continue
    return out


def parse_ways(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Normalize an Overpass JSON response (or GeoJSON) into a list of
    {id, name, highway, coords:[(lon,lat),...]} ways."""
    ways: list[dict[str, Any]] = []

    # Overpass JSON ('elements' with type 'way' and 'geometry').
    for el in payload.get("elements", []):
        if el.get("type") != "way":
            continue
        coords = _way_coords(el)
        if len(coords) < 2:
            continue
        tags = el.get("tags", {}) or {}
        ways.append(
            {
                "id": str(el.get("id")),
                "name": tags.get("name"),
                "highway": tags.get("highway", "road"),
                "coords": coords,
            }
        )

    # GeoJSON LineStrings (an alternative export shape).
    for feat in payload.get("features", []):
        geom = feat.get("geometry", {}) or {}
        if geom.get("type") != "LineString":
            continue
        coords = [(float(c[0]), float(c[1])) for c in geom.get("coordinates", []) if len(c) >= 2]
        if len(coords) < 2:
            continue
        props = feat.get("properties", {}) or {}
        ways.append(
            {
                "id": str(props.get("@id") or props.get("osm_id") or feat.get("id") or len(ways)),
                "name": props.get("name"),
                "highway": props.get("highway", "road"),
                "coords": coords,
            }
        )
    return ways


def _node_key(lon: float, lat: float) -> tuple[float, float]:
    return (round(lon, _NODE_DP), round(lat, _NODE_DP))


def intersection_nodes(ways: list[dict[str, Any]]) -> set[tuple[float, float]]:
    """Nodes shared by two or more distinct ways — i.e. real intersections."""
    ways_per_node: dict[tuple[float, float], set[str]] = {}
    for way in ways:
        wid = way["id"]
        for lon, lat in way["coords"]:
            ways_per_node.setdefault(_node_key(lon, lat), set()).add(wid)
    return {node for node, wids in ways_per_node.items() if len(wids) >= 2}


def split_way(
    coords: list[tuple[float, float]], nodes: set[tuple[float, float]]
) -> list[list[tuple[float, float]]]:
    """Split a way's coordinates into sub-segments at intersection nodes."""
    segments: list[list[tuple[float, float]]] = []
    current: list[tuple[float, float]] = [coords[0]]
    for lon, lat in coords[1:]:
        current.append((lon, lat))
        if _node_key(lon, lat) in nodes:
            segments.append(current)
            current = [(lon, lat)]
    if len(current) >= 2:
        segments.append(current)
    return segments


def to_feature(segment_id: str, name: str, coords: list[tuple[float, float]]) -> dict[str, Any]:
    return {
        "type": "Feature",
        "geometry": {"type": "LineString", "coordinates": [[lon, lat] for lon, lat in coords]},
        "properties": {"segment_id": segment_id, "name": name},
    }


def build_streets(ways: list[dict[str, Any]], split: bool) -> dict[str, Any]:
    features: list[dict[str, Any]] = []
    nodes = intersection_nodes(ways) if split else set()
    for way in ways:
        name = way["name"] or f"unnamed {way['highway']}"
        if split:
            pieces = split_way(way["coords"], nodes)
            for i, piece in enumerate(pieces, start=1):
                features.append(to_feature(f"osm-w{way['id']}-{i}", name, piece))
        else:
            features.append(to_feature(f"osm-w{way['id']}", name, way["coords"]))
    return {"type": "FeatureCollection", "features": features}


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--city", choices=sorted(CITY_BBOX), help="Known city bbox (live query).")
    src.add_argument("--bbox", help="Bounding box W,S,E,N in degrees (live query).")
    src.add_argument(
        "--from-file", help="Read a saved Overpass JSON / GeoJSON instead of the network."
    )
    p.add_argument("--highway", default=DEFAULT_HIGHWAYS, help="Comma list of highway classes.")
    p.add_argument(
        "--no-split",
        action="store_true",
        help="Keep whole OSM ways instead of splitting them at intersections.",
    )
    p.add_argument("--out", default="-", help="Output path for streets.geojson ('-' for stdout).")
    p.add_argument("--base-url", default=OVERPASS_URL, help=argparse.SUPPRESS)
    return p.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)

    if args.from_file:
        with Path(args.from_file).open(encoding="utf-8") as fh:
            payload = json.load(fh)
    else:
        if args.city:
            bbox = CITY_BBOX[args.city]
        else:
            parts = [float(x) for x in args.bbox.split(",")]
            if len(parts) != 4:
                print("error: --bbox must be W,S,E,N", file=sys.stderr)
                return 2
            bbox = (parts[0], parts[1], parts[2], parts[3])
        query = build_query(bbox, args.highway)
        try:
            payload = overpass_fetch(query, args.base_url)
        except (urllib.error.URLError, TimeoutError) as exc:  # pragma: no cover - network
            print(f"error: could not reach Overpass ({args.base_url}): {exc}", file=sys.stderr)
            print(
                "hint: this host may be blocked by your network egress policy. Run an Overpass "
                "query in a browser, save the JSON, and pass it with --from-file.",
                file=sys.stderr,
            )
            return 1

    ways = parse_ways(payload)
    streets = build_streets(ways, split=not args.no_split)

    text = json.dumps(streets, ensure_ascii=False, indent=2)
    if args.out == "-":
        print(text)
    else:
        with Path(args.out).open("w", encoding="utf-8") as fh:
            fh.write(text + "\n")

    where = "stdout" if args.out == "-" else args.out
    print(
        f"fetch_osm_streets: {len(ways)} ways -> {len(streets['features'])} segments "
        f"({'split at intersections' if not args.no_split else 'whole ways'}) to {where}",
        file=sys.stderr,
    )
    if not streets["features"]:
        print(
            "fetch_osm_streets: no segments — widen the bbox or relax --highway.", file=sys.stderr
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
