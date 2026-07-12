# SPDX-License-Identifier: Apache-2.0
"""Bounded FARS accident/person join for deterministic road-user modes."""

from __future__ import annotations

import csv
import hashlib
import io
import re
import zipfile
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, cast

from .fars import FarsAdapter, FarsRawBatch, read_export_bytes
from .outcomes import OutcomeProvenance

PERSON_MODE_MAPPING_VERSION = "1.0.0"
MODE_ORDER = (
    "motor_vehicle_occupant",
    "motorcyclist",
    "pedalcyclist",
    "pedestrian",
    "other_road_user",
    "unknown",
)
_REQUIRED_PERSON_COLUMNS = {
    "STATE",
    "ST_CASE",
    "VEH_NO",
    "PER_NO",
    "PER_TYP",
    "INJ_SEV",
    "BODY_TYP",
}
_MAX_INPUT_BYTES = 256 * 1024 * 1024
_MAX_MEMBER_BYTES = 128 * 1024 * 1024
_MAX_EXPANDED_BYTES = 256 * 1024 * 1024
_MAX_MEMBERS = 1_000
_MAX_COMPRESSION_RATIO = 200
# The final 2024 national file contains 88,326 rows. This 13% headroom is
# intentionally narrow: the mapping is 2024-only, and a materially larger
# replacement must be reviewed instead of expanding into unbounded Python
# row objects inside an ingestion worker.
_MAX_PERSON_ROWS = 100_000
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
_DIGITS_RE = re.compile(r"^[0-9]+$")
_MAPPING_PROXY_TYPE: type[Any] = type(MappingProxyType({}))


def _frozen_row(row: Mapping[str, str]) -> Mapping[str, str]:
    return row if isinstance(row, _MAPPING_PROXY_TYPE) else MappingProxyType(dict(row))


@dataclass(frozen=True)
class FarsJoinedRawBatch:
    accident_rows: tuple[Mapping[str, str], ...]
    person_rows: tuple[Mapping[str, str], ...]
    input_sha256: str
    accident_sha256: str
    person_sha256: str

    def __post_init__(self) -> None:
        if any(
            _DIGEST_RE.fullmatch(value) is None
            for value in (self.input_sha256, self.accident_sha256, self.person_sha256)
        ):
            raise ValueError("joined FARS digests must be lowercase SHA-256 values")
        object.__setattr__(
            self,
            "accident_rows",
            tuple(_frozen_row(row) for row in self.accident_rows),
        )
        object.__setattr__(
            self,
            "person_rows",
            tuple(_frozen_row(row) for row in self.person_rows),
        )


@dataclass(frozen=True)
class PersonJoinProvenance:
    mapping_version: str
    dataset_year: int
    input_sha256: str
    accident_sha256: str
    person_sha256: str
    records_read: int
    records_accepted: int
    cases_joined: int
    records_excluded_with_rejected_crash: int
    cases_excluded_with_rejected_crash: int
    rejection_reasons: Mapping[str, int]

    def __post_init__(self) -> None:
        reasons = MappingProxyType(dict(sorted(self.rejection_reasons.items())))
        if self.dataset_year != 2024:
            raise ValueError("joined FARS person mapping supports dataset year 2024 only")
        if self.records_accepted + self.records_excluded_with_rejected_crash != self.records_read:
            raise ValueError("joined FARS person accounting must cover every record")
        object.__setattr__(self, "rejection_reasons", reasons)

    def as_dict(self) -> dict[str, object]:
        return {
            "mapping_version": self.mapping_version,
            "dataset_year": self.dataset_year,
            "input_sha256": self.input_sha256,
            "accident_sha256": self.accident_sha256,
            "person_sha256": self.person_sha256,
            "records_read": self.records_read,
            "records_accepted": self.records_accepted,
            "cases_joined": self.cases_joined,
            "records_excluded_with_rejected_crash": self.records_excluded_with_rejected_crash,
            "cases_excluded_with_rejected_crash": self.cases_excluded_with_rejected_crash,
            "rejection_reasons": dict(self.rejection_reasons),
        }


