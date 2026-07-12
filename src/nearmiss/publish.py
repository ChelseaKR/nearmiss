"""Publish: build the open GeoJSON and an aggregated, privacy-safe public dataset.

The published artifact contains ONLY segment-level aggregates, and only for
segments that clear the minimum-occupancy floor (k-anonymity): a segment with a
non-zero report count below ``min_publish_n`` is withheld entirely, so no place
ever reads "exactly one or two people reported an incident on this block." No
per-report coordinate, timestamp, reporter token, note, mode, or severity is
ever written, in the GeoJSON OR the metadata (hard rule #4).
:func:`assert_published_clean` and :func:`assert_metadata_clean` enforce these as
invariants and raise rather than emitting a leaky file. Output is stably sorted
and rounded so ``make reproduce`` is byte-for-byte deterministic.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from . import __version__
from .config import Config
from .engine import build_analysis, load_city
from .errors import PrivacyError
from .manifest import build_manifest, canonical_json
from .models import Report, Segment, SegmentStats
from .stats.bias import to_metadata as bias_to_metadata
from .stats.maup import to_metadata as maup_to_metadata
from .stats.temporal import to_metadata as temporal_to_metadata

# Property/field keys that must NEVER appear in any published artifact.
_FORBIDDEN_KEYS = frozenset(
    (
        "reporter_token",
        "occurred_at",
        "note",
        "heading_deg",
        "lat",
        "lon",
        "accuracy_m",
        "mode",
        "severity",
    )
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
            "getis_ord_significant": stat.significant,
            "rate_sensitivity_delta": stat.rate_sensitivity_delta,
            "confidence_label": stat.confidence_label,
            "hazard_breakdown": dict(sorted(stat.hazard_breakdown.items())),
            # Per-hazard-type rate layers. The ``rate`` above is the pooled rate
            # across all hazard types (an explicit union); these are the
            # type-specific exposure-normalized rates, present only for types
            # whose count clears the small-sample threshold (others suppressed).
            "rates_by_type": {
                t: dict(rates_by_type_entry)
                for t, rates_by_type_entry in sorted(stat.rates_by_type.items())
            },
            "quality_flags": list(stat.quality_flags),
        },
    }


def build_geojson(stats: list[SegmentStats], segments: list[Segment]) -> dict[str, object]:
    """Build the FeatureCollection, omitting segments withheld for k-anonymity."""
    by_id = {s.id: s for s in segments}
    features = [
        _feature(st, by_id[st.segment_id])
        for st in sorted(stats, key=lambda s: s.segment_id)
        if st.publishable and st.segment_id in by_id
    ]
    return {"type": "FeatureCollection", "features": features}


def _iter_lonlat(coords: object) -> Iterator[tuple[float, float]]:
    """Yield every leaf (lon, lat) pair from any GeoJSON coordinate nesting."""
    if (
        isinstance(coords, list | tuple)
        and len(coords) == 2
        and all(isinstance(c, int | float) for c in coords)
    ):
        yield float(coords[0]), float(coords[1])
    elif isinstance(coords, list | tuple):
        for item in coords:
            yield from _iter_lonlat(item)


def assert_published_clean(
    geojson: dict[str, object], reports: list[Report], min_publish_n: int
) -> None:
    """Enforce the publication privacy invariants; raise rather than leak."""
    raw_points = {(round(r.lat, 6), round(r.lon, 6)) for r in reports}
    features = geojson.get("features", [])
    if not isinstance(features, list):
        raise PrivacyError("published geojson has no feature list")
    for feat in features:
        props = feat.get("properties", {}) if isinstance(feat, dict) else {}
        leaked = _FORBIDDEN_KEYS.intersection(props)
        if leaked:
            raise PrivacyError(f"published feature exposes forbidden keys: {sorted(leaked)}")
        # k-anonymity: a published feature must have 0 or >= min_publish_n reports.
        rc = props.get("report_count")
        if isinstance(rc, int) and 0 < rc < min_publish_n:
            raise PrivacyError(
                f"published feature {props.get('segment_id')!r} has report_count={rc} "
                f"below the minimum-occupancy floor {min_publish_n}"
            )
        # Segment geometry is public street infrastructure; still verify no published
        # vertex coincides exactly with a raw report point.
        geom = feat.get("geometry", {}) if isinstance(feat, dict) else {}
        for lon, lat in _iter_lonlat(geom.get("coordinates", [])):
            if (round(lat, 6), round(lon, 6)) in raw_points:
                raise PrivacyError("published vertex coincides with a raw report location")


def assert_metadata_clean(metadata: dict[str, object], reports: list[Report]) -> None:
    """The sidecar metadata must contain no forbidden key and no raw coordinate."""
    text = json.dumps(metadata)
    for key in _FORBIDDEN_KEYS:
        if f'"{key}"' in text:
            raise PrivacyError(f"metadata exposes forbidden key: {key}")
    for r in reports:
        if f"{round(r.lat, 5)}" in text and f"{round(r.lon, 5)}" in text:
            raise PrivacyError("metadata appears to contain a raw report coordinate")


# Canonical serialization lives in ``manifest`` (a pure, stdlib-only module) so the
# published GeoJSON, its metadata sidecar, and the run manifest all serialize
# byte-identically. Kept as a module-local name so existing call sites are unchanged.
_canonical_json = canonical_json


@dataclass
class PublishResult:
    geojson_path: Path
    metadata_path: Path
    manifest_path: Path
    geojson_sha256: str
    manifest_digest: str
    feature_count: int
    withheld_count: int


def publish(config: Config) -> PublishResult:
    bundle = build_analysis(config)
    stats = bundle.result.segments
    geojson = build_geojson(stats, bundle.segments)
    reports = load_city(config).reports
    withheld = sum(1 for s in stats if not s.publishable)

    # Reporting-bias audit (who the dataset over-/under-reports), filtered to the
    # segments that clear the k-anonymity floor — the same filter the brief applies
    # — so the web UI can surface it alongside the brief, not only in the artifacts.
    publishable = {s.segment_id for s in stats if s.publishable}
    bias_meta = bias_to_metadata(bundle.result.bias, publishable)

    # Embed a self-describing metadata member on the FeatureCollection (a GeoJSON
    # foreign member) so the open file carries its own version, license, and
    # privacy/method provenance without a separate fetch. No content hash here
    # (that would be self-referential); the sidecar carries the hash.
    embedded: dict[str, object] = {
        "schema_version": "1.0.0",
        "dataset_version": "0.1.0",
        "city": config.city,
        "license": "Apache-2.0",
        "dataset_note": config.dataset_note,
        # Analysis window (METHODOLOGY §1): every published number is traceable to a
        # stated period. Keys are always present (null when unconfigured) so the
        # schema is stable.
        "window": {"start": config.window_start, "end": config.window_end},
        "exposure_unit": config.exposure_unit,
        "schema_doc": "schema/dataset.schema.md",
        "data_card": "docs/DATA-CARD.md",
        "segments_published": len(stats) - withheld,
        "segments_withheld_low_count": withheld,
        "significance": "Getis-Ord Gi* on the exposure-normalized rate, Benjamini-Hochberg FDR",
        # Reporting-bias audit (over-/under-represented segments + caveat note), so the
        # open file — and the web UI that reads this embedded member — carries the "who
        # is over/under-reported" finding, not only the segment aggregates.
        "bias": bias_meta,
        "privacy": (
            "Aggregated to public street segments; low-count segments withheld (k-anonymity); "
            "no per-report coordinate, time, reporter, mode, or severity is published."
        ),
    }
    assert_metadata_clean(embedded, reports)
    geojson["metadata"] = embedded

    # Enforce the privacy invariants against the raw reports before writing anything.
    assert_published_clean(geojson, reports, config.min_publish_n)

    payload = _canonical_json(geojson)
    sha = hashlib.sha256(payload.encode("utf-8")).hexdigest()

    metadata: dict[str, object] = {
        "city": config.city,
        "version": "0.1.0",
        "schema_version": "1.0.0",
        "dataset_note": config.dataset_note,
        # Analysis window bounding every rate in this dataset (null when unset).
        "window": {"start": config.window_start, "end": config.window_end},
        "license": "Apache-2.0",
        "schema": "schema/dataset.schema.md",
        "data_card": "docs/DATA-CARD.md",
        "methods": {
            "rate_per": config.rate_per,
            "confidence_z": config.confidence_z,
            "small_n": config.small_n,
            "min_publish_n": config.min_publish_n,
            "fdr_alpha": config.fdr_alpha,
            "getis_ord_band_m": config.gi_band_m,
            "kde_bandwidth_m": config.kde_bandwidth_m,
            "significance": "Getis-Ord Gi* on the exposure-normalized rate, Benjamini-Hochberg FDR",
            # RR-02: quasi-Poisson dispersion of the report counts. phi ~1 is a clean
            # Poisson process; phi materially above 1 is overdispersion (clustered
            # reporting) that makes the pure Poisson intervals too narrow. When
            # `adjusted` is true the published per-segment intervals were widened by
            # sqrt(phi) (config `overdispersion_adjust`); when false phi is reported
            # but the intervals stand as a lower bound on the true uncertainty.
            "dispersion": {
                "phi": bundle.result.dispersion,
                "model": "quasi-Poisson (Pearson) on the rate/offset model",
                "adjusted": bundle.result.overdispersion_adjusted,
            },
            "rate_definition": (
                "pooled across all hazard types (union); per-type rates in "
                "rates_by_type where count >= small_n"
            ),
        },
        "summary": {
            "segments_total": len(bundle.segments),
            "segments_published": len(stats) - withheld,
            "segments_withheld_low_count": withheld,
            "reports_in": bundle.summary["reports_in"],
            "out_of_window": bundle.summary["out_of_window"],
            "duplicates_removed": bundle.summary["duplicates_removed"],
            "snapped": bundle.summary["snapped"],
            "unsnapped": bundle.summary["unsnapped"],
            "exposure_coverage": round(bundle.result.exposure_coverage, 4),
            # Fraction of snapped reports excluded from the primary rate for low
            # confidence (low_accuracy / far_snap); they feed only the sensitivity rate.
            "excluded_low_confidence_fraction": round(
                bundle.result.excluded_low_confidence_fraction, 4
            ),
        },
        # The KDE report-intensity peak is reported ONLY as a segment id, never a coordinate.
        "report_intensity_peak_segment": bundle.result.kde_peak_segment,
        # City-wide time-of-day / weather report-VOLUME breakdown (never a per-report
        # timestamp; withheld below the k-anonymity floor). Volume, not a rate.
        "temporal": temporal_to_metadata(bundle.result.temporal),
        # RR-05: does the top hotspot survive re-drawing the block boundaries (MAUP)?
        # Unit counts, a segment id, ranks, and boolean summaries only — no coordinate.
        "maup_rank_stability": (
            maup_to_metadata(bundle.result.rank_stability)
            if bundle.result.rank_stability is not None
            else None
        ),
        # Reporting-bias audit: over-/under-represented segments vs exposure, plus the
        # caveat that over-representation is not confirmed danger. Publishable ids only.
        "bias": bias_meta,
        "geojson_sha256": sha,
        "privacy": (
            "Aggregated to public street segments; segments with a non-zero report count below "
            "min_publish_n are withheld (k-anonymity). No per-report coordinate, time, reporter "
            "token, note, mode, or severity is published. Small-n hazard breakdowns are suppressed."
        ),
    }
    assert_metadata_clean(metadata, reports)

    # Per-run provenance manifest: input hashes, effective-config digest, package
    # version, and per-stage counts (deterministic) plus a wall-time sidecar. Its
    # provenance section is counts-and-hashes only, so it passes the same privacy
    # gate as the metadata; the timings section is unhashed and NOT byte-stable, so
    # the file is treated as a regenerated artifact (see .gitignore: *.run.json).
    manifest = build_manifest(
        config,
        inputs={
            "streets": config.streets_path,
            "reports": config.reports_path,
            "exposure": config.exposure_path,
        },
        stage_summaries=bundle.stages,
        package_version=__version__,
    )
    provenance = manifest["provenance"]
    assert isinstance(provenance, dict)
    assert_metadata_clean(provenance, reports)
    manifest_digest = manifest["manifest_digest"]
    assert isinstance(manifest_digest, str)

    config.out_dir.mkdir(parents=True, exist_ok=True)
    slug = _slug(config.city)
    geojson_path = config.out_dir / f"{slug}.geojson"
    metadata_path = config.out_dir / f"{slug}.metadata.json"
    manifest_path = config.out_dir / f"{slug}.run.json"
    geojson_path.write_text(payload, encoding="utf-8")
    metadata_path.write_text(_canonical_json(metadata), encoding="utf-8")
    manifest_path.write_text(_canonical_json(manifest), encoding="utf-8")

    return PublishResult(
        geojson_path=geojson_path,
        metadata_path=metadata_path,
        manifest_path=manifest_path,
        geojson_sha256=sha,
        manifest_digest=manifest_digest,
        feature_count=len(stats) - withheld,
        withheld_count=withheld,
    )
