"""Rates with confidence intervals .

A count over an exposure denominator is a Poisson rate. We attach a confidence
interval appropriate to small counts using Byar's approximation to the exact
Poisson interval — a closed form that is well behaved down to a count of zero,
so a sparse unit is shown as uncertain rather than ranked as if it were
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


def empirical_bayes_rates(
    counts: list[int], exposures: list[float]
) -> tuple[list[float], float, float, list[float]]:
    """Marshall's global empirical-Bayes shrinkage of a set of rates.

    Returns ``(shrunk_rates, global_rate, between_unit_variance, weights)``, all
    on the raw ``count / exposure`` scale.

    A sparse unit's raw rate is dominated by Poisson noise: one extra event on a
    low-exposure unit moves it a long way, which is the mechanism behind most
    spurious "worst place" findings. Empirical Bayes borrows strength across
    units, pulling each rate toward the overall rate in proportion to how little
    information it carries::

        m     = sum(y) / sum(E)                                # overall rate
        A     = sum(E_i * (r_i - m)^2) / sum(E)  -  m / mean(E) # between-unit variance
        w_i   = A / (A + m / E_i)                               # weight on the raw rate
        theta = m + w_i * (r_i - m)

    ``A`` is a method-of-moments estimate of the variance *between* units, net of
    the Poisson variance within them. It can come out negative, which means the
    spread across units is no larger than Poisson noise alone would produce; by
    Marshall's convention it is then clamped to 0, every weight is 0, and every
    unit shrinks all the way to the overall rate. A caller must treat that as
    "these counts do not distinguish these units", not as a ranking.

    The scale matters: the weights are **not** invariant to multiplying rates by
    a constant, so this works on the raw ``y / E`` scale and any per-1000-style
    factor is applied to the result afterwards.

    Reference: Marshall, *Mapping disease and mortality rates using empirical
    Bayes estimators*, Applied Statistics 40(2), 1991; Clayton & Kaldor,
    *Empirical Bayes estimates of age-standardized relative risks*, Biometrics
    43(3), 1987.
    """
    if len(counts) != len(exposures):
        raise ValueError("counts and exposures must have the same length")
    n = len(counts)
    if n == 0:
        return [], 0.0, 0.0, []
    if any(e <= 0 for e in exposures):
        raise ValueError("every exposure must be positive to shrink a rate")
    total_exposure = sum(exposures)
    global_rate = sum(counts) / total_exposure
    mean_exposure = total_exposure / n
    raw = [c / e for c, e in zip(counts, exposures, strict=True)]
    weighted_spread = (
        sum(e * (r - global_rate) ** 2 for r, e in zip(raw, exposures, strict=True))
        / total_exposure
    )
    variance = weighted_spread - global_rate / mean_exposure
    if variance < 0.0:
        variance = 0.0
    weights = [
        variance / (variance + global_rate / e) if (variance + global_rate / e) > 0 else 0.0
        for e in exposures
    ]
    shrunk = [global_rate + w * (r - global_rate) for r, w in zip(raw, weights, strict=True)]
    return shrunk, global_rate, variance, weights


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
