# SPDX-License-Identifier: Apache-2.0
"""Bounded FARS accident/person join for deterministic road-user modes."""

from __future__ import annotations

import csv
import hashlib
import io
import re
import zipfile
import zlib
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, cast

from ..fars_year_contracts import FarsYearContract, fars_year_contract
from .fars import FarsAdapter, FarsRawBatch, read_export_bytes
from .outcomes import OutcomeProvenance

PERSON_MODE_MAPPING_VERSION = "1.0.0"
FARS_COUNTY_CODE_SYSTEM = "nhtsa_fars_gsa_2024"
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
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
_CRC32_RE = re.compile(r"^[0-9a-f]{8}$")
_DIGITS_RE = re.compile(r"^[0-9]+$")
_MAPPING_PROXY_TYPE: type[Any] = type(MappingProxyType({}))


def _frozen_row(row: Mapping[str, str]) -> Mapping[str, str]:
    return row if isinstance(row, _MAPPING_PROXY_TYPE) else MappingProxyType(dict(row))


def _canonical_archive_path(value: str) -> str:
    if (
        not value
        or not value.isascii()
        or value.startswith("/")
        or re.match(r"^[A-Za-z]:", value) is not None
        or "\\" in value
        or "%" in value
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise ValueError("joined FARS member path is unsafe or noncanonical")
    parts = value.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise ValueError("joined FARS member path is unsafe or noncanonical")
    return value


@dataclass(frozen=True)
class FarsMemberDescriptor:
    """Exact identity of one selected CSV member in the official ZIP."""

    archive_path: str
    name: str
    uncompressed_size: int
    crc32: str
    sha256: str

    def __post_init__(self) -> None:
        path = _canonical_archive_path(self.archive_path)
        if self.name != path.rsplit("/", 1)[-1]:
            raise ValueError("joined FARS member name must match its canonical archive path")
        if self.name.casefold() not in {"accident.csv", "person.csv"}:
            raise ValueError("joined FARS member name is not a supported table")
        if (
            isinstance(self.uncompressed_size, bool)
            or not isinstance(self.uncompressed_size, int)
            or not 0 < self.uncompressed_size <= _MAX_MEMBER_BYTES
        ):
            raise ValueError("joined FARS member size is invalid")
        if _CRC32_RE.fullmatch(self.crc32) is None:
            raise ValueError("joined FARS member CRC32 must be eight lowercase hexadecimal digits")
        if _DIGEST_RE.fullmatch(self.sha256) is None:
            raise ValueError("joined FARS member SHA-256 must be lowercase hexadecimal")

    def as_dict(self) -> dict[str, object]:
        return {
            "archive_path": self.archive_path,
            "name": self.name,
            "uncompressed_size": self.uncompressed_size,
            "crc32": self.crc32,
            "sha256": self.sha256,
        }


@dataclass(frozen=True)
class FarsJoinedRawBatch:
    accident_rows: tuple[Mapping[str, str], ...]
    person_rows: tuple[Mapping[str, str], ...]
    input_sha256: str
    accident_sha256: str
    person_sha256: str
    accident_member: FarsMemberDescriptor
    person_member: FarsMemberDescriptor
    year_contract: FarsYearContract

    def __post_init__(self) -> None:
        if any(
            _DIGEST_RE.fullmatch(value) is None
            for value in (self.input_sha256, self.accident_sha256, self.person_sha256)
        ):
            raise ValueError("joined FARS digests must be lowercase SHA-256 values")
        if not isinstance(self.accident_member, FarsMemberDescriptor) or not isinstance(
            self.person_member, FarsMemberDescriptor
        ):
            raise TypeError("joined FARS members must have verified descriptors")
        if not isinstance(self.year_contract, FarsYearContract):
            raise TypeError("joined FARS batch requires an immutable year contract")
        if self.accident_member.name.casefold() != "accident.csv":
            raise ValueError("joined FARS accident descriptor names the wrong table")
        if self.person_member.name.casefold() != "person.csv":
            raise ValueError("joined FARS person descriptor names the wrong table")
        if self.accident_member.archive_path == self.person_member.archive_path:
            raise ValueError("joined FARS table descriptors must identify distinct members")
        if (
            self.accident_sha256 != self.accident_member.sha256
            or self.person_sha256 != self.person_member.sha256
        ):
            raise ValueError("joined FARS member descriptors do not match table digests")
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
    accident_member: FarsMemberDescriptor
    person_member: FarsMemberDescriptor
    records_read: int
    records_accepted: int
    cases_joined: int
    records_excluded_with_rejected_crash: int
    cases_excluded_with_rejected_crash: int
    rejection_reasons: Mapping[str, int]
    semantic_regime_id: str = "fars_per_typ_2022_2024_v1"

    def __post_init__(self) -> None:
        reasons = MappingProxyType(dict(sorted(self.rejection_reasons.items())))
        if any(
            _DIGEST_RE.fullmatch(value) is None
            for value in (self.input_sha256, self.accident_sha256, self.person_sha256)
        ):
            raise ValueError("joined FARS provenance digests must be lowercase SHA-256 values")
        if not isinstance(self.accident_member, FarsMemberDescriptor) or not isinstance(
            self.person_member, FarsMemberDescriptor
        ):
            raise TypeError("joined FARS provenance requires member descriptors")
        if (
            self.accident_member.name.casefold() != "accident.csv"
            or self.person_member.name.casefold() != "person.csv"
            or self.accident_member.archive_path == self.person_member.archive_path
        ):
            raise ValueError("joined FARS provenance member identities are invalid")
        if (
            self.accident_sha256 != self.accident_member.sha256
            or self.person_sha256 != self.person_member.sha256
        ):
            raise ValueError("joined FARS provenance member digests are inconsistent")
        contract = fars_year_contract(self.dataset_year)
        if self.semantic_regime_id != contract.semantic_regime_id:
            raise ValueError("joined FARS person semantic regime does not match dataset year")
        counts = (
            self.records_read,
            self.records_accepted,
            self.cases_joined,
            self.records_excluded_with_rejected_crash,
            self.cases_excluded_with_rejected_crash,
        )
        if any(
            isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in counts
        ):
            raise ValueError("joined FARS person accounting values must be nonnegative integers")
        if self.records_accepted + self.records_excluded_with_rejected_crash != self.records_read:
            raise ValueError("joined FARS person accounting must cover every record")
        if any(
            not isinstance(key, str)
            or not key
            or isinstance(value, bool)
            or not isinstance(value, int)
            or value < 1
            for key, value in reasons.items()
        ):
            raise ValueError("joined FARS person rejection accounting is invalid")
        if sum(reasons.values()) != self.records_excluded_with_rejected_crash:
            raise ValueError("joined FARS person rejection reasons must cover excluded records")
        object.__setattr__(self, "rejection_reasons", reasons)

    def as_dict(self) -> dict[str, object]:
        return {
            "mapping_version": self.mapping_version,
            "dataset_year": self.dataset_year,
            "input_sha256": self.input_sha256,
            "accident_sha256": self.accident_sha256,
            "person_sha256": self.person_sha256,
            "accident_member": self.accident_member.as_dict(),
            "person_member": self.person_member.as_dict(),
            "records_read": self.records_read,
            "records_accepted": self.records_accepted,
            "cases_joined": self.cases_joined,
            "records_excluded_with_rejected_crash": self.records_excluded_with_rejected_crash,
            "cases_excluded_with_rejected_crash": self.cases_excluded_with_rejected_crash,
            "rejection_reasons": dict(self.rejection_reasons),
        }


@dataclass(frozen=True)
class FarsJurisdictionSummary:
    """Source-native crash jurisdiction retained for private coarse projections."""

    source_record_id: str
    state_code: str
    county_code: str
    county_status: str
    county_code_system: str = FARS_COUNTY_CODE_SYSTEM

    def __post_init__(self) -> None:
        identity = re.fullmatch(r"^(202[0-4]):[1-9][0-9]*$", self.source_record_id, re.ASCII)
        if identity is None:
            raise ValueError("FARS jurisdiction source identity is invalid")
        if re.fullmatch(r"^[1-9][0-9]?$", self.state_code, re.ASCII) is None:
            raise ValueError("FARS jurisdiction state code is invalid")
        if re.fullmatch(r"^[0-9]{3}$", self.county_code, re.ASCII) is None:
            raise ValueError("FARS jurisdiction county code is invalid")
        expected_status = {
            "000": "not_applicable",
            "997": "other",
            "998": "not_reported",
            "999": "unknown",
        }.get(self.county_code, "reported")
        if self.county_status != expected_status:
            raise ValueError("FARS jurisdiction county status is invalid")
        expected_code_system = f"nhtsa_fars_gsa_{identity.group(1)}"
        if self.county_code_system != expected_code_system:
            raise ValueError("FARS jurisdiction county code system is invalid")

    def as_dict(self) -> dict[str, str]:
        return {
            "source_record_id": self.source_record_id,
            "state_code": self.state_code,
            "county_code": self.county_code,
            "county_status": self.county_status,
            "county_code_system": self.county_code_system,
        }


@dataclass(frozen=True)
class FarsModeSummary:
    source_record_id: str
    involved_modes: tuple[str, ...]
    fatality_modes: tuple[str, ...]
    involved_person_count_by_mode: Mapping[str, int]
    fatality_count_by_mode: Mapping[str, int]
    jurisdiction: FarsJurisdictionSummary | None = None

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
        if self.jurisdiction is not None and not isinstance(
            self.jurisdiction, FarsJurisdictionSummary
        ):
            raise TypeError("FARS mode summary jurisdiction is invalid")

    def as_dict(self) -> dict[str, object]:
        return {
            "source_record_id": self.source_record_id,
            "involved_modes": list(self.involved_modes),
            "fatality_modes": list(self.fatality_modes),
            "involved_person_count_by_mode": dict(self.involved_person_count_by_mode),
            "fatality_count_by_mode": dict(self.fatality_count_by_mode),
        }


def _member(archive: zipfile.ZipFile, basename: str) -> zipfile.ZipInfo:
    matches: list[zipfile.ZipInfo] = []
    for member in archive.infolist():
        original = getattr(member, "orig_filename", member.filename)
        if original != member.filename:
            raise ValueError("joined FARS member path is unsafe or noncanonical")
        if member.is_dir():
            if not member.filename.endswith("/"):
                raise ValueError("joined FARS member path is unsafe or noncanonical")
            _canonical_archive_path(member.filename[:-1])
            continue
        path = _canonical_archive_path(member.filename)
        if path.rsplit("/", 1)[-1].casefold() == basename:
            matches.append(member)
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


def _descriptor(
    member: zipfile.ZipInfo, *, size: int, crc32: int, sha256: str
) -> FarsMemberDescriptor:
    if size != member.file_size or crc32 != member.CRC:
        raise ValueError("joined FARS member content does not match ZIP metadata")
    return FarsMemberDescriptor(
        archive_path=member.filename,
        name=member.filename.rsplit("/", 1)[-1],
        uncompressed_size=size,
        crc32=f"{crc32:08x}",
        sha256=sha256,
    )


def _hash_member(archive: zipfile.ZipFile, member: zipfile.ZipInfo) -> FarsMemberDescriptor:
    digest = hashlib.sha256()
    crc32 = 0
    total = 0
    with archive.open(member) as stream:
        while block := stream.read(1024 * 1024):
            total += len(block)
            if total > _MAX_MEMBER_BYTES:
                raise ValueError("joined FARS accident.csv exceeds its safety limit")
            digest.update(block)
            crc32 = zlib.crc32(block, crc32)
    return _descriptor(
        member,
        size=total,
        crc32=crc32 & 0xFFFFFFFF,
        sha256=digest.hexdigest(),
    )


class _HashingReader(io.RawIOBase):
    def __init__(self, stream: Any) -> None:
        self._stream = stream
        self.digest = hashlib.sha256()
        self.crc32 = 0
        self.total = 0

    def readable(self) -> bool:
        return True

    def readinto(self, buffer: Any) -> int:
        count = cast(int, self._stream.readinto(buffer))
        if count:
            self.digest.update(memoryview(buffer)[:count])
            self.crc32 = zlib.crc32(memoryview(buffer)[:count], self.crc32)
            self.total += count
            if self.total > _MAX_MEMBER_BYTES:
                raise ValueError("joined FARS person.csv exceeds its safety limit")
        return count


def _person_rows(
    stream: io.TextIOBase,
    *,
    row_cap: int,
) -> tuple[Mapping[str, str], ...]:
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
        if len(rows) >= row_cap:
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
    archive: zipfile.ZipFile,
    member: zipfile.ZipInfo,
    *,
    contract: FarsYearContract,
) -> tuple[tuple[Mapping[str, str], ...], FarsMemberDescriptor]:
    with archive.open(member) as compressed:
        hashing = _HashingReader(compressed)
        with (
            io.BufferedReader(hashing) as buffered,
            io.TextIOWrapper(buffered, encoding=contract.person_encoding, newline="") as text,
        ):
            rows = _person_rows(text, row_cap=contract.person_row_cap)
        descriptor = _descriptor(
            member,
            size=hashing.total,
            crc32=hashing.crc32 & 0xFFFFFFFF,
            sha256=hashing.digest.hexdigest(),
        )
        return rows, descriptor


