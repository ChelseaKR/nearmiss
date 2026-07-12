"""Reporting-bias characterization (hard rule #3).

Reports are biased by who reports, where they ride, and which streets are even
traveled. This module makes that explicit: it compares each segment's share of
reports to its share of exposure, surfacing where the dataset over- and
under-represents. A finding that could be an artifact of where people report is
labeled, and the brief says so in plain language rather than burying it.

The comparison itself (event share vs. exposure share, for units with positive
exposure) is domain-agnostic and now lives in the standalone `honest_rates
<https://github.com/ChelseaKR/nearmiss/tree/main/src/honest_rates>`_ library
(roadmap item EXP-08) as :func:`honest_rates.bias.characterize_bias`. This
module is the nearmiss-specific adapter: it converts nearmiss's ``Exposure``
model (which carries a source and date, not just a number) to the plain
``dict[str, float]`` that library expects, and keeps the ``segment_id``-named
result shape nearmiss's brief renderer already depends on.
"""

from __future__ import annotations

from dataclasses import dataclass

from honest_rates.bias import characterize_bias as _characterize_bias

from ..models import Exposure


@dataclass(frozen=True)
class BiasFinding:
    segment_id: str
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
    "Shares compare where reports land against where exposure is. They cannot, on "
    "their own, separate 'more dangerous' from 'more reported': reporter pools skew "
    "by route choice, demographics, app access, and language. Treat over-represented "
    "segments as candidates for attention and scrutiny, not as confirmed rankings."
)


def characterize_bias(seg_counts: dict[str, int], exposure_map: dict[str, Exposure]) -> BiasReport:
    """Compare report share vs exposure share for segments that have exposure."""
    generic = _characterize_bias(
        seg_counts, {sid: exp.estimate for sid, exp in exposure_map.items()}
    )
    findings = tuple(
        BiasFinding(
            segment_id=f.unit_id,
            report_share=f.report_share,
            exposure_share=f.exposure_share,
        )
        for f in generic.findings
    )
    return BiasReport(findings=findings, note=_NOTE)


def to_metadata(report: BiasReport, publishable: set[str]) -> dict[str, object]:
    """A privacy-safe, JSON-serializable view of the reporting-bias audit.

    Mirrors ``stats/temporal.to_metadata``: it surfaces the caveat note plus the
    over- and under-represented segments so the web UI (not only the brief) can
    show *who* the dataset over- and under-reports. Only segments that clear the
    k-anonymity floor are included — the same filter :mod:`nearmiss.brief` applies
    — and only a segment id and two rounded shares are emitted. No coordinate,
    raw count, or reporter field ever appears here (hard rule #4 / privacy).
    """

    def entry(f: BiasFinding) -> dict[str, object]:
        return {
            "segment_id": f.segment_id,
            "report_share": round(f.report_share, 4),
            "exposure_share": round(f.exposure_share, 4),
        }

    over = [entry(f) for f in report.over_represented if f.segment_id in publishable]
    under = [entry(f) for f in report.under_represented if f.segment_id in publishable]
    # The caveat is emitted as "caveat" (not "note"): "note" is a forbidden
    # per-report field name, so it must never appear as a key in any artifact.
    return {
        "caveat": report.note,
        "over_represented": over,
        "under_represented": under,
    }
