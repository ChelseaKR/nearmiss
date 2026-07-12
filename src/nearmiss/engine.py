"""End-to-end orchestration tying the stages together.

This is the one place that runs intake-free loading, the pipeline, and the
statistics in order, so the CLI commands and the tests share exactly one code
path (reproducibility / testability).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from . import pipeline
from .config import Config
from .errors import NearmissError
from .loaders import load_exposure, load_reports, load_streets, reports_from_dicts
from .models import CleanRecord, Exposure, Report, Segment
from .stats import AnalysisResult, analyze


@dataclass
class CityInputs:
    reports: list[Report]
    segments: list[Segment]
    exposure: dict[str, Exposure]


def load_city(config: Config) -> CityInputs:
    return CityInputs(
        reports=reports_from_dicts(load_reports(config.reports_path)),
        segments=load_streets(config.streets_path),
        exposure=load_exposure(config.exposure_path),
    )


@dataclass
class AnalysisBundle:
    result: AnalysisResult
    records: list[CleanRecord]
    summary: dict[str, int]
    segments: list[Segment]
    exposure_unmatched: list[str]
    # Per-stage telemetry for the run manifest / stage logs: one
    # {"stage": str, "counts": dict[str, int], "ms": float} per timed stage. The
    # counts are deterministic (they go into the hashed provenance section); the
    # ``ms`` wall-times are an unhashed sidecar (see :mod:`nearmiss.manifest`).
    stages: list[dict[str, object]] = field(default_factory=list)


def _elapsed_ms(start: float) -> float:
    """Wall-time since ``start`` (a ``perf_counter`` value), in milliseconds."""
    return round((time.perf_counter() - start) * 1000.0, 3)


def build_analysis(config: Config) -> AnalysisBundle:
    stages: list[dict[str, object]] = []

    t0 = time.perf_counter()
    city = load_city(config)
    stages.append(
        {
            "stage": "load",
            "counts": {
                "reports": len(city.reports),
                "segments": len(city.segments),
                "exposure": len(city.exposure),
            },
            "ms": _elapsed_ms(t0),
        }
    )

    # Exposure joins to streets by exact segment_id. A TOTAL mismatch almost
    # always means the two layers use different id schemes — fail loudly rather
    # than silently producing exposure_coverage = 0% (which would read as "no
    # denominators" instead of "you wired it up wrong").
    seg_ids = {s.id for s in city.segments}
    exp_ids = set(city.exposure)
    if exp_ids and not (exp_ids & seg_ids):
        raise NearmissError(
            "no exposure segment_id matches any street segment_id — the exposure layer and the "
            "street network must use the same id scheme "
            f"(exposure e.g. {sorted(exp_ids)[:3]}, streets e.g. {sorted(seg_ids)[:3]})"
        )
    unmatched = sorted(exp_ids - seg_ids)

    # Optional open/supplied weather dataset for the time-of-day correlation hook.
    weather_days = None
    weather_source = None
    if config.weather_path is not None:
        from .stats.temporal import load_weather

        record = load_weather(config.weather_path)
        weather_days = record.days
        weather_source = record.source

    t1 = time.perf_counter()
    records, summary = pipeline.run(city.reports, city.segments, config)
    stages.append({"stage": "pipeline", "counts": dict(summary), "ms": _elapsed_ms(t1)})

    t2 = time.perf_counter()
    result = analyze(
        records,
        city.reports,
        city.segments,
        city.exposure,
        config,
        weather=weather_days,
        weather_source=weather_source,
    )
    withheld = sum(1 for s in result.segments if not s.publishable)
    stages.append(
        {
            "stage": "analyze",
            "counts": {
                "segments_total": len(result.segments),
                "segments_publishable": len(result.segments) - withheld,
                "segments_withheld_low_count": withheld,
                "exposure_matched": len(city.exposure) - len(unmatched),
                "exposure_unmatched": len(unmatched),
            },
            "ms": _elapsed_ms(t2),
        }
    )

    return AnalysisBundle(
        result=result,
        records=records,
        summary=summary,
        segments=city.segments,
        exposure_unmatched=unmatched,
        stages=stages,
    )
