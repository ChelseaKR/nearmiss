"""Confidence-interval methods: Byar Poisson interval and Wilson interval."""

from __future__ import annotations

import pytest

from nearmiss.stats.rates import poisson_ci, rate_with_ci, wilson_ci


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


def test_wilson_ci_bounds() -> None:
    low, high = wilson_ci(3, 10)
    assert 0.0 <= low < 0.3 < high <= 1.0
    assert wilson_ci(0, 0) == (0.0, 0.0)


def test_wilson_ci_rejects_successes_over_trials() -> None:
    with pytest.raises(ValueError):
        wilson_ci(11, 10)
