"""MAUP rank-stability sensitivity (RR-05).

Re-segmenting the network must not invent or destroy the planted hotspot: the
Davis fixture's planted 5th St hotspot (seg-06) should survive a coarser
re-segmentation as the top-ranked, still-significant cluster, and the
re-segmentation itself must be deterministic and genuinely coarser.
"""

from __future__ import annotations

import dataclasses

from nearmiss.config import Config
from nearmiss.engine import AnalysisBundle, load_city
from nearmiss.models import CleanRecord, Exposure, Segment, SegmentStats
from nearmiss.stats import analyze
from nearmiss.stats.aggregate import aggregate
from nearmiss.stats.maup import _pair_segments, rank_stability


def test_pairing_is_deterministic_and_coarser(bundle: AnalysisBundle) -> None:
    first = _pair_segments(bundle.segments)
    second = _pair_segments(bundle.segments)
    assert first == second  # deterministic
    n = len(bundle.segments)
    units = len(set(first.values()))
    # Greedy pairwise merge roughly halves the unit count (ceil(n/2)).
    assert units == (n + 1) // 2
    # Every segment is assigned exactly once.
    assert set(first) == {s.id for s in bundle.segments}


def test_planted_hotspot_survives_resegmentation(bundle: AnalysisBundle, config: Config) -> None:
    exposure = load_city(config).exposure
    agg = aggregate(bundle.records)
    rs = rank_stability(
        bundle.result.segments,
        bundle.segments,
        exposure,
        config,
        primary_counts={sid: a.count_primary for sid, a in agg.items()},
    )
    assert rs.top_hotspot_id == "seg-06"  # same hotspot the primary analysis ranks first
    assert rs.coarse_units < rs.fine_units  # genuinely coarser
    # The coarse unit holding the hotspot leads the coarse ranking AND stays significant.
    assert rs.top_hotspot_coarse_rank == 1
    assert rs.top_hotspot_still_significant is True
    assert rs.top_hotspot_survives is True
    # The top-k ranking is largely preserved across the re-segmentation.
    assert rs.topk_overlap >= 0.5


def test_analysis_exposes_rank_stability(bundle: AnalysisBundle) -> None:
    rs = bundle.result.rank_stability
    assert rs is not None
    assert rs.top_hotspot_survives is True
    assert rs.top_hotspot_id == "seg-06"


def _seg(sid: str, lat: float, lon: float) -> Segment:
    return Segment(id=sid, name=sid, coords=((lat, lon), (lat, lon + 0.0002)))


def _stat(sid: str, count: int, exposure: float | None, rate: float | None) -> SegmentStats:
    return SegmentStats(
        segment_id=sid,
        report_count=count,
        n=count,
        exposure_estimate=exposure,
        exposure_source="test" if exposure is not None else None,
        exposure_date="2026-01-01" if exposure is not None else None,
        rate=rate,
        rate_ci_low=None,
        rate_ci_high=None,
        getis_ord_z=None,
        significant=False,
        confidence_label="certain" if rate is not None else "exposure_unknown",
    )


def test_exposure_less_counts_never_enter_a_coarse_rate(config: Config) -> None:
    """ "Every rate has a denominator" must hold for the coarse units too.

    A segment with reports but no usable exposure gets no rate in the primary
    analysis; its count must not leak into a coarse unit's numerator while its
    (nonexistent) exposure is absent from the denominator — that would inflate
    the coarse rate and could flip the rank-stability verdict.
    """
    # Two well-separated pairs: (a, b) and (c, d). b has 100 reports but NO
    # usable exposure; c is the genuine fine-grained top hotspot.
    segments = [
        _seg("seg-a", 38.5500, -121.7400),
        _seg("seg-b", 38.5504, -121.7400),  # ~45 m north of a -> pairs with a
        _seg("seg-c", 38.6000, -121.7400),  # ~5.5 km away -> pairs with d
        _seg("seg-d", 38.6004, -121.7400),
    ]
    stats = [
        _stat("seg-a", 3, 1000.0, 3.0),
        _stat("seg-b", 100, None, None),  # reports without a denominator
        _stat("seg-c", 9, 1000.0, 9.0),
        _stat("seg-d", 0, 1000.0, 0.0),
    ]
    exposure_map = {
        "seg-a": Exposure("seg-a", 1000.0, "test", "2026-01-01"),
        "seg-c": Exposure("seg-c", 1000.0, "test", "2026-01-01"),
        "seg-d": Exposure("seg-d", 1000.0, "test", "2026-01-01"),
    }
    rs = rank_stability(
        stats,
        segments,
        exposure_map,
        config,
        k=2,
        primary_counts={s.segment_id: s.report_count for s in stats},
    )
    assert rs.top_hotspot_id == "seg-c"
    # With the invariant enforced, seg-c's coarse unit (rate 9/2000) outranks
    # seg-a's (rate 3/1000). If seg-b's denominator-less 100 reports leaked into
    # the numerator, seg-a's unit would show ~103/1000 and take rank 1.
    assert rs.top_hotspot_coarse_rank == 1


