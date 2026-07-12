"""Corridor-level aggregation (EXP-03): merge contiguous significant blocks.

Uses hand-built segments/stats (not the shared ``bundle`` fixture) so each
test isolates one contiguity rule: shared endpoint + same street name merges;
a name change or a geometric gap (a "barrier") never bridges a corridor; and
a corridor never surfaces a block that wasn't already significant and
publishable on its own.
"""

from __future__ import annotations

from nearmiss.models import Segment, SegmentStats
from nearmiss.stats.corridors import build_corridors

RATE_PER = 1000.0
Z = 1.96
SMALL_N = 5


def _segment(seg_id: str, name: str, coords: tuple[tuple[float, float], ...]) -> Segment:
    return Segment(id=seg_id, name=name, coords=coords)


def _stat(
    seg_id: str,
    *,
    count: int,
    exposure: float | None,
    rate: float | None,
    significant: bool,
    publishable: bool = True,
) -> SegmentStats:
    return SegmentStats(
        segment_id=seg_id,
        report_count=count,
        n=count,
        exposure_estimate=exposure,
        exposure_source="synthetic",
        exposure_date="2026-01-01",
        rate=rate,
        rate_ci_low=rate,
        rate_ci_high=rate,
        getis_ord_z=2.5 if significant else 0.0,
        significant=significant,
        confidence_label="certain",
        publishable=publishable,
    )


def test_two_contiguous_significant_same_name_segments_merge() -> None:
    segments = [
        _segment("seg-a", "5th St (C-D)", ((38.0, -121.0), (38.0, -120.999))),
        _segment("seg-b", "5th St (D-E)", ((38.0, -120.999), (38.0, -120.998))),
    ]
    stats = [
        _stat("seg-a", count=6, exposure=300.0, rate=20.0, significant=True),
        _stat("seg-b", count=6, exposure=300.0, rate=20.0, significant=True),
    ]
    corridors = build_corridors(stats, segments, RATE_PER, Z, SMALL_N)
    assert len(corridors) == 1
    c = corridors[0]
    assert set(c.segment_ids) == {"seg-a", "seg-b"}
    assert c.report_count == 12
    assert c.n == 12
    assert c.exposure_estimate == 600.0
    assert c.rate is not None and c.rate == 20.0  # same rate as each member (12/600 == 6/300)
    assert c.name == "5th St (C–E)"
    assert c.significant is True
    assert c.publishable is True


def test_gap_between_same_name_segments_does_not_merge() -> None:
    # Same street name, same-shaped spans, but the geometry does NOT share an
    # endpoint (e.g. a park or a freeway crossing breaks the block) — a "barrier".
    segments = [
        _segment("seg-a", "5th St (C-D)", ((38.0, -121.0), (38.0, -120.999))),
        _segment("seg-b", "5th St (D-E)", ((38.0, -120.900), (38.0, -120.899))),
    ]
    stats = [
        _stat("seg-a", count=6, exposure=300.0, rate=20.0, significant=True),
        _stat("seg-b", count=6, exposure=300.0, rate=20.0, significant=True),
    ]
    corridors = build_corridors(stats, segments, RATE_PER, Z, SMALL_N)
    assert corridors == []


def test_different_street_names_do_not_merge_even_if_touching() -> None:
    segments = [
        _segment("seg-a", "5th St (C-D)", ((38.0, -121.0), (38.0, -120.999))),
        _segment("seg-b", "D St (4th-5th)", ((38.0, -120.999), (38.001, -120.999))),
    ]
    stats = [
        _stat("seg-a", count=6, exposure=300.0, rate=20.0, significant=True),
        _stat("seg-b", count=6, exposure=300.0, rate=20.0, significant=True),
    ]
    corridors = build_corridors(stats, segments, RATE_PER, Z, SMALL_N)
    assert corridors == []


def test_non_significant_neighbor_is_excluded_from_the_corridor() -> None:
    segments = [
        _segment("seg-a", "5th St (C-D)", ((38.0, -121.0), (38.0, -120.999))),
        _segment("seg-b", "5th St (D-E)", ((38.0, -120.999), (38.0, -120.998))),
        _segment("seg-c", "5th St (E-F)", ((38.0, -120.998), (38.0, -120.997))),
    ]
    stats = [
        _stat("seg-a", count=6, exposure=300.0, rate=20.0, significant=True),
        _stat("seg-b", count=1, exposure=300.0, rate=3.3, significant=False),
        _stat("seg-c", count=6, exposure=300.0, rate=20.0, significant=True),
    ]
    corridors = build_corridors(stats, segments, RATE_PER, Z, SMALL_N)
    # seg-b breaks the chain: seg-a and seg-c are each alone -> no corridor forms.
    assert corridors == []


