"""Exact-value guards for the spatial-statistics core (mutation-hardening).

The known-answer fixtures in ``test_hotspot.py`` prove the *pipeline* recovers the
planted hotspot, but they only pin coarse properties (seg-06 is the hottest and
significant). Advisory mutation testing (``make mutation``, backlog #15) showed
that lets whole classes of silent numerical bugs survive inside
:func:`nearmiss.stats.getis_ord.getis_ord_star` — a flipped sign in the Gi*
numerator, a ``*``/``/`` slip in the standard-error denominator, an ``n - 1`` ->
``n + 1`` off-by-one in the variance term — because they perturb the z-scores
without changing the ranking.

These tests close that gap by pinning the Gi* z-scores of a tiny, fully
hand-computable arrangement to their exact closed-form values, and by nailing the
degenerate branches and the FDR ranking. See docs/MUTATION-TESTING.md.
"""

from __future__ import annotations

import math

import pytest

from nearmiss.config import Config
from nearmiss.models import CleanRecord, Exposure, Segment
from nearmiss.stats import analyze
from nearmiss.stats.getis_ord import benjamini_hochberg, getis_ord_star
from nearmiss.stats.rates import rate_with_ci


def test_getis_ord_star_pins_exact_zscores() -> None:
    """Gi* z-scores match the exact closed form on a hand-computable neighbor map.

    Two hot neighbours (A, B) and two cold neighbours (C, D), each pair mutually
    adjacent (as a network-adjacency neighbor map, e.g. from SegmentGraph, would
    give a pair of segments meeting at a shared intersection) and the two pairs
    NOT neighbors of each other. Membership is unambiguous and the weights are
    binary, so the statistic is exactly solvable:

        n = 4,  mean = 5,  s = 5;
        every segment neighbours exactly its own pair (w_sum = w2_sum = 2), so the
        standardization factor is (n*w2_sum - w_sum^2)/(n-1) = 4/3 (deliberately
        NOT 1, so a ``*``/``/`` slip in the standard error cannot hide);
        z_A = z_B = +sqrt(3);  z_C = z_D = -sqrt(3).

    This single assertion kills the numerator sign flip, the denominator ``*``/``/``
    swap, the ``(n - 1)`` off-by-one, and the mean/variance mutants.
    """
    values = {"A": 10.0, "B": 10.0, "C": 0.0, "D": 0.0}
    neighbor_ids = {"A": {"B"}, "B": {"A"}, "C": {"D"}, "D": {"C"}}

    z = getis_ord_star(values, neighbor_ids)

    assert z["A"] == pytest.approx(math.sqrt(3.0), abs=1e-9)
    assert z["B"] == pytest.approx(math.sqrt(3.0), abs=1e-9)
    assert z["C"] == pytest.approx(-math.sqrt(3.0), abs=1e-9)
    assert z["D"] == pytest.approx(-math.sqrt(3.0), abs=1e-9)
    # The hot pair is strictly positive and the cold pair strictly negative:
    # a numerator sign flip would not preserve this opposition.
    assert z["A"] > 0.0 > z["C"]


def test_getis_ord_star_boundary_and_degenerate_inputs() -> None:
    """The n == 3 boundary computes; undefined cases return exactly 0.0 for every id."""
    # Exactly three segments is the MINIMUM that standardizes (guard is `n < 3`),
    # and it must still produce a real hotspot, not silently collapse to zeros.
    # Same neighbor map as above minus D: A,B neighbour each other, C is isolated
    # (empty neighbor set, so only itself) -> z_A = z_B = +sqrt(2), z_C = -sqrt(2).
    # Kills the `n < 3` -> `n <= 3` off-by-one.
    three = getis_ord_star(
        {"A": 10.0, "B": 10.0, "C": 0.0},
        {"A": {"B"}, "B": {"A"}, "C": set()},
    )
    assert three["A"] == pytest.approx(math.sqrt(2.0), abs=1e-9)
    assert three["C"] == pytest.approx(-math.sqrt(2.0), abs=1e-9)

    # Fewer than three segments -> no stable standardization -> 0.0 (never None).
    two = getis_ord_star({"A": 1.0, "B": 9.0}, {"A": {"B"}, "B": {"A"}})
    assert two == {"A": 0.0, "B": 0.0}

    # Zero spatial variance (all values identical) -> s == 0 -> 0.0 everywhere.
    neighbor_ids = {"A": {"B"}, "B": {"A"}, "C": set()}
    flat = getis_ord_star({"A": 5.0, "B": 5.0, "C": 5.0}, neighbor_ids)
    assert flat == {"A": 0.0, "B": 0.0, "C": 0.0}


