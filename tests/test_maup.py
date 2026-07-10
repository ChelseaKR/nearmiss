"""MAUP rank-stability sensitivity (RR-05).

Re-segmenting the network must not invent or destroy the planted hotspot: the
Davis fixture's planted 5th St hotspot (seg-06) should survive a coarser
re-segmentation as the top-ranked, still-significant cluster, and the
re-segmentation itself must be deterministic and genuinely coarser.
"""

from __future__ import annotations

from nearmiss.config import Config
from nearmiss.engine import AnalysisBundle, load_city
from nearmiss.models import Exposure, Segment, SegmentStats
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
    rs = rank_stability(bundle.result.segments, bundle.segments, exposure, config)
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
    rs = rank_stability(stats, segments, exposure_map, config, k=2)
    assert rs.top_hotspot_id == "seg-c"
    # With the invariant enforced, seg-c's coarse unit (rate 9/2000) outranks
    # seg-a's (rate 3/1000). If seg-b's denominator-less 100 reports leaked into
    # the numerator, seg-a's unit would show ~103/1000 and take rank 1.
    assert rs.top_hotspot_coarse_rank == 1
