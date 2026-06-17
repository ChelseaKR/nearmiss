"""Classification: normalize the hazard type to the published vocabulary.

Reports already carry a hazard type from the closed schema vocabulary; this
stage is where free-text imports would be mapped onto that vocabulary. An
unrecognized value is mapped to ``other`` rather than dropped, so nothing is
lost silently.
"""

from __future__ import annotations

from ..models import HazardType, Report

_KNOWN: frozenset[str] = frozenset(
    ("close_pass", "dooring", "surface_hazard", "sightline", "signal", "debris", "other")
)


def classify(report: Report) -> str:
    ht: HazardType | str = report.hazard_type
    return ht if ht in _KNOWN else "other"
