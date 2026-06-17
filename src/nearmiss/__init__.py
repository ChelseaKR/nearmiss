"""nearmiss — an open dataset and statistically honest analysis of road hazards.

The package is organized as a sequence of pure, recorded transforms:

    intake -> pipeline (dedupe, geocode, snap, classify, quality)
           -> exposure -> stats (rates, bias, kde, getis_ord)
           -> publish -> brief -> server

Each stage consumes and emits plain, inspectable data structures (see
:mod:`nearmiss.models`), so any stage can be tested, piped, or replaced
independently. Nothing in the public path emits a precise raw report.
"""

from __future__ import annotations

__all__ = ["__version__"]

__version__ = "0.1.0"
