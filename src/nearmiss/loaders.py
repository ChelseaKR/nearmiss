"""Readers that turn input files into the plain models in :mod:`nearmiss.models`.

Inputs are deliberately boring formats: GeoJSON for streets, JSON for exposure
and reports. A missing or malformed input file is reported as a clean
:class:`NearmissError` (clear message, no raw traceback), not as an unhandled
crash.
"""

from __future__ import annotations

import json
from pathlib import Path

from .errors import NearmissError
from .models import Exposure, ExposureReading, ExposureTier, Report, Segment

_EXPOSURE_TIERS: frozenset[str] = frozenset(("observed", "modeled", "proxy", "unknown"))


def _read_json(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise NearmissError(f"input file not found: {path}") from exc
    except OSError as exc:
        raise NearmissError(f"could not read {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise NearmissError(f"invalid JSON in {path}: {exc}") from exc


def load_streets(path: Path) -> list[Segment]:
    """Load street segments from a GeoJSON FeatureCollection of LineStrings."""
    data = _read_json(path)
    if not isinstance(data, dict):
        raise NearmissError(f"{path}: expected a GeoJSON object")
    segments: list[Segment] = []
    for feat in data.get("features", []):
        geom = feat.get("geometry", {})
        if geom.get("type") != "LineString":
            continue
        props = feat.get("properties", {})
        sid = str(props.get("segment_id") or props.get("id") or feat.get("id"))
        name = str(props.get("name", sid))
        # GeoJSON is [lon, lat]; models use (lat, lon).
        coords = tuple((float(c[1]), float(c[0])) for c in geom["coordinates"])
        if len(coords) < 2:
            raise NearmissError(
                f"{path}: segment {sid!r} has fewer than two vertices; "
                "a LineString needs at least two positions"
            )
        segments.append(Segment(id=sid, name=name, coords=coords))
    if not segments:
        raise NearmissError(f"no LineString segments found in {path}")
    return segments


def _tier(path: Path, row: dict[str, object]) -> ExposureTier:
    """Parse an exposure row's trust tier, defaulting to ``"unknown"`` for rows
    written before this field existed (honest default, never fabricated)."""
    raw = row.get("tier", "unknown")
    value = str(raw) if raw is not None else "unknown"
    if value not in _EXPOSURE_TIERS:
        raise NearmissError(
            f"{path}: unknown exposure tier {value!r}; expected one of {sorted(_EXPOSURE_TIERS)}"
        )
    return value  # type: ignore[return-value]


def _sources(path: Path, row: dict[str, object]) -> tuple[ExposureReading, ...]:
    """Parse optional corroborating readings (multi-source exposure; FIX-04)."""
    raw = row.get("sources")
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise NearmissError(f"{path}: exposure row 'sources' must be a list")
    readings = []
    for entry in raw:
        readings.append(
            ExposureReading(
                estimate=float(entry["estimate"]),
                source=str(entry["source"]),
                date=str(entry["date"]),
                tier=_tier(path, entry),
            )
        )
    return tuple(readings)


def load_exposure(path: Path) -> dict[str, Exposure]:
    """Load per-segment exposure denominators keyed by segment id.

    Accepts the optional ``tier`` (observed/modeled/proxy/unknown) and ``sources``
    (additional corroborating readings) fields; both are backward compatible —
    older exposure files with neither field load with ``tier="unknown"`` and no
    corroborating sources, honestly rather than silently promoted to "observed".
    """
    data = _read_json(path)
    rows = data.get("segments", []) if isinstance(data, dict) else data
    if not isinstance(rows, list):
        raise NearmissError(f"{path}: expected exposure rows or a {{'segments': [...]}} object")
    out: dict[str, Exposure] = {}
    try:
        for row in rows:
            sid = str(row["segment_id"])
            out[sid] = Exposure(
                segment_id=sid,
                estimate=float(row["estimate"]),
                source=str(row["source"]),
                date=str(row["date"]),
                tier=_tier(path, row),
                sources=_sources(path, row),
            )
    except (KeyError, TypeError, ValueError) as exc:
        raise NearmissError(f"{path}: malformed exposure row ({exc})") from exc
    return out


def load_reports(path: Path) -> list[dict[str, object]]:
    """Load raw report dicts (NOT yet validated) from a JSON array or {reports:[]}."""
    data = _read_json(path)
    rows = data["reports"] if isinstance(data, dict) else data
    if not isinstance(rows, list):
        raise NearmissError(f"{path}: expected a list of reports or a {{'reports': [...]}} object")
    return [dict(r) for r in rows]


def reports_from_dicts(rows: list[dict[str, object]]) -> list[Report]:
    return [Report.from_dict(r) for r in rows]
