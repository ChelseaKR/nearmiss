from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import pytest

from nearmiss.__main__ import (
    _validate_fars_joined_normalized_candidate,
    build_parser,
    main,
)

ROOT = Path(__file__).resolve().parents[1]
ACCIDENT_WITHOUT_COUNTY = (
    (ROOT / "tests" / "fixtures" / "fars" / "accident.csv")
    .read_bytes()
    .replace(b",2023,", b",2024,")
)


def _with_county_column(payload: bytes) -> bytes:
    lines = payload.decode().splitlines()
    output = [lines[0].replace(",FATALS", ",COUNTY,FATALS")]
    for line in lines[1:]:
        values = line.split(",")
        values.insert(-1, "113")
        output.append(",".join(values))
    return ("\n".join(output) + "\n").encode()


ACCIDENT = _with_county_column(ACCIDENT_WITHOUT_COUNTY)
PERSON_HEADER = "STATE,ST_CASE,VEH_NO,PER_NO,PER_TYP,INJ_SEV,BODY_TYP\n"
PERSON_ROWS = [
    "6,100001,1,1,1,4,4",
    "6,100001,0,1,5,2,",
    "6,100002,1,1,1,4,80",
    "6,100002,0,1,6,4,",
    "6,100003,0,1,5,4,",
]
URL = "https://static.nhtsa.gov/nhtsa/downloads/FARS/2024/National/FARS2024NationalCSV.zip"


def _person(rows: list[str] | None = None) -> bytes:
    return (PERSON_HEADER + "\n".join(PERSON_ROWS if rows is None else rows) + "\n").encode()


def _archive(path: Path, *, accident: bytes = ACCIDENT, rows: list[str] | None = None) -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("National/accident.csv", accident)
        archive.writestr("National/person.csv", _person(rows))
    path.write_bytes(buffer.getvalue())


