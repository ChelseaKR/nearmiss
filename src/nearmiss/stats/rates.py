"""Rates with confidence intervals (hard rule #2).

A count over an exposure denominator is a Poisson rate. We attach a confidence
interval appropriate to small counts using Byar's approximation to the exact
Poisson interval — a closed form that is well behaved down to a count of zero,
so a sparse segment is shown as uncertain rather than ranked as if it were
certain. The Wilson score interval is provided for proportions.

References: Breslow & Day (1987), Byar's approximation; Wilson (1927).
"""

from __future__ import annotations

import math

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


def rate_with_ci(
    count: int, exposure: float, per: float = 1000.0, z: float = Z95
) -> tuple[float, float, float]:
    """Return (rate, ci_low, ci_high) as counts per ``per`` exposure units.

    Raises ``ValueError`` for a non-positive exposure — a rate without a real
    denominator is never produced.
    """
    if exposure <= 0:
        raise ValueError("exposure must be positive to compute a rate")
    scale = per / exposure
    lam_low, lam_high = poisson_ci(count, z)
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
