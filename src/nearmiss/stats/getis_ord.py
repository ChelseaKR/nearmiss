"""Getis-Ord Gi* local hotspot statistic (hard rule #3's hotspot half).

The actual implementation lives in the standalone `honest_rates
<https://github.com/ChelseaKR/nearmiss/tree/main/src/honest_rates>`_ library
(roadmap item EXP-08): Gi* on the exposure-normalized rate (never a raw
count), over a caller-supplied neighbor map, with a Benjamini-Hochberg
false-discovery-rate correction so "significant" survives
multiple-comparison scrutiny. nearmiss is that library's first consumer —
this module re-exports its public API under nearmiss's historical import
path so existing callers and tests are unaffected.

nearmiss always feeds Gi* **street-network** neighborhoods
(``nearmiss.network.SegmentGraph.neighbors_within``, FIX-02) — the library's
straight-line ``band_neighbors`` fallback is for standalone consumers
without a network graph and is not used in this pipeline.

Reference: Getis & Ord (1992); Ord & Getis (1995); Benjamini & Hochberg (1995).
"""

from __future__ import annotations

from honest_rates.hotspot import benjamini_hochberg, getis_ord_star, two_sided_p

__all__ = ["benjamini_hochberg", "getis_ord_star", "two_sided_p"]
