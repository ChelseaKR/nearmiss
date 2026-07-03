"""Confidence-interval methods: Byar Poisson interval and Wilson interval."""

from __future__ import annotations

import math

import pytest

from nearmiss.stats.rates import (
    pearson_dispersion,
    poisson_ci,
    quasi_poisson_ci,
    rate_with_ci,
    wilson_ci,
)


def test_poisson_ci_zero_count() -> None:
    low, high = poisson_ci(0)
    assert low == 0.0
    assert high > 0.0


def test_poisson_ci_contains_point_and_widens_relatively_for_small_n() -> None:
    for count in (1, 5, 20, 100):
        low, high = poisson_ci(count)
        assert low < count < high
    # Relative width shrinks as n grows (more data -> more certainty).
    lo1, hi1 = poisson_ci(2)
    lo2, hi2 = poisson_ci(200)
    assert (hi1 - lo1) / 2 > (hi2 - lo2) / 200


def test_rate_with_ci_scales_by_exposure() -> None:
    rate, low, high = rate_with_ci(6, 300.0, per=1000.0)
    assert rate == pytest.approx(20.0)
    assert low < rate < high


def test_rate_requires_positive_exposure() -> None:
    with pytest.raises(ValueError):
        rate_with_ci(5, 0.0)
    with pytest.raises(ValueError):
        rate_with_ci(5, -10.0)


# --- Overdispersion / quasi-Poisson (RR-02) ---------------------------------


def test_pearson_dispersion_is_about_one_for_poisson_consistent_counts() -> None:
    # Counts equal to the pooled-rate expectation on every segment -> no extra
    # variance -> dispersion well below the "materially above 1" overdispersion line.
    exposures = [1000.0] * 6
    counts = [5, 5, 5, 5, 5, 5]
    assert pearson_dispersion(counts, exposures) == pytest.approx(0.0, abs=1e-9)


def test_pearson_dispersion_detects_clustered_overdispersion() -> None:
    # A burst on one segment (clustered reporting) against an otherwise quiet
    # network is strongly overdispersed: variance >> mean.
    exposures = [1000.0] * 6
    counts = [0, 0, 0, 0, 0, 40]
    assert pearson_dispersion(counts, exposures) > 5.0


def test_pearson_dispersion_guards_degenerate_inputs() -> None:
    assert pearson_dispersion([], []) == 1.0  # no data
    assert pearson_dispersion([7], [100.0]) == 1.0  # single observation
    assert pearson_dispersion([0, 0, 0], [10.0, 10.0, 10.0]) == 1.0  # no events
    assert pearson_dispersion([5, 5], [0.0, 0.0]) == 1.0  # no exposure
    with pytest.raises(ValueError):
        pearson_dispersion([1, 2, 3], [10.0, 20.0])  # mismatched lengths


def test_quasi_poisson_ci_equals_poisson_when_not_overdispersed() -> None:
    for count in (0, 1, 5, 20):
        assert quasi_poisson_ci(count, 1.0) == poisson_ci(count)
        assert quasi_poisson_ci(count, 0.4) == poisson_ci(count)  # never narrows below Poisson


def test_quasi_poisson_ci_widens_by_sqrt_dispersion() -> None:
    # A count large enough that the widened lower bound does not hit the 0 clamp,
    # so the pure sqrt(phi) half-width scaling is exact.
    count, phi = 100, 4.0
    p_low, p_high = poisson_ci(count)
    q_low, q_high = quasi_poisson_ci(count, phi)
    # Half-widths about the point estimate scale by sqrt(phi) = 2.
    assert q_high - count == pytest.approx((p_high - count) * math.sqrt(phi))
    assert count - q_low == pytest.approx((count - p_low) * math.sqrt(phi))
    assert q_low >= 0.0  # lower bound never goes negative
    assert q_low < p_low and q_high > p_high


def test_quasi_poisson_ci_lower_bound_clamps_at_zero() -> None:
    low, _ = quasi_poisson_ci(2, 100.0)
    assert low == 0.0


def test_rate_with_ci_widens_for_overdispersion_without_moving_the_point() -> None:
    rate, lo, hi = rate_with_ci(6, 300.0, per=1000.0)
    rate_od, lo_od, hi_od = rate_with_ci(6, 300.0, per=1000.0, dispersion=9.0)
    assert rate_od == pytest.approx(rate)  # the rate point estimate is unchanged
    assert lo_od < lo and hi_od > hi  # only the interval widens
    assert lo_od >= 0.0


def test_wilson_ci_bounds() -> None:
    low, high = wilson_ci(3, 10)
    assert 0.0 <= low < 0.3 < high <= 1.0
    assert wilson_ci(0, 0) == (0.0, 0.0)


def test_wilson_ci_rejects_successes_over_trials() -> None:
    with pytest.raises(ValueError):
        wilson_ci(11, 10)
