"""The minimal analysis-unit shape this library asks of a caller.

Nothing here requires inheriting from a base class. Anything with a stable
string ``id`` and a ``(lat, lon)`` centroid — a street segment, a census tract,
a store location, a patrol beat, a 311 service area — satisfies :class:`Unit`
structurally and can be analyzed with :func:`analyze`.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from .hotspot import band_neighbors, benjamini_hochberg, getis_ord_star, two_sided_p
from .rates import Z95, rate_with_ci


@runtime_checkable
class Unit(Protocol):
    """A point-event analysis unit: a stable id plus a (lat, lon) centroid."""

    @property
    def id(self) -> str: ...

    @property
    def lat(self) -> float: ...

    @property
    def lon(self) -> float: ...


@dataclass(frozen=True)
class SimpleUnit:
    """A ready-made :class:`Unit` implementation for callers with no model of
    their own — just an id and a centroid."""

    id: str
    lat: float
    lon: float


@dataclass(frozen=True)
class UnitRate:
    """One unit's exposure-normalized rate, confidence interval, and hotspot
    status — the per-unit result row of :func:`analyze`."""

    unit_id: str
    count: int
    exposure: float | None
    rate: float | None
    rate_ci_low: float | None
    rate_ci_high: float | None
    getis_ord_z: float | None
    significant: bool


def analyze(
    units: Sequence[Unit],
    counts: Mapping[str, int],
    exposure: Mapping[str, float],
    *,
    band_m: float,
    per: float = 1000.0,
    alpha: float = 0.05,
    z: float = Z95,
) -> list[UnitRate]:
    """Exposure-normalize, confidence-bound, and hotspot-test a set of units.

    For each unit with positive exposure: computes the rate and its Byar
    confidence interval (:func:`honest_rates.rates.rate_with_ci`), then runs
    Getis-Ord Gi* on the resulting rates (:func:`honest_rates.hotspot.getis_ord_star`)
    with a Benjamini-Hochberg false-discovery-rate correction
    (:func:`honest_rates.hotspot.benjamini_hochberg`) so a "significant" cluster
    survives multiple-comparison scrutiny. Units with no positive exposure are
    still returned (rate fields ``None``) but are excluded from the hotspot
    computation — a rate without a real denominator is never produced, per
    :func:`honest_rates.rates.rate_with_ci`.

    This is a convenience orchestrator; nothing it does cannot be done by
    calling ``rates`` and ``hotspot`` directly, which a caller with more
    specific needs (custom weighting, a different multiple-comparison
    correction, streaming units) is free to do instead.
    """
    rate_values: dict[str, float] = {}
    centroids: dict[str, tuple[float, float]] = {}
    rows: dict[str, UnitRate] = {}

    for u in units:
        count = counts.get(u.id, 0)
        exp = exposure.get(u.id)
        if exp is not None and exp > 0:
            rate, lo, hi = rate_with_ci(count, exp, per=per, z=z)
            rate_values[u.id] = rate
            centroids[u.id] = (u.lat, u.lon)
            rows[u.id] = UnitRate(
                unit_id=u.id,
                count=count,
                exposure=exp,
                rate=rate,
                rate_ci_low=lo,
                rate_ci_high=hi,
                getis_ord_z=None,
                significant=False,
            )
        else:
            rows[u.id] = UnitRate(
                unit_id=u.id,
                count=count,
                exposure=exp,
                rate=None,
                rate_ci_low=None,
                rate_ci_high=None,
                getis_ord_z=None,
                significant=False,
            )

    if rate_values:
        zscores = getis_ord_star(rate_values, band_neighbors(centroids, band_m))
        pvalues = {uid: two_sided_p(zi) for uid, zi in zscores.items()}
        rejected = benjamini_hochberg(pvalues, alpha)
        for uid, zi in zscores.items():
            row = rows[uid]
            rows[uid] = UnitRate(
                unit_id=row.unit_id,
                count=row.count,
                exposure=row.exposure,
                rate=row.rate,
                rate_ci_low=row.rate_ci_low,
                rate_ci_high=row.rate_ci_high,
                getis_ord_z=zi,
                significant=uid in rejected and zi > 0.0,
            )

    return [rows[u.id] for u in units]
