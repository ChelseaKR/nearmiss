from __future__ import annotations

import datetime as dt
import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import NoReturn, cast

import pytest

import nearmiss.ingestion as ingestion
import nearmiss.verified_outcomes as verifier
from nearmiss.ingestion import IngestionError, run_ingestion
from nearmiss.verified_outcomes import VerificationError

NOW = dt.datetime(2026, 7, 12, 18, tzinfo=dt.UTC)


def _clock() -> dt.datetime:
    return NOW


def _success_receipt(tmp_path: Path, *, attempt: str = "edge-success") -> dict[str, object]:
    result = run_ingestion(
        root=tmp_path,
        source_id="source",
        fetch=lambda: b"raw",
        normalize=lambda raw: raw,
        clock=_clock,
        attempt_id=attempt,
    )
    return cast(dict[str, object], json.loads(result.receipt_path.read_text()))


def _record(
    attempt: str,
    *,
    status: str = "success",
    completed: dt.datetime | None = NOW,
    raw: str = "a" * 64,
    normalized: str = "b" * 64,
    previous: str | None = None,
    payload: bytes | None = None,
) -> verifier._ReceiptRecord:
    receipt: dict[str, object] = {
        "attempt_id": attempt,
        "status": status,
        "raw_sha256": raw,
        "normalized_sha256": normalized,
        "previous_normalized_sha256": previous,
    }
    return verifier._ReceiptRecord(
        attempt_id=attempt,
        started_at=NOW,
        completed_at=completed,
        receipt=receipt,
        payload=payload if payload is not None else attempt.encode(),
    )


@pytest.mark.parametrize(
    "operation",
    [
        lambda root: ingestion._ensure_subdirectory(root, Path("/absolute")),
        lambda root: ingestion._ensure_subdirectory(root, Path("child/../escape")),
        lambda root: ingestion._relative_parts(root, root.parent / "outside"),
        lambda root: ingestion._relative_parts(root, root),
        lambda root: ingestion._artifact_from_relative(root, "/absolute"),
        lambda root: ingestion._artifact_from_relative(root, "../escape"),
    ],
)
def test_ingestion_path_guards_reject_escape(
    tmp_path: Path, operation: Callable[[Path], object]
) -> None:
    root = tmp_path / "source"
    root.mkdir()
    with pytest.raises(IngestionError):
        operation(root)


