"""The SimRa adapter maps real bicycle near-miss records onto the intake contract.

A small SimRa-shaped sample (no network) exercises the parser and the crosswalk,
and every emitted report is validated against schema/report.schema.json.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import jsonschema

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads((ROOT / "schema" / "report.schema.json").read_text(encoding="utf-8"))


def _load_tool() -> ModuleType:
    spec = importlib.util.spec_from_file_location("fetch_simra", ROOT / "tools" / "fetch_simra.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


fs = _load_tool()

# One real-looking ride file: header, two incident rows (one annotated close pass,
# one un-annotated placeholder), the divider, then a couple of GPS trace rows.
SAMPLE = (
    "90#1#0\n"
    "key,lat,lon,ts,bike,childCheckBox,trailerCheckBox,pLoc,incident,i1,i2,i3,i4,i5,i6,i7,i8,i9,scary,desc,i10\n"
    ",52.50,13.40,1678451179000,3,0,0,0,1,0,0,0,0,0,0,0,0,0,1,,0\n"
    ",52.48,13.28,1678451279000,3,0,0,0,7,0,0,0,0,0,0,0,0,0,0,,0\n"
    ",,,,3,0,0,0,-5,0,0,0,0,0,0,0,0,0,0,,0\n"
    "=========================\n"
    "lat,lon,X,Y,Z,timeStamp,acc,a,b,c\n"
    "52.50,13.40,0,0,9.8,1678451179000,10,0,0,0\n"
)


def test_parses_only_annotated_incidents() -> None:
    rows = fs.parse_incidents(SAMPLE)
    assert len(rows) == 3  # all three incident rows, including the placeholder
    reports = [fs.map_incident(r, "VM2_x", None) for r in rows]
    kept = [r for r in reports if r is not None]
    assert len(kept) == 2  # the -5 placeholder is dropped


def test_mapped_reports_are_schema_valid() -> None:
    reports = [
        r for r in (fs.map_incident(row, "f", None) for row in fs.parse_incidents(SAMPLE)) if r
    ]
    validator = jsonschema.Draft202012Validator(SCHEMA)
    for rep in reports:
        assert not list(validator.iter_errors(rep))


def test_crosswalk_and_epoch_time() -> None:
    rows = fs.parse_incidents(SAMPLE)
    reps = [r for r in (fs.map_incident(row, "f", None) for row in rows) if r]
    by_haz = {r["hazard_type"] for r in reps}
    assert "close_pass" in by_haz  # incident code 1
    assert "dooring" in by_haz  # incident code 7
    # Epoch-ms timestamp becomes RFC 3339 UTC, and SimRa is always near_miss.
    assert all(r["severity"] == "near_miss" for r in reps)
    assert all(r["occurred_at"].endswith("Z") for r in reps)
    assert all(r["mode"] == "cyclist" for r in reps)


def test_bbox_filters() -> None:
    rows = fs.parse_incidents(SAMPLE)
    # A bbox far from Berlin drops everything.
    reps = [r for r in (fs.map_incident(row, "f", (-1.0, 50.0, 0.0, 51.0)) for row in rows) if r]
    assert reps == []
