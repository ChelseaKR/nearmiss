# SPDX-License-Identifier: Apache-2.0
"""Adapters for contributor reports and separately typed official outcomes.

Report adapters turn a real-world report source into nearmiss intake reports
via a declarative TOML crosswalk. See ``base.py`` for the ``SourceAdapter``
protocol and ``Crosswalk``/``Provenance`` contracts.

Registered adapters (``registry``) map a short source id to its adapter
instance, e.g. ``registry["bikemaps"]`` / ``registry["simra"]``.
Official outcomes intentionally use the sibling ``OfficialOutcomeAdapter``
contract and never appear in that registry.
"""

from __future__ import annotations

from .base import Crosswalk, Provenance, SourceAdapter, load_crosswalk
from .bikemaps import BikeMapsAdapter
from .fars import FarsAdapter, FarsRawBatch
from .outcomes import OfficialOutcomeAdapter, OutcomeProvenance
from .simra import SimRaAdapter

registry: dict[str, SourceAdapter] = {
    "bikemaps": BikeMapsAdapter(),
    "simra": SimRaAdapter(),
}

__all__ = [
    "BikeMapsAdapter",
    "Crosswalk",
    "FarsAdapter",
    "FarsRawBatch",
    "OfficialOutcomeAdapter",
    "OutcomeProvenance",
    "Provenance",
    "SimRaAdapter",
    "SourceAdapter",
    "load_crosswalk",
    "registry",
]