def read_joined_export_bytes(payload: bytes, *, expected_year: int = 2024) -> FarsJoinedRawBatch:
    """Read one bounded ZIP under the legacy/replay-compatible year contract."""
    if not isinstance(payload, bytes):
        raise TypeError("joined FARS export must be bytes")
    if len(payload) > _MAX_INPUT_BYTES:
        raise ValueError("joined FARS export exceeds its safety limit")
    contract = fars_year_contract(expected_year)
    if not zipfile.is_zipfile(io.BytesIO(payload)):
        raise ValueError("joined FARS export must be a ZIP archive")
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        if len(archive.infolist()) > _MAX_MEMBERS:
            raise ValueError("joined FARS ZIP contains too many members")
        accident_member = _member(archive, contract.accident_member)
        person_member = _member(archive, contract.person_member)
        if accident_member.file_size + person_member.file_size > _MAX_EXPANDED_BYTES:
            raise ValueError("joined FARS selected members exceed the expansion safety limit")
        accident_descriptor = _hash_member(archive, accident_member)
        person_rows, person_descriptor = _read_person_member(
            archive,
            person_member,
            contract=contract,
        )
    crash_batch = read_export_bytes(
        payload,
        encoding=contract.accident_encoding,
        row_cap=contract.accident_row_cap,
    )
    if any(
        _DIGITS_RE.fullmatch(row.get("YEAR", "")) is None or int(row["YEAR"]) != contract.year
        for row in crash_batch.rows
    ):
        raise ValueError("joined FARS accident year does not match its fixed-year contract")
    return FarsJoinedRawBatch(
        accident_rows=crash_batch.rows,
        person_rows=person_rows,
        input_sha256=hashlib.sha256(payload).hexdigest(),
        accident_sha256=accident_descriptor.sha256,
        person_sha256=person_descriptor.sha256,
        accident_member=accident_descriptor,
        person_member=person_descriptor,
        year_contract=contract,
    )


