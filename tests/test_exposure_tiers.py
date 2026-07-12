"""FIX-04: exposure trust tiers, corroboration, the exposure floor, and the
temporal-alignment staleness flag, exercised directly through ``stats.analyze``
with a minimal synthetic segment/report/exposure setup (no fixture files needed).
"""

from __future__ import annotations

import dataclasses

from nearmiss.config import Config
from nearmiss.models import CleanRecord, Exposure, ExposureReading, Segment
from nearmiss.stats import analyze

SEGMENT = Segment(id="a", name="A St", coords=((0.0, 0.0), (0.0, 0.001)))


def _config(**overrides: object) -> Config:
    base = Config(
        city="Test",
        streets_path=None,  # type: ignore[arg-type]
        reports_path=None,  # type: ignore[arg-type]
        exposure_path=None,  # type: ignore[arg-type]
        raw_dir=None,  # type: ignore[arg-type]
        out_dir=None,  # type: ignore[arg-type]
        min_publish_n=1,  # keep the single test segment publishable
    )
    return dataclasses.replace(base, **overrides)  # type: ignore[arg-type]


def _records(n: int, occurred_at: str = "2026-06-01T00:00:00-07:00") -> list[CleanRecord]:
    return [
        CleanRecord(
            report_id=f"r{i}",
            occurred_at=occurred_at,
            segment_id="a",
            hazard_type="close_pass",
            severity="near_miss",
            mode="cyclist",
            snapped_distance_m=1.0,
        )
        for i in range(n)
    ]


def test_exposure_tier_is_published_from_the_exposure_row() -> None:
    exposure_map = {"a": Exposure("a", 100.0, "counts", "2026-06-01", tier="observed")}
    result = analyze(_records(5), [], [SEGMENT], exposure_map, _config())
    (stat,) = result.segments
    assert stat.exposure_tier == "observed"


def test_exposure_tier_defaults_to_unknown_when_no_exposure_row() -> None:
    result = analyze(_records(5), [], [SEGMENT], {}, _config())
    (stat,) = result.segments
    assert stat.exposure_tier == "unknown"
    assert "exposure_unknown" in stat.quality_flags


def test_exposure_disagreement_is_published_for_multi_source_segments() -> None:
    exposure_map = {
        "a": Exposure(
            "a",
            100.0,
            "counts",
            "2026-06-01",
            tier="observed",
            sources=(ExposureReading(60.0, "demand-model", "2026-06-01", tier="modeled"),),
        )
    }
    result = analyze(_records(5), [], [SEGMENT], exposure_map, _config())
    (stat,) = result.segments
    assert stat.exposure_disagreement == 0.4  # 1 - min(100,60)/max(100,60)


def test_exposure_disagreement_is_none_for_single_source_segments() -> None:
    exposure_map = {"a": Exposure("a", 100.0, "counts", "2026-06-01", tier="observed")}
    result = analyze(_records(5), [], [SEGMENT], exposure_map, _config())
    (stat,) = result.segments
    assert stat.exposure_disagreement is None


def test_exposure_floor_marks_a_below_floor_segment_exposure_unknown() -> None:
    exposure_map = {"a": Exposure("a", 5.0, "counts", "2026-06-01", tier="observed")}
    result = analyze(_records(5), [], [SEGMENT], exposure_map, _config(exposure_floor=10.0))
    (stat,) = result.segments
    assert stat.rate is None
    assert stat.confidence_label == "exposure_unknown"
    assert "exposure_unknown" in stat.quality_flags


def test_exposure_stale_flag_set_when_vintage_is_far_from_reports() -> None:
    exposure_map = {"a": Exposure("a", 100.0, "counts", "2020-01-01", tier="observed")}
    result = analyze(
        _records(5, occurred_at="2026-06-01T00:00:00-07:00"),
        [],
        [SEGMENT],
        exposure_map,
        _config(exposure_stale_days=365),
    )
    (stat,) = result.segments
    assert "exposure_stale" in stat.quality_flags


def test_exposure_stale_flag_absent_when_vintage_is_recent() -> None:
    exposure_map = {"a": Exposure("a", 100.0, "counts", "2026-05-20", tier="observed")}
    result = analyze(
        _records(5, occurred_at="2026-06-01T00:00:00-07:00"),
        [],
        [SEGMENT],
        exposure_map,
        _config(exposure_stale_days=365),
    )
    (stat,) = result.segments
    assert "exposure_stale" not in stat.quality_flags
