"""Known-answer and adversarial tests for the FARS person-mode join."""

from __future__ import annotations

import dataclasses
import hashlib
import io
import json
import zipfile
import zlib
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from nearmiss.adapters import fars_joined
from nearmiss.adapters.fars_joined import (
    collect_joined,
    read_joined_export_bytes,
)

ROOT = Path(__file__).resolve().parents[1]
ACCIDENT = (
    (ROOT / "tests" / "fixtures" / "fars" / "accident.csv")
    .read_bytes()
    .replace(b",2023,", b",2024,")
)
HEADER = "STATE,ST_CASE,VEH_NO,PER_NO,PER_TYP,INJ_SEV,BODY_TYP\n"
ROWS = [
    "6,100001,1,1,1,4,4",
    "6,100001,0,1,5,2,",
    "6,100002,1,1,1,4,80",
    "6,100002,0,1,6,4,",
    "6,100003,0,1,5,4,",
]


def _person(rows: list[str] | None = None) -> bytes:
    return (HEADER + "\n".join(ROWS if rows is None else rows) + "\n").encode()


def _archive(
    person: bytes | None = None,
    *,
    duplicate: str | None = None,
    accident: bytes = ACCIDENT,
    accident_name: str = "FARS/accident.csv",
    person_name: str = "FARS/person.csv",
) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(accident_name, accident)
        archive.writestr(person_name, _person() if person is None else person)
        if duplicate == "person":
            archive.writestr("other/PERSON.CSV", _person())
        if duplicate == "accident":
            archive.writestr("other/ACCIDENT.CSV", ACCIDENT)
    return buffer.getvalue()


def test_reads_hashes_and_joins_deterministic_mode_summaries() -> None:
    payload = _archive()
    batch = read_joined_export_bytes(payload)
    outcomes, summaries, crash_provenance, join_provenance = collect_joined(
        batch, release_status="final"
    )
    assert batch.input_sha256 == hashlib.sha256(payload).hexdigest()
    assert batch.accident_sha256 == hashlib.sha256(ACCIDENT).hexdigest()
    assert batch.person_sha256 == hashlib.sha256(_person()).hexdigest()
    assert batch.accident_member.as_dict() == {
        "archive_path": "FARS/accident.csv",
        "name": "accident.csv",
        "uncompressed_size": len(ACCIDENT),
        "crc32": f"{zlib.crc32(ACCIDENT):08x}",
        "sha256": hashlib.sha256(ACCIDENT).hexdigest(),
    }
    assert batch.person_member.as_dict() == {
        "archive_path": "FARS/person.csv",
        "name": "person.csv",
        "uncompressed_size": len(_person()),
        "crc32": f"{zlib.crc32(_person()):08x}",
        "sha256": hashlib.sha256(_person()).hexdigest(),
    }
    assert crash_provenance.input_sha256 == batch.input_sha256
    assert join_provenance.records_read == 5
    assert join_provenance.records_accepted == 4
    assert join_provenance.cases_joined == 2
    assert join_provenance.dataset_year == 2024
    assert join_provenance.records_excluded_with_rejected_crash == 1
    assert join_provenance.cases_excluded_with_rejected_crash == 1
    assert join_provenance.rejection_reasons == {"parent_crash_rejected": 1}
    assert join_provenance.accident_member == batch.accident_member
    assert join_provenance.person_member == batch.person_member
    assert join_provenance.as_dict()["person_member"] == batch.person_member.as_dict()

    first, second = summaries
    assert first.involved_modes == ("motor_vehicle_occupant", "pedestrian")
    assert first.fatality_modes == ("motor_vehicle_occupant",)
    assert first.involved_person_count_by_mode["pedestrian"] == 1
    assert first.fatality_count_by_mode["pedestrian"] == 0
    assert second.involved_modes == ("motorcyclist", "pedalcyclist")
    assert second.fatality_modes == ("motorcyclist", "pedalcyclist")
    assert all(
        set(outcome).isdisjoint({"involved_modes", "fatality_modes"}) for outcome in outcomes
    )
    schema = json.loads((ROOT / "schema" / "official-outcome.schema.json").read_text())
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    assert all(not list(validator.iter_errors(outcome)) for outcome in outcomes)


def test_person_row_order_does_not_change_outcomes() -> None:
    first = collect_joined(read_joined_export_bytes(_archive()))[0]
    second = collect_joined(read_joined_export_bytes(_archive(_person(list(reversed(ROWS))))))[0]
    assert first == second


def test_source_coded_unknown_and_died_prior_are_involved_but_not_fatal() -> None:
    rows = ROWS.copy()
    rows[0] = "6,100001,1,1,9,4,99"
    rows[1] = "6,100001,0,2,5,6,"
    rows[0] = "6,100001,0,1,19,4,"
    summaries = collect_joined(read_joined_export_bytes(_archive(_person(rows))))[1]
    assert summaries[0].involved_modes == ("pedestrian", "unknown")
    assert summaries[0].fatality_modes == ("unknown",)


