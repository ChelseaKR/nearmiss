# SPDX-License-Identifier: Apache-2.0
"""Spreadsheet source adapter: an advocacy group's own file of close calls.

#186 recorded the bind this exists to break. The registry shipped two report
adapters and zero publishable real-data paths: BikeMaps has no Davis coverage,
SimRa's CC BY-NC clause survives aggregation, and no open US dataset pairs
near-miss reports with the bicycle counts a rate needs. The one source a group
always has rights to is its own records — a shared spreadsheet of member
reports, exported as CSV.

This adapter is the generic half of that. It reads a CSV and a crosswalk
manifest that says which column carries which intake field and how the
source's own vocabulary maps onto the closed enums in
``schema/report.schema.json``. The manifest is validated by the same
:func:`~nearmiss.adapters.base.load_crosswalk_file` that validates the
committed ones, so a group's crosswalk cannot reach intake with its bias
profile blank.

What it will not do
-------------------

Nothing here fills a field in. Four kinds of row are *excluded and counted*,
never repaired:

* a travel mode the crosswalk does not map (``mode`` has no ``unknown`` member,
  so there is nothing to fall back to that is not an invention);
* a timestamp that carries no timezone and no declared offset to give it one;
* a timestamp that will not parse at all;
* a row with neither coordinates nor an address.

:class:`SpreadsheetImport` carries those counts beside the reports, and
``nearmiss crosswalk import`` prints them, because a row silently dropped is a
row that leaves the denominator looking smaller and the file looking cleaner
than it is. Rows that carry an address rather than coordinates are emitted with
``address`` set and resolved later by the pipeline's geocode stage, which
reports its own unresolved count; this adapter does not geocode.

Condition records — a 311 service request, a pavement-inspection export — are
still not reports, whatever their file format. See ``base.py``'s module
docstring and ``docs/REAL-DATA.md``.
"""

from __future__ import annotations

import csv
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from .base import Crosswalk, Provenance, load_crosswalk_file

#: Namespace for the deterministic report ids this adapter mints. Ids are
#: derived from the source id and the row's own mapped content, so importing
#: the same export twice produces the same ids and the dedupe stage can do its
#: job instead of seeing every row as new.
_NS = uuid.uuid5(uuid.NAMESPACE_URL, "https://github.com/ChelseaKR/nearmiss#spreadsheet")

#: Intake fields a spreadsheet must supply a column for. ``occurred_at``,
#: ``mode``, ``hazard_type`` and ``severity`` are the schema's own required
#: fields minus the two the adapter supplies itself (``schema_version`` and
#: ``id``). Location is handled separately: the schema accepts either
#: coordinates or an address, so the requirement is one of them, not both.
REQUIRED_COLUMNS: tuple[str, ...] = ("occurred_at", "mode", "hazard_type", "severity")

#: Optional intake fields a spreadsheet may supply.
OPTIONAL_COLUMNS: tuple[str, ...] = ("note", "language")

#: Location columns. ``lat``/``lon`` must appear together; ``address`` stands
#: alone. A manifest must map one of the two shapes.
LOCATION_COLUMNS: tuple[str, ...] = ("lat", "lon", "address")

#: Every key ``[field_map]`` may hold, besides ``timezone_offset``.
MAPPABLE_COLUMNS: tuple[str, ...] = REQUIRED_COLUMNS + OPTIONAL_COLUMNS + LOCATION_COLUMNS

#: Why a row did not become a report. Every counter is reported; none is
#: silently swallowed.
SKIP_REASONS: tuple[str, ...] = (
    "unmapped_mode",
    "unparseable_time",
    "naive_time_no_offset",
    "no_location",
)


class SpreadsheetCrosswalkError(ValueError):
    """A spreadsheet crosswalk manifest that cannot be used as written."""


@dataclass(frozen=True)
class FieldMap:
    """Which source column carries which intake field.

    ``columns`` maps an intake field name (a member of
    :data:`MAPPABLE_COLUMNS`) to the CSV column header that holds it.
    ``timezone_offset`` is the fixed UTC offset to attach to timestamps that
    carry none, as ``+HH:MM`` / ``-HH:MM``; when it is None, a naive timestamp
    is excluded and counted rather than guessed at.
    """

    columns: dict[str, str]
    timezone_offset: str | None = None

    def source_column(self, intake_field: str) -> str | None:
        return self.columns.get(intake_field)


