"""Planted-truth synthetic fixtures for validating any hotspot pipeline.

The core honesty test for a hotspot pipeline is not "does it run" but "does it
recover a truth we already know." :func:`planted_cluster_fixture` generates a
small, deterministic, synthetic point-event dataset with a **known ground
truth**:

* a **planted hotspot** — a compact cluster of low-exposure units with
  concentrated events, so a correct analysis ranks it first by rate and flags
  it as a spatially significant Getis-Ord cluster;
* a **busy decoy** — one lone, distant, high-exposure unit with the *most raw
  events* in the whole dataset, but a low rate once normalized, planted
  specifically to catch a "busier looks more dangerous" bug;
* ordinary **context units** with no strong signal either way.

Any hotspot pipeline — this library's own :func:`honest_rates.unit.analyze`,
or an independent implementation being checked against it — can run against
this fixture and assert three things: the hotspot cluster ranks first by rate,
the busy decoy does NOT rank near the top, and the hotspot cluster (not the
decoy) is the one flagged significant. This is the same shape of harness that
backs nearmiss's own known-answer tests (``tests/test_hotspot.py``,
``tests/test_fdr.py``), generalized here to plain units so it can validate
*any* point-event pipeline, not just street-segment ones.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .unit import SimpleUnit

# A simple square lattice in local metres, converted to (lat, lon) around an
# arbitrary reference point. The absolute location is not meaningful; only the
# relative geometry (which units are close together) matters.
_LAT0, _LON0 = 38.5430, -121.7460
_M_PER_DEG_LAT = 110_540.0
_M_PER_DEG_LON = 84_000.0  # approx at this reference latitude


def _latlon(x_m: float, y_m: float) -> tuple[float, float]:
    return _LAT0 + y_m / _M_PER_DEG_LAT, _LON0 + x_m / _M_PER_DEG_LON


@dataclass(frozen=True)
class PlantedFixture:
    """A synthetic point-event dataset with a known hotspot and a known decoy."""

    units: tuple[SimpleUnit, ...]
    counts: dict[str, int]
    exposure: dict[str, float]
    hotspot_ids: frozenset[str]
    """The planted cluster: should rank first by rate and be flagged significant."""
    decoy_id: str
    """The busy decoy: has the most raw events but must NOT rank near the top."""
    band_m: float
    """A Gi* distance band appropriate to this fixture's spacing."""


def planted_cluster_fixture(*, spacing_m: float = 250.0, n_context: int = 8) -> PlantedFixture:
    """Build a deterministic planted-hotspot / busy-decoy fixture.

    Layout (all distances relative, in a local metric grid of ``spacing_m``):

    * ``hot-0``, ``hot-1``, ``hot-2`` sit in a tight triangle at the origin —
      low exposure, high counts, close enough together to form a Gi* cluster.
    * ``decoy`` sits far away (``6 * spacing_m``, well outside any reasonable
      ``band_m``) with high exposure AND the highest raw count of any unit —
      but its rate is low once normalized.
    * ``context-N`` units ring the hotspot at moderate distance with moderate,
      unremarkable exposure and counts, so the fixture is not a trivial
      two-unit dataset.
    """
    units: list[SimpleUnit] = []
    counts: dict[str, int] = {}
    exposure: dict[str, float] = {}

    # Planted hotspot: a tight triangle, low exposure, concentrated events.
    hotspot_offsets = ((0.0, 0.0), (spacing_m * 0.6, 0.0), (0.0, spacing_m * 0.6))
    hotspot_ids: list[str] = []
    for i, (dx, dy) in enumerate(hotspot_offsets):
        uid = f"hot-{i}"
        lat, lon = _latlon(dx, dy)
        units.append(SimpleUnit(id=uid, lat=lat, lon=lon))
        counts[uid] = 9 + i  # 9, 10, 11 — concentrated
        exposure[uid] = 50.0  # low exposure -> high rate
        hotspot_ids.append(uid)

    # Busy decoy: far away, most raw events, but heavily exposed -> low rate.
    decoy_lat, decoy_lon = _latlon(spacing_m * 6.0, spacing_m * 6.0)
    units.append(SimpleUnit(id="decoy", lat=decoy_lat, lon=decoy_lon))
    counts["decoy"] = 40  # the most raw events in the whole dataset
    exposure["decoy"] = 8_000.0  # but a huge denominator -> a low rate

    # Ordinary context units: moderate, unremarkable signal, ringing the hotspot
    # far enough out that they fall outside a tight Gi* band around it.
    for i in range(n_context):
        angle_step = i * (360.0 / max(n_context, 1))
        dx = spacing_m * 3.0 * math.cos(math.radians(angle_step))
        dy = spacing_m * 3.0 * math.sin(math.radians(angle_step))
        uid = f"context-{i}"
        lat, lon = _latlon(dx, dy)
        units.append(SimpleUnit(id=uid, lat=lat, lon=lon))
        counts[uid] = 2
        exposure[uid] = 500.0

    return PlantedFixture(
        units=tuple(units),
        counts=counts,
        exposure=exposure,
        hotspot_ids=frozenset(hotspot_ids),
        decoy_id="decoy",
        band_m=spacing_m,
    )