def read_pinned_joined_export_bytes(payload: bytes, *, expected_year: int) -> FarsJoinedRawBatch:
    """Read a fixed-year ZIP only after exact reviewed package identity validation."""
    if not isinstance(payload, bytes):
        raise TypeError("joined FARS export must be bytes")
    if len(payload) > _MAX_INPUT_BYTES:
        raise ValueError("joined FARS export exceeds its safety limit")
    fars_year_contract(expected_year).validate_raw_package(payload)
    return read_joined_export_bytes(payload, expected_year=expected_year)


def _integer(row: Mapping[str, str], key: str, *, positive: bool = False) -> int:
    value = row.get(key, "")
    if _DIGITS_RE.fullmatch(value) is None:
        raise ValueError(f"invalid FARS person {key}")
    result = int(value)
    if positive and result < 1:
        raise ValueError(f"invalid FARS person {key}")
    return result


def _person_type_domain(semantic_regime_id: str) -> tuple[set[int], set[int]]:
    if semantic_regime_id == "fars_union_legacy_v1":
        return set(range(1, 14)) | {19}, {4, 8, 10, 11, 12, 13}
    if semantic_regime_id == "fars_per_typ_2020_2021_v1":
        return {1, 2, 3, 4, 5, 6, 7, 9, 10, 11, 12, 13}, {4, 10, 11, 12, 13}
    if semantic_regime_id == "fars_per_typ_2022_2024_v1":
        return set(range(1, 11)) | {19}, {4, 8, 10}
    raise ValueError("unsupported FARS person semantic regime")


