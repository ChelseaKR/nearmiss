"""End-to-end orchestration tying the stages together.

This is the one place that runs intake-free loading, the pipeline, and the
statistics in order, so the CLI commands and the tests share exactly one code
path (reproducibility / testability).
"""

from __future__ import annotations

from dataclasses import dataclass

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


def build_analysis(config: Config) -> AnalysisBundle:
    city = load_city(config)

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

    records, summary = pipeline.run(city.reports, city.segments, config)
    result = analyze(
        records,
        city.reports,
        city.segments,
        city.exposure,
        config,
        weather=weather_days,
        weather_source=weather_source,
    )
    return AnalysisBundle(
        result=result,
        records=records,
        summary=summary,
        segments=city.segments,
        exposure_unmatched=unmatched,
    )