@dataclass(frozen=True)
class FarsModeSummary:
    source_record_id: str
    involved_modes: tuple[str, ...]
    fatality_modes: tuple[str, ...]
    involved_person_count_by_mode: Mapping[str, int]
    fatality_count_by_mode: Mapping[str, int]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "involved_person_count_by_mode",
            MappingProxyType(dict(self.involved_person_count_by_mode)),
        )
        object.__setattr__(
            self,
            "fatality_count_by_mode",
            MappingProxyType(dict(self.fatality_count_by_mode)),
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "source_record_id": self.source_record_id,
            "involved_modes": list(self.involved_modes),
            "fatality_modes": list(self.fatality_modes),
            "involved_person_count_by_mode": dict(self.involved_person_count_by_mode),
            "fatality_count_by_mode": dict(self.fatality_count_by_mode),
        }


def _member(archive: zipfile.ZipFile, basename: str) -> zipfile.ZipInfo:
    matches = [
        member
        for member in archive.infolist()
        if not member.is_dir() and member.filename.rsplit("/", 1)[-1].casefold() == basename
    ]
    if len(matches) != 1:
        raise ValueError(f"joined FARS ZIP must contain exactly one {basename}")
    member = matches[0]
    if member.flag_bits & 0x1:
        raise ValueError(f"joined FARS {basename} must not be encrypted")
    if member.file_size > _MAX_MEMBER_BYTES:
        raise ValueError(f"joined FARS {basename} exceeds its safety limit")
    if member.file_size and (
        member.compress_size == 0
        or member.file_size / member.compress_size > _MAX_COMPRESSION_RATIO
    ):
        raise ValueError(f"joined FARS {basename} has a suspicious compression ratio")
    return member


def _hash_member(archive: zipfile.ZipFile, member: zipfile.ZipInfo) -> str:
    digest = hashlib.sha256()
    with archive.open(member) as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


class _HashingReader(io.RawIOBase):
    def __init__(self, stream: Any) -> None:
        self._stream = stream
        self.digest = hashlib.sha256()
        self.total = 0

    def readable(self) -> bool:
        return True

    def readinto(self, buffer: Any) -> int:
        count = cast(int, self._stream.readinto(buffer))
        if count:
            self.digest.update(memoryview(buffer)[:count])
            self.total += count
            if self.total > _MAX_MEMBER_BYTES:
                raise ValueError("joined FARS person.csv exceeds its safety limit")
        return count


def _person_rows(stream: io.TextIOBase) -> tuple[Mapping[str, str], ...]:
    reader = csv.DictReader(stream)
    if reader.fieldnames is None:
        raise ValueError("FARS person.csv has no header")
    columns = [column.strip().upper() for column in reader.fieldnames]
    if len(columns) != len(set(columns)):
        raise ValueError("FARS person.csv has duplicate normalized columns")
    missing = sorted(_REQUIRED_PERSON_COLUMNS - set(columns))
    if missing:
        raise ValueError(f"FARS person.csv missing required columns: {', '.join(missing)}")
    rows: list[Mapping[str, str]] = []
    for source in reader:
        if len(rows) >= _MAX_PERSON_ROWS:
            raise ValueError("FARS person.csv exceeds its row-count safety limit")
        if None in source:
            raise ValueError("FARS person.csv row has more values than its header")
        rows.append(
            MappingProxyType(
                {
                    columns[index]: (source.get(original) or "").strip()
                    for index, original in enumerate(reader.fieldnames)
                    if columns[index] in _REQUIRED_PERSON_COLUMNS
                }
            )
        )
    return tuple(rows)


