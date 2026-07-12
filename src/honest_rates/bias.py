"""Reporting-bias characterization.

Point-event datasets are biased by who reports, where activity happens, and
which places are even observed. This module makes that explicit: it compares
each unit's share of events to its share of exposure, surfacing where the
dataset over- and under-represents. A finding that could be an artifact of
*where people report* is labeled as such rather than silently folded into a
ranking.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class BiasFinding:
    unit_id: str
    report_share: float
    exposure_share: float

    @property
    def over_representation(self) -> float:
        return self.report_share - self.exposure_share


@dataclass(frozen=True)
class BiasReport:
    findings: tuple[BiasFinding, ...]
    note: str

    @property
    def over_represented(self) -> tuple[BiasFinding, ...]:
        return tuple(f for f in self.findings if f.over_representation > 0)[:3]

    @property
    def under_represented(self) -> tuple[BiasFinding, ...]:
        return tuple(reversed([f for f in self.findings if f.over_representation < 0]))[:3]


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
