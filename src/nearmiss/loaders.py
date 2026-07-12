"""Readers that turn input files into the plain models in :mod:`nearmiss.models`.

Inputs are deliberately boring formats: GeoJSON for streets, JSON for exposure
and reports. A missing or malformed input file is reported as a clean
:class:`NearmissError` (clear message, no raw traceback), not as an unhandled
crash.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

from .errors import NearmissError
from .models import Exposure, ExposureReading, ExposureTier, Report, Segment

_EXPOSURE_TIERS: frozenset[str] = frozenset(("observed", "modeled", "proxy", "unknown"))
_MAX_JSON_NESTING = 256


def _decode_json(path: Path, payload: bytes) -> object:
    try:
        data = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        raise NearmissError(f"invalid JSON in {path}: {exc}") from exc
    _require_unicode_scalars(path, data)
    return data


def _require_unicode_scalars(path: Path, value: object) -> None:
    pending: list[tuple[object, int]] = [(value, 0)]
    while pending:
        current, depth = pending.pop()
        if depth > _MAX_JSON_NESTING:
            raise NearmissError(f"invalid JSON in {path}: nesting exceeds safety limit")
        if isinstance(current, str):
            try:
                current.encode("utf-8")
            except UnicodeEncodeError:
                raise NearmissError(
                    f"invalid JSON in {path}: invalid Unicode scalar value"
                ) from None
        elif isinstance(current, dict):
            pending.extend((child, depth + 1) for pair in current.items() for child in pair)
        elif isinstance(current, list):
            pending.extend((child, depth + 1) for child in current)


def _read_json(path: Path) -> object:
    try:
        return _decode_json(path, path.read_bytes())
    except FileNotFoundError as exc:
        raise NearmissError(f"input file not found: {path}") from exc
    except OSError as exc:
        raise NearmissError(f"could not read {path}: {exc}") from exc


def _finite_number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        parsed = float(value)
    except OverflowError:
        return None
    return parsed if math.isfinite(parsed) else None


def _line_coordinates(path: Path, value: object) -> tuple[tuple[float, float], ...]:
    if not isinstance(value, list):
        raise NearmissError(f"{path}: LineString coordinates must be an array")
    parsed: list[tuple[float, float]] = []
    for position in value:
        if not isinstance(position, list) or len(position) < 2:
            raise NearmissError(f"{path}: LineString positions must contain finite numbers")
        longitude = _finite_number(position[0])
        latitude = _finite_number(position[1])
        if longitude is None or latitude is None:
            raise NearmissError(f"{path}: LineString positions must contain finite numbers")
        # GeoJSON is [lon, lat]; models use (lat, lon).
        parsed.append((latitude, longitude))
    return tuple(parsed)


def _segment_from_feature(path: Path, value: object) -> Segment | None:
    if not isinstance(value, dict) or value.get("type") != "Feature":
        raise NearmissError(f"{path}: malformed GeoJSON feature")
    props = value.get("properties")
    if not isinstance(props, dict):
        raise NearmissError(f"{path}: feature properties must be an object")
    geom = value.get("geometry")
    if not isinstance(geom, dict) or not isinstance(geom.get("type"), str):
        raise NearmissError(f"{path}: feature geometry must be an object with a type")
    if geom["type"] != "LineString":
        return None
    sid = str(props.get("segment_id") or props.get("id") or value.get("id"))
    name = str(props.get("name", sid))
    coords = _line_coordinates(path, geom.get("coordinates"))
    if len(coords) < 2:
        raise NearmissError(
            f"{path}: segment {sid!r} has fewer than two vertices; "
            "a LineString needs at least two positions"
        )
    return Segment(id=sid, name=name, coords=coords)


def _streets_from_data(path: Path, data: object) -> list[Segment]:
    if not isinstance(data, dict):
        raise NearmissError(f"{path}: expected a GeoJSON object")
    if data.get("type") != "FeatureCollection":
        raise NearmissError(f"{path}: expected a GeoJSON FeatureCollection")
    features = data.get("features")
    if not isinstance(features, list):
        raise NearmissError(f"{path}: FeatureCollection features must be an array")
    segments: list[Segment] = []
    for feature in features:
        segment = _segment_from_feature(path, feature)
        if segment is not None:
            segments.append(segment)
    if not segments:
        raise NearmissError(f"no LineString segments found in {path}")
    return segments


def load_streets(path: Path) -> list[Segment]:
    """Load street segments from a GeoJSON FeatureCollection of LineStrings."""
    return _streets_from_data(path, _read_json(path))


def load_streets_bytes(path: Path, payload: bytes) -> list[Segment]:
    """Parse already-read GeoJSON bytes without reopening the network file."""
    if not isinstance(payload, bytes):
        raise TypeError("street network payload must be bytes")
    return _streets_from_data(path, _decode_json(path, payload))


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
