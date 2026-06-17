"""The core honesty test: exposure normalization and Getis-Ord recover the truth.

The fixtures plant a hotspot (seg-06: low exposure, high rate) and a busy decoy
(seg-03: high exposure, the MOST raw reports, but a low rate). A correct analysis
must rank seg-06 first by rate, flag it as the unique significant cluster, and
must NOT be fooled by seg-03's raw volume.
"""

from __future__ import annotations

from nearmiss.engine import AnalysisBundle


def test_planted_hotspot_ranks_first_by_rate(bundle: AnalysisBundle) -> None:
    ranked = sorted(
        (s for s in bundle.result.segments if s.rate is not None),
        key=lambda s: s.rate or 0.0,
        reverse=True,
    )
    assert ranked[0].segment_id == "seg-06"


def test_busy_decoy_has_most_raw_reports_but_low_rate(bundle: AnalysisBundle) -> None:
    by_id = {s.segment_id: s for s in bundle.result.segments}
    busy, hot = by_id["seg-03"], by_id["seg-06"]
    # seg-03 has more raw reports than the hotspot...
    assert busy.report_count > hot.report_count
    # ...yet a far lower exposure-normalized rate.
    assert (busy.rate or 0.0) < (hot.rate or 0.0)
    # ...and it is NOT near the top of the ranking.
    ranked = sorted(
        (s for s in bundle.result.segments if s.rate is not None),
        key=lambda s: s.rate or 0.0,
        reverse=True,
    )
    top3 = {s.segment_id for s in ranked[:3]}
    assert "seg-03" not in top3


def test_getis_ord_uniquely_flags_the_hotspot(bundle: AnalysisBundle) -> None:
    significant = [s.segment_id for s in bundle.result.segments if s.significant]
    assert significant == ["seg-06"]
    # seg-06 also has the maximum Gi* z-score.
    zed = {s.segment_id: (s.getis_ord_z or 0.0) for s in bundle.result.segments}
    assert max(zed, key=lambda k: zed[k]) == "seg-06"
    assert zed["seg-06"] > 1.96


def test_small_n_segments_are_marked_uncertain(bundle: AnalysisBundle) -> None:
    by_id = {s.segment_id: s for s in bundle.result.segments}
    # seg-01 has n=2 (< small_n=5) -> uncertain; seg-06 has n=6 -> certain.
    assert by_id["seg-01"].confidence_label == "uncertain"
    assert by_id["seg-06"].confidence_label == "certain"
