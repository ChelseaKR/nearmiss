"""Publish: build the open GeoJSON and an aggregated, privacy-safe public dataset.

The published artifact contains ONLY segment-level aggregates. No per-report
coordinate, timestamp, reporter token, note, mode, or severity is ever written
(hard rule #4). :func:`assert_published_clean` enforces this as an invariant and
raises rather than emitting a leaky file. Output is stably sorted and rounded so
``make reproduce`` is byte-for-byte deterministic.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

from .config import Config
from .engine import build_analysis, load_city
from .errors import PrivacyError
from .models import Report, Segment, SegmentStats

# Property keys that must NEVER appear on a published feature.
_FORBIDDEN_KEYS = frozenset(
    ("reporter_token", "occurred_at", "note", "heading_deg", "lat", "lon", "accuracy_m")
)


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def _feature(stat: SegmentStats, segment: Segment) -> dict[str, object]:
    coordinates = [[lon, lat] for (lat, lon) in segment.coords]
    return {
        "type": "Feature",
        "geometry": {"type": "LineString", "coordinates": coordinates},
        "properties": {
            "segment_id": stat.segment_id,
            "name": segment.name,
            "report_count": stat.report_count,
            "n": stat.n,
            "exposure_estimate": stat.exposure_estimate,
            "exposure_source": stat.exposure_source,
            "exposure_date": stat.exposure_date,
            "rate": stat.rate,
            "rate_ci_low": stat.rate_ci_low,
            "rate_ci_high": stat.rate_ci_high,
            "getis_ord_z": stat.getis_ord_z,
            "significant": stat.significant,
            "confidence_label": stat.confidence_label,
            "hazard_breakdown": dict(sorted(stat.hazard_breakdown.items())),
            "quality_flags": list(stat.quality_flags),
        },
    }


def build_geojson(stats: list[SegmentStats], segments: list[Segment]) -> dict[str, object]:
    by_id = {s.id: s for s in segments}
    features = [
        _feature(st, by_id[st.segment_id])
        for st in sorted(stats, key=lambda s: s.segment_id)
        if st.segment_id in by_id
    ]
    return {"type": "FeatureCollection", "features": features}


def assert_published_clean(geojson: dict[str, object], reports: list[Report]) -> None:
    """Verify no forbidden field and no exact raw report coordinate leaked."""
    raw_points = {(round(r.lat, 6), round(r.lon, 6)) for r in reports}
    features = geojson.get("features", [])
    if not isinstance(features, list):
        raise PrivacyError("published geojson has no feature list")
    for feat in features:
        props = feat.get("properties", {}) if isinstance(feat, dict) else {}
        leaked = _FORBIDDEN_KEYS.intersection(props)
        if leaked:
            raise PrivacyError(f"published feature exposes forbidden keys: {sorted(leaked)}")
        # Segment geometry is public street infrastructure; still verify a published
        # vertex never coincides exactly with a raw report point.
        geom = feat.get("geometry", {}) if isinstance(feat, dict) else {}
        for lon, lat in geom.get("coordinates", []):
            if (round(float(lat), 6), round(float(lon), 6)) in raw_points:
                raise PrivacyError("published vertex coincides with a raw report location")


def _canonical_json(obj: object) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


@dataclass
class PublishResult:
    geojson_path: Path
    metadata_path: Path
    geojson_sha256: str
    feature_count: int


def publish(config: Config) -> PublishResult:
    bundle = build_analysis(config)
    geojson = build_geojson(bundle.result.segments, bundle.segments)

    # Enforce the privacy invariant against the raw reports before writing anything.
    assert_published_clean(geojson, load_city(config).reports)

    payload = _canonical_json(geojson)
    sha = hashlib.sha256(payload.encode("utf-8")).hexdigest()

    peak = bundle.result.kde.peak
    metadata = {
        "city": config.city,
        "license": "Apache-2.0",
        "schema": "schema/dataset.schema.md",
        "data_card": "docs/DATA-CARD.md",
        "methods": {
            "rate_per": config.rate_per,
            "confidence_z": config.confidence_z,
            "small_n": config.small_n,
            "getis_ord_band_m": config.gi_band_m,
            "kde_bandwidth_m": config.kde_bandwidth_m,
        },
        "summary": {
            "segments": len(bundle.segments),
            "reports_in": bundle.summary["reports_in"],
            "duplicates_removed": bundle.summary["duplicates_removed"],
            "snapped": bundle.summary["snapped"],
            "unsnapped": bundle.summary["unsnapped"],
            "exposure_coverage": round(bundle.result.exposure_coverage, 4),
        },
        "kde_peak": ({"lat": round(peak.lat, 5), "lon": round(peak.lon, 5)} if peak else None),
        "geojson_sha256": sha,
        "privacy": (
            "Aggregated to segment level; no per-report coordinate, time, reporter, "
            "note, mode, or severity is published. Small-n hazard breakdowns suppressed."
        ),
    }

    config.out_dir.mkdir(parents=True, exist_ok=True)
    slug = _slug(config.city)
    geojson_path = config.out_dir / f"{slug}.geojson"
    metadata_path = config.out_dir / f"{slug}.metadata.json"
    geojson_path.write_text(payload, encoding="utf-8")
    metadata_path.write_text(_canonical_json(metadata), encoding="utf-8")

    return PublishResult(
        geojson_path=geojson_path,
        metadata_path=metadata_path,
        geojson_sha256=sha,
        feature_count=len(bundle.segments),
    )
