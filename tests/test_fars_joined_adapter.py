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
    read_pinned_joined_export_bytes,
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


def _accident_with_counties(counties: tuple[str, str, str] = ("113", "997", "999")) -> bytes:
    lines = ACCIDENT.decode().splitlines()
    output = [lines[0].replace(",FATALS", ",COUNTY,FATALS")]
    for line, county in zip(lines[1:], counties, strict=True):
        values = line.split(",")
        values.insert(-1, county)
        output.append(",".join(values))
    return ("\n".join(output) + "\n").encode()


def _cp1252_accident_2020() -> bytes:
    lines = ACCIDENT.decode().replace(",2024,", ",2020,").splitlines()
    output = [f"{lines[0]},CITYNAME"]
    output.extend(f"{line},LA CAÑADA" for line in lines[1:])
    return ("\n".join(output) + "\n").encode("cp1252")


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


def test_retains_source_native_county_jurisdiction_when_official_column_is_present() -> None:
    summaries = collect_joined(
        read_joined_export_bytes(_archive(accident=_accident_with_counties()))
    )[1]
    assert summaries[0].jurisdiction is not None
    assert summaries[0].jurisdiction.as_dict() == {
        "source_record_id": "2024:100001",
        "state_code": "6",
        "county_code": "113",
        "county_status": "reported",
        "county_code_system": "nhtsa_fars_gsa_2024",
    }
    assert summaries[1].jurisdiction is not None
    assert summaries[1].jurisdiction.county_status == "other"


def test_accounts_for_not_applicable_source_county_without_minting_an_identity() -> None:
    summaries = collect_joined(
        read_joined_export_bytes(_archive(accident=_accident_with_counties(("0", "113", "113"))))
    )[1]
    assert summaries[0].jurisdiction is not None
    assert summaries[0].jurisdiction.county_code == "000"
    assert summaries[0].jurisdiction.county_status == "not_applicable"


@pytest.mark.parametrize(("county", "message"), [("", "COUNTY"), ("1000", "COUNTY")])
def test_invalid_source_county_codes_fail_closed(county: str, message: str) -> None:
    accident = _accident_with_counties((county, "113", "113"))
    with pytest.raises(ValueError, match=message):
        collect_joined(read_joined_export_bytes(_archive(accident=accident)))


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
        ([ROWS[0].replace(",1,4,4", ",77,4,4"), *ROWS[1:]], "FARS person PER_TYP"),
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


def test_person_row_count_is_bounded() -> None:
    with pytest.raises(ValueError, match="row-count safety limit"):
        fars_joined._person_rows(io.StringIO(_person().decode()), row_cap=1)


@pytest.mark.parametrize("person_type", ["11", "12", "13"])
def test_early_regime_personal_conveyance_codes_are_supported(person_type: str) -> None:
    rows = ROWS.copy()
    rows[1] = f"6,100001,0,1,{person_type},2,"
    accident = ACCIDENT.replace(b",2024,", b",2021,")
    summaries = collect_joined(
        read_joined_export_bytes(
            _archive(_person(rows), accident=accident),
            expected_year=2021,
        )
    )[1]
    assert summaries[0].involved_modes == ("motor_vehicle_occupant", "other_road_user")


@pytest.mark.parametrize("person_type", ["8", "19"])
def test_early_regime_rejects_late_person_types(person_type: str) -> None:
    rows = ROWS.copy()
    rows[1] = f"6,100001,0,1,{person_type},2,"
    accident = ACCIDENT.replace(b",2024,", b",2021,")
    with pytest.raises(ValueError, match="semantic regime"):
        collect_joined(
            read_joined_export_bytes(
                _archive(_person(rows), accident=accident),
                expected_year=2021,
            )
        )


@pytest.mark.parametrize("person_type", ["11", "12", "13"])
def test_late_regime_rejects_early_personal_conveyance_codes(person_type: str) -> None:
    rows = ROWS.copy()
    rows[1] = f"6,100001,0,1,{person_type},2,"
    with pytest.raises(ValueError, match="semantic regime"):
        collect_joined(read_joined_export_bytes(_archive(_person(rows))))


@pytest.mark.parametrize("body", ["", "98", "99"])
def test_unknown_occupant_body_is_not_misclassified(body: str) -> None:
    rows = ROWS.copy()
    rows[0] = f"6,100001,1,1,9,4,{body}"
    summaries = collect_joined(read_joined_export_bytes(_archive(_person(rows))))[1]
    assert summaries[0].fatality_modes == ("unknown",)


def test_reader_rejects_dataset_year_mismatched_to_contract() -> None:
    archive = _archive(accident=ACCIDENT.replace(b",2024,", b",2023,"))
    with pytest.raises(ValueError, match="fixed-year contract"):
        read_joined_export_bytes(archive)


def test_pinned_reader_rejects_unreviewed_same_year_package_before_parsing() -> None:
    with pytest.raises(ValueError, match="raw archive identity"):
        read_pinned_joined_export_bytes(_archive(), expected_year=2024)


def test_person_mapping_supports_reviewed_2023_contract() -> None:
    archive = _archive(accident=ACCIDENT.replace(b",2024,", b",2023,"))
    outcomes, summaries, _crash, person = collect_joined(
        read_joined_export_bytes(archive, expected_year=2023)
    )
    assert person.dataset_year == 2023
    assert outcomes[0]["source_record_id"] == "2023:100001"
    assert summaries[0].source_record_id == "2023:100001"


def test_2020_contract_uses_strict_cp1252_accident_decoding() -> None:
    archive = _archive(accident=_cp1252_accident_2020())
    outcomes, summaries, _crash, person = collect_joined(
        read_joined_export_bytes(archive, expected_year=2020)
    )
    assert person.dataset_year == 2020
    assert outcomes[0]["source_record_id"] == "2020:100001"
    assert summaries[0].source_record_id == "2020:100001"


def test_release_status_is_validated_by_the_crash_adapter() -> None:
    batch = read_joined_export_bytes(_archive())
    with pytest.raises(ValueError, match="release_status must not be empty"):
        collect_joined(batch, release_status="  ")


def test_person_row_limit_fails_closed() -> None:
    with pytest.raises(ValueError, match="row-count safety limit"):
        fars_joined._person_rows(io.StringIO(_person().decode()), row_cap=1)
