#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Fetch open historical daily weather and emit the nearmiss *weather dataset*
the time-of-day analysis correlates reports against (stats/temporal.py).

The data source is Open-Meteo's Historical Weather API (https://open-meteo.com),
an open, key-free archive of reanalysis weather. Like the other fetchers in this
directory (fetch_osm_streets.py, fetch_bikemaps.py) this tool does **not**
invent data and does **not** claim a rate: it maps an open weather record onto a
simple per-day {date, precip_mm, wet, condition} schema so the analysis can ask
"do reports cluster on wet days *relative to how common wet days are*?" — an
honest association, never a weather risk rate (there is no weather-conditioned
exposure denominator).

Two sources, same mapping (mirrors the other fetchers):

  * ``--city`` / ``--lat/--lon`` with ``--start``/``--end`` queries the live
    Open-Meteo archive API (allowlisted host only; see ALLOWED_HOSTS).
  * ``--from-file archive.json`` reads a saved Open-Meteo response, so this works
    with no network access at all.

Usage:
    python tools/fetch_weather.py --city davis --start 2026-06-01 --end 2026-06-30 -o weather.json
    python tools/fetch_weather.py --lat 38.54 --lon -121.74 --start 2026-06-01 --end 2026-06-30
    python tools/fetch_weather.py --from-file open-meteo-archive.json --out weather.json

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
from urllib.parse import urlparse

# Open-Meteo historical (archive) endpoint. Open data, no API key required.
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"

# Egress allowlist: this fetcher only ever talks to Open-Meteo, even if --base-url
# is passed. A request to any other host is refused — the same allowlist discipline
# the project applies to its other networked adapters.
ALLOWED_HOSTS = frozenset({"archive-api.open-meteo.com", "api.open-meteo.com"})

# Convenience city centroids, shared in spirit with the other fetchers' CITY_BBOX.
CITY_LATLON = {
    "davis": (38.5449, -121.7405),
    "sacramento": (38.5816, -121.4944),
    "victoria": (48.4284, -123.3656),
    "vancouver": (49.2827, -123.1207),
}

# A WMO weather-code -> coarse condition label. Open-Meteo returns weather_code per
# day; we collapse it to a human label and a wet/dry flag. Codes >= 51 are drizzle/
# rain/snow/showers/thunderstorm (precipitation); below that is dry-ish.
_WMO_WET_FROM = 51


def _wmo_condition(code: int) -> str:
    if code == 0:
        return "clear"
    if code in (1, 2, 3):
        return "partly_cloudy"
    if code in (45, 48):
        return "fog"
    if 51 <= code <= 67:
        return "rain"
    if 71 <= code <= 77:
        return "snow"
    if 80 <= code <= 82:
        return "showers"
    if 85 <= code <= 86:
        return "snow_showers"
    if 95 <= code <= 99:
        return "thunderstorm"
    return "other"


def _check_host(url: str) -> None:
    host = (urlparse(url).hostname or "").lower()
    if host not in ALLOWED_HOSTS:
        raise SystemExit(
            f"refusing to fetch from non-allowlisted host {host!r}; "
            f"allowed: {sorted(ALLOWED_HOSTS)} (use --from-file for other data)"
        )


def build_url(base_url: str, lat: float, lon: float, start: str, end: str) -> str:
    query = urllib.parse.urlencode(
        {
            "latitude": lat,
            "longitude": lon,
            "start_date": start,
            "end_date": end,
            "daily": "weather_code,precipitation_sum",
            "timezone": "auto",
        }
    )
    return f"{base_url}?{query}"


def fetch(url: str, timeout: float = 60.0) -> dict[str, Any]:
    _check_host(url)
    req = urllib.request.Request(url, headers={"User-Agent": "nearmiss-fetch-weather/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data: dict[str, Any] = json.loads(resp.read().decode("utf-8"))
    return data


def to_weather_dataset(payload: dict[str, Any], source: str) -> dict[str, Any]:
    """Map an Open-Meteo archive response to the nearmiss weather dataset schema."""
    daily = payload.get("daily", {}) or {}
    dates = daily.get("time", []) or []
    codes = daily.get("weather_code", []) or []
    precips = daily.get("precipitation_sum", []) or []
    rows: list[dict[str, Any]] = []
    for i, date in enumerate(dates):
        code = int(codes[i]) if i < len(codes) and codes[i] is not None else -1
        precip = precips[i] if i < len(precips) else None
        precip_mm = float(precip) if precip is not None else None
        wet = (code >= _WMO_WET_FROM) or (precip_mm is not None and precip_mm > 0.0)
        rows.append(
            {
                "date": str(date)[:10],
                "precip_mm": precip_mm,
                "wet": wet,
                "condition": _wmo_condition(code) if code >= 0 else ("wet" if wet else "dry"),
            }
        )
    return {
        "source": source,
        "license": "Open-Meteo (CC-BY 4.0); ERA5 reanalysis",
        "latitude": payload.get("latitude"),
        "longitude": payload.get("longitude"),
        "daily": rows,
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument(
        "--city", choices=sorted(CITY_LATLON), help="Known city centroid (live query)."
    )
    src.add_argument("--lat", type=float, help="Latitude (with --lon; live query).")
    src.add_argument("--from-file", help="Read a saved Open-Meteo archive JSON instead of network.")
    p.add_argument("--lon", type=float, help="Longitude (with --lat).")
    p.add_argument("--start", help="Start date YYYY-MM-DD (live query).")
    p.add_argument("--end", help="End date YYYY-MM-DD (live query).")
    p.add_argument("--out", default="-", help="Output path ('-' for stdout).")
    p.add_argument("--base-url", default=ARCHIVE_URL, help=argparse.SUPPRESS)
    return p.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)

    if args.from_file:
        payload = json.loads(Path(args.from_file).read_text(encoding="utf-8"))
        source = f"Open-Meteo Historical (from file {args.from_file})"
    else:
        if args.city:
            lat, lon = CITY_LATLON[args.city]
        elif args.lat is not None and args.lon is not None:
            lat, lon = args.lat, args.lon
        else:
            print("error: provide --city, or both --lat and --lon", file=sys.stderr)
            return 2
        if not (args.start and args.end):
            print("error: --start and --end are required for a live query", file=sys.stderr)
            return 2
        url = build_url(args.base_url, lat, lon, args.start, args.end)
        try:
            payload = fetch(url)
        except (urllib.error.URLError, TimeoutError) as exc:  # pragma: no cover - network
            print(f"error: could not reach Open-Meteo: {exc}", file=sys.stderr)
            print(
                "hint: run the archive query in a browser, save the JSON, and pass --from-file.",
                file=sys.stderr,
            )
            return 1
        source = "Open-Meteo Historical Weather API (archive-api.open-meteo.com)"

    dataset = to_weather_dataset(payload, source)
    text = json.dumps(dataset, ensure_ascii=False, indent=2)
    if args.out == "-":
        print(text)
    else:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    print(
        f"fetch_weather: {len(dataset['daily'])} day(s) -> "
        f"{'stdout' if args.out == '-' else args.out}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
