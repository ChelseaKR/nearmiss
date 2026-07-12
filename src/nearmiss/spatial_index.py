"""Uniform spatial grid index for acceleration of distance-based queries.

Shared by snap, dedupe, KDE, and Gi* neighbor search. The implementation lives
in the standalone `honest_rates
<https://github.com/ChelseaKR/nearmiss/tree/main/src/honest_rates>`_ library
(roadmap item EXP-08) — it has no nearmiss-specific logic, so it was
extracted rather than duplicated. This module re-exports it under nearmiss's
historical import path so existing callers and tests are unaffected.
"""

from __future__ import annotations

from honest_rates.spatial_index import SpatialIndex

__all__ = ["SpatialIndex"]
