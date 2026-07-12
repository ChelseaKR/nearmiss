"""Adversarial preflight tests for an existing active ingestion marker."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any, cast

import pytest

import nearmiss.ingestion as ingestion
from nearmiss.ingestion import IngestionError, IngestionResult, run_ingestion


def _initial(tmp_path: Path) -> IngestionResult:
    return run_ingestion(
        root=tmp_path,
        source_id="source",
        fetch=lambda: b"raw-active",
        normalize=lambda _raw: b"normalized-active",
        attempt_id="active",
    )


def _replace(path: Path, payload: bytes) -> None:
    path.chmod(0o600)
    path.write_bytes(payload)
    path.chmod(0o400)


def _assert_rejected_before_work(
    tmp_path: Path,
    current_path: Path,
    *,
    max_raw_bytes: int | None = None,
    max_normalized_bytes: int | None = None,
) -> None:
    marker_before = current_path.read_bytes()
    fetch_calls = normalize_calls = 0

    def fetch() -> bytes:
        nonlocal fetch_calls
        fetch_calls += 1
        return b"replacement-raw"

    def normalize(raw: bytes) -> bytes:
        nonlocal normalize_calls
        normalize_calls += 1
        return raw

    with pytest.raises(IngestionError):
        run_ingestion(
            root=tmp_path,
            source_id="source",
            fetch=fetch,
            normalize=normalize,
            attempt_id="blocked",
            max_raw_bytes=max_raw_bytes,
            max_normalized_bytes=max_normalized_bytes,
        )

    assert (fetch_calls, normalize_calls) == (0, 0)
    assert current_path.read_bytes() == marker_before
    blocked_receipt = tmp_path / "source" / "receipts" / "blocked.json"
    if blocked_receipt.exists():
        receipt = json.loads(blocked_receipt.read_bytes())
        assert receipt["status"] == "failure"
        assert receipt["activated"] is False
        assert receipt["raw_snapshot"] is None
        assert receipt["normalized_path"] is None
    assert not (tmp_path / "source" / ".ingestion.lock").exists()


@pytest.mark.parametrize("target_name", ["current_path", "raw_snapshot", "normalized_path"])
def test_preflight_rejects_hardlinked_active_files(tmp_path: Path, target_name: str) -> None:
    result = _initial(tmp_path)
    target = getattr(result, target_name)
    os.link(target, target.with_name(f"{target.name}.second-link"))

    _assert_rejected_before_work(tmp_path, result.current_path)


@pytest.mark.parametrize(
    ("target_name", "mode"),
    [("current_path", 0o600), ("raw_snapshot", 0o440), ("normalized_path", 0o444)],
)
def test_preflight_rejects_any_mode_other_than_exact_0400(
    tmp_path: Path, target_name: str, mode: int
) -> None:
    result = _initial(tmp_path)
    target = getattr(result, target_name)
    target.chmod(mode)

    _assert_rejected_before_work(tmp_path, result.current_path)
    assert target.stat().st_mode & 0o777 == mode


@pytest.mark.parametrize("target_name", ["current_path", "raw_snapshot", "normalized_path"])
def test_preflight_rejects_empty_active_payloads(tmp_path: Path, target_name: str) -> None:
    result = _initial(tmp_path)
    _replace(getattr(result, target_name), b"")

    _assert_rejected_before_work(tmp_path, result.current_path)


def test_preflight_bounds_current_receipt_to_one_mebibyte(tmp_path: Path) -> None:
    result = _initial(tmp_path)
    _replace(result.current_path, b"x" * (1024 * 1024 + 1))

    _assert_rejected_before_work(tmp_path, result.current_path)


def test_preflight_rejects_symlinked_active_artifact_ancestor(tmp_path: Path) -> None:
    result = _initial(tmp_path)
    normalized_directory = tmp_path / "source" / "normalized"
    outside = tmp_path / "outside-normalized"
    shutil.move(normalized_directory, outside)
    normalized_directory.symlink_to(outside, target_is_directory=True)

    _assert_rejected_before_work(tmp_path, result.current_path)


def test_preflight_rejects_nonprivate_active_artifact_ancestor(tmp_path: Path) -> None:
    result = _initial(tmp_path)
    result.raw_snapshot.parent.chmod(0o755)

    _assert_rejected_before_work(tmp_path, result.current_path)
    assert result.raw_snapshot.parent.stat().st_mode & 0o777 == 0o755


@pytest.mark.parametrize("limited", ["raw", "normalized"])
def test_preflight_applies_current_run_caps_to_prior_active_payloads(
    tmp_path: Path, limited: str
) -> None:
    result = _initial(tmp_path)
    raw_cap = len(b"raw-active") - 1 if limited == "raw" else None
    normalized_cap = len(b"normalized-active") - 1 if limited == "normalized" else None

    _assert_rejected_before_work(
        tmp_path,
        result.current_path,
        max_raw_bytes=raw_cap,
        max_normalized_bytes=normalized_cap,
    )
    blocked = json.loads((tmp_path / "source" / "receipts" / "blocked.json").read_bytes())
    assert blocked["error"] == {
        "type": "IngestionError",
        "message": "active artifact preflight failed",
    }


def test_active_loader_uses_limit_plus_one_reads_for_every_configured_cap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = _initial(tmp_path)
    real_fdopen = os.fdopen
    requested_sizes: list[int] = []

    class TrackingHandle:
        def __init__(self, handle: Any) -> None:
            self.handle = handle

        def __enter__(self) -> TrackingHandle:
            self.handle.__enter__()
            return self

        def __exit__(self, *args: object) -> object:
            return self.handle.__exit__(*args)

        def read(self, size: int = -1) -> bytes:
            requested_sizes.append(size)
            return cast(bytes, self.handle.read(size))

        def __getattr__(self, name: str) -> Any:
            return getattr(self.handle, name)

    def tracking_fdopen(descriptor: int, mode: str) -> TrackingHandle:
        return TrackingHandle(real_fdopen(descriptor, mode))

    monkeypatch.setattr(os, "fdopen", tracking_fdopen)
    active = ingestion._load_active_marker(
        tmp_path / "source",
        result.current_path,
        "source",
        max_raw_bytes=len(b"raw-active"),
        max_normalized_bytes=len(b"normalized-active"),
    )

    assert active is not None
    assert requested_sizes == [
        1024 * 1024 + 1,
        len(b"raw-active") + 1,
        len(b"normalized-active") + 1,
    ]


def test_active_loader_uses_finite_default_limits_when_caps_are_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = _initial(tmp_path)
    real_fdopen = os.fdopen
    requested_sizes: list[int] = []

    class TrackingHandle:
        def __init__(self, handle: Any) -> None:
            self.handle = handle

        def __enter__(self) -> TrackingHandle:
            self.handle.__enter__()
            return self

        def __exit__(self, *args: object) -> object:
            return self.handle.__exit__(*args)

        def read(self, size: int = -1) -> bytes:
            requested_sizes.append(size)
            return cast(bytes, self.handle.read(size))

        def __getattr__(self, name: str) -> Any:
            return getattr(self.handle, name)

    monkeypatch.setattr(
        os, "fdopen", lambda descriptor, mode: TrackingHandle(real_fdopen(descriptor, mode))
    )
    active = ingestion._load_active_marker(tmp_path / "source", result.current_path, "source")

    assert active is not None
    assert requested_sizes == [
        ingestion._MAX_ACTIVE_RECEIPT_BYTES + 1,
        ingestion._MAX_ACTIVE_ARTIFACT_BYTES + 1,
        ingestion._MAX_ACTIVE_ARTIFACT_BYTES + 1,
    ]


def test_regular_reader_rejects_same_size_mutation_during_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = _initial(tmp_path)
    target = result.normalized_path
    real_fdopen = os.fdopen

    class MutatingHandle:
        def __init__(self, handle: Any) -> None:
            self.handle = handle
            self.mutated = False

        def __enter__(self) -> MutatingHandle:
            self.handle.__enter__()
            return self

        def __exit__(self, *args: object) -> object:
            return self.handle.__exit__(*args)

        def read(self, size: int = -1) -> bytes:
            if not self.mutated:
                self.mutated = True
                _replace(target, b"x" * len(b"normalized-active"))
                self.handle.seek(0)
            return cast(bytes, self.handle.read(size))

        def __getattr__(self, name: str) -> Any:
            return getattr(self.handle, name)

    monkeypatch.setattr(
        os, "fdopen", lambda descriptor, mode: MutatingHandle(real_fdopen(descriptor, mode))
    )
    with pytest.raises(IngestionError, match="changed while it was read"):
        ingestion._read_regular(
            tmp_path / "source", target, maximum_bytes=len(b"normalized-active")
        )


def test_regular_reader_rejects_fifo_without_blocking(tmp_path: Path) -> None:
    _initial(tmp_path)
    fifo = tmp_path / "source" / "raw" / "untrusted-fifo"
    os.mkfifo(fifo, mode=0o400)
    fifo.chmod(0o400)

    with pytest.raises(IngestionError, match="not a regular file"):
        ingestion._read_regular(tmp_path / "source", fifo, maximum_bytes=1024)


def test_regular_reader_fails_closed_without_required_platform_flags(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = _initial(tmp_path)
    monkeypatch.setattr(os, "O_NOFOLLOW", 0)

    with pytest.raises(IngestionError, match="platform does not support secure"):
        ingestion._read_regular(tmp_path / "source", result.normalized_path, maximum_bytes=1024)


@pytest.mark.parametrize("marker_kind", ["duplicate-key", "noncanonical"])
def test_preflight_rejects_ambiguous_or_noncanonical_marker_json(
    tmp_path: Path, marker_kind: str
) -> None:
    result = _initial(tmp_path)
    marker = result.current_path.read_bytes()
    if marker_kind == "duplicate-key":
        replacement = marker.replace(
            b'  "source_id": "source",',
            b'  "source_id": "other",\n  "source_id": "source",',
        )
    else:
        replacement = json.dumps(json.loads(marker)).encode()
    _replace(result.current_path, replacement)

    _assert_rejected_before_work(tmp_path, result.current_path)


def test_commit_fails_if_active_marker_changes_after_preflight(
    tmp_path: Path,
) -> None:
    result = _initial(tmp_path)
    changed_marker = result.current_path.read_bytes() + b" "

    def mutate_current_during_fetch() -> bytes:
        _replace(result.current_path, changed_marker)
        return b"replacement-raw"

    with pytest.raises(ingestion.IngestionRunError) as raised:
        run_ingestion(
            root=tmp_path,
            source_id="source",
            fetch=mutate_current_during_fetch,
            normalize=lambda raw: raw,
            attempt_id="changed-during-fetch",
        )

    assert result.current_path.read_bytes() == changed_marker
    failure = json.loads(raised.value.receipt_path.read_bytes())
    assert failure["activated"] is False
    assert failure["error"] == {
        "type": "IngestionError",
        "message": "active marker commit failed",
    }
    assert not (tmp_path / "source" / ".ingestion.lock").exists()