def _line(sid: str, lat: float, lon: float) -> Segment:
    """A short east-west segment centred near (lat, lon)."""
    return Segment(id=sid, name=sid, coords=((lat, lon), (lat, lon + 0.0002)))


def _record(rid: str, sid: str, *, low_confidence: bool) -> CleanRecord:
    return CleanRecord(
        report_id=rid,
        occurred_at="2026-03-01T08:00:00Z",
        segment_id=sid,
        hazard_type="close_pass",
        severity="near_miss",
        mode="bike",
        snapped_distance_m=5.0,
        quality_flags=("low_accuracy",) if low_confidence else (),
    )


def test_coarse_rates_use_the_primary_count_the_published_rate_uses(config: Config) -> None:
    """The re-segmentation check must swap the units and nothing else.

    The published rate is the PRIMARY rate: low-confidence records
    (`low_accuracy` / `far_snap`) are excluded from its numerator
    (METHODOLOGY §2, claim `low-confidence-excluded-from-primary`). If the coarse
    rate is built from the all-records count instead, the check compares a
    primary-count fine ranking against an all-records coarse ranking, so it can
    report a hotspot "did not survive re-segmentation" when what actually moved
    was the numerator definition, which is a MAUP finding that is not about MAUP.

    Here seg-c carries six low-confidence reports. On the published (primary)
    numerator seg-a's coarse unit leads; on the all-records numerator seg-c's
    does.
    """
    segments = [
        _line("seg-a", 38.5500, -121.7400),
        _line("seg-b", 38.5504, -121.7400),  # ~45 m from a -> pairs with a
        _line("seg-c", 38.6000, -121.7400),  # ~5.5 km away -> pairs with d
        _line("seg-d", 38.6004, -121.7400),
    ]
    exposure_map = {s.id: Exposure(s.id, 100.0, "test", "2026-01-01") for s in segments}
    records = [_record(f"a{i}", "seg-a", low_confidence=False) for i in range(5)]
    records += [_record(f"c{i}", "seg-c", low_confidence=False) for i in range(2)]
    records += [_record(f"x{i}", "seg-c", low_confidence=True) for i in range(6)]

    result = analyze(records, [], segments, exposure_map, config)
    rs = result.rank_stability
    assert rs is not None
    assert rs.top_hotspot_id == "seg-a"  # 5/100 primary beats seg-c's 2/100
    # seg-a's coarse unit rates 5/200; seg-c's rates 2/200 on the primary count
    # and 8/200 on the all-records count. Only the primary numerator keeps the
    # published top segment at coarse rank 1.
    assert rs.top_hotspot_coarse_rank == 1


def test_coarse_units_respect_the_configured_exposure_floor(config: Config) -> None:
    """A denominator the primary analysis refused must not reappear coarsened.

    `is_usable` takes the configured `exposure_floor` (METHODOLOGY §3.3): an
    estimate at or below it is "exposure unknown", not a denominator. The MAUP
    check has to apply the same floor, or a segment published as unrated can
    still push a coarse unit up the ranking through the back door.
    """
    cfg = dataclasses.replace(config, exposure_floor=500.0)
    segments = [
        _line("seg-a", 38.5500, -121.7400),
        _line("seg-b", 38.5504, -121.7400),
        _line("seg-c", 38.6000, -121.7400),
        _line("seg-d", 38.6004, -121.7400),
    ]
    stats = [
        _stat("seg-a", 5, 1000.0, 5.0),
        _stat("seg-b", 50, 100.0, None),  # below the floor: published unrated
        _stat("seg-c", 20, 1000.0, 20.0),
        _stat("seg-d", 0, 1000.0, 0.0),
    ]
    exposure_map = {
        "seg-a": Exposure("seg-a", 1000.0, "test", "2026-01-01"),
        "seg-b": Exposure("seg-b", 100.0, "test", "2026-01-01"),
        "seg-c": Exposure("seg-c", 1000.0, "test", "2026-01-01"),
        "seg-d": Exposure("seg-d", 1000.0, "test", "2026-01-01"),
    }
    rs = rank_stability(
        stats,
        segments,
        exposure_map,
        cfg,
        k=2,
        primary_counts={s.segment_id: s.report_count for s in stats},
    )
    assert rs.top_hotspot_id == "seg-c"
    # Floor respected: seg-a's unit rates 5/1000, seg-c's 20/2000 -> seg-c leads.
    # Floor ignored: seg-b's 50 reports over 100 exposure lift seg-a's unit to
    # 55/1100 and seg-c falls to rank 2.
    assert rs.top_hotspot_coarse_rank == 1
