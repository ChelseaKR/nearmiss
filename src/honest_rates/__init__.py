"""honest_rates — exposure-normalized rates and honest hotspot detection for
any point-event dataset.

This library is the extracted statistics core of `nearmiss
<https://github.com/ChelseaKR/nearmiss>`_: the part of that project that has
nothing to do with streets, cyclists, or road hazards. It answers one question
for *any* dataset of point events with a known exposure denominator — crime
incidents vs. foot traffic, 311 service requests vs. housing units,
code-enforcement complaints vs. inspected properties, wildlife strikes vs.
flight hours — **"is this place actually more dangerous, or just busier?"**

Four honesty rules, enforced in code rather than left to the analyst:

1. **A count is never a rate.** Ranking or mapping raw counts rewards traffic,
   not danger — the busiest unit always looks "hottest" even when nothing
   unusual is happening there. Every rate here is counts *divided by a real
   exposure denominator* (:mod:`honest_rates.rates`).
2. **Small counts get honest uncertainty, not false precision.** A unit with
   one event is not "twice as dangerous" as one with zero — it is *very
   uncertain*. Every rate ships a confidence interval, well-behaved down to a
   count of zero (:func:`honest_rates.rates.poisson_ci`, Byar's approximation).
3. **A cluster must be one, not a coincidence.** Getis-Ord Gi* finds where
   *rates* cluster spatially beyond what chance alone would produce, and a
   Benjamini-Hochberg false-discovery-rate correction keeps "significant" from
   quietly meaning "one of many independent coin flips that came up heads"
   (:mod:`honest_rates.hotspot`).
4. **Ground truth is provable, not assumed.** :mod:`honest_rates.fixtures`
   generates synthetic datasets with a *known* planted hotspot and a *known*
   busy decoy, so any pipeline built on this library — or a competing one —
   can be checked against a known answer instead of trusted on faith.

The public surface takes only plain sequences, dicts, and the minimal
:class:`honest_rates.unit.Unit` structural protocol — never a domain model
like nearmiss's ``Segment``. Anything with a stable string id and a
``(lat, lon)`` is a valid analysis unit.

See ``examples/potholes_demo.py`` in this package for a non-traffic worked
example (311 pothole reports vs. street traffic, deliberately *not* a
near-miss dataset) that reaches the "busy is not the same as dangerous"
conclusion using only this library.
"""

from __future__ import annotations

from .bias import BiasFinding, BiasReport, characterize_bias
from .hotspot import band_neighbors, benjamini_hochberg, getis_ord_star, two_sided_p
from .rates import (
    Z95,
    pearson_dispersion,
    poisson_ci,
    quasi_poisson_ci,
    rate_with_ci,
    wilson_ci,
)
from .unit import SimpleUnit, Unit, UnitRate, analyze

__version__ = "0.1.0"

__all__ = [
    "Z95",
    "BiasFinding",
    "BiasReport",
    "SimpleUnit",
    "Unit",
    "UnitRate",
    "analyze",
    "band_neighbors",
    "benjamini_hochberg",
    "characterize_bias",
    "getis_ord_star",
    "pearson_dispersion",
    "poisson_ci",
    "quasi_poisson_ci",
    "rate_with_ci",
    "two_sided_p",
    "wilson_ci",
]