@pytest.mark.parametrize(
    ("rows", "message"),
    [
        ([*ROWS, ROWS[0]], "duplicate FARS person identity"),
        ([row for row in ROWS if ",100003," not in row], "without person rows"),
        ([*ROWS, "6,999999,0,1,5,4,"], "orphan FARS person case"),
        ([ROWS[0].replace("6,100001", "7,100001"), *ROWS[1:]], "state does not match"),
        ([ROWS[0].replace(",4,4", ",3,4"), *ROWS[1:]], "fatal count does not match"),
        ([ROWS[0].replace(",1,1,1,", ",1,0,1,"), *ROWS[1:]], "invalid FARS person PER_NO"),
        ([ROWS[0].replace(",1,4,4", ",77,4,4"), *ROWS[1:]], "invalid FARS person PER_TYP"),
        ([ROWS[0].replace(",1,1,1,", ",0,1,1,"), *ROWS[1:]], "positive VEH_NO"),
        ([ROWS[1].replace(",0,1,5,", ",1,1,5,"), ROWS[0], *ROWS[2:]], "VEH_NO zero"),
    ],
)
def test_join_integrity_failures_are_closed(rows: list[str], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        collect_joined(read_joined_export_bytes(_archive(_person(rows))))


def test_requires_zip_with_exactly_one_of_each_table() -> None:
    with pytest.raises(ValueError, match="ZIP archive"):
        read_joined_export_bytes(ACCIDENT)
    for duplicate in ("accident", "person"):
        with pytest.raises(ValueError, match="exactly one"):
            read_joined_export_bytes(_archive(duplicate=duplicate))


def test_case_insensitive_table_names_preserve_exact_canonical_member_paths() -> None:
    batch = read_joined_export_bytes(
        _archive(
            accident_name="National/ACCIDENT.CSV",
            person_name="National/Person.CsV",
        )
    )
    assert batch.accident_member.archive_path == "National/ACCIDENT.CSV"
    assert batch.accident_member.name == "ACCIDENT.CSV"
    assert batch.person_member.archive_path == "National/Person.CsV"
    assert batch.person_member.name == "Person.CsV"


@pytest.mark.parametrize(
    "member_path",
    [
        "/FARS/person.csv",
        "C:/FARS/person.csv",
        "FARS\\person.csv",
        "FARS/../person.csv",
        "FARS/./person.csv",
        "FARS//person.csv",
        "FARS/%70erson.csv",
        "FARS/\x01person.csv",
    ],
)
def test_unsafe_or_ambiguous_member_paths_are_rejected(member_path: str) -> None:
    with pytest.raises(ValueError, match="unsafe or noncanonical"):
        read_joined_export_bytes(_archive(person_name=member_path))


def test_member_descriptors_and_batch_digest_binding_are_fail_closed() -> None:
    batch = read_joined_export_bytes(_archive())
    with pytest.raises(ValueError, match="descriptors do not match"):
        dataclasses.replace(batch, person_sha256="a" * 64)
    with pytest.raises(ValueError, match="CRC32"):
        dataclasses.replace(batch.person_member, crc32="ABCDEF00")
    with pytest.raises(ValueError, match="size"):
        dataclasses.replace(batch.accident_member, uncompressed_size=0)


def test_person_provenance_validates_descriptor_and_rejection_accounting() -> None:
    batch = read_joined_export_bytes(_archive())
    provenance = collect_joined(batch)[3]
    with pytest.raises(ValueError, match="member digests are inconsistent"):
        dataclasses.replace(provenance, person_sha256="a" * 64)
    with pytest.raises(ValueError, match="rejection reasons must cover"):
        dataclasses.replace(provenance, rejection_reasons={})


def test_missing_columns_and_compression_bombs_are_rejected() -> None:
    with pytest.raises(ValueError, match="missing required columns"):
        read_joined_export_bytes(_archive(b"STATE,ST_CASE\n6,1\n"))
    with pytest.raises(ValueError, match="suspicious compression ratio"):
        read_joined_export_bytes(_archive(b"0" * 1_000_000))


def test_batch_rows_are_immutable() -> None:
    batch = read_joined_export_bytes(_archive())
    with pytest.raises(TypeError):
        batch.person_rows[0]["PER_TYP"] = "5"  # type: ignore[index]


def test_person_row_count_is_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("nearmiss.adapters.fars_joined._MAX_PERSON_ROWS", 1)
    with pytest.raises(ValueError, match="row-count safety limit"):
        read_joined_export_bytes(_archive())


@pytest.mark.parametrize("person_type", ["11", "12", "13"])
def test_documented_other_road_user_codes_are_supported(person_type: str) -> None:
    rows = ROWS.copy()
    rows[1] = f"6,100001,0,1,{person_type},2,"
    summaries = collect_joined(read_joined_export_bytes(_archive(_person(rows))))[1]
    assert summaries[0].involved_modes == ("motor_vehicle_occupant", "other_road_user")


@pytest.mark.parametrize("body", ["", "98", "99"])
def test_unknown_occupant_body_is_not_misclassified(body: str) -> None:
    rows = ROWS.copy()
    rows[0] = f"6,100001,1,1,9,4,{body}"
    summaries = collect_joined(read_joined_export_bytes(_archive(_person(rows))))[1]
    assert summaries[0].fatality_modes == ("unknown",)


def test_person_mapping_rejects_non_2024_dataset() -> None:
    archive = _archive(accident=ACCIDENT.replace(b",2024,", b",2023,"))
    with pytest.raises(ValueError, match="supports dataset year 2024 only"):
        collect_joined(read_joined_export_bytes(archive))


def test_release_status_is_validated_by_the_crash_adapter() -> None:
    batch = read_joined_export_bytes(_archive())
    with pytest.raises(ValueError, match="release_status must not be empty"):
        collect_joined(batch, release_status="  ")


def test_person_row_limit_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(fars_joined, "_MAX_PERSON_ROWS", 1)
    with pytest.raises(ValueError, match="row-count safety limit"):
        read_joined_export_bytes(_archive())
