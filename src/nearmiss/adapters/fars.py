# SPDX-License-Identifier: Apache-2.0
"""Offline adapter for NHTSA Fatality Analysis Reporting System crash CSVs.

This first slice maps the crash-level ``accident.csv`` table only. It therefore
describes fatal crashes across all road users and intentionally does not infer
pedestrian or cyclist involvement; that requires a later person-table join.
"""

from __future__ import annotations

import csv
import datetime as dt
import hashlib
import io
import math
import re
import uuid
import zipfile
from collections.abc import Iterable, Mapping
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import IO, Any

from .outcomes import OutcomeProvenance

SOURCE_URL = "https://www.nhtsa.gov/research-data/fatality-analysis-reporting-system-fars"
_NS = uuid.uuid5(uuid.NAMESPACE_URL, SOURCE_URL)
_REQUIRED_COLUMNS = {"ST_CASE", "YEAR", "MONTH", "DAY", "LATITUDE", "LONGITUD", "FATALS"}
_RETAINED_COLUMNS = _REQUIRED_COLUMNS | {"HOUR", "MINUTE", "STATE"}
_LATITUDE_SENTINELS = {77.7777, 77.777777, 88.8888, 88.888888, 99.9999, 99.999999}
_MAX_INPUT_BYTES = 256 * 1024 * 1024
_MAX_CSV_BYTES = 128 * 1024 * 1024
_MAX_ZIP_MEMBERS = 1_000
_MAX_COMPRESSION_RATIO = 200
_INTEGER_RE = re.compile(r"^[+]?[0-9]+$")


@dataclass(frozen=True)
class FarsRawBatch:
    rows: tuple[Mapping[str, str], ...]
    input_sha256: str

    def __post_init__(self) -> None:
        if re.fullmatch(r"[0-9a-f]{64}", self.input_sha256) is None:
            raise ValueError("FARS input_sha256 must be a lowercase SHA-256 digest")
        frozen_rows = tuple(MappingProxyType(dict(row)) for row in self.rows)
        object.__setattr__(self, "rows", frozen_rows)


def _normalized_rows(stream: io.TextIOBase) -> tuple[dict[str, str], ...]:
    reader = csv.DictReader(stream)
    if reader.fieldnames is None:
        raise ValueError("FARS CSV has no header")
    normalized = [name.strip().upper() for name in reader.fieldnames]
    if len(set(normalized)) != len(normalized):
        raise ValueError("FARS CSV contains duplicate columns after normalization")
    missing = sorted(_REQUIRED_COLUMNS - set(normalized))
    if missing:
        raise ValueError(f"FARS CSV missing required column(s): {', '.join(missing)}")
    rows: list[dict[str, str]] = []
    for source_row in reader:
        rows.append(
            {
                normalized[index]: (source_row.get(original) or "").strip()
                for index, original in enumerate(reader.fieldnames)
                if normalized[index] in _RETAINED_COLUMNS
            }
        )
    return tuple(rows)


def _read_limited(stream: IO[bytes], *, limit: int, label: str) -> bytes:
    payload = stream.read(limit + 1)
    if len(payload) > limit:
        raise ValueError(f"FARS {label} exceeds the {limit}-byte safety limit")
    return payload


def _read_zip_member(payload: bytes) -> bytes:
    """Read only the crash table, bounding archive metadata and expansion."""
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        members = archive.infolist()
        if len(members) > _MAX_ZIP_MEMBERS:
            raise ValueError(f"FARS ZIP contains too many members (limit {_MAX_ZIP_MEMBERS})")
        matches = [
            member
            for member in members
            if not member.is_dir() and Path(member.filename).name.casefold() == "accident.csv"
        ]
        if len(matches) != 1:
            raise ValueError(
                f"FARS ZIP must contain exactly one accident.csv (found {len(matches)})"
            )
        member = matches[0]
        if member.flag_bits & 0x1:
            raise ValueError("FARS accident.csv ZIP member must not be encrypted")
        if member.file_size > _MAX_CSV_BYTES:
            raise ValueError(f"FARS accident.csv exceeds the {_MAX_CSV_BYTES}-byte safety limit")
        if member.file_size and (
            member.compress_size == 0
            or member.file_size / member.compress_size > _MAX_COMPRESSION_RATIO
        ):
            raise ValueError("FARS accident.csv has a suspicious ZIP compression ratio")
        with archive.open(member) as stream:
            return _read_limited(stream, limit=_MAX_CSV_BYTES, label="accident.csv")