def test_benjamini_hochberg_ranks_by_pvalue_and_handles_edges() -> None:
    """FDR rejection is by p-value rank, with correct empty/singleton behaviour."""
    # A single clearly significant test is rejected (m == 1 path).
    assert benjamini_hochberg({"only": 0.001}, 0.05) == {"only"}

    # Nothing clears its rank-adjusted threshold -> empty set, not a partial reject
    # and not an error (guards the loop's initial threshold_rank == 0).
    assert benjamini_hochberg({"a": 0.9, "b": 0.95}, 0.05) == set()

    # Ordering is by p-value, NOT by key/insertion order: the significant id wins
    # even though it sorts LAST alphabetically.
    assert benjamini_hochberg({"z": 0.001, "a": 0.5}, 0.05) == {"z"}


def _clean(report_id: str, segment_id: str, flags: tuple[str, ...] = ()) -> CleanRecord:
    return CleanRecord(
        report_id=report_id,
        occurred_at="2026-06-10T12:00:00-07:00",
        segment_id=segment_id,
        hazard_type="close_pass",
        severity="near_miss",
        mode="cyclist",
        snapped_distance_m=1.0,
        quality_flags=flags,
    )


def test_quality_tier_split_primary_rate_excludes_low_confidence(config: Config) -> None:
    """The PRIMARY rate is built from the N clean records only; the all-records
    rate uses N+M; the sensitivity delta and excluded fraction are exact.

    Segment ``seg-a`` has N=5 clean records and M=10 ``low_accuracy`` records over an
    exposure of 1000 (so a rate is numerically its count). The primary rate must be
    5/1000, the all-records rate 15/1000, and because 15 falls outside the Byar CI of
    the primary count (5) the signed delta is reported. ``report_count``/``n`` stay the
    all-records total. The excluded fraction is M / (N + M) = 10/15.
    """
    n_clean, m_low = 5, 10
    records = [_clean(f"c-{i}", "seg-a") for i in range(n_clean)]
    records += [_clean(f"l-{i}", "seg-a", ("low_accuracy",)) for i in range(m_low)]

    segments = [
        Segment(id="seg-a", name="A St", coords=((38.50, -121.70), (38.50, -121.699))),
        # A second, report-free segment so Getis-Ord has >1 id; it must not perturb
        # the excluded fraction (it contributes zero snapped records).
        Segment(id="seg-b", name="B St", coords=((38.60, -121.60), (38.60, -121.599))),
    ]
    exposure = {
        "seg-a": Exposure("seg-a", 1000.0, "test", "2026-01-01"),
        "seg-b": Exposure("seg-b", 1000.0, "test", "2026-01-01"),
    }

    result = analyze(records, [], segments, exposure, config)
    by_id = {s.segment_id: s for s in result.segments}
    a = by_id["seg-a"]

    # report_count / n stay the ALL-records total.
    assert a.report_count == n_clean + m_low
    assert a.n == n_clean + m_low

    # Published rate is the PRIMARY (clean-only) rate.
    rate_primary, _, hi_primary = rate_with_ci(
        n_clean, 1000.0, config.rate_per, config.confidence_z
    )
    rate_all, _, _ = rate_with_ci(n_clean + m_low, 1000.0, config.rate_per, config.confidence_z)
    assert a.rate == pytest.approx(rate_primary)
    assert a.rate == pytest.approx(5.0)

    # The all-records rate lands outside the primary CI, so a delta is reported.
    assert rate_all > hi_primary
    assert a.rate_sensitivity_delta == pytest.approx(round(rate_all - rate_primary, 4))
    assert a.rate_sensitivity_delta == pytest.approx(10.0)

    # Excluded fraction is exactly M / (N + M) across all snapped records (rounded).
    assert result.excluded_low_confidence_fraction == round(m_low / (n_clean + m_low), 4)


def test_quality_tier_no_delta_when_all_records_rate_inside_primary_ci(config: Config) -> None:
    """A single excluded record that leaves the rate inside the primary CI reports
    no delta (delta is only raised on a MATERIAL move), and never changes n."""
    records = [_clean(f"c-{i}", "seg-a") for i in range(6)]
    records.append(_clean("l-0", "seg-a", ("far_snap",)))
    segments = [
        Segment(id="seg-a", name="A St", coords=((38.50, -121.70), (38.50, -121.699))),
        Segment(id="seg-b", name="B St", coords=((38.60, -121.60), (38.60, -121.599))),
    ]
    exposure = {
        "seg-a": Exposure("seg-a", 1000.0, "test", "2026-01-01"),
        "seg-b": Exposure("seg-b", 1000.0, "test", "2026-01-01"),
    }
    result = analyze(records, [], segments, exposure, config)
    a = {s.segment_id: s for s in result.segments}["seg-a"]
    assert a.report_count == 7  # all-records total unchanged by the split
    assert a.rate == pytest.approx(6.0)  # primary rate = 6 clean records
    assert a.rate_sensitivity_delta is None  # 7 is well within the CI of 6
    assert result.excluded_low_confidence_fraction == round(1 / 7, 4)
