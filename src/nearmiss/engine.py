"""End-to-end orchestration tying the stages together.

This is the one place that runs intake-free loading, the pipeline, and the
statistics in order, so the CLI commands and the tests share exactly one code
path (reproducibility / testability).
"""

from __future__ import annotations

from dataclasses import dataclass

from . import pipeline
from .config import Config
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


def build_analysis(config: Config) -> AnalysisBundle:
    city = load_city(config)
    records, summary = pipeline.run(city.reports, city.segments, config)
    result = analyze(records, city.reports, city.segments, city.exposure, config)
    return AnalysisBundle(result=result, records=records, summary=summary, segments=city.segments)