def _read_bytes(payload: bytes, *, zipped: bool) -> tuple[dict[str, str], ...]:
    if zipped:
        csv_bytes = _read_zip_member(payload)
    else:
        if len(payload) > _MAX_CSV_BYTES:
            raise ValueError(f"FARS CSV exceeds the {_MAX_CSV_BYTES}-byte safety limit")
        csv_bytes = payload
    return _normalized_rows(io.StringIO(csv_bytes.decode("utf-8-sig")))


def read_export(path: str | Path) -> FarsRawBatch:
    """Read an extracted accident CSV or an NHTSA CSV ZIP into an immutable batch."""
    source = Path(path)
    with source.open("rb") as stream:
        payload = _read_limited(stream, limit=_MAX_INPUT_BYTES, label="export")
    rows = _read_bytes(payload, zipped=zipfile.is_zipfile(io.BytesIO(payload)))
    return FarsRawBatch(rows=rows, input_sha256=hashlib.sha256(payload).hexdigest())


def _integer(row: Mapping[str, str], key: str) -> int:
    value = row.get(key, "")
    if _INTEGER_RE.fullmatch(value) is None:
        # Reject signs other than an optional plus, decimals, exponents, and
        # other representations that ``int`` would accept lossily.
        raise ValueError
    return int(value)


def _calendar_year(row: Mapping[str, str]) -> int:
    year = _integer(row, "YEAR")
    if year < 1975:
        raise ValueError
    dt.date(year, 1, 1)
    return year


def _case_id(row: Mapping[str, str]) -> str:
    case = _integer(row, "ST_CASE")
    if case < 1:
        raise ValueError
    return str(case)


def _location(row: Mapping[str, str]) -> tuple[float, float]:
    lat = float(row["LATITUDE"])
    lon = float(row["LONGITUD"])
    if not math.isfinite(lat) or not math.isfinite(lon):
        raise ValueError
    if any(abs(lat - sentinel) < 1e-7 for sentinel in _LATITUDE_SENTINELS):
        raise ValueError
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValueError
    return lat, lon


def _local_time(row: Mapping[str, str]) -> str | None:
    try:
        hour = _integer(row, "HOUR")
        minute = _integer(row, "MINUTE")
    except (KeyError, TypeError, ValueError):
        return None
    if 0 <= hour <= 23 and 0 <= minute <= 59:
        return f"{hour:02d}:{minute:02d}"
    return None


def _map_row(row: Mapping[str, str]) -> tuple[dict[str, Any] | None, str | None]:
    try:
        case = _case_id(row)
        year = _calendar_year(row)
    except (KeyError, TypeError, ValueError):
        return None, "invalid_identity"
    try:
        occurred = dt.date(year, _integer(row, "MONTH"), _integer(row, "DAY"))
    except (KeyError, TypeError, ValueError):
        return None, "invalid_date"
    try:
        lat, lon = _location(row)
    except (KeyError, TypeError, ValueError):
        return None, "invalid_location"
    try:
        fatalities = _integer(row, "FATALS")
        if fatalities < 1:
            raise ValueError
    except (KeyError, TypeError, ValueError):
        return None, "invalid_fatality_count"

    outcome: dict[str, Any] = {
        "schema_version": "1.0.0",
        "id": str(uuid.uuid5(_NS, f"fars:{year}:{case}")),
        "source_record_id": f"{year}:{case}",
        "occurred_on": occurred.isoformat(),
        "location": {"lat": lat, "lon": lon},
        "outcome_type": "motor_vehicle_traffic_crash",
        "maximum_injury_severity": "fatal",
        "fatality_count": fatalities,
    }
    local_time = _local_time(row)
    if local_time is not None:
        outcome["occurred_time_local"] = local_time
    state = row.get("STATE", "").strip()
    if state:
        outcome["state_code"] = state
    return outcome, None


def _normalize_row(source_row: Mapping[str, str]) -> dict[str, str]:
    row: dict[str, str] = {}
    for source_key, source_value in source_row.items():
        key = str(source_key).strip().upper()
        if key in row:
            raise ValueError(f"FARS row contains duplicate normalized column {key!r}")
        row[key] = str(source_value).strip()
    return row