def _mode(row: Mapping[str, str], *, semantic_regime_id: str) -> str:
    person_type = _integer(row, "PER_TYP")
    allowed_types, other_types = _person_type_domain(semantic_regime_id)
    if person_type not in allowed_types:
        raise ValueError("FARS person PER_TYP is invalid for its semantic regime")
    if person_type == 5:
        return "pedestrian"
    if person_type in {6, 7}:
        return "pedalcyclist"
    if person_type in other_types:
        return "other_road_user"
    if person_type == 19:
        return "unknown"
    body = row.get("BODY_TYP", "")
    if not body or body in {"98", "99"}:
        return "unknown"
    if _DIGITS_RE.fullmatch(body) is None or not 1 <= int(body) <= 99:
        raise ValueError("invalid FARS person BODY_TYP")
    return "motorcyclist" if 80 <= int(body) <= 89 else "motor_vehicle_occupant"


def _accident_index(
    batch: FarsJoinedRawBatch,
) -> tuple[dict[str, tuple[str, int, int, FarsJurisdictionSummary | None]], int]:
    accident: dict[str, tuple[str, int, int, FarsJurisdictionSummary | None]] = {}
    years: set[int] = set()
    county_presence = {"COUNTY" in row for row in batch.accident_rows}
    if len(county_presence) > 1:
        raise ValueError("joined FARS accident rows inconsistently provide COUNTY")
    has_county = county_presence == {True}
    for row in batch.accident_rows:
        case = str(_integer(row, "ST_CASE", positive=True))
        if case in accident:
            raise ValueError("duplicate FARS accident case")
        year = _integer(row, "YEAR", positive=True)
        years.add(year)
        state = str(_integer(row, "STATE", positive=True))
        jurisdiction: FarsJurisdictionSummary | None = None
        if has_county:
            county = _integer(row, "COUNTY")
            if county > 999:
                raise ValueError("invalid FARS accident COUNTY")
            county_code = f"{county:03d}"
            jurisdiction = FarsJurisdictionSummary(
                source_record_id=f"{year}:{case}",
                state_code=state,
                county_code=county_code,
                county_status={
                    "000": "not_applicable",
                    "997": "other",
                    "998": "not_reported",
                    "999": "unknown",
                }.get(county_code, "reported"),
                county_code_system=batch.year_contract.county_code_system,
            )
        accident[case] = (state, _integer(row, "FATALS"), year, jurisdiction)
    if len(years) != 1:
        raise ValueError("joined FARS export must contain exactly one dataset year")
    year = years.pop()
    if year != batch.year_contract.year:
        raise ValueError("joined FARS dataset year does not match its fixed-year contract")
    return accident, year


