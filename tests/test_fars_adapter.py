"""Known-answer tests for the offline FARS crash-level adapter."""

from __future__ import annotations

import io
import math
import zipfile
from pathlib import Path

import pytest

from nearmiss.adapters.fars import FarsAdapter, FarsRawBatch, collect, read_export

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