def _argv(export: Path, root: Path, *extra: str) -> list[str]:
    return [
        "ingest-fars-joined",
        str(export),
        "--root",
        str(root),
        "--year",
        "2024",
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


def _private(root: Path, summary: dict[str, object], key: str) -> Path:
    relative = Path(str(summary[key]))
    assert not relative.is_absolute()
    assert str(root) not in str(relative)
    return root / relative


def test_joined_ingestion_is_deterministic_private_and_isolated(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    export = tmp_path / "fars-2024.zip"
    root = tmp_path / "private"
    _archive(export)

    assert main(_argv(export, root)) == 0
    first = _output(capsys)
    assert main(_argv(export, root)) == 0
    second = _output(capsys)

    assert first["source_id"] == "fars-joined"
    assert first["year"] == 2024
    assert first["release_status"] == "final"
    assert first["crash_counts"] == {
        "records_read": 3,
        "records_accepted": 2,
        "rejection_reasons": {"invalid_location": 1},
    }
    assert first["person_counts"] == {
        "records_read": 5,
        "records_accepted": 4,
        "cases_joined": 2,
        "records_excluded_with_rejected_crash": 1,
        "cases_excluded_with_rejected_crash": 1,
        "rejection_reasons": {"parent_crash_rejected": 1},
    }
    assert first["raw_sha256"] == second["raw_sha256"]
    assert first["normalized_sha256"] == second["normalized_sha256"]
    assert first["artifact_path"] == second["artifact_path"]
    assert first["receipt_path"] != second["receipt_path"]
    for key in ("artifact_path", "current_path", "receipt_path"):
        assert _private(root, first, key).is_file()
    assert not (root / "fars").exists()
    assert len(list((root / "fars-joined" / "raw" / "sha256").glob("*.bin"))) == 1
    assert len(list((root / "fars-joined" / "normalized" / "sha256").glob("*.bin"))) == 1
    assert "records" not in first


def test_new_ingestion_fails_closed_without_county_identity(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    export = tmp_path / "fars-2024.zip"
    _archive(export, accident=ACCIDENT_WITHOUT_COUNTY)

    assert main(_argv(export, tmp_path / "private")) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "joined FARS ingestion failed" in captured.err


def test_person_regression_rolls_back_until_explicit_override(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    export = tmp_path / "fars-2024.zip"
    root = tmp_path / "private"
    _archive(export)
    assert main(_argv(export, root)) == 0
    initial = _output(capsys)
    current = _private(root, initial, "current_path")
    before = current.read_bytes()

    _archive(export, rows=[row for index, row in enumerate(PERSON_ROWS) if index != 1])
    assert main(_argv(export, root)) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "joined FARS ingestion failed" in captured.err
    assert "regressed" not in captured.err
    assert str(export) not in captured.err
    assert current.read_bytes() == before
    receipts = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in (root / "fars-joined" / "receipts").glob("*.json")
    ]
    failure = next(receipt for receipt in receipts if receipt["status"] == "failure")
    assert failure["error"]["message"] == "normalized artifact validation failed"

    assert main(_argv(export, root, "--allow-record-regression", "--allow-mode-regression")) == 0
    overridden = _output(capsys)
    assert overridden["allow_record_regression"] is True
    assert overridden["person_counts"]["records_accepted"] == 3  # type: ignore[index]
    artifact = json.loads(_private(root, overridden, "artifact_path").read_text(encoding="utf-8"))
    assert artifact["crash_normalization"]["allow_record_regression"] is True
    assert artifact["join_policy"]["allow_mode_regression"] is True


def test_crash_and_case_regression_preserves_last_known_good(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    export = tmp_path / "fars-2024.zip"
    root = tmp_path / "private"
    all_valid = ACCIDENT.replace(b"77.777777", b"38.560000")
    _archive(export, accident=all_valid)
    assert main(_argv(export, root)) == 0
    initial = _output(capsys)
    current = _private(root, initial, "current_path")
    before = current.read_bytes()

    _archive(export)
    assert main(_argv(export, root)) == 2
    assert current.read_bytes() == before
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "joined FARS ingestion failed" in captured.err

    assert main(_argv(export, root, "--allow-record-regression", "--allow-mode-regression")) == 0
    overridden = _output(capsys)
    assert overridden["person_counts"]["records_excluded_with_rejected_crash"] == 1  # type: ignore[index]
    artifact = json.loads(_private(root, overridden, "artifact_path").read_text(encoding="utf-8"))
    assert artifact["crash_normalization"]["allow_record_regression"] is True
    assert artifact["join_policy"]["allow_mode_regression"] is True


def test_release_regression_requires_distinct_recorded_override(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    export = tmp_path / "fars-2024.zip"
    root = tmp_path / "private"
    _archive(export)
    assert main(_argv(export, root)) == 0
    initial = _output(capsys)
    current = _private(root, initial, "current_path")
    before = current.read_bytes()
    preliminary = _argv(export, root)
    preliminary[preliminary.index("--release-status") + 1] = "preliminary"

    assert main(preliminary) == 2
    assert current.read_bytes() == before
    assert "joined FARS ingestion failed" in capsys.readouterr().err

    assert main([*preliminary, "--allow-release-regression"]) == 0
    overridden = _output(capsys)
    assert overridden["allow_release_regression"] is True
    artifact = json.loads(_private(root, overridden, "artifact_path").read_text(encoding="utf-8"))
    assert artifact["join_policy"]["allow_release_regression"] is True
    assert artifact["crash_provenance"]["release_status"] == "preliminary"


def test_same_total_mode_regression_requires_distinct_recorded_override(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    export = tmp_path / "fars-2024.zip"
    root = tmp_path / "private"
    _archive(export)
    assert main(_argv(export, root)) == 0
    initial = _output(capsys)
    current = _private(root, initial, "current_path")
    before = current.read_bytes()
    changed = PERSON_ROWS.copy()
    changed[1] = "6,100001,0,1,11,2,"
    _archive(export, rows=changed)

    assert main(_argv(export, root)) == 2
    assert current.read_bytes() == before
    assert "joined FARS ingestion failed" in capsys.readouterr().err

    assert main(_argv(export, root, "--allow-mode-regression")) == 0
    overridden = _output(capsys)
    assert overridden["allow_mode_regression"] is True
    artifact = json.loads(_private(root, overridden, "artifact_path").read_text(encoding="utf-8"))
    assert artifact["join_policy"]["allow_mode_regression"] is True


def test_malformed_export_error_is_redacted_and_preserves_current(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    export = tmp_path / "private-coordinates-38.1--121.2.zip"
    root = tmp_path / "private"
    _archive(export)
    assert main(_argv(export, root)) == 0
    success = _output(capsys)
    current = _private(root, success, "current_path")
    before = current.read_bytes()
    secret = "precise-person-record-38.123,-121.456"
    export.write_bytes(("PK malformed " + secret).encode())

    assert main(_argv(export, root)) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "joined FARS ingestion failed" in captured.err
    assert secret not in captured.err
    assert str(export) not in captured.err
    assert current.read_bytes() == before


@pytest.mark.parametrize(
    ("option", "invalid"),
    [
        ("--year", "2023"),
        ("--release-status", "certified"),
        (
            "--distribution-url",
            "https://static.nhtsa.gov/nhtsa/downloads/FARS/2024/National/accident.csv",
        ),
    ],
)
def test_joined_prevalidation_rejects_before_export_acquisition(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    option: str,
    invalid: str,
) -> None:
    export = tmp_path / "missing.zip"
    root = tmp_path / "must-not-exist"
    argv = _argv(export, root)
    argv[argv.index(option) + 1] = invalid

    with pytest.raises(SystemExit) as raised:
        main(argv)

    assert raised.value.code == 2
    assert capsys.readouterr().err
    assert not root.exists()


def test_distribution_year_mismatch_fails_before_root_or_export_access(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "must-not-exist"
    argv = _argv(tmp_path / "missing.zip", root)
    argv[argv.index("--distribution-url") + 1] = URL.replace("/2024/", "/2023/")

    assert main(argv) == 2

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "preflight validation failed" in captured.err
    assert str(root) not in captured.err
    assert not root.exists()


def test_repository_local_private_root_is_rejected_without_creation(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = ROOT / ".joined-cli-private-root-must-not-exist"
    assert not root.exists()
    export = tmp_path / "fars-2024.zip"
    _archive(export)

    assert main(_argv(export, root)) == 2

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "outside the repository" in captured.err
    assert str(root) not in captured.err
    assert not root.exists()


def test_malformed_private_root_fails_legacy_cli_preflight(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    export = tmp_path / "fars-2024.zip"
    _archive(export)
    argv = _argv(export, tmp_path / "private")
    argv[argv.index("--root") + 1] = "bad\0root"

    assert main(argv) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "joined FARS preflight validation failed" in captured.err


def test_joined_validator_strictly_decodes_prior_and_binds_override(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    export = tmp_path / "fars-2024.zip"
    root = tmp_path / "private"
    _archive(export)
    assert main(_argv(export, root)) == 0
    summary = _output(capsys)
    candidate = _private(root, summary, "artifact_path").read_bytes()

    with pytest.raises(ValueError, match="constant"):
        _validate_fars_joined_normalized_candidate(
            candidate,
            b'{"person_join": Infinity}',
            allow_record_regression=False,
            allow_mode_regression=False,
            allow_release_regression=False,
        )
    with pytest.raises(ValueError, match="duplicate"):
        _validate_fars_joined_normalized_candidate(
            candidate,
            b'{"person_join": {}, "person_join": {}}',
            allow_record_regression=False,
            allow_mode_regression=False,
            allow_release_regression=False,
        )
    with pytest.raises(ValueError, match="override policy"):
        _validate_fars_joined_normalized_candidate(
            candidate,
            None,
            allow_record_regression=True,
            allow_mode_regression=False,
            allow_release_regression=False,
        )


def test_joined_parser_defaults_and_help(capsys: pytest.CaptureFixture[str]) -> None:
    parser = build_parser()
    parsed = parser.parse_args(
        [
            "ingest-fars-joined",
            "export.zip",
            "--root",
            "private",
            "--year",
            "2024",
            "--release-status",
            "final",
            "--distribution-url",
            URL,
        ]
    )
    assert parsed.max_raw_bytes == 64 * 1024 * 1024
    assert parsed.max_normalized_bytes == 64 * 1024 * 1024

    with pytest.raises(SystemExit) as raised:
        parser.parse_args(["ingest-fars-joined", "--help"])
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
        "--allow-mode-regression",
        "--allow-release-regression",
    ):
        assert option in help_text