def _read_person_member(
    archive: zipfile.ZipFile, member: zipfile.ZipInfo
) -> tuple[tuple[Mapping[str, str], ...], str]:
    with archive.open(member) as compressed:
        hashing = _HashingReader(compressed)
        with (
            io.BufferedReader(hashing) as buffered,
            io.TextIOWrapper(buffered, encoding="utf-8-sig", newline="") as text,
        ):
            rows = _person_rows(text)
        if hashing.total != member.file_size:
            raise ValueError("joined FARS person.csv size does not match ZIP metadata")
        return rows, hashing.digest.hexdigest()


def read_joined_export_bytes(payload: bytes) -> FarsJoinedRawBatch:
    """Read exactly accident.csv and person.csv from one bounded FARS ZIP."""
    if not isinstance(payload, bytes):
        raise TypeError("joined FARS export must be bytes")
    if len(payload) > _MAX_INPUT_BYTES:
        raise ValueError("joined FARS export exceeds its safety limit")
    if not zipfile.is_zipfile(io.BytesIO(payload)):
        raise ValueError("joined FARS export must be a ZIP archive")
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        if len(archive.infolist()) > _MAX_MEMBERS:
            raise ValueError("joined FARS ZIP contains too many members")
        accident_member = _member(archive, "accident.csv")
        person_member = _member(archive, "person.csv")
        if accident_member.file_size + person_member.file_size > _MAX_EXPANDED_BYTES:
            raise ValueError("joined FARS selected members exceed the expansion safety limit")
        accident_sha256 = _hash_member(archive, accident_member)
        person_rows, person_sha256 = _read_person_member(archive, person_member)
    crash_batch = read_export_bytes(payload)
    return FarsJoinedRawBatch(
        accident_rows=crash_batch.rows,
        person_rows=person_rows,
        input_sha256=hashlib.sha256(payload).hexdigest(),
        accident_sha256=accident_sha256,
        person_sha256=person_sha256,
    )


def _integer(row: Mapping[str, str], key: str, *, positive: bool = False) -> int:
    value = row.get(key, "")
    if _DIGITS_RE.fullmatch(value) is None:
        raise ValueError(f"invalid FARS person {key}")
    result = int(value)
    if positive and result < 1:
        raise ValueError(f"invalid FARS person {key}")
    return result


def _mode(row: Mapping[str, str]) -> str:
    person_type = _integer(row, "PER_TYP")
    if person_type == 5:
        return "pedestrian"
    if person_type in {6, 7}:
        return "pedalcyclist"
    if person_type in {4, 8, 10, 11, 12, 13}:
        return "other_road_user"
    if person_type == 19:
        return "unknown"
    if person_type not in {1, 2, 3, 9}:
        raise ValueError("invalid FARS person PER_TYP")
    body = row.get("BODY_TYP", "")
    if not body or body in {"98", "99"}:
        return "unknown"
    if _DIGITS_RE.fullmatch(body) is None or not 1 <= int(body) <= 99:
        raise ValueError("invalid FARS person BODY_TYP")
    return "motorcyclist" if 80 <= int(body) <= 89 else "motor_vehicle_occupant"


def _accident_index(
    batch: FarsJoinedRawBatch,
) -> tuple[dict[str, tuple[str, int, int]], int]:
    accident: dict[str, tuple[str, int, int]] = {}
    years: set[int] = set()
    for row in batch.accident_rows:
        case = str(_integer(row, "ST_CASE", positive=True))
        if case in accident:
            raise ValueError("duplicate FARS accident case")
        year = _integer(row, "YEAR", positive=True)
        years.add(year)
        accident[case] = (str(_integer(row, "STATE", positive=True)), _integer(row, "FATALS"), year)
    if len(years) != 1:
        raise ValueError("joined FARS export must contain exactly one dataset year")
    year = years.pop()
    if year != 2024:
        raise ValueError("joined FARS person mapping supports dataset year 2024 only")
    return accident, year


