# SPDX-License-Identifier: Apache-2.0
"""BikeMaps.org source adapter — the first ``SourceAdapter`` implementation.

BikeMaps.org (https://bikemaps.org, SPARLab/BikeMaps) is a crowdsourced global
map of cycling collisions, near misses, hazards, and thefts. This adapter reads
BikeMaps' public GeoJSON (live or an exported file) and emits reports in the
intake contract (``schema/report.schema.json``), using the declarative
crosswalk in ``crosswalks/bikemaps.toml`` for every source-vocabulary mapping
(no hardcoded hazard/severity dict here — see ``docs/REAL-DATA.md`` for the
crosswalk table rendered as prose).

``tools/fetch_bikemaps.py`` is now a thin CLI over this module.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
import uuid
from typing import Any

from .base import Crosswalk, Provenance, load_crosswalk

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


def hazard_from_incident_with(crosswalk: Crosswalk, value: str | None) -> str:
    return crosswalk.hazard_from(value)


def severity_from_injury(crosswalk: Crosswalk, injury: str | None) -> str:
    """Collision severity from BikeMaps' injury text via the crosswalk. A
    collision always involved contact, so the crosswalk's default is "minor"
    even when ``injury`` is empty/unrecognized."""
    return crosswalk.severity_from(injury)


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


def map_feature(
    feature: dict[str, Any], kind: str, utc_offset: str, crosswalk: Crosswalk
) -> dict[str, Any] | None:
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
        severity = severity_from_injury(crosswalk, props.get("injury"))
        hazard_type = hazard_from_incident_with(crosswalk, props.get("incident_with"))
    else:  # nearmiss
        severity = "near_miss"
        hazard_type = hazard_from_incident_with(crosswalk, props.get("incident_with"))

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
    lon, lat = float(coords[0]), float(coords[1])
    w, s, e, n = bbox
    return w <= lon <= e and s <= lat <= n


def fetch_geojson(url: str, timeout: float = 60.0) -> dict[str, Any]:
    req = urllib.request.Request(url, headers={"User-Agent": "nearmiss-fetch-bikemaps/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # nosec B310 - fixed https host
        payload: dict[str, Any] = json.loads(resp.read().decode("utf-8"))
        return payload


def collect(
    features_by_kind: dict[str, list[dict[str, Any]]],
    bbox: tuple[float, float, float, float] | None,
    utc_offset: str,
    crosswalk: Crosswalk | None = None,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    crosswalk = crosswalk or load_crosswalk("bikemaps")
    reports: list[dict[str, Any]] = []
    counts: dict[str, int] = {}
    for kind, feats in features_by_kind.items():
        kept = 0
        for f in feats:
            if bbox is not None and not in_bbox(f, bbox):
                continue
            report = map_feature(f, kind, utc_offset, crosswalk)
            if report is not None:
                reports.append(report)
                kept += 1
        counts[kind] = kept
    return reports, counts


class BikeMapsAdapter:
    """``SourceAdapter`` implementation for BikeMaps.org."""

    source_id = "bikemaps"

    def __init__(self) -> None:
        self.crosswalk = load_crosswalk("bikemaps")

    def fetch(self, **kwargs: Any) -> Any:
        """Live-fetch BikeMaps' public GeoJSON endpoints for the given kinds.

        Keywords: ``types`` (iterable of ``nearmiss``/``collision``/``hazard``,
        default all three) and ``base_url`` (default :data:`BASE_URL`). Raises
        ``urllib.error.URLError``/``TimeoutError`` on network failure — callers
        wanting the offline path should build ``features_by_kind`` from a saved
        export and call :meth:`parse` directly instead (matching the source
        adapter contract: fetch() and parse() are separate so tests never need
        the network).
        """
        types: tuple[str, ...] = kwargs.get("types", ("nearmiss", "collision", "hazard"))
        base_url: str = kwargs.get("base_url", BASE_URL)
        features_by_kind: dict[str, list[dict[str, Any]]] = {}
        for kind in types:
            gj = fetch_geojson(base_url + ENDPOINTS[kind])
            features_by_kind[kind] = gj.get("features", [])
        return features_by_kind

    def parse(self, raw: Any, **kwargs: Any) -> tuple[list[dict[str, Any]], Provenance]:
        """Keywords: ``bbox`` (``(W, S, E, N)``, default unfiltered) and
        ``utc_offset`` (default ``"+00:00"``, applied to naive timestamps)."""
        bbox: tuple[float, float, float, float] | None = kwargs.get("bbox")
        utc_offset: str = kwargs.get("utc_offset", "+00:00")
        reports, counts = collect(raw, bbox, utc_offset, self.crosswalk)
        return reports, self.crosswalk.provenance(counts)
