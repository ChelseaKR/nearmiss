from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from nearmiss.__main__ import (
    _decode_outcome_artifact,
    _validate_fars_normalized_candidate,
    build_parser,
    main,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "fars" / "accident.csv"
URL = "https://static.nhtsa.gov/nhtsa/downloads/FARS/2023/National/FARS2023NationalCSV.zip"


def _zip_export(tmp_path: Path) -> Path:
    export = tmp_path / "fars-2023.zip"
    with zipfile.ZipFile(export, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("National/accident.csv", FIXTURE.read_bytes())
    return export


def _argv(export: Path, root: Path, *extra: str) -> list[str]:
    return [
        "ingest-fars",
        str(export),
        "--root",
        str(root),
        "--year",
        "2023",
        "--release-status",
        "final",
        "--distribution-url",
        URL,
        "--max-invalid-fraction",
        "0.34",
        *extra,
    ]


def _output(capsys: pytest.CaptureFixture[str]) -> dict[str, object]:
    value = json.loads(capsys.readouterr().out)
    assert isinstance(value, dict)
    return value


def _private_path(root: Path, summary: dict[str, object], key: str) -> Path:
    relative = Path(str(summary[key]))
    assert not relative.is_absolute()
    return root / relative


def test_ingest_fars_success_prints_traceability_without_outcome_locations(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    export = _zip_export(tmp_path)
    private_root = tmp_path / "private"

    assert main(_argv(export, private_root)) == 0

    summary = _output(capsys)
    assert summary["source_id"] == "fars"
    assert summary["years"] == [2023]
    assert summary["release_status"] == "final"
    assert summary["counts"] == {
        "records_read": 3,
        "records_accepted": 2,
        "records_rejected": 1,
        "rejection_reasons": {"invalid_location": 1},
    }
    assert len(str(summary["raw_sha256"])) == 64
    assert len(str(summary["normalized_sha256"])) == 64
    for key in ("artifact_path", "current_path", "receipt_path"):
        assert _private_path(private_root, summary, key).is_file()
        assert str(private_root) not in str(summary[key])
    assert "outcomes" not in summary
    assert "lat" not in summary
    assert "lon" not in summary


def test_ingest_fars_rerun_reuses_deterministic_content_addressed_payloads(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    export = _zip_export(tmp_path)
    private_root = tmp_path / "private"

    assert main(_argv(export, private_root)) == 0
    first = _output(capsys)
    assert main(_argv(export, private_root)) == 0
    second = _output(capsys)

    assert first["raw_sha256"] == second["raw_sha256"]
    assert first["normalized_sha256"] == second["normalized_sha256"]
    assert first["artifact_path"] == second["artifact_path"]
    assert first["receipt_path"] != second["receipt_path"]
    assert len(list((private_root / "fars" / "raw" / "sha256").glob("*.bin"))) == 1
    assert len(list((private_root / "fars" / "normalized" / "sha256").glob("*.bin"))) == 1
    assert len(list((private_root / "fars" / "receipts").glob("*.json"))) == 2


def test_record_count_regression_preserves_current_until_explicitly_overridden(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    export = _zip_export(tmp_path)
    private_root = tmp_path / "private"
    assert main(_argv(export, private_root)) == 0
    initial = _output(capsys)
    current_path = _private_path(private_root, initial, "current_path")
    current_before = current_path.read_bytes()

    fixture_lines = FIXTURE.read_text(encoding="utf-8").splitlines()
    export.write_text("\n".join(fixture_lines[:2]) + "\n", encoding="utf-8")
    assert main(_argv(export, private_root)) == 2

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "FARS ingestion failed" in captured.err
    assert "regressed" not in captured.err
    assert current_path.read_bytes() == current_before
    receipts = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in (private_root / "fars" / "receipts").glob("*.json")
    ]
    failure = next(item for item in receipts if item["status"] == "failure")
    assert failure["error"]["message"] == "normalized artifact validation failed"

    assert main(_argv(export, private_root, "--allow-record-regression")) == 0
    overridden = _output(capsys)
    assert overridden["counts"] == {
        "records_read": 1,
        "records_accepted": 1,
        "records_rejected": 0,
        "rejection_reasons": {},
    }
    assert current_path.read_bytes() != current_before
    artifact = json.loads(_private_path(private_root, overridden, "artifact_path").read_bytes())
    assert artifact["normalization"]["allow_record_regression"] is True


def test_dataset_year_regression_requires_distinct_recorded_override(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    export = _zip_export(tmp_path)
    private_root = tmp_path / "private"
    assert main(_argv(export, private_root)) == 0
    initial = _output(capsys)
    current_path = _private_path(private_root, initial, "current_path")
    current_before = current_path.read_bytes()

    export.write_text(
        FIXTURE.read_text(encoding="utf-8").replace("2023,", "2022,"),
        encoding="utf-8",
    )
    argv = _argv(export, private_root)
    argv[argv.index("--year") + 1] = "2022"
    argv[argv.index("--distribution-url") + 1] = URL.replace("2023", "2022")

    assert main(argv) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "FARS ingestion failed" in captured.err
    assert "year regressed" not in captured.err
    assert current_path.read_bytes() == current_before

    assert main([*argv, "--allow-year-regression"]) == 0
    overridden = _output(capsys)
    artifact = json.loads(_private_path(private_root, overridden, "artifact_path").read_bytes())
    assert artifact["normalization"]["allow_year_regression"] is True
    assert artifact["normalization"]["allow_record_regression"] is False
    assert artifact["normalization"]["expected_year"] == 2022


@pytest.mark.parametrize(
    ("replacement_args", "expected_stage"),
    [
        (("--year", "2022"), "normalization failed"),
        (("--max-invalid-fraction", "0.05"), "normalization failed"),
    ],
)
def test_semantic_failure_is_redacted_receipted_and_preserves_last_known_good(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    replacement_args: tuple[str, str],
    expected_stage: str,
) -> None:
    export = _zip_export(tmp_path)
    private_root = tmp_path / "private"
    assert main(_argv(export, private_root)) == 0
    success = _output(capsys)
    current_path = _private_path(private_root, success, "current_path")
    current_before = current_path.read_bytes()

    argv = _argv(export, private_root)
    option, replacement = replacement_args
    argv[argv.index(option) + 1] = replacement
    assert main(argv) == 2

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "FARS ingestion failed" in captured.err
    assert "expected year" not in captured.err.lower()
    assert "invalid fraction" not in captured.err.lower()
    assert str(export) not in captured.err
    assert current_path.read_bytes() == current_before
    receipts = sorted((private_root / "fars" / "receipts").glob("*.json"))
    assert len(receipts) == 2
    failures = [json.loads(path.read_text(encoding="utf-8")) for path in receipts]
    failure = next(item for item in failures if item["status"] == "failure")
    assert failure["activated"] is False
    assert failure["error"]["message"] == expected_stage


def test_malformed_zip_failure_is_redacted_receipted_and_preserves_active_artifact(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    export = _zip_export(tmp_path)
    private_root = tmp_path / "private"
    assert main(_argv(export, private_root)) == 0
    success = _output(capsys)
    current_path = _private_path(private_root, success, "current_path")
    current_before = current_path.read_bytes()
    secret = "private-case-location-38.123,-121.456"
    export.write_bytes(("PK malformed " + secret).encode())

    assert main(_argv(export, private_root)) == 2

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "FARS ingestion failed" in captured.err
    assert secret not in captured.err
    assert str(export) not in captured.err
    assert current_path.read_bytes() == current_before
    receipts = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in (private_root / "fars" / "receipts").glob("*.json")
    ]
    failure = next(item for item in receipts if item["status"] == "failure")
    assert failure["error"] == {"message": "normalization failed", "type": "ValueError"}


@pytest.mark.parametrize(
    "invalid_url",
    [
        "https://example.test/nhtsa/downloads/FARS/2023/FARS2023.zip",
        URL + "?download=1",
        "https://static.nhtsa.gov:99999/nhtsa/downloads/FARS/2023/FARS2023.zip",
    ],
)
def test_invalid_distribution_url_is_rejected_before_export_acquisition(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], invalid_url: str
) -> None:
    missing_export = tmp_path / "must-not-be-read.zip"
    argv = _argv(missing_export, tmp_path / "private")
    argv[argv.index("--distribution-url") + 1] = invalid_url

    with pytest.raises(SystemExit) as raised:
        main(argv)

    assert raised.value.code == 2
    captured = capsys.readouterr()
    assert "static.nhtsa.gov FARS HTTPS distribution URL" in captured.err
    assert not (tmp_path / "private").exists()


def test_max_raw_bytes_is_enforced_during_bounded_acquisition(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    export = _zip_export(tmp_path)
    private_root = tmp_path / "private"

    assert main(_argv(export, private_root, "--max-raw-bytes", "16")) == 2

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "FARS ingestion failed" in captured.err
    receipts = list((private_root / "fars" / "receipts").glob("*.json"))
    assert len(receipts) == 1
    receipt = json.loads(receipts[0].read_text(encoding="utf-8"))
    assert receipt["status"] == "failure"
    assert receipt["raw_snapshot"] is None
    assert receipt["error"]["message"] == "fetch failed"


def test_strict_artifact_decoder_rejects_nonstandard_constants_and_duplicate_keys() -> None:
    with pytest.raises(ValueError, match="constant"):
        _decode_outcome_artifact(b'{"provenance": NaN}')
    with pytest.raises(ValueError, match="duplicate"):
        _decode_outcome_artifact(b'{"provenance": {}, "provenance": {}}')


def test_candidate_validation_fails_closed_when_prior_artifact_is_malformed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    export = _zip_export(tmp_path)
    private_root = tmp_path / "private"
    assert main(_argv(export, private_root)) == 0
    summary = _output(capsys)
    candidate = _private_path(private_root, summary, "artifact_path").read_bytes()

    with pytest.raises(ValueError, match="constant"):
        _validate_fars_normalized_candidate(
            candidate,
            b'{"provenance": Infinity}',
            allow_record_regression=False,
            allow_year_regression=False,
        )


def test_ingest_fars_help_names_operator_safety_controls(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as raised:
        build_parser().parse_args(["ingest-fars", "--help"])

    assert raised.value.code == 0
    help_text = capsys.readouterr().out
    for option in (
        "--root",
        "--year",
        "--release-status",
        "--distribution-url",
        "--max-invalid-fraction",
        "--max-raw-bytes",
        "--max-normalized-bytes",
        "--allow-record-regression",
        "--allow-year-regression",
    ):
        assert option in help_text
