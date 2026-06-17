"""Readers that turn input files into the plain models in :mod:`nearmiss.models`.

Inputs are deliberately boring formats: GeoJSON for streets, JSON for exposure
and reports. Everything a stage needs is loadable and inspectable on its own.
"""

from __future__ import annotations

import json
from pathlib import Path

from .errors import NearmissError
from .models import Exposure, Report, Segment


def load_streets(path: Path) -> list[Segment]:
    """Load street segments from a GeoJSON FeatureCollection of LineStrings."""
    data = json.loads(path.read_text(encoding="utf-8"))
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
        if len(coords) < 1:
            continue
        segments.append(Segment(id=sid, name=name, coords=coords))
    if not segments:
        raise NearmissError(f"no LineString segments found in {path}")
    return segments


def load_exposure(path: Path) -> dict[str, Exposure]:
    """Load per-segment exposure denominators keyed by segment id."""
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = data["segments"] if isinstance(data, dict) else data
    out: dict[str, Exposure] = {}
    for row in rows:
        sid = str(row["segment_id"])
        out[sid] = Exposure(
            segment_id=sid,
            estimate=float(row["estimate"]),
            source=str(row["source"]),
            date=str(row["date"]),
        )
    return out


def load_reports(path: Path) -> list[dict[str, object]]:
    """Load raw report dicts (NOT yet validated) from a JSON array or {reports:[]}."""
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = data["reports"] if isinstance(data, dict) else data
    return [dict(r) for r in rows]


def reports_from_dicts(rows: list[dict[str, object]]) -> list[Report]:
    return [Report.from_dict(r) for r in rows]
