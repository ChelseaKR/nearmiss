"""Plain, inspectable data structures passed between pipeline stages.

These are deliberately simple dataclasses with no behavior beyond construction
and light serialization, so every stage's input and output can be dumped,
diffed, and tested. The closed vocabularies (mode / hazard type / severity)
mirror ``schema/report.schema.json`` exactly — the schema is authoritative and
intake validates against it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Mode = Literal["cyclist", "pedestrian", "wheelchair", "scooter", "other"]
HazardType = Literal[
    "close_pass", "dooring", "surface_hazard", "sightline", "signal", "debris", "other"
]
Severity = Literal["near_miss", "minor", "serious"]
ConfidenceLabel = Literal["certain", "uncertain", "exposure_unknown"]
# METHODOLOGY §3.1's trust ordering, most to least trusted: a direct count station,
# a calibrated demand model, or a third-party activity proxy (e.g. a fitness-app
# heatmap). "unknown" is the honest default for exposure rows that predate this
# field or omit it — never fabricated, never silently promoted to "observed".
ExposureTier = Literal["observed", "modeled", "proxy", "unknown"]

# Ordinal weight used only for summaries; never used to fabricate a rate.
SEVERITY_WEIGHT: dict[str, int] = {"near_miss": 1, "minor": 2, "serious": 3}


def _as_float(value: object) -> float:
    if not isinstance(value, (int, float, str)):
        raise TypeError(f"expected a number, got {type(value).__name__}")
    return float(value)


def _opt_float(value: object) -> float | None:
    return None if value is None else _as_float(value)


def _opt_str(value: object) -> str | None:
    return None if value is None else str(value)


@dataclass(frozen=True)
class Report:
    """A raw, precise, PRIVATE incoming report. Never published as-is."""

    id: str
    occurred_at: str  # ISO-8601
    lat: float
    lon: float
    mode: str
    hazard_type: str
    severity: str
    schema_version: str = "1.0.0"
    accuracy_m: float | None = None
    heading_deg: float | None = None
    note: str | None = None
    reporter_token: str | None = None
    address: str | None = None
    language: str = "en"

    @staticmethod
    def from_dict(d: dict[str, object]) -> Report:
        loc = d.get("location")
        lat = lon = 0.0
        accuracy: float | None = None
        if isinstance(loc, dict):
            lat = _as_float(loc.get("lat", 0.0))
            lon = _as_float(loc.get("lon", 0.0))
            accuracy = _opt_float(loc.get("accuracy_m"))
        return Report(
            id=str(d["id"]),
            occurred_at=str(d["occurred_at"]),
            lat=lat,
            lon=lon,
            accuracy_m=accuracy,
            mode=str(d["mode"]),
            hazard_type=str(d["hazard_type"]),
            severity=str(d["severity"]),
            schema_version=str(d.get("schema_version", "1.0.0")),
            heading_deg=_opt_float(d.get("heading_deg")),
            note=_opt_str(d.get("note")),
            reporter_token=_opt_str(d.get("reporter_token")),
            address=_opt_str(d.get("address")),
            language=str(d.get("language", "en")),
        )


@dataclass(frozen=True)
class Segment:
    """A public street segment. Geometry is public infrastructure, not private."""

    id: str
    name: str
    coords: tuple[tuple[float, float], ...]  # ((lat, lon), ...) along the segment


@dataclass(frozen=True)
class ExposureReading:
    """One contributing denominator reading, used to corroborate a segment's primary
    exposure (METHODOLOGY §3.1: "when two or more sources cover the same segment they
    can corroborate the denominator; a large disagreement ... is itself a finding").
    """

    estimate: float
    source: str
    date: str  # ISO date the exposure figure is as-of
    tier: ExposureTier = "unknown"


@dataclass(frozen=True)
class Exposure:
    """A per-segment denominator. Always carries its source and date (hard rule #1).

    ``tier`` records how much the estimate should be trusted (METHODOLOGY §3.1):
    a direct count is trusted more than a demand model, which is trusted more than
    a proxy layer. ``sources`` optionally carries additional corroborating readings
    for the same segment beyond the primary (estimate, source, date, tier) above;
    :func:`nearmiss.exposure.corroboration` compares them and a large disagreement
    is surfaced, not averaged away.
    """

    segment_id: str
    estimate: float
    source: str
    date: str  # ISO date the exposure figure is as-of
    tier: ExposureTier = "unknown"
    sources: tuple[ExposureReading, ...] = ()


@dataclass(frozen=True)
class CleanRecord:
    """A raw report after the pipeline: deduped, snapped, classified, flagged."""

    report_id: str
    occurred_at: str
    segment_id: str | None
    hazard_type: str
    severity: str
    mode: str
    snapped_distance_m: float | None
    quality_flags: tuple[str, ...] = ()


@dataclass
class SegmentStats:
    """Per-segment published statistics. The unit of the open dataset.

    Contains ONLY aggregates. No per-report coordinate, time, reporter token,
    note, mode, or severity reaches this structure (hard rule #4).
    """

    segment_id: str
    report_count: int
    n: int
    exposure_estimate: float | None
    exposure_source: str | None
    exposure_date: str | None
    rate: float | None
    rate_ci_low: float | None
    rate_ci_high: float | None
    getis_ord_z: float | None
    significant: bool
    confidence_label: ConfidenceLabel
    # False when withheld from publication for k-anonymity (0 < report_count < min_publish_n).
    publishable: bool = True
    hazard_breakdown: dict[str, int] = field(default_factory=dict)
    # Per-hazard-type exposure-normalized rate layers. The top-level ``rate`` is
    # the pooled rate across ALL hazard types (an explicit union); this maps each
    # hazard type with a count at or above the small-sample threshold to its own
    # aggregate rate + confidence interval. Types below the threshold are
    # suppressed (no entry at all) for the same small-n reason breakdowns are.
    # Aggregate-only invariant holds: values are {"count", "rate", "rate_ci_low",
    # "rate_ci_high"} — never any per-report datum.
    rates_by_type: dict[str, dict[str, float]] = field(default_factory=dict)
    quality_flags: tuple[str, ...] = ()
    # Trust tier of exposure_estimate ("observed"/"modeled"/"proxy"/"unknown"; FIX-04).
    exposure_tier: ExposureTier = "unknown"
    # Cross-source disagreement in [0, 1] (1 - min/max of all corroborating readings);
    # None when the segment has only a single exposure reading (nothing to corroborate).
    exposure_disagreement: float | None = None
    # Signed difference (all-records rate minus primary rate, in rate units) reported
    # only when the all-records rate falls outside the primary rate's confidence
    # interval — i.e. when excluding low-confidence reports materially moves the rate.
    # None when the two agree within the interval (the common case).
    rate_sensitivity_delta: float | None = None