def test_lone_significant_segment_forms_no_corridor() -> None:
    segments = [_segment("seg-a", "5th St (C-D)", ((38.0, -121.0), (38.0, -120.999)))]
    stats = [_stat("seg-a", count=6, exposure=300.0, rate=20.0, significant=True)]
    assert build_corridors(stats, segments, RATE_PER, Z, SMALL_N) == []


def test_withheld_segment_is_never_pulled_into_a_corridor() -> None:
    segments = [
        _segment("seg-a", "5th St (C-D)", ((38.0, -121.0), (38.0, -120.999))),
        _segment("seg-b", "5th St (D-E)", ((38.0, -120.999), (38.0, -120.998))),
    ]
    stats = [
        _stat("seg-a", count=6, exposure=300.0, rate=20.0, significant=True),
        # significant=True but withheld for k-anonymity -- must never be merged in.
        _stat("seg-b", count=2, exposure=300.0, rate=6.6, significant=True, publishable=False),
    ]
    corridors = build_corridors(stats, segments, RATE_PER, Z, SMALL_N)
    assert corridors == []


def test_corridor_publishable_report_count_never_below_min_publish_n() -> None:
    # Regression guard for the k-anonymity invariant asserted in publish.py:
    # a corridor's report_count is a sum of already-publishable segments, so it
    # can never itself fall (0, min_publish_n).
    segments = [
        _segment("seg-a", "5th St (C-D)", ((38.0, -121.0), (38.0, -120.999))),
        _segment("seg-b", "5th St (D-E)", ((38.0, -120.999), (38.0, -120.998))),
    ]
    stats = [
        _stat("seg-a", count=3, exposure=150.0, rate=20.0, significant=True),
        _stat("seg-b", count=3, exposure=150.0, rate=20.0, significant=True),
    ]
    corridors = build_corridors(stats, segments, RATE_PER, Z, SMALL_N)
    assert len(corridors) == 1
    assert corridors[0].report_count >= 3  # >= the min_publish_n each member cleared


def test_three_segment_chain_merges_in_traversal_order() -> None:
    segments = [
        _segment("seg-c", "5th St (D-E)", ((38.0, -120.999), (38.0, -120.998))),
        _segment("seg-a", "5th St (C-D)", ((38.0, -121.0), (38.0, -120.999))),
        _segment("seg-e", "5th St (E-F)", ((38.0, -120.998), (38.0, -120.997))),
    ]
    stats = [
        _stat("seg-c", count=6, exposure=300.0, rate=20.0, significant=True),
        _stat("seg-a", count=6, exposure=300.0, rate=20.0, significant=True),
        _stat("seg-e", count=6, exposure=300.0, rate=20.0, significant=True),
    ]
    corridors = build_corridors(stats, segments, RATE_PER, Z, SMALL_N)
    assert len(corridors) == 1
    c = corridors[0]
    assert set(c.segment_ids) == {"seg-a", "seg-c", "seg-e"}
    assert c.name == "5th St (C–F)"
    assert c.report_count == 18


def test_missing_exposure_on_one_member_withholds_the_corridor_rate() -> None:
    segments = [
        _segment("seg-a", "5th St (C-D)", ((38.0, -121.0), (38.0, -120.999))),
        _segment("seg-b", "5th St (D-E)", ((38.0, -120.999), (38.0, -120.998))),
    ]
    stats = [
        _stat("seg-a", count=6, exposure=300.0, rate=20.0, significant=True),
        _stat("seg-b", count=6, exposure=None, rate=None, significant=True),
    ]
    corridors = build_corridors(stats, segments, RATE_PER, Z, SMALL_N)
    assert len(corridors) == 1
    c = corridors[0]
    assert c.exposure_estimate is None
    assert c.rate is None
    assert c.rate_ci_low is None
    assert c.rate_ci_high is None
    assert c.report_count == 12  # counts still sum even without a shared denominator