def _person_index(  # noqa: C901 - whole-batch relational checks remain auditable together
    batch: FarsJoinedRawBatch,
    *,
    legacy_mode_semantics: bool = False,
) -> tuple[
    dict[str, dict[str, Any]],
    dict[str, FarsJurisdictionSummary | None],
    int,
]:
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
        semantic_regime_id = (
            "fars_union_legacy_v1"
            if legacy_mode_semantics
            else batch.year_contract.semantic_regime_id
        )
        mode = _mode(row, semantic_regime_id=semantic_regime_id)
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
    return joined, {case: values[3] for case, values in accident.items()}, year


def collect_joined(
    batch: FarsJoinedRawBatch,
    *,
    release_status: str = "unspecified",
    legacy_mode_semantics: bool = False,
) -> tuple[
    list[dict[str, Any]],
    list[FarsModeSummary],
    OutcomeProvenance,
    PersonJoinProvenance,
]:
    """Map crash outcomes and attach deterministic crash-level person mode summaries."""
    joined, jurisdictions, year = _person_index(
        batch,
        legacy_mode_semantics=legacy_mode_semantics,
    )
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
                jurisdiction=jurisdictions[case],
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
        accident_member=batch.accident_member,
        person_member=batch.person_member,
        records_read=len(batch.person_rows),
        records_accepted=accepted_person_records,
        cases_joined=len(emitted_cases),
        records_excluded_with_rejected_crash=excluded_person_records,
        cases_excluded_with_rejected_crash=len(excluded_cases),
        rejection_reasons=reasons,
        semantic_regime_id=batch.year_contract.semantic_regime_id,
    )
    return outcomes, summaries, crash_provenance, provenance
