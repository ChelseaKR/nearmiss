"""Rates with confidence intervals (hard rule #2).

The actual implementation lives in the standalone `honest_rates
<https://github.com/ChelseaKR/nearmiss/tree/main/src/honest_rates>`_ library
(roadmap item EXP-08): a count over an exposure denominator is a Poisson rate,
small counts get an honest confidence interval via Byar's approximation, and
overdispersed counts (RR-02) widen it by sqrt(phi) via the quasi-Poisson
functions. nearmiss is that library's first consumer — this module re-exports
its public API under nearmiss's historical import path so existing callers and
tests are unaffected.

References: Breslow & Day (1987); Wilson (1927); McCullagh & Nelder (1989).
"""

from __future__ import annotations

from honest_rates.rates import (
    Z95,
    pearson_dispersion,
    poisson_ci,
    quasi_poisson_ci,
    rate_with_ci,
    wilson_ci,
)

__all__ = [
    "Z95",
    "pearson_dispersion",
    "poisson_ci",
    "quasi_poisson_ci",
    "rate_with_ci",
    "wilson_ci",
]