@dataclass
class SpreadsheetImport:
    """The result of reading one export: what became a report, and what did not."""

    reports: list[dict[str, Any]] = field(default_factory=list)
    rows_read: int = 0
    skipped: dict[str, int] = field(default_factory=lambda: dict.fromkeys(SKIP_REASONS, 0))

    @property
    def skipped_total(self) -> int:
        return sum(self.skipped.values())

    def counts_by_kind(self) -> dict[str, int]:
        """Provenance counts: rows in, reports out, and every exclusion named.

        ``rows_read`` and ``reports`` are both present on purpose. A consumer
        that sees only the report count cannot tell a clean 40-row export from
        a 400-row export that lost 90% of its rows to an unmapped mode.
        """
        counts = {"rows_read": self.rows_read, "reports": len(self.reports)}
        counts.update(self.skipped)
        return counts


def load_field_map(path: Path, name: str | None = None) -> FieldMap:
    """Read and check the ``[field_map]`` table of a spreadsheet crosswalk.

    Raises :class:`SpreadsheetCrosswalkError` when a required intake field has
    no column, when no location shape is mapped, or when an unknown key
    appears. A required field is never defaulted: a manifest that cannot say
    where ``mode`` lives is refused here rather than producing reports whose
    mode was chosen by this file.
    """
    import tomllib

    name = name or path.stem
    with path.open("rb") as handle:
        data = tomllib.load(handle)
    raw = data.get("field_map")
    if not isinstance(raw, dict):
        raise SpreadsheetCrosswalkError(
            f"crosswalk {name!r}: missing required [field_map] table. A spreadsheet "
            f"crosswalk has to say which column carries which intake field."
        )

    timezone_offset = raw.get("timezone_offset")
    if timezone_offset is not None and not isinstance(timezone_offset, str):
        raise SpreadsheetCrosswalkError(
            f"crosswalk {name!r}: [field_map] timezone_offset must be a string like '-07:00'"
        )
    if isinstance(timezone_offset, str) and _parse_offset(timezone_offset) is None:
        raise SpreadsheetCrosswalkError(
            f"crosswalk {name!r}: [field_map] timezone_offset {timezone_offset!r} is not a "
            f"UTC offset of the form '+HH:MM' or '-HH:MM'"
        )

    columns = {key: value for key, value in raw.items() if key != "timezone_offset" and value != ""}
    unknown = sorted(set(columns) - set(MAPPABLE_COLUMNS))
    if unknown:
        raise SpreadsheetCrosswalkError(
            f"crosswalk {name!r}: [field_map] has unrecognized field(s) {unknown}; "
            f"the mappable intake fields are {list(MAPPABLE_COLUMNS)}"
        )
    non_strings = sorted(key for key, value in columns.items() if not isinstance(value, str))
    if non_strings:
        raise SpreadsheetCrosswalkError(
            f"crosswalk {name!r}: [field_map] value(s) for {non_strings} must be column names"
        )

    missing = [field_name for field_name in REQUIRED_COLUMNS if field_name not in columns]
    if missing:
        raise SpreadsheetCrosswalkError(
            f"crosswalk {name!r}: [field_map] has no column for required intake field(s) "
            f"{missing}. These are never defaulted: a report with a mode nobody wrote down "
            f"is not a report about anybody."
        )

    has_coordinates = "lat" in columns and "lon" in columns
    if ("lat" in columns) != ("lon" in columns):
        raise SpreadsheetCrosswalkError(
            f"crosswalk {name!r}: [field_map] maps one of lat/lon and not the other; "
            f"a coordinate needs both."
        )
    if not has_coordinates and "address" not in columns:
        raise SpreadsheetCrosswalkError(
            f"crosswalk {name!r}: [field_map] maps neither lat/lon nor address. A report "
            f"must carry one of them (schema/report.schema.json, anyOf)."
        )

    return FieldMap(columns=dict(columns), timezone_offset=timezone_offset)


def _parse_offset(value: str) -> str | None:
    """Return ``value`` if it is a ``+HH:MM``/``-HH:MM`` UTC offset, else None."""
    if len(value) != 6 or value[0] not in "+-" or value[3] != ":":
        return None
    hours, minutes = value[1:3], value[4:6]
    if not (hours.isascii() and hours.isdigit() and minutes.isascii() and minutes.isdigit()):
        return None
    if int(hours) > 23 or int(minutes) > 59:
        return None
    return value


def _normalize_time(value: str, timezone_offset: str | None) -> tuple[str | None, str | None]:
    """Return ``(rfc3339, None)`` or ``(None, skip_reason)`` for one timestamp.

    Accepts what :func:`datetime.datetime.fromisoformat` accepts, including a
    space between the date and the time, which is what a spreadsheet exports.
    A timestamp that already carries an offset keeps its own; one that does not
    is given the manifest's declared offset, and if the manifest declares none
    the row is excluded and counted. Local time with an assumed offset would be
    a fabricated hour, and time-of-day analysis reads those hours.
    """
    text = value.strip()
    if not text:
        return None, "unparseable_time"
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None, "unparseable_time"
    if parsed.tzinfo is None:
        if timezone_offset is None:
            return None, "naive_time_no_offset"
        try:
            parsed = datetime.fromisoformat(f"{parsed.isoformat()}{timezone_offset}")
        except ValueError:  # pragma: no cover - _parse_offset already vetted it
            return None, "naive_time_no_offset"
    return parsed.isoformat(), None


