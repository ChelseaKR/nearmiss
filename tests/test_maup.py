"""MAUP rank-stability sensitivity (RR-05).

Re-segmenting the network must not invent or destroy the planted hotspot: the
Davis fixture's planted 5th St hotspot (seg-06) should survive a coarser
re-segmentation as the top-ranked, still-significant cluster, and the
re-segmentation itself must be deterministic and genuinely coarser.
"""

from __future__ import annotations

from nearmiss.config import Config
from nearmiss.engine import AnalysisBundle, load_city
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
