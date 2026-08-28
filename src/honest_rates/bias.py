"""Reporting-bias characterization.

Point-event datasets are biased by who reports, where activity happens, and
which places are even observed. This module makes that explicit: it compares
each unit's share of events to its share of exposure, surfacing where the
dataset over- and under-represents. A finding that could be an artifact of
*where people report* is labeled as such rather than silently folded into a
ranking.
"""

from __future__ import annotations

from collections.abc import Callable, Container, Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class BiasFinding:
    unit_id: str
    report_share: float
    exposure_share: float

    @property
    def over_representation(self) -> float:
        return self.report_share - self.exposure_share


#: How many findings each direction of the audit names by default.
TOP_N = 3


@dataclass(frozen=True)
class BiasReport:
    findings: tuple[BiasFinding, ...]
    note: str

    def over_represented(
        self, limit: int = TOP_N, eligible: Container[str] | None = None
    ) -> tuple[BiasFinding, ...]:
        """The most over-represented units, chosen *after* the eligibility filter.

        ``eligible`` is the set of unit ids a consumer is allowed to name (in
        nearmiss, the segments that clear the k-anonymity floor). Filtering has to
        happen before the cut, not after it: a unit that cannot be named but ranks
        in the top ``limit`` would otherwise spend a slot and leave the audit
        publishing fewer findings than it says it publishes, with nothing
        backfilled from the next eligible unit. Units withheld for having very few
        events are also the units most likely to show an extreme share ratio, so
        the two conditions coincide rather than being independent.
        """
        return self._take(lambda f: f.over_representation > 0, limit, eligible)

    def under_represented(
        self, limit: int = TOP_N, eligible: Container[str] | None = None
    ) -> tuple[BiasFinding, ...]:
        """The most under-represented units, chosen after the same filter."""
        return tuple(
            reversed(self._take(lambda f: f.over_representation < 0, limit, eligible, tail=True))
        )

    def _take(
        self,
        keep: Callable[[BiasFinding], bool],
        limit: int,
        eligible: Container[str] | None,
        tail: bool = False,
    ) -> tuple[BiasFinding, ...]:
        """``findings`` is sorted most- to least-over-represented; take one end."""
        ranked = [
            f for f in self.findings if keep(f) and (eligible is None or f.unit_id in eligible)
        ]
        return tuple(ranked[-limit:] if tail else ranked[:limit])


_NOTE = (
    "Shares compare where events land against where exposure is. They cannot, on "
    "their own, separate 'more dangerous' from 'more reported': reporter pools skew "
    "by route choice, demographics, app access, and language. Treat over-represented "
    "units as candidates for attention and scrutiny, not as confirmed rankings."
)


def characterize_bias(counts: Mapping[str, int], exposure: Mapping[str, float]) -> BiasReport:
    """Compare event share vs. exposure share for units that have positive exposure.

    ``counts`` and ``exposure`` are both keyed by the same stable unit id;
    ``counts`` may be sparse (a missing id is treated as a count of zero).
    """
    pairs = [(uid, counts.get(uid, 0), exposure[uid]) for uid in exposure if exposure[uid] > 0]
    total_reports = sum(c for _, c, _ in pairs)
    total_exposure = sum(e for _, _, e in pairs)
    findings: list[BiasFinding] = []
    if total_reports > 0 and total_exposure > 0:
        for uid, c, e in pairs:
            findings.append(
                BiasFinding(
                    unit_id=uid,
                    report_share=c / total_reports,
                    exposure_share=e / total_exposure,
                )
            )
    findings.sort(key=lambda f: f.over_representation, reverse=True)
    return BiasReport(findings=tuple(findings), note=_NOTE)
