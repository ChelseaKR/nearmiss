# SPDX-License-Identifier: Apache-2.0
"""Sibling adapter contract for official road-safety outcomes.

Official outcomes are not contributor reports: they have no reporter mode,
hazard classification, or self-assessed severity. Keeping this protocol apart
from :class:`nearmiss.adapters.base.SourceAdapter` prevents official records
from acquiring those semantics merely to fit the near-miss intake schema.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Protocol, runtime_checkable

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class OutcomeProvenance:
    """Traceability and known scope for one parsed official-outcome batch."""

    source_id: str
    source_name: str
    source_url: str
    license: str
    dataset_years: tuple[int, ...]
    release_status: str
    scope: str
    limitations: tuple[str, ...]
    records_read: int
    records_accepted: int
    rejection_reasons: Mapping[str, int]
    input_sha256: str | None = None

    def __post_init__(self) -> None:
        """Freeze and validate accounting carried across trust boundaries."""
        if self.records_read < 0 or self.records_accepted < 0:
            raise ValueError("outcome record counts cannot be negative")
        if self.records_accepted > self.records_read:
            raise ValueError("accepted outcome count cannot exceed records read")
        reasons = dict(sorted(self.rejection_reasons.items()))
        if any(not reason or count <= 0 for reason, count in reasons.items()):
            raise ValueError("outcome rejection reasons require positive counts")
        if self.records_accepted + sum(reasons.values()) != self.records_read:
            raise ValueError("outcome provenance accounting must cover every record read")
        if tuple(sorted(set(self.dataset_years))) != self.dataset_years:
            raise ValueError("outcome dataset years must be sorted and unique")
        if self.input_sha256 is not None and _SHA256_RE.fullmatch(self.input_sha256) is None:
            raise ValueError("outcome input_sha256 must be a lowercase SHA-256 digest")
        object.__setattr__(self, "rejection_reasons", MappingProxyType(reasons))

    def as_dict(self) -> dict[str, object]:
        return {
            "source_id": self.source_id,
            "source_name": self.source_name,
            "source_url": self.source_url,
            "license": self.license,
            "dataset_years": list(self.dataset_years),
            "release_status": self.release_status,
            "scope": self.scope,
            "limitations": list(self.limitations),
            "records_read": self.records_read,
            "records_accepted": self.records_accepted,
            "rejection_reasons": dict(sorted(self.rejection_reasons.items())),
            "input_sha256": self.input_sha256,
        }


@runtime_checkable
class OfficialOutcomeAdapter(Protocol):
    """Offline-testable fetch/parse boundary for an official outcome source."""

    source_id: str

    def fetch(self, **kwargs: Any) -> Any:
        """Acquire a bounded, adapter-specific raw batch without mapping outcomes."""
        ...

    def parse(self, raw: Any, **kwargs: Any) -> tuple[list[dict[str, Any]], OutcomeProvenance]:
        """Return canonical official outcomes and batch provenance."""
        ...