def _person_index(  # noqa: C901 - whole-batch relational checks remain auditable together
    batch: FarsJoinedRawBatch,
) -> tuple[dict[str, dict[str, Any]], int]:
    accident, year = _accident_index(batch)
    joined: dict[str, dict[str, Any]] = {}
    person_keys: set[tuple[str, int, int]] = set()
    allowed_injury = {0, 1, 2, 3, 4, 5, 6, 9}
    for row in batch.person_rows:
        case = str(_integer(row, "ST_CASE", positive=True))
        vehicle = _integer(row, "VEH_NO")
        person = _integer(row, "PER_NO", positive=True)
        key = case, vehicle, person
        if key in person_keys:
            raise ValueError("duplicate FARS person identity")
        person_keys.add(key)
        if case not in accident:
            raise ValueError("orphan FARS person case")
        if str(_integer(row, "STATE", positive=True)) != accident[case][0]:
            raise ValueError("FARS person state does not match accident")
        injury = _integer(row, "INJ_SEV")
        if injury not in allowed_injury:
            raise ValueError("invalid FARS person INJ_SEV")
        mode = _mode(row)
        person_type = _integer(row, "PER_TYP")
        occupant_types = {1, 2, 3, 9}
        if person_type in occupant_types and vehicle < 1:
            raise ValueError("FARS occupant person must have positive VEH_NO")
        if person_type not in occupant_types and vehicle != 0:
            raise ValueError("FARS nonoccupant person must have VEH_NO zero")
        summary = joined.setdefault(
            case,
            {
                "involved": dict.fromkeys(MODE_ORDER, 0),
                "fatal": dict.fromkeys(MODE_ORDER, 0),
            },
        )
        summary["involved"][mode] += 1
        if injury == 4:
            summary["fatal"][mode] += 1
    if set(joined) != set(accident):
        raise ValueError("joined FARS export has accident cases without person rows")
    for case, summary in joined.items():
        if sum(summary["fatal"].values()) != accident[case][1]:
            raise ValueError("FARS person fatal count does not match accident")
    return joined, year


def collect_joined(
    batch: FarsJoinedRawBatch,
    *,
    release_status: str = "unspecified",
) -> tuple[
    list[dict[str, Any]],
    list[FarsModeSummary],
    OutcomeProvenance,
    PersonJoinProvenance,
]:
    """Map crash outcomes and attach deterministic crash-level person mode summaries."""
    joined, year = _person_index(batch)
    outcomes, crash_provenance = FarsAdapter().parse(
        FarsRawBatch(rows=batch.accident_rows, input_sha256=batch.input_sha256),
        release_status=release_status,
    )
    summaries: list[FarsModeSummary] = []
    emitted_cases: set[str] = set()
    for outcome in outcomes:
        case = str(outcome["source_record_id"]).partition(":")[2]
        emitted_cases.add(case)
        summary = joined[case]
        involved = dict(summary["involved"])
        fatal = dict(summary["fatal"])
        summaries.append(
            FarsModeSummary(
                source_record_id=str(outcome["source_record_id"]),
                involved_modes=tuple(mode for mode in MODE_ORDER if involved[mode] > 0),
                fatality_modes=tuple(mode for mode in MODE_ORDER if fatal[mode] > 0),
                involved_person_count_by_mode=involved,
                fatality_count_by_mode=fatal,
            )
        )
    excluded_cases = set(joined) - emitted_cases
    accepted_person_records = sum(sum(joined[case]["involved"].values()) for case in emitted_cases)
    excluded_person_records = len(batch.person_rows) - accepted_person_records
    reasons = {"parent_crash_rejected": excluded_person_records} if excluded_person_records else {}
    provenance = PersonJoinProvenance(
        mapping_version=PERSON_MODE_MAPPING_VERSION,
        dataset_year=year,
        input_sha256=batch.input_sha256,
        accident_sha256=batch.accident_sha256,
        person_sha256=batch.person_sha256,
        records_read=len(batch.person_rows),
        records_accepted=accepted_person_records,
        cases_joined=len(emitted_cases),
        records_excluded_with_rejected_crash=excluded_person_records,
        cases_excluded_with_rejected_crash=len(excluded_cases),
        rejection_reasons=reasons,
    )
    return outcomes, summaries, crash_provenance, provenance
