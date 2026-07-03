"""Rates with confidence intervals (hard rule #2).

A count over an exposure denominator is a Poisson rate. We attach a confidence
interval appropriate to small counts using Byar's approximation to the exact
Poisson interval — a closed form that is well behaved down to a count of zero,
so a sparse segment is shown as uncertain rather than ranked as if it were
certain. The Wilson score interval is provided for proportions.

**Overdispersion (RR-02).** Real report counts cluster — one viral post, one
active local group, one bad week drives a burst of correlated reports — so the
counts are usually *more* variable than a clean Poisson would be, and a pure
Poisson interval is then too narrow (a false-confidence claim, the exact failure
mode this project exists to avoid). :func:`pearson_dispersion` estimates the
quasi-Poisson dispersion ``phi`` for the rate/offset model, and
:func:`quasi_poisson_ci` widens the Poisson interval by ``sqrt(phi)`` when the
data are overdispersed. Widening is the conservative direction — it only ever
makes a claim weaker, never stronger.

References: Breslow & Day (1987), Byar's approximation; Wilson (1927);
McCullagh & Nelder (1989), *Generalized Linear Models* (quasi-Poisson dispersion).
"""

from __future__ import annotations

import math
from collections.abc import Sequence

Z95 = 1.959963984540054  # standard normal quantile for a 95% two-sided interval


def poisson_ci(count: int, z: float = Z95) -> tuple[float, float]:
    """Confidence interval for a Poisson mean given an observed ``count``.

    Byar's approximation. For ``count == 0`` the lower bound is 0 and the upper
    bound uses the (count + 1) form.
    """
    if count < 0:
        raise ValueError("count must be non-negative")
    if count == 0:
        low = 0.0
    else:
        low = count * (1.0 - 1.0 / (9.0 * count) - z / (3.0 * math.sqrt(count))) ** 3
    c1 = count + 1
    high = c1 * (1.0 - 1.0 / (9.0 * c1) + z / (3.0 * math.sqrt(c1))) ** 3
    return max(0.0, low), high


def pearson_dispersion(counts: Sequence[int], exposures: Sequence[float]) -> float:
    """Quasi-Poisson Pearson dispersion ``phi`` for a count/offset (rate) model.

    Fits a single pooled rate ``theta_hat = sum(counts) / sum(exposures)`` and
    returns the mean Pearson chi-square residual against that fitted rate::

        phi = (1 / (n - 1)) * sum_s (y_s - theta_hat * E_s)**2 / (theta_hat * E_s)

    Under a clean Poisson process ``phi`` is ~1; ``phi`` materially above 1 is
    overdispersion (counts more variable than Poisson), the gap the methodology
    flags. The estimate is *conservative*: because it is taken against one pooled
    rate, genuine between-segment rate heterogeneity (the real signal the
    Getis-Ord step is built to find) inflates ``phi`` too, so it is an upper
    bound on nuisance overdispersion — and widening intervals by ``sqrt(phi)``
    therefore errs only toward wider, more cautious intervals, never narrower.

    Only observations with a positive exposure offset are used. Returns ``1.0``
    (the Poisson, no-adjustment value) when there are fewer than two such
    observations or no events at all — too little data to claim overdispersion.
    """
    pairs = [(c, e) for c, e in zip(counts, exposures, strict=True) if e > 0]
    n = len(pairs)
    if n < 2:
        return 1.0
    total_y = sum(c for c, _ in pairs)
    total_e = sum(e for _, e in pairs)
    if total_y <= 0 or total_e <= 0:
        return 1.0
    theta = total_y / total_e
    chi2 = sum((c - theta * e) ** 2 / (theta * e) for c, e in pairs)
    return chi2 / (n - 1)


def quasi_poisson_ci(count: int, dispersion: float = 1.0, z: float = Z95) -> tuple[float, float]:
    """Byar Poisson interval widened for overdispersion by ``sqrt(dispersion)``.

    The quasi-Poisson variance is ``Var(y) = phi * mu``, so the standard error —
    and hence the interval half-width — scales by ``sqrt(phi)``. We scale the
    Byar interval's half-widths about the observed ``count`` and clamp the lower
    bound at 0. For ``dispersion <= 1`` this returns the unmodified Poisson
    interval, so the rate path is **never narrowed** below Poisson.
    """
    low, high = poisson_ci(count, z)
    scale = math.sqrt(dispersion) if dispersion > 1.0 else 1.0
    if scale == 1.0:
        return low, high
    widened_low = count - (count - low) * scale
    widened_high = count + (high - count) * scale
    return max(0.0, widened_low), widened_high


def rate_with_ci(
    count: int, exposure: float, per: float = 1000.0, z: float = Z95, dispersion: float = 1.0
) -> tuple[float, float, float]:
    """Return (rate, ci_low, ci_high) as counts per ``per`` exposure units.

    The interval is the quasi-Poisson interval (:func:`quasi_poisson_ci`), which
    equals the pure Byar Poisson interval when ``dispersion <= 1`` (the default),
    and widens by ``sqrt(dispersion)`` when the counts are overdispersed (RR-02).

    Raises ``ValueError`` for a non-positive exposure — a rate without a real
    denominator is never produced.
    """
    if exposure <= 0:
        raise ValueError("exposure must be positive to compute a rate")
    scale = per / exposure
    lam_low, lam_high = quasi_poisson_ci(count, dispersion, z)
    return count * scale, lam_low * scale, lam_high * scale


def wilson_ci(successes: int, trials: int, z: float = Z95) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion."""
    if trials <= 0:
        return 0.0, 0.0
    if successes < 0 or successes > trials:
        raise ValueError("successes must be in [0, trials]")
    p = successes / trials
    denom = 1.0 + z * z / trials
    centre = (p + z * z / (2.0 * trials)) / denom
    half = (z * math.sqrt(p * (1.0 - p) / trials + z * z / (4.0 * trials * trials))) / denom
    return max(0.0, centre - half), min(1.0, centre + half)
