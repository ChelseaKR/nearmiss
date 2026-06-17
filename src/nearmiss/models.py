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
        )


@dataclass(frozen=True)
class Segment:
    """A public street segment. Geometry is public infrastructure, not private."""

    id: str
    name: str
    coords: tuple[tuple[float, float], ...]  # ((lat, lon), ...) along the segment


@dataclass(frozen=True)
class Exposure:
    """A per-segment denominator. Always carries its source and date (hard rule #1)."""

    segment_id: str
    estimate: float
    source: str
    date: str  # ISO date the exposure figure is as-of


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
    hazard_breakdown: dict[str, int] = field(default_factory=dict)
    quality_flags: tuple[str, ...] = ()
