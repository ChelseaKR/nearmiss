# SPDX-License-Identifier: Apache-2.0
"""SimRa source adapter — the second ``SourceAdapter`` implementation (EXP-04),
landing the previously-orphaned SimRa fetch tool onto the adapter framework.

SimRa (https://github.com/simra-project/dataset, TU Berlin) is a crowdsourced,
openly-published dataset of **bicycle near-crashes** with GPS — the closest
real-world analogue to nearmiss's own input, and unusual in that the same
source also carries the *ride* GPS traces, a natural exposure denominator
(not wired up here; see ``docs/REAL-DATA.md``'s exposure section).

Each SimRa ride file has an incidents section (one annotated near-miss per row:
``lat,lon,ts,...,incident,...,scary,...``) then a divider then the ride GPS
trace. This adapter reads a directory of such files and emits reports
conforming to ``schema/report.schema.json``, using the declarative crosswalk in
``crosswalks/simra.toml`` for the incident-code -> hazard_type mapping (no
hardcoded dict here).

``tools/fetch_simra.py`` is a thin CLI over this module.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .base import Crosswalk, Provenance, load_crosswalk

DIVIDER = "========================="
_NS = uuid.uuid5(uuid.NAMESPACE_URL, "https://simra-project.github.io/")

# Convenience bounding boxes (W, S, E, N) for SimRa regions.
CITY_BBOX = {
    "berlin": (13.0, 52.30, 13.77, 52.70),
    "london": (-0.55, 51.28, 0.30, 51.70),
    "munich": (11.36, 48.06, 11.72, 48.25),
}


def hazard_from_code(crosswalk: Crosswalk, code: str) -> str:
    return crosswalk.hazard_from(code.strip())


def _iso_from_ts(ts: str) -> str | None:
    """SimRa timestamps are epoch milliseconds (UTC). Return RFC 3339 'Z' time."""
    try:
        ms = int(float(ts))
    except (TypeError, ValueError):
        return None
    if ms <= 0:
        return None
    return datetime.fromtimestamp(ms / 1000.0, tz=UTC).isoformat().replace("+00:00", "Z")


def parse_incidents(text: str) -> list[dict[str, str]]:
    """Return the annotated-incident rows (as dicts) from one SimRa ride file."""
    if DIVIDER not in text:
        return []
    head = text.split(DIVIDER)[0].splitlines()
    if len(head) < 2:
        return []
    cols = head[1].split(",")
    out: list[dict[str, str]] = []
    for line in head[2:]:
        if not line.strip():
            continue
        out.append(dict(zip(cols, line.split(","), strict=False)))
    return out


def in_bbox(lat: float, lon: float, bbox: tuple[float, float, float, float] | None) -> bool:
    if bbox is None:
        return True
    w, s, e, n = bbox
    return w <= lon <= e and s <= lat <= n


def map_incident(
    row: dict[str, str],
    source: str,
    bbox: tuple[float, float, float, float] | None,
    crosswalk: Crosswalk | None = None,
) -> dict[str, Any] | None:
    crosswalk = crosswalk or load_crosswalk("simra")
    lat_s, lon_s, inc = row.get("lat", ""), row.get("lon", ""), row.get("incident", "")
    # An un-annotated row has empty coordinates and incident == -5.
    if not lat_s.strip() or not lon_s.strip() or inc.strip() in ("", "-5"):
        return None
    try:
        lat, lon = float(lat_s), float(lon_s)
    except ValueError:
        return None
    if not (-90 <= lat <= 90 and -180 <= lon <= 180) or not in_bbox(lat, lon, bbox):
        return None
    occurred_at = _iso_from_ts(row.get("ts", ""))
    if occurred_at is None:
        return None
    key = f"simra:{source}:{lat:.6f},{lon:.6f}:{row.get('ts', '')}"
    return {
        "schema_version": "1.0.0",
        "id": str(uuid.uuid5(_NS, key)),
        "occurred_at": occurred_at,
        "location": {"lat": lat, "lon": lon},
        "mode": "cyclist",  # SimRa reporters are cyclists
        "hazard_type": hazard_from_code(crosswalk, inc),
        # SimRa records near-crashes only, so this is unconditionally near_miss.
        "severity": crosswalk.severity_from(None),
    }


def collect(
    root: Path, bbox: tuple[float, float, float, float] | None, crosswalk: Crosswalk | None = None
) -> list[dict[str, Any]]:
    crosswalk = crosswalk or load_crosswalk("simra")
    reports: list[dict[str, Any]] = []
    files = [p for p in root.rglob("*") if p.is_file() and p.name.startswith(("VM2_", "VM"))]
    for fp in files:
        try:
            text = fp.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for row in parse_incidents(text):
            rep = map_incident(row, fp.name, bbox, crosswalk)
            if rep is not None:
                reports.append(rep)
    return reports


class SimRaAdapter:
    """``SourceAdapter`` implementation for the SimRa (TU Berlin) dataset."""

    source_id = "simra"

    def __init__(self) -> None:
        self.crosswalk = load_crosswalk("simra")

    def fetch(self, **kwargs: Any) -> Any:
        """SimRa ships as a directory of ride files (no live API); "fetching"
        is just resolving that path — the real read happens in :meth:`parse`.

        Keywords: ``dir`` (required, a SimRa region folder or a parent of them).
        """
        path = Path(kwargs["dir"])
        if not path.exists():
            raise FileNotFoundError(f"SimRa directory not found: {path}")
        return path

    def parse(self, raw: Any, **kwargs: Any) -> tuple[list[dict[str, Any]], Provenance]:
        """Keywords: ``bbox`` (``(W, S, E, N)``, default unfiltered)."""
        bbox: tuple[float, float, float, float] | None = kwargs.get("bbox")
        reports = collect(raw, bbox, self.crosswalk)
        counts_by_kind = {"near_miss": len(reports)}
        return reports, self.crosswalk.provenance(counts_by_kind)