def test_ingestion_clock_and_platform_guards(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(IngestionError, match="timezone-aware"):
        ingestion._timestamp(dt.datetime(2026, 7, 12))

    monkeypatch.setattr(os, "O_NOFOLLOW", 0)
    with pytest.raises(IngestionError, match="platform"):
        ingestion._required_open_flag("O_NOFOLLOW")


def test_ingestion_rejects_missing_dir_fd_support(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source"
    source.mkdir(mode=0o700)
    monkeypatch.setattr(os, "supports_dir_fd", set())
    with pytest.raises(IngestionError, match="platform"):
        ingestion._open_regular_beneath(source, source / "file", optional=False)


def test_ingestion_owner_and_permission_guards(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    directory = tmp_path / "owned"
    directory.mkdir(mode=0o700)
    monkeypatch.setattr(os, "geteuid", lambda: directory.stat().st_uid + 1)
    with pytest.raises(IngestionError, match="not owned"):
        ingestion._ensure_directory(directory)
    with pytest.raises(IngestionError, match="not owned"):
        ingestion._ensure_source_directory(tmp_path, "source")

    file = tmp_path / "artifact"
    file.write_bytes(b"x")
    file.chmod(0o400)
    with pytest.raises(IngestionError, match="not owned"):
        ingestion._validate_regular_metadata(file, file.stat(), None)
    with pytest.raises(IngestionError, match="unsafe"):
        ingestion._validate_directory_metadata(directory, directory.stat())


def test_ingestion_directory_chmod_failures_are_redacted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    directory = tmp_path / "directory"
    directory.mkdir(mode=0o700)

    def fail_chmod(*_args: object, **_kwargs: object) -> NoReturn:
        raise OSError("private chmod detail")

    monkeypatch.setattr(Path, "chmod", fail_chmod)
    with pytest.raises(IngestionError, match="permissions are unsafe"):
        ingestion._ensure_directory(directory)
    with pytest.raises(IngestionError, match="root permissions are unsafe"):
        ingestion._ensure_source_directory(tmp_path, "source")


def test_verifier_secure_open_guards_close_invalid_descriptors(tmp_path: Path) -> None:
    missing = tmp_path / "missing"
    with pytest.raises(VerificationError, match="filesystem"):
        verifier._open_root(missing)

    unsafe = tmp_path / "unsafe"
    unsafe.mkdir(mode=0o700)
    unsafe.chmod(0o755)
    with pytest.raises(VerificationError, match="filesystem"):
        verifier._open_root(unsafe)

    safe = tmp_path / "safe"
    safe.mkdir(mode=0o700)
    root_fd = verifier._open_root(safe)
    try:
        for invalid in ("", ".", "..", "child/name"):
            with pytest.raises(VerificationError, match="filesystem"):
                verifier._open_directory(root_fd, invalid)
            with pytest.raises(VerificationError, match="filesystem"):
                verifier._open_file(root_fd, invalid)
        with pytest.raises(VerificationError, match="filesystem"):
            verifier._open_directory(root_fd, "missing")
        with pytest.raises(VerificationError, match="filesystem"):
            verifier._open_file(root_fd, "missing")

        child = safe / "child"
        child.mkdir(mode=0o700)
        child.chmod(0o755)
        with pytest.raises(VerificationError, match="filesystem"):
            verifier._open_directory(root_fd, "child")

        artifact = safe / "artifact"
        artifact.write_bytes(b"x")
        artifact.chmod(0o600)
        with pytest.raises(VerificationError, match="filesystem"):
            verifier._open_file(root_fd, "artifact")
    finally:
        os.close(root_fd)


def test_verifier_read_size_and_lock_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "root"
    root.mkdir(mode=0o700)
    artifact = root / "artifact"
    artifact.write_bytes(b"payload")
    artifact.chmod(0o400)
    root_fd = verifier._open_root(root)
    try:
        with pytest.raises(VerificationError, match="size limit"):
            verifier._read_file(root_fd, "artifact", maximum=1)

        def fail_lock(*_args: object, **_kwargs: object) -> NoReturn:
            raise PermissionError("private lock detail")

        monkeypatch.setattr(os, "stat", fail_lock)
        with pytest.raises(VerificationError, match="lock verification"):
            verifier._lock_absent(root_fd)
    finally:
        os.close(root_fd)


@pytest.mark.parametrize(
    "payload",
    [b"\xff", b"[]", b'{"key":1,"key":2}', b'{"value":NaN}'],
)
def test_verifier_strict_json_rejects_ambiguous_values(payload: bytes) -> None:
    with pytest.raises(VerificationError, match="JSON decoding"):
        verifier._strict_json(payload)


def test_verifier_receipt_identity_and_chronology_guards(tmp_path: Path) -> None:
    receipt = _success_receipt(tmp_path)
    with pytest.raises(VerificationError, match="source"):
        verifier._validate_receipt(receipt, expected_source_id="other")

    forged_raw = dict(receipt)
    forged_raw["raw_snapshot"] = f"raw/sha256/{'f' * 64}.bin"
    with pytest.raises(VerificationError, match="raw identity"):
        verifier._validate_receipt(forged_raw, expected_source_id="source")

    forged_normalized = dict(receipt)
    forged_normalized["normalized_path"] = f"normalized/sha256/{'e' * 64}.bin"
    with pytest.raises(VerificationError, match="normalized identity"):
        verifier._validate_receipt(forged_normalized, expected_source_id="source")

    with pytest.raises(VerificationError, match="not successful"):
        verifier._active_success({"status": "failure", "activated": False, "error": {}})
    for value in ("not-a-time", "2026-07-12T18:00:00"):
        with pytest.raises(VerificationError, match="chronology"):
            verifier._timestamp(value)

    canonical = verifier._canonical_receipt_bytes(receipt)
    with pytest.raises(VerificationError, match="encoding"):
        verifier._parse_receipt(json.dumps(receipt).encode(), expected_source_id="source")
    with pytest.raises(VerificationError, match="filename"):
        verifier._parse_receipt(canonical, "wrong.json", expected_source_id="source")

    reversed_receipt = dict(receipt)
    reversed_receipt["started_at"] = "2026-07-12T19:00:00Z"
    reversed_receipt["completed_at"] = "2026-07-12T18:00:00Z"
    with pytest.raises(VerificationError, match="chronology"):
        verifier._parse_receipt(
            verifier._canonical_receipt_bytes(reversed_receipt),
            expected_source_id="source",
        )


def test_verifier_receipt_scan_and_order_limits(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(os, "listdir", lambda _fd: (_ for _ in ()).throw(OSError("private")))
    with pytest.raises(VerificationError, match="scan failed"):
        verifier._scan_receipts(123)

    current_without_completion = _record("current", completed=None)
    with pytest.raises(VerificationError, match="completion time"):
        verifier._ordered_successes(current_without_completion, [current_without_completion])

    failed = _record("failed", status="failure", payload=b"same")
    current_failed = verifier._ReceiptRecord(
        attempt_id="failed",
        started_at=NOW,
        completed_at=NOW,
        receipt=failed.receipt,
        payload=b"same",
    )
    with pytest.raises(VerificationError, match="no successful"):
        verifier._ordered_successes(current_failed, [failed])

    current = _record("current", payload=b"current")
    later = _record(
        "later",
        completed=NOW + dt.timedelta(hours=1),
        payload=b"later",
    )
    with pytest.raises(VerificationError, match="not the latest"):
        verifier._ordered_successes(current, [current, later])

    monkeypatch.setattr(verifier, "_MAX_SUCCESS_GENERATIONS", 0)
    with pytest.raises(VerificationError, match="exceeds"):
        verifier._ordered_successes(current, [current])


def test_empty_and_observed_verifier_chains(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(VerificationError, match="no successful"):
        verifier._verify_success_chain([], -1, -1)
    with pytest.raises(VerificationError, match="no successful"):
        verifier._verify_joined_chain([], -1, -1)

    first = _record("first")
    second = _record("second", previous="b" * 64)
    generation = verifier._VerifiedGeneration(
        receipt=first,
        artifact={},
        normalized_bytes=b"normalized",
    )
    calls = 0
    observed: list[str] = []

    def verify_generation(
        receipt: verifier._ReceiptRecord, _raw: int, _normalized: int
    ) -> verifier._VerifiedGeneration:
        nonlocal calls
        calls += 1
        return verifier._VerifiedGeneration(
            receipt=receipt,
            artifact={},
            normalized_bytes=b"normalized",
        )

    monkeypatch.setattr(verifier, "_verify_joined_generation", verify_generation)
    monkeypatch.setattr(verifier, "_validate_joined_regression", lambda *_args: None)
    active = verifier._verify_joined_chain(
        [first, second],
        -1,
        -1,
        observe_generation=lambda item: observed.append(item.receipt.attempt_id),
    )
    assert generation.normalized_bytes == active.normalized_bytes
    assert calls == 1
    assert observed == ["first", "second"]


def test_ingestion_post_activation_integrity_error_branches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source"
    source.mkdir(mode=0o700)
    marker = b"marker"

    monkeypatch.setattr(ingestion, "_candidate_artifacts_authenticated", lambda **_kwargs: True)
    monkeypatch.setattr(ingestion, "_load_active_marker", lambda *_args, **_kwargs: None)
    with pytest.raises(ingestion._ActivatedIntegrityError, match="marker changed"):
        ingestion._require_activated_integrity(
            source_root=source,
            source_id="source",
            current_path=source / "current.json",
            success_marker=marker,
            raw_snapshot=source / "raw.bin",
            raw=b"raw",
            raw_digest="a" * 64,
            normalized_path=source / "normalized.bin",
            normalized=b"normalized",
            normalized_digest="b" * 64,
            max_raw_bytes=None,
            max_normalized_bytes=None,
        )

    monkeypatch.setattr(
        ingestion,
        "_load_active_marker",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(IngestionError("private")),
    )
    with pytest.raises(ingestion._ActivatedIntegrityError, match="state changed"):
        ingestion._require_activated_integrity(
            source_root=source,
            source_id="source",
            current_path=source / "current.json",
            success_marker=marker,
            raw_snapshot=source / "raw.bin",
            raw=b"raw",
            raw_digest="a" * 64,
            normalized_path=source / "normalized.bin",
            normalized=b"normalized",
            normalized_digest="b" * 64,
            max_raw_bytes=None,
            max_normalized_bytes=None,
        )


def test_ingestion_marker_and_error_classification_branches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source"
    source.mkdir(mode=0o700)
    current = source / "current.json"
    monkeypatch.setattr(
        ingestion,
        "_read_optional_regular",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(IngestionError("private")),
    )
    assert ingestion._marker_state(source, current, None, b"candidate") == "ambiguous"
    with pytest.raises(ingestion._ActiveMarkerChangedError):
        ingestion._require_active_marker_unchanged(source, current, None)

    assert ingestion._error_type(TimeoutError(), False) == "TimeoutError"
    assert ingestion._error_type(OSError(), False) == "OSError"
    assert ingestion._error_type(TypeError(), False) == "TypeError"
    assert ingestion._error_type(RuntimeError(), False) == "Exception"


def test_ingestion_candidate_authentication_handles_read_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        ingestion,
        "_read_regular",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(IngestionError("private")),
    )
    assert not ingestion._candidate_artifacts_authenticated(
        source_root=tmp_path,
        raw_snapshot=tmp_path / "raw",
        raw=b"raw",
        raw_digest="a" * 64,
        normalized_path=tmp_path / "normalized",
        normalized=b"normalized",
        normalized_digest="b" * 64,
    )