def _location_for(row: dict[str, str], field_map: FieldMap) -> dict[str, Any] | None:
    """The ``location``/``address`` half of one report, or None if it has neither."""
    lat_column, lon_column = field_map.source_column("lat"), field_map.source_column("lon")
    if lat_column and lon_column:
        lat_text, lon_text = row.get(lat_column, ""), row.get(lon_column, "")
        try:
            lat, lon = float(lat_text), float(lon_text)
        except (TypeError, ValueError):
            lat = lon = None  # type: ignore[assignment]
        if lat is not None and lon is not None and -90 <= lat <= 90 and -180 <= lon <= 180:
            return {"location": {"lat": lat, "lon": lon}}
    address_column = field_map.source_column("address")
    if address_column:
        address = (row.get(address_column) or "").strip()
        if len(address) >= 3:
            return {"address": address[:200]}
    return None


def map_row(
    row: dict[str, str], crosswalk: Crosswalk, field_map: FieldMap
) -> tuple[dict[str, Any] | None, str | None]:
    """Turn one CSV row into an intake report, or say why it could not be one."""
    mode = crosswalk.mode_from(row.get(field_map.columns["mode"], ""))
    if mode is None:
        return None, "unmapped_mode"

    occurred_at, reason = _normalize_time(
        row.get(field_map.columns["occurred_at"], "") or "", field_map.timezone_offset
    )
    if occurred_at is None:
        return None, reason

    location = _location_for(row, field_map)
    if location is None:
        return None, "no_location"

    report: dict[str, Any] = {
        "schema_version": "1.0.0",
        "id": "",
        "occurred_at": occurred_at,
        "mode": mode,
        "hazard_type": crosswalk.hazard_from(
            (row.get(field_map.columns["hazard_type"], "") or "").strip()
        ),
        "severity": crosswalk.severity_from(row.get(field_map.columns["severity"], "")),
        **location,
    }
    note_column = field_map.source_column("note")
    if note_column:
        note = (row.get(note_column) or "").strip()
        if note:
            report["note"] = note[:1000]
    language_column = field_map.source_column("language")
    if language_column:
        language = (row.get(language_column) or "").strip()
        if language:
            report["language"] = language
    key = "|".join(f"{name}={report[name]}" for name in sorted(report) if name != "id")
    report["id"] = str(uuid.uuid5(_NS, f"{crosswalk.source_id}:{key}"))
    return report, None


def read_csv(path: Path, crosswalk: Crosswalk, field_map: FieldMap) -> SpreadsheetImport:
    """Read one CSV export into reports plus a full account of what was excluded."""
    result = SpreadsheetImport()
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            result.rows_read += 1
            report, reason = map_row(row, crosswalk, field_map)
            if report is None:
                assert reason is not None
                result.skipped[reason] = result.skipped.get(reason, 0) + 1
                continue
            result.reports.append(report)
    return result


class SpreadsheetAdapter:
    """``SourceAdapter`` for a group's own CSV export of member reports.

    Unlike the committed adapters this one is constructed with the path to the
    group's crosswalk, because the manifest belongs to the group's project
    rather than to this package. It is deliberately absent from
    ``adapters.registry`` for the same reason: there is no single "spreadsheet"
    source to register, only one per group.
    """

    def __init__(self, crosswalk_path: Path) -> None:
        self.crosswalk_path = Path(crosswalk_path)
        self.crosswalk = load_crosswalk_file(self.crosswalk_path)
        self.field_map = load_field_map(self.crosswalk_path)
        self.source_id = self.crosswalk.source_id

    def fetch(self, **kwargs: Any) -> Any:
        """Keywords: ``path`` (the CSV export). No network access, ever."""
        path = Path(kwargs["path"])
        if not path.is_file():
            raise FileNotFoundError(f"spreadsheet export not found: {path}")
        return path

    def parse(self, raw: Any, **kwargs: Any) -> tuple[list[dict[str, Any]], Provenance]:
        result = self.read(Path(raw))
        return result.reports, self.crosswalk.provenance(result.counts_by_kind())

    def read(self, path: Path) -> SpreadsheetImport:
        """The same read as :meth:`parse`, keeping the exclusion counts."""
        return read_csv(path, self.crosswalk, self.field_map)