def _validated_bbox(
    bbox: tuple[float, float, float, float] | None,
) -> tuple[float, float, float, float] | None:
    if bbox is None:
        return None
    if not isinstance(bbox, (tuple, list)) or len(bbox) != 4:
        raise ValueError("FARS bbox must contain west, south, east, north")
    if any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in bbox):
        raise TypeError("FARS bbox coordinates must be numeric")
    west, south, east, north = (float(value) for value in bbox)
    if not all(math.isfinite(value) for value in (west, south, east, north)):
        raise ValueError("FARS bbox coordinates must be finite")
    if not (-180 <= west <= east <= 180 and -90 <= south <= north <= 90):
        raise ValueError("FARS bbox coordinates are out of range or inverted")
    return west, south, east, north


def collect(
    rows: Iterable[Mapping[str, str]],
    *,
    input_sha256: str | None = None,
    bbox: tuple[float, float, float, float] | None = None,
    release_status: str = "unspecified",
) -> tuple[list[dict[str, Any]], OutcomeProvenance]:
    """Map crash rows, retaining deterministic rejection accounting."""
    bbox = _validated_bbox(bbox)
    candidates: dict[str, list[dict[str, Any]]] = {}
    rejected: dict[str, int] = {}
    years: set[int] = set()
    records_read = 0
    for source_row in rows:
        records_read += 1
        if not isinstance(source_row, Mapping):
            raise TypeError(f"FARS row {records_read} must be a mapping")
        row = _normalize_row(source_row)
        with suppress(TypeError, ValueError):
            years.add(_calendar_year(row))
        outcome, reason = _map_row(row)
        if reason is not None:
            rejected[reason] = rejected.get(reason, 0) + 1
            continue
        assert outcome is not None
        outcome_id = str(outcome["id"])
        location = outcome["location"]
        if bbox is not None:
            west, south, east, north = bbox
            if not (west <= location["lon"] <= east and south <= location["lat"] <= north):
                rejected["outside_bbox"] = rejected.get("outside_bbox", 0) + 1
                continue
        candidates.setdefault(outcome_id, []).append(outcome)
    outcomes: list[dict[str, Any]] = []
    for duplicate_group in candidates.values():
        if len(duplicate_group) > 1:
            rejected["duplicate_source_record"] = rejected.get("duplicate_source_record", 0) + len(
                duplicate_group
            )
        else:
            outcomes.append(duplicate_group[0])
    outcomes.sort(key=lambda item: (item["occurred_on"], item["source_record_id"]))
    provenance = OutcomeProvenance(
        source_id="fars",
        source_name="NHTSA Fatality Analysis Reporting System",
        source_url=SOURCE_URL,
        license="NHTSA public data; review source terms before redistribution",
        dataset_years=tuple(sorted(years)),
        release_status=release_status,
        scope="Fatal motor-vehicle traffic crashes represented by the supplied FARS export",
        limitations=(
            "FARS includes only crashes resulting in a death within 30 days.",
            "Crash-level rows do not identify involved pedestrian or cyclist modes.",
            "Reported local times have no timezone attached.",
            "Release status is supplied by the operator, not derived from archive contents.",
        ),
        records_read=records_read,
        records_accepted=len(outcomes),
        rejection_reasons=dict(sorted(rejected.items())),
        input_sha256=input_sha256,
    )
    return outcomes, provenance


class FarsAdapter:
    """OfficialOutcomeAdapter for a local FARS accident CSV or CSV archive."""

    source_id = "fars"

    def fetch(self, **kwargs: Any) -> FarsRawBatch:
        path = kwargs.get("path")
        if path is None:
            raise ValueError("FarsAdapter.fetch requires path=<CSV-or-ZIP>")
        return read_export(path)

    def parse(self, raw: Any, **kwargs: Any) -> tuple[list[dict[str, Any]], OutcomeProvenance]:
        bbox: tuple[float, float, float, float] | None = kwargs.get("bbox")
        release_status: str = kwargs.get("release_status", "unspecified")
        if not isinstance(release_status, str):
            raise TypeError("FARS release_status must be a string")
        release_status = release_status.strip()
        if not release_status:
            raise ValueError("FARS release_status must not be empty")
        rows: Iterable[Mapping[str, str]]
        if isinstance(raw, FarsRawBatch):
            rows = raw.rows
            digest: str | None = raw.input_sha256
        elif isinstance(raw, (str, Path)):
            batch = read_export(raw)
            rows = batch.rows
            digest = batch.input_sha256
        else:
            if isinstance(raw, (bytes, bytearray, memoryview, Mapping)) or not isinstance(
                raw, Iterable
            ):
                raise TypeError(
                    "FarsAdapter.parse requires a path, FarsRawBatch, or iterable of row mappings"
                )
            rows = raw
            digest = None
        return collect(rows, input_sha256=digest, bbox=bbox, release_status=release_status)
