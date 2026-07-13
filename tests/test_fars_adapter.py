"""Known-answer tests for the offline FARS crash-level adapter."""

from __future__ import annotations

import io
import math
import uuid
import zipfile
from pathlib import Path

import pytest

import nearmiss.adapters.fars as fars
from nearmiss.adapters.fars import (
    FarsAdapter,
    FarsRawBatch,
    collect,
    collect_v1,
    fars_outcome_id,
    load_export_bytes,
    read_export,
    read_export_bytes,
    validate_fars_distribution_url,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "fars" / "accident.csv"


def test_maps_valid_rows_and_names_limitations() -> None:
    outcomes, provenance = FarsAdapter().parse(FIXTURE, release_status="final")
    assert len(outcomes) == 2
    assert outcomes[0]["occurred_time_local"] == "17:30"
    assert "occurred_time_local" not in outcomes[1]
    assert outcomes[1]["fatality_count"] == 2
    assert "involved_modes" not in outcomes[0]
    assert provenance.dataset_years == (2023,)
    assert provenance.release_status == "final"
    assert provenance.rejection_reasons == {"invalid_location": 1}
    assert len(provenance.input_sha256 or "") == 64


def test_ids_and_order_are_stable() -> None:
    adapter = FarsAdapter()
    first, _ = adapter.parse(FIXTURE)
    second, _ = adapter.parse(FIXTURE)
    assert first == second
    assert [row["source_record_id"] for row in first] == ["2023:100001", "2023:100002"]
    assert first[0]["id"] == fars_outcome_id(2023, "100001")
    assert uuid.UUID(first[0]["id"]).version == 5


def test_current_collect_wrapper_preserves_named_v1_mapping() -> None:
    batch = read_export(FIXTURE)
    assert collect(batch.rows, input_sha256=batch.input_sha256) == collect_v1(
        batch.rows,
        input_sha256=batch.input_sha256,
    )


def test_direct_collect_preserves_legacy_release_status_behavior() -> None:
    assert collect([], release_status=" final ")[1].release_status == " final "
    assert collect([], release_status="  ")[1].release_status == "  "


def test_year_scoped_case_ids_are_globally_qualified() -> None:
    row = {
        "ST_CASE": "100001",
        "YEAR": "2023",
        "MONTH": "1",
        "DAY": "1",
        "LATITUDE": "38",
        "LONGITUD": "-121",
        "FATALS": "1",
    }
    outcomes, _ = collect([row, {**row, "YEAR": "2024"}])
    assert [outcome["source_record_id"] for outcome in outcomes] == [
        "2023:100001",
        "2024:100001",
    ]
    assert len({outcome["id"] for outcome in outcomes}) == 2


def test_bbox_is_accounted_for_as_a_rejection() -> None:
    outcomes, provenance = FarsAdapter().parse(FIXTURE, bbox=(-121.745, 38.54, -121.735, 38.55))
    assert [row["source_record_id"] for row in outcomes] == ["2023:100001"]
    assert provenance.rejection_reasons == {"invalid_location": 1, "outside_bbox": 1}


def test_invalid_rows_have_specific_reasons() -> None:
    base = {
        "ST_CASE": "1",
        "YEAR": "2023",
        "MONTH": "1",
        "DAY": "1",
        "LATITUDE": "38",
        "LONGITUD": "-121",
        "FATALS": "1",
    }
    rows = [
        {**base, "ST_CASE": ""},
        {**base, "ST_CASE": "garbage"},
        {**base, "YEAR": "1974"},
        {**base, "MONTH": "13"},
        {**base, "LONGITUD": "999.999999"},
        {**base, "FATALS": "0"},
    ]
    outcomes, provenance = collect(rows)
    assert not outcomes
    assert provenance.rejection_reasons == {
        "invalid_identity": 3,
        "invalid_date": 1,
        "invalid_location": 1,
        "invalid_fatality_count": 1,
    }


def test_all_rows_for_duplicate_source_case_are_rejected_deterministically() -> None:
    row = {
        "ST_CASE": "1",
        "YEAR": "2023",
        "MONTH": "1",
        "DAY": "1",
        "LATITUDE": "38",
        "LONGITUD": "-121",
        "FATALS": "1",
    }
    outcomes, provenance = collect([row, row])
    assert not outcomes
    assert provenance.rejection_reasons == {"duplicate_source_record": 2}
    assert provenance.records_accepted + sum(provenance.rejection_reasons.values()) == 2


def test_reads_case_insensitive_nested_zip_member(tmp_path: Path) -> None:
    archive_path = tmp_path / "fars.zip"
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("CSV/ACCIDENT.CSV", FIXTURE.read_bytes())
    archive_path.write_bytes(buffer.getvalue())
    batch = read_export(archive_path)
    assert len(batch.rows) == 3
    assert len(batch.input_sha256) == 64


def test_path_and_byte_export_boundaries_are_equivalent() -> None:
    payload = load_export_bytes(FIXTURE)
    assert read_export(FIXTURE) == read_export_bytes(payload)


def test_load_export_bytes_is_bounded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "too-large.csv"
    path.write_bytes(b"12345")
    monkeypatch.setattr(fars, "_MAX_INPUT_BYTES", 4)
    with pytest.raises(ValueError, match="safety limit"):
        load_export_bytes(path)


def test_operator_export_limit_is_applied_before_read(tmp_path: Path) -> None:
    path = tmp_path / "too-large.csv"
    path.write_bytes(b"12345")
    with pytest.raises(ValueError, match="4-byte safety limit"):
        load_export_bytes(path, limit=4)


def test_builtin_export_cap_cannot_be_raised_by_operator(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "too-large.csv"
    path.write_bytes(b"12345")
    monkeypatch.setattr(fars, "_MAX_INPUT_BYTES", 4)
    with pytest.raises(ValueError, match="4-byte safety limit"):
        load_export_bytes(path, limit=100)


@pytest.mark.parametrize("limit", [0, -1])
def test_operator_export_limit_must_be_positive(tmp_path: Path, limit: int) -> None:
    path = tmp_path / "export.csv"
    path.write_bytes(b"1")
    with pytest.raises(ValueError, match="must be positive"):
        load_export_bytes(path, limit=limit)


@pytest.mark.parametrize("limit", [True, 1.5, "1"])
def test_operator_export_limit_must_be_an_integer(tmp_path: Path, limit: object) -> None:
    path = tmp_path / "export.csv"
    path.write_bytes(b"1")
    with pytest.raises(TypeError, match="must be an integer"):
        load_export_bytes(path, limit=limit)  # type: ignore[arg-type]


def test_read_export_bytes_requires_immutable_bytes() -> None:
    with pytest.raises(TypeError, match="must be bytes"):
        read_export_bytes(bytearray(FIXTURE.read_bytes()))  # type: ignore[arg-type]


def test_export_decoder_requires_an_explicit_supported_encoding() -> None:
    lines = FIXTURE.read_text(encoding="utf-8").splitlines()
    payload = (
        "\n".join([f"{lines[0]},CITYNAME", *[f"{line},LA CAÑADA" for line in lines[1:]]]) + "\n"
    ).encode("cp1252")
    assert len(read_export_bytes(payload, encoding="cp1252").rows) == 3
    with pytest.raises(ValueError, match="explicitly supported"):
        read_export_bytes(payload, encoding="latin-1")
    with pytest.raises(ValueError, match="row-count safety limit"):
        read_export_bytes(payload, encoding="cp1252", row_cap=1)
    with pytest.raises(ValueError, match="positive integer"):
        read_export_bytes(payload, encoding="cp1252", row_cap=True)


def test_validates_canonical_nhtsa_fars_distribution_url() -> None:
    url = "https://static.nhtsa.gov/nhtsa/downloads/FARS/2023/National/FARS2023.zip"
    assert validate_fars_distribution_url(url) == url
    assert validate_fars_distribution_url(url, expected_year=2023) == url


@pytest.mark.parametrize(
    "url",
    [
        "http://static.nhtsa.gov/nhtsa/downloads/FARS/2023/data.zip",
        "https://evil.test/nhtsa/downloads/FARS/2023/data.zip",
        "https://static.nhtsa.gov.evil.test/nhtsa/downloads/FARS/2023/data.zip",
        "https://user:secret@static.nhtsa.gov/nhtsa/downloads/FARS/2023/data.zip",
        "https://static.nhtsa.gov:443/nhtsa/downloads/FARS/2023/data.zip",
        "https://static.nhtsa.gov:bad/nhtsa/downloads/FARS/2023/data.zip",
        "https://static.nhtsa.gov/nhtsa/downloads/FARS/2023/data.zip?token=secret",
        "https://static.nhtsa.gov/nhtsa/downloads/FARS/2023/data.zip#fragment",
        "https://static.nhtsa.gov/nhtsa/downloads/FARS/2023/../other/data.zip",
        "https://static.nhtsa.gov/nhtsa/downloads/FARS/2023/%2e%2e/other/data.zip",
        "https://static.nhtsa.gov/nhtsa/downloads/FARS/2023//National/data.zip",
        "https://static.nhtsa.gov/nhtsa/downloads/FARS/2023/National\\data.zip",
        "https://static.nhtsa.gov/other/data.zip",
        "https://static.nhtsa.gov/nhtsa/downloads/FARS/National/data.zip",
        "https://static.nhtsa.gov/nhtsa/downloads/FARS/2023/readme.txt",
    ],
)
def test_rejects_noncanonical_fars_distribution_urls(url: str) -> None:
    with pytest.raises(ValueError, match="FARS distribution URL"):
        validate_fars_distribution_url(url)


def test_distribution_url_year_must_match_expected_year() -> None:
    url = "https://static.nhtsa.gov/nhtsa/downloads/FARS/2023/National/data.zip"
    with pytest.raises(ValueError, match="match expected_year"):
        validate_fars_distribution_url(url, expected_year=2024)


@pytest.mark.parametrize(
    ("year", "case_id"),
    [(1974, "1"), (2023, "0"), (2023, "01"), (2023, "+1"), (2023, "abc")],
)
def test_fars_outcome_id_rejects_noncanonical_identity(year: int, case_id: str) -> None:
    with pytest.raises(ValueError, match="FARS"):
        fars_outcome_id(year, case_id)


def test_raw_batch_rows_are_immutable() -> None:
    batch = read_export(FIXTURE)
    with pytest.raises(TypeError):
        batch.rows[0]["YEAR"] = "1900"  # type: ignore[index]


def test_raw_batch_discards_unused_source_columns() -> None:
    batch = read_export(FIXTURE)
    assert set(batch.rows[0]) == {
        "STATE",
        "ST_CASE",
        "YEAR",
        "MONTH",
        "DAY",
        "HOUR",
        "MINUTE",
        "LATITUDE",
        "LONGITUD",
        "FATALS",
    }


def test_raw_batch_rejects_untraceable_digest() -> None:
    with pytest.raises(ValueError, match="SHA-256"):
        FarsRawBatch(rows=(), input_sha256="not-a-digest")


def test_missing_columns_fail_loudly(tmp_path: Path) -> None:
    path = tmp_path / "accident.csv"
    path.write_text("ST_CASE,YEAR\n1,2023\n", encoding="utf-8")
    with pytest.raises(ValueError, match="missing required column"):
        read_export(path)


def test_zip_must_have_one_accident_table(tmp_path: Path) -> None:
    path = tmp_path / "bad.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("readme.txt", "none")
    with pytest.raises(ValueError, match=r"exactly one accident\.csv"):
        read_export(path)


def test_zip_rejects_duplicate_case_insensitive_accident_tables(tmp_path: Path) -> None:
    path = tmp_path / "ambiguous.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("one/accident.csv", FIXTURE.read_bytes())
        archive.writestr("two/ACCIDENT.CSV", FIXTURE.read_bytes())
    with pytest.raises(ValueError, match=r"exactly one accident\.csv"):
        read_export(path)


def test_zip_rejects_suspiciously_compressed_accident_table(tmp_path: Path) -> None:
    path = tmp_path / "bomb.zip"
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("accident.csv", b"0" * 1_000_000)
    with pytest.raises(ValueError, match="suspicious ZIP compression ratio"):
        read_export(path)


@pytest.mark.parametrize(
    "raw",
    [b"not rows", bytearray(b"not rows"), memoryview(b"not rows"), {"YEAR": "2023"}, 3],
)
def test_parse_rejects_non_row_iterables(raw: object) -> None:
    with pytest.raises(TypeError, match="iterable of row mappings"):
        FarsAdapter().parse(raw)


def test_collect_rejects_non_mapping_rows() -> None:
    with pytest.raises(TypeError, match="row 1 must be a mapping"):
        collect(["not a mapping"])  # type: ignore[list-item]


@pytest.mark.parametrize(
    "bbox",
    [
        (-181.0, 0.0, 1.0, 1.0),
        (1.0, 0.0, -1.0, 1.0),
        (0.0, 2.0, 1.0, 1.0),
        (0.0, 0.0, math.inf, 1.0),
    ],
)
def test_invalid_bbox_fails_loudly(bbox: tuple[float, float, float, float]) -> None:
    with pytest.raises(ValueError, match="bbox"):
        collect([], bbox=bbox)


def test_dataset_years_describe_input_even_when_bbox_excludes_every_row() -> None:
    _, provenance = FarsAdapter().parse(FIXTURE, bbox=(-80.0, 40.0, -70.0, 45.0))
    assert provenance.dataset_years == (2023,)


def test_actual_fars_coordinate_sentinel_precision_is_rejected() -> None:
    row = {
        "ST_CASE": "1",
        "YEAR": "2024",
        "MONTH": "1",
        "DAY": "1",
        "LATITUDE": "77.77770000",
        "LONGITUD": "-121",
        "FATALS": "1",
    }
    outcomes, provenance = collect([row])
    assert not outcomes
    assert provenance.rejection_reasons == {"invalid_location": 1}


def test_release_status_must_be_a_nonempty_string() -> None:
    with pytest.raises(ValueError, match="release_status"):
        FarsAdapter().parse([], release_status="  ")


def test_programmatic_rows_have_no_source_byte_digest() -> None:
    _, provenance = FarsAdapter().parse([])
    assert provenance.input_sha256 is None
