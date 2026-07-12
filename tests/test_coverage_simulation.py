"""Seeded Monte-Carlo interval-coverage simulation (METHODOLOGY §9.2).

Section 9.2 promises that the confidence intervals are *checked by simulation*:
draw many datasets from a known true rate, build a 95% interval each time, and
confirm the intervals cover the truth close to 95% of the time. A method that
claims 95% but covers 80% is exactly the miscalibration this test exists to
expose (it is the lie the banned Wald interval tells).

This is the implementation of that promise for Byar's Poisson interval
(``stats/rates.poisson_ci``, the published default). It is deterministic — a
fixed-seed RNG makes the empirical coverage reproducible run to run — and marked
``slow`` because it draws thousands of samples per true rate.
"""

from __future__ import annotations

import random

import pytest

from nearmiss.stats.rates import poisson_ci

# Small-count regime the project actually operates in (Section 5): a handful of
# reports per segment. Coverage of a discrete interval oscillates with the mean,
# so we check several representative true rates rather than a single one.
TRUE_LAMBDAS = (1.0, 3.0, 5.0, 10.0, 25.0)
DRAWS = 2000
SEED = 20260702
# Byar's approximation targets 95% nominal coverage. The band is deliberately
# ASYMMETRIC around nominal, because the two directions mean different things:
#   * Under-coverage is the lie this test exists to catch — an interval that
#     claims 95% but covers 80% (what the banned Wald interval does at small
#     counts). The lower bound is therefore strict: 0.92 leaves only ~1.5% of
#     slack below nominal for lattice oscillation and Monte-Carlo noise
#     (~0.5% at 2000 draws).
#   * Over-coverage is SAFE, not a defect: like the exact Poisson interval it
#     approximates, Byar's method is conservative at small counts because the
#     Poisson is discrete, so at lambda in {1, 3} it legitimately covers ~0.98.
#     A conservative interval never over-claims precision, so the upper bound is
#     lenient (0.995) — it only fails a method that is absurdly, uselessly wide.
COVERAGE_LOW = 0.92
COVERAGE_HIGH = 0.995


def _poisson(rng: random.Random, lam: float) -> int:
    """Knuth's algorithm: a Poisson(lam) draw from a seeded ``random.Random``.

    Kept dependency-free (no numpy required) so the coverage check runs in the
    same "pure Python, runs anywhere" environment as the rest of the suite.
    """
    target = pow(2.718281828459045, -lam)
    k = 0
    p = 1.0
    while True:
        k += 1
        p *= rng.random()
        if p <= target:
            return k - 1


@pytest.mark.slow
@pytest.mark.parametrize("lam", TRUE_LAMBDAS)
def test_byar_poisson_interval_coverage(lam: float) -> None:
    """Byar's 95% interval covers the true Poisson mean ~95% of the time."""
    rng = random.Random(SEED + int(lam))
    covered = 0
    for _ in range(DRAWS):
        count = _poisson(rng, lam)
        low, high = poisson_ci(count)  # default z == 95% two-sided
        if low <= lam <= high:
            covered += 1
    coverage = covered / DRAWS
    assert COVERAGE_LOW <= coverage <= COVERAGE_HIGH, (
        f"lambda={lam}: empirical coverage {coverage:.4f} outside "
        f"[{COVERAGE_LOW}, {COVERAGE_HIGH}] — Byar interval may be miscalibrated"
    )
