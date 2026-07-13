from __future__ import annotations

import datetime as dt
import hashlib
import json
import stat
import traceback
from pathlib import Path
from typing import cast

import pytest
from jsonschema import Draft202012Validator, FormatChecker

import nearmiss.ingestion as ingestion
from nearmiss.ingestion import (
    ConcurrentIngestionError,
    IngestionError,
    IngestionRunError,
    run_ingestion,
)

NOW = dt.datetime(2026, 7, 12, 18, 30, tzinfo=dt.UTC)
SCHEMA_PATH = Path(__file__).parents[1] / "schema" / "ingestion-receipt.schema.json"
SCHEMA = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
VALIDATOR = Draft202012Validator(SCHEMA, format_checker=FormatChecker())


def _clock() -> dt.datetime:
    return NOW


def _receipt(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    VALIDATOR.validate(value)
    return value


def test_receipt_schema_is_valid_and_matches_embedded_runtime_contract() -> None:
    Draft202012Validator.check_schema(SCHEMA)
    assert SCHEMA == ingestion.RECEIPT_SCHEMA


def test_success_writes_content_addressed_snapshot_and_activates_atomically(
    tmp_path: Path,
) -> None:
    raw = b'{"features": [1]}\n'
    normalized = b'{"reports": [1]}\n'

    result = run_ingestion(
        root=tmp_path,
        source_id="bikemaps-sacramento",
        fetch=lambda: raw,
        normalize=lambda payload: normalized if payload == raw else b"",
        clock=_clock,
        attempt_id="success-1",
    )

    raw_hash = hashlib.sha256(raw).hexdigest()
    assert result.raw_snapshot == (
        tmp_path / "bikemaps-sacramento" / "raw" / "sha256" / f"{raw_hash}.bin"
    )
    assert result.raw_snapshot.read_bytes() == raw
    assert result.normalized_path.read_bytes() == normalized
    assert result.current_path == (tmp_path / "bikemaps-sacramento" / "normalized" / "current.json")
    assert result.raw_snapshot.stat().st_mode & stat.S_IWUSR == 0
    assert result.normalized_path.stat().st_mode & stat.S_IWUSR == 0
    receipt = _receipt(result.receipt_path)
    assert receipt["schema_version"] == "1.0.0"
    assert receipt["status"] == "success"
    assert receipt["activated"] is True
    assert receipt["raw_sha256"] == raw_hash
    assert receipt["normalized_sha256"] == hashlib.sha256(normalized).hexdigest()
    assert receipt["previous_normalized_sha256"] is None
    assert receipt["error"] is None
    assert result.current_path.read_bytes() == result.receipt_path.read_bytes()
    assert result.receipt_path.stat().st_mode & stat.S_IWUSR == 0


def test_repeated_payload_reuses_immutable_snapshot_and_creates_new_receipt(tmp_path: Path) -> None:
    raw = b"same upstream payload"
    normalize = lambda _payload: b"same normalized payload"  # noqa: E731

    first = run_ingestion(
        root=tmp_path,
        source_id="source",
        fetch=lambda: raw,
        normalize=normalize,
        clock=_clock,
        attempt_id="attempt-1",
    )
    second = run_ingestion(
        root=tmp_path,
        source_id="source",
        fetch=lambda: raw,
        normalize=normalize,
        clock=_clock,
        attempt_id="attempt-2",
    )

    assert first.raw_snapshot == second.raw_snapshot
    assert first.raw_snapshot.read_bytes() == raw
    assert first.receipt_path != second.receipt_path
    assert len(list((tmp_path / "source" / "raw" / "sha256").glob("*.bin"))) == 1
    assert len(list((tmp_path / "source" / "normalized" / "sha256").glob("*.bin"))) == 1
    second_receipt = _receipt(second.receipt_path)
    assert second_receipt["previous_normalized_sha256"] == second.normalized_sha256


def test_receipt_bytes_are_deterministic_for_fixed_attempt_and_clock(tmp_path: Path) -> None:
    raw = b"raw"
    normalized = b"normalized"
    result = run_ingestion(
        root=tmp_path,
        source_id="source",
        fetch=lambda: raw,
        normalize=lambda _raw: normalized,
        clock=_clock,
        attempt_id="deterministic",
    )
    raw_hash = hashlib.sha256(raw).hexdigest()
    expected = {
        "schema_version": "1.0.0",
        "attempt_id": "deterministic",
        "source_id": "source",
        "status": "success",
        "started_at": "2026-07-12T18:30:00Z",
        "completed_at": "2026-07-12T18:30:00Z",
        "raw_sha256": raw_hash,
        "raw_snapshot": f"raw/sha256/{raw_hash}.bin",
        "normalized_sha256": hashlib.sha256(normalized).hexdigest(),
        "normalized_path": (f"normalized/sha256/{hashlib.sha256(normalized).hexdigest()}.bin"),
        "previous_normalized_sha256": None,
        "activated": True,
        "error": None,
    }
    assert (
        result.receipt_path.read_bytes()
        == (json.dumps(expected, indent=2, sort_keys=True) + "\n").encode()
    )


def test_invalid_internal_failure_receipt_is_not_installed_or_allowed_to_mask_cause(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class OriginalError(RuntimeError):
        pass

    original = OriginalError("private upstream detail")

    def fail_fetch() -> bytes:
        raise original

    monkeypatch.setattr(ingestion, "_error_type", lambda _exc, _rollback: "invalid type!")
    with pytest.raises(IngestionError, match="failure receipt could not be written") as raised:
        run_ingestion(
            root=tmp_path,
            source_id="source",
            fetch=fail_fetch,
            normalize=lambda raw: raw,
            clock=_clock,
            attempt_id="invalid-internal",
        )

    rendered = "".join(traceback.format_exception(raised.value))
    assert raised.value.__cause__ is None
    assert str(original) not in rendered
    assert not (tmp_path / "source" / "receipts" / "invalid-internal.json").exists()


def test_receipt_validation_rejects_digest_path_mismatch() -> None:
    digest = "a" * 64
    receipt: dict[str, object] = {
        "schema_version": "1.0.0",
        "attempt_id": "attempt",
        "source_id": "source",
        "status": "success",
        "started_at": "2026-07-12T18:30:00Z",
        "completed_at": "2026-07-12T18:30:00Z",
        "raw_sha256": digest,
        "raw_snapshot": f"raw/sha256/{'b' * 64}.bin",
        "normalized_sha256": digest,
        "normalized_path": f"normalized/sha256/{digest}.bin",
        "previous_normalized_sha256": None,
        "activated": True,
        "error": None,
    }
    with pytest.raises(IngestionError, match="does not match its digest"):
        ingestion._receipt_bytes(cast(ingestion.IngestionReceipt, receipt))


@pytest.mark.parametrize("class_name", ["unsafe error!", "Token_supersecret"])
def test_uncontrolled_exception_type_is_sanitized(tmp_path: Path, class_name: str) -> None:
    unsafe_error = type(class_name, (RuntimeError,), {})

    def fail_fetch() -> bytes:
        raise unsafe_error("private")

    with pytest.raises(IngestionRunError) as raised:
        run_ingestion(
            root=tmp_path,
            source_id="source",
            fetch=fail_fetch,
            normalize=lambda raw: raw,
            clock=_clock,
            attempt_id="sanitized-type",
        )

    assert _receipt(raised.value.receipt_path)["error"] == {
        "message": "fetch failed",
        "type": "Exception",
    }


@pytest.mark.parametrize("failure_stage", ["fetch", "normalize"])
def test_failure_receipt_preserves_last_known_good(tmp_path: Path, failure_stage: str) -> None:
    initial = run_ingestion(
        root=tmp_path,
        source_id="source",
        fetch=lambda: b"raw-v1",
        normalize=lambda _raw: b"normalized-v1",
        clock=_clock,
        attempt_id="initial",
    )
    before = initial.normalized_path.read_bytes()

    def fail_fetch() -> bytes:
        if failure_stage == "fetch":
            raise TimeoutError("upstream timed out")
        return b"raw-v2"

    def fail_normalize(_raw: bytes) -> bytes:
        if failure_stage == "normalize":
            raise ValueError("schema validation failed")
        return b"normalized-v2"

    with pytest.raises(IngestionRunError) as raised:
        run_ingestion(
            root=tmp_path,
            source_id="source",
            fetch=fail_fetch,
            normalize=fail_normalize,
            clock=_clock,
            attempt_id=f"failed-{failure_stage}",
        )

    assert initial.normalized_path.read_bytes() == before
    receipt = _receipt(raised.value.receipt_path)
    assert receipt["status"] == "failure"
    assert receipt["activated"] is False
    assert receipt["previous_normalized_sha256"] == initial.normalized_sha256
    assert isinstance(receipt["error"], dict)
    if failure_stage == "fetch":
        assert receipt["raw_snapshot"] is None
    else:
        assert receipt["raw_snapshot"] is not None


def test_failure_receipt_and_public_error_do_not_expose_exception_text(
    tmp_path: Path,
) -> None:
    secret = "https://token:super-secret@example.test/private"

    def fail_fetch() -> bytes:
        raise RuntimeError(secret)

    with pytest.raises(IngestionRunError) as raised:
        run_ingestion(
            root=tmp_path,
            source_id="source",
            fetch=fail_fetch,
            normalize=lambda raw: raw,
            clock=_clock,
            attempt_id="redacted",
        )

    receipt_text = raised.value.receipt_path.read_text(encoding="utf-8")
    assert secret not in receipt_text
    assert secret not in str(raised.value)
    assert secret not in "".join(traceback.format_exception(raised.value))
    assert _receipt(raised.value.receipt_path)["error"] == {
        "message": "fetch failed",
        "type": "Exception",
    }


def test_failure_receipt_uses_null_when_completion_time_cannot_be_observed(
    tmp_path: Path,
) -> None:
    clock_calls = 0

    def fail_after_start() -> dt.datetime:
        nonlocal clock_calls
        clock_calls += 1
        if clock_calls == 1:
            return NOW
        raise RuntimeError("clock unavailable")

    def fail_fetch() -> bytes:
        raise RuntimeError("fetch failed")

    with pytest.raises(IngestionRunError) as raised:
        run_ingestion(
            root=tmp_path,
            source_id="source",
            fetch=fail_fetch,
            normalize=lambda raw: raw,
            clock=fail_after_start,
            attempt_id="missing-completion-time",
        )

    receipt = _receipt(raised.value.receipt_path)
    assert receipt["started_at"] == "2026-07-12T18:30:00Z"
    assert receipt["completed_at"] is None


def test_lock_rejects_concurrent_writer_without_fetching(tmp_path: Path) -> None:
    lock = tmp_path / "source" / ".ingestion.lock"
    lock.mkdir(parents=True)
    called = False

    def fetch() -> bytes:
        nonlocal called
        called = True
        return b"raw"

    with pytest.raises(ConcurrentIngestionError):
        run_ingestion(
            root=tmp_path,
            source_id="source",
            fetch=fetch,
            normalize=lambda raw: raw,
            clock=_clock,
            attempt_id="concurrent",
        )

    assert called is False
    assert lock.is_dir()


def test_lock_cleanup_never_recursively_deletes_or_masks_original_error(
    tmp_path: Path,
) -> None:
    lock = tmp_path / "source" / ".ingestion.lock"

    def fail_normalize(_raw: bytes) -> bytes:
        (lock / "unexpected-owner-data").write_text("preserve me", encoding="utf-8")
        raise ValueError("normalization failed")

    with pytest.raises(IngestionRunError, match="ingestion failed"):
        run_ingestion(
            root=tmp_path,
            source_id="source",
            fetch=lambda: b"raw",
            normalize=fail_normalize,
            clock=_clock,
            attempt_id="dirty-lock",
        )

    assert (lock / "unexpected-owner-data").read_text(encoding="utf-8") == "preserve me"


def test_preflight_errors_release_owned_lock_without_fetching(tmp_path: Path) -> None:
    run_ingestion(
        root=tmp_path,
        source_id="source",
        fetch=lambda: b"raw",
        normalize=lambda raw: raw,
        clock=_clock,
        attempt_id="duplicate",
    )
    called = False

    def fetch() -> bytes:
        nonlocal called
        called = True
        return b"replacement"

    with pytest.raises(IngestionError, match="attempt receipt already exists"):
        run_ingestion(
            root=tmp_path,
            source_id="source",
            fetch=fetch,
            normalize=lambda raw: raw,
            clock=_clock,
            attempt_id="duplicate",
        )

    assert called is False
    assert not (tmp_path / "source" / ".ingestion.lock").exists()


def test_invalid_source_and_attempt_ids_cannot_escape_root(tmp_path: Path) -> None:
    for source_id, attempt_id in (("../escape", "safe"), ("source", "../escape")):
        with pytest.raises(IngestionError):
            run_ingestion(
                root=tmp_path,
                source_id=source_id,
                fetch=lambda: b"raw",
                normalize=lambda raw: raw,
                clock=_clock,
                attempt_id=attempt_id,
            )

    assert not (tmp_path.parent / "escape").exists()


def test_symlinked_source_and_artifacts_fail_closed(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    root = tmp_path / "root"
    root.mkdir()
    (root / "source").symlink_to(outside, target_is_directory=True)

    with pytest.raises(IngestionError, match="real directory"):
        run_ingestion(
            root=root,
            source_id="source",
            fetch=lambda: b"raw",
            normalize=lambda raw: raw,
            clock=_clock,
            attempt_id="source-link",
        )
    assert list(outside.iterdir()) == []

    (root / "source").unlink()
    snapshot_target = outside / "snapshot"
    snapshot_target.write_bytes(b"raw")
    raw_hash = hashlib.sha256(b"raw").hexdigest()
    raw_dir = root / "source" / "raw" / "sha256"
    raw_dir.mkdir(parents=True)
    (raw_dir / f"{raw_hash}.bin").symlink_to(snapshot_target)

    with pytest.raises(IngestionRunError) as raised:
        run_ingestion(
            root=root,
            source_id="source",
            fetch=lambda: b"raw",
            normalize=lambda raw: raw,
            clock=_clock,
            attempt_id="artifact-link",
        )
    assert snapshot_target.read_bytes() == b"raw"
    assert not (root / "source" / "normalized" / "current.json").exists()
    assert _receipt(raised.value.receipt_path)["error"] == {
        "message": "raw snapshot preservation failed",
        "type": "IngestionError",
    }
    assert _receipt(raised.value.receipt_path)["raw_snapshot"] is None


def test_symlinked_ingestion_root_is_rejected(tmp_path: Path) -> None:
    actual = tmp_path / "actual"
    actual.mkdir()
    linked = tmp_path / "linked"
    linked.symlink_to(actual, target_is_directory=True)

    with pytest.raises(IngestionError, match="not a symlink"):
        run_ingestion(
            root=linked,
            source_id="source",
            fetch=lambda: b"raw",
            normalize=lambda raw: raw,
            clock=_clock,
            attempt_id="root-link",
        )
    assert list(actual.iterdir()) == []


def test_non_bytes_and_empty_payloads_fail_closed(tmp_path: Path) -> None:
    fetchers: list[object] = [lambda: b"", lambda: "not bytes"]
    for index, fetch in enumerate(fetchers):
        with pytest.raises(IngestionRunError):
            run_ingestion(
                root=tmp_path,
                source_id="source",
                fetch=fetch,  # type: ignore[arg-type]
                normalize=lambda raw: raw,
                clock=_clock,
                attempt_id=f"bad-{index}",
            )
    assert not (tmp_path / "source" / "normalized" / "current.json").exists()


def test_limits_and_source_aware_validator_reject_suspicious_payloads(
    tmp_path: Path,
) -> None:
    initial = run_ingestion(
        root=tmp_path,
        source_id="source",
        fetch=lambda: b"raw-v1",
        normalize=lambda _raw: b"many-records",
        clock=_clock,
        attempt_id="initial",
    )

    def reject_regression(candidate: bytes, previous: bytes | None) -> None:
        assert previous == b"many-records"
        if len(candidate) < len(previous) // 2:
            raise ValueError("customer@example.test dataset regressed")

    with pytest.raises(IngestionRunError) as regression:
        run_ingestion(
            root=tmp_path,
            source_id="source",
            fetch=lambda: b"raw-v2",
            normalize=lambda _raw: b"tiny",
            validate_normalized=reject_regression,
            clock=_clock,
            attempt_id="regressed",
        )
    assert initial.normalized_path.read_bytes() == b"many-records"
    regression_receipt = _receipt(regression.value.receipt_path)
    assert regression_receipt["error"] == {
        "message": "normalized artifact validation failed",
        "type": "ValueError",
    }
    assert "customer@example.test" not in regression.value.receipt_path.read_text()

    with pytest.raises(IngestionRunError) as oversized:
        run_ingestion(
            root=tmp_path,
            source_id="source",
            fetch=lambda: b"too-large",
            normalize=lambda raw: raw,
            max_raw_bytes=3,
            clock=_clock,
            attempt_id="oversized",
        )
    assert _receipt(oversized.value.receipt_path)["error"] == {
        "message": "active artifact preflight failed",
        "type": "IngestionError",
    }


def test_history_validator_runs_under_lock_after_preservation_before_commit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_root = tmp_path / "source"
    candidate = b"normalized-with-history"
    candidate_digest = hashlib.sha256(candidate).hexdigest()
    candidate_path = source_root / "normalized" / "sha256" / f"{candidate_digest}.bin"
    events: list[str] = []
    original_require_unchanged = ingestion._require_active_marker_unchanged
    original_replace = ingestion._atomic_replace

    def track_require_unchanged(
        actual_source_root: Path, current_path: Path, expected: bytes | None
    ) -> None:
        events.append("marker-reread")
        original_require_unchanged(actual_source_root, current_path, expected)

    def track_replace(root: Path, destination: Path, payload: bytes) -> None:
        events.append("replace")
        original_replace(root, destination, payload)

    def validate_history(
        actual_source_root: Path, actual_candidate: bytes, actual_started_at: str
    ) -> None:
        assert actual_source_root == source_root
        assert actual_candidate == candidate
        assert actual_started_at == "2026-07-12T18:30:00Z"
        assert candidate_path.read_bytes() == candidate
        assert (source_root / ".ingestion.lock").is_dir()
        events.append("history-validation")

    def validate_candidate(actual_candidate: bytes, previous: bytes | None) -> None:
        assert actual_candidate == candidate
        assert previous is None
        assert not candidate_path.exists()
        assert (source_root / ".ingestion.lock").is_dir()
        events.append("candidate-validation")

    monkeypatch.setattr(ingestion, "_require_active_marker_unchanged", track_require_unchanged)
    monkeypatch.setattr(ingestion, "_atomic_replace", track_replace)
    result = run_ingestion(
        root=tmp_path,
        source_id="source",
        fetch=lambda: b"raw-with-history",
        normalize=lambda _raw: candidate,
        validate_normalized=validate_candidate,
        validate_history=validate_history,
        clock=_clock,
        attempt_id="history-success",
    )

    assert events == [
        "candidate-validation",
        "history-validation",
        "marker-reread",
        "replace",
    ]
    assert result.normalized_path == candidate_path
    assert not (source_root / ".ingestion.lock").exists()


def test_history_validator_failure_preserves_current_and_prevents_replace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    initial = run_ingestion(
        root=tmp_path,
        source_id="source",
        fetch=lambda: b"raw-initial",
        normalize=lambda _raw: b"normalized-initial",
        clock=_clock,
        attempt_id="history-initial",
    )
    marker_before = initial.current_path.read_bytes()
    candidate = b"private-candidate-payload"
    candidate_digest = hashlib.sha256(candidate).hexdigest()
    candidate_path = tmp_path / "source" / "normalized" / "sha256" / f"{candidate_digest}.bin"
    replace_calls = 0
    secret = f"{tmp_path}/private-candidate-payload"
    original_replace = ingestion._atomic_replace

    def track_replace(root: Path, destination: Path, payload: bytes) -> None:
        nonlocal replace_calls
        replace_calls += 1
        original_replace(root, destination, payload)

    def reject_history(source_root: Path, actual_candidate: bytes, actual_started_at: str) -> None:
        assert source_root == tmp_path / "source"
        assert actual_candidate == candidate
        assert actual_started_at == "2026-07-12T18:30:00Z"
        assert candidate_path.read_bytes() == candidate
        assert (source_root / ".ingestion.lock").is_dir()
        raise ValueError(secret)

    monkeypatch.setattr(ingestion, "_atomic_replace", track_replace)
    with pytest.raises(IngestionRunError) as raised:
        run_ingestion(
            root=tmp_path,
            source_id="source",
            fetch=lambda: b"raw-candidate",
            normalize=lambda _raw: candidate,
            validate_history=reject_history,
            clock=_clock,
            attempt_id="history-rejected",
        )

    assert replace_calls == 0
    assert initial.current_path.read_bytes() == marker_before
    assert candidate_path.read_bytes() == candidate
    receipt_text = raised.value.receipt_path.read_text(encoding="utf-8")
    assert _receipt(raised.value.receipt_path)["error"] == {
        "message": "normalized artifact validation failed",
        "type": "ValueError",
    }
    assert secret not in receipt_text
    assert secret not in str(raised.value)
    assert secret not in "".join(traceback.format_exception(raised.value))
    assert not (tmp_path / "source" / ".ingestion.lock").exists()


@pytest.mark.parametrize("target_kind", ["raw", "normalized"])
def test_history_validator_cannot_mutate_preserved_candidate_before_commit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, target_kind: str
) -> None:
    initial = run_ingestion(
        root=tmp_path,
        source_id="source",
        fetch=lambda: b"raw-initial",
        normalize=lambda _raw: b"normalized-initial",
        clock=_clock,
        attempt_id=f"candidate-{target_kind}-initial",
    )
    marker_before = initial.current_path.read_bytes()
    raw = b"private-candidate-raw"
    normalized = b"private-candidate-normalized"
    target_payload = raw if target_kind == "raw" else normalized
    target_digest = hashlib.sha256(target_payload).hexdigest()
    target_directory = "raw" if target_kind == "raw" else "normalized"
    replace_calls = 0
    original_replace = ingestion._atomic_replace

    def track_replace(root: Path, destination: Path, payload: bytes) -> None:
        nonlocal replace_calls
        replace_calls += 1
        original_replace(root, destination, payload)

    def mutate_candidate(
        source_root: Path, actual_candidate: bytes, actual_started_at: str
    ) -> None:
        assert actual_candidate == normalized
        assert actual_started_at == "2026-07-12T18:30:00Z"
        target = source_root / target_directory / "sha256" / f"{target_digest}.bin"
        target.chmod(0o600)
        target.write_bytes(b"x" * len(target_payload))
        target.chmod(0o400)

    monkeypatch.setattr(ingestion, "_atomic_replace", track_replace)
    with pytest.raises(IngestionRunError) as raised:
        run_ingestion(
            root=tmp_path,
            source_id="source",
            fetch=lambda: raw,
            normalize=lambda _raw: normalized,
            validate_history=mutate_candidate,
            clock=_clock,
            attempt_id=f"candidate-{target_kind}-mutated",
        )

    assert replace_calls == 0
    assert initial.current_path.read_bytes() == marker_before
    failure = _receipt(raised.value.receipt_path)
    assert failure["error"] == {
        "message": "active marker commit failed",
        "type": "IngestionError",
    }
    assert failure["raw_sha256"] is None
    assert failure["raw_snapshot"] is None
    assert failure["normalized_sha256"] is None
    assert failure["normalized_path"] is None
    assert "private-candidate" not in raised.value.receipt_path.read_text(encoding="utf-8")
    assert not (tmp_path / "source" / ".ingestion.lock").exists()


@pytest.mark.parametrize("target_kind", ["raw", "normalized", "current"])
def test_history_validator_cannot_mutate_prior_active_state_before_commit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, target_kind: str
) -> None:
    initial = run_ingestion(
        root=tmp_path,
        source_id="source",
        fetch=lambda: b"raw-initial",
        normalize=lambda _raw: b"normalized-initial",
        clock=_clock,
        attempt_id=f"prior-{target_kind}-initial",
    )
    marker_before = initial.current_path.read_bytes()
    target = {
        "raw": initial.raw_snapshot,
        "normalized": initial.normalized_path,
        "current": initial.current_path,
    }[target_kind]
    original_payload = target.read_bytes()
    changed_payload = b"x" * len(original_payload)
    replace_calls = 0
    original_replace = ingestion._atomic_replace

    def track_replace(root: Path, destination: Path, payload: bytes) -> None:
        nonlocal replace_calls
        replace_calls += 1
        original_replace(root, destination, payload)

    def mutate_prior(_source_root: Path, _candidate: bytes, actual_started_at: str) -> None:
        assert actual_started_at == "2026-07-12T18:30:00Z"
        target.chmod(0o600)
        target.write_bytes(changed_payload)
        target.chmod(0o400)

    monkeypatch.setattr(ingestion, "_atomic_replace", track_replace)
    with pytest.raises(IngestionRunError) as raised:
        run_ingestion(
            root=tmp_path,
            source_id="source",
            fetch=lambda: b"raw-candidate",
            normalize=lambda _raw: b"normalized-candidate",
            validate_history=mutate_prior,
            clock=_clock,
            attempt_id=f"prior-{target_kind}-mutated",
        )

    assert replace_calls == 0
    expected_marker = changed_payload if target_kind == "current" else marker_before
    assert initial.current_path.read_bytes() == expected_marker
    assert _receipt(raised.value.receipt_path)["error"] == {
        "message": "active marker commit failed",
        "type": "IngestionError",
    }
    assert not (tmp_path / "source" / ".ingestion.lock").exists()


def test_history_validator_is_optional_for_backward_compatible_calls(
    tmp_path: Path,
) -> None:
    result = run_ingestion(
        root=tmp_path,
        source_id="source",
        fetch=lambda: b"raw-without-history-validator",
        normalize=lambda raw: raw,
        clock=_clock,
        attempt_id="history-optional",
    )

    assert result.current_path.read_bytes() == result.receipt_path.read_bytes()


def test_activated_validator_runs_under_lock_after_replace_before_success_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_root = tmp_path / "source"
    candidate = b"normalized-activated-candidate"
    expected_receipt = source_root / "receipts" / "activated-order.json"
    events: list[str] = []
    original_replace = ingestion._atomic_replace
    original_install = ingestion._install_immutable

    def track_replace(root: Path, destination: Path, payload: bytes) -> None:
        original_replace(root, destination, payload)
        events.append("replace")

    def track_install(root: Path, destination: Path, payload: bytes) -> None:
        if destination == expected_receipt:
            events.append("receipt")
        original_install(root, destination, payload)

    def validate_activated(
        actual_source_root: Path, actual_candidate: bytes, success_marker: bytes
    ) -> None:
        assert actual_source_root == source_root
        assert actual_candidate == candidate
        assert (source_root / ".ingestion.lock").is_dir()
        assert (source_root / "normalized" / "current.json").read_bytes() == success_marker
        assert not expected_receipt.exists()
        marker = json.loads(success_marker)
        assert marker["status"] == "success"
        assert marker["attempt_id"] == "activated-order"
        events.append("activated-validation")

    monkeypatch.setattr(ingestion, "_atomic_replace", track_replace)
    monkeypatch.setattr(ingestion, "_install_immutable", track_install)
    result = run_ingestion(
        root=tmp_path,
        source_id="source",
        fetch=lambda: b"raw-activated-candidate",
        normalize=lambda _raw: candidate,
        validate_activated=validate_activated,
        clock=_clock,
        attempt_id="activated-order",
    )

    assert events == ["replace", "activated-validation", "receipt"]
    assert result.current_path.read_bytes() == result.receipt_path.read_bytes()
    assert not (source_root / ".ingestion.lock").exists()


def test_first_activated_validator_failure_removes_current_and_is_redacted(
    tmp_path: Path,
) -> None:
    secret = f"{tmp_path}/private-activated-validator-secret"

    def reject_activated(source_root: Path, candidate: bytes, success_marker: bytes) -> None:
        assert candidate == b"normalized-candidate"
        assert (source_root / "normalized" / "current.json").read_bytes() == success_marker
        assert (source_root / ".ingestion.lock").is_dir()
        raise ValueError(secret)

    with pytest.raises(IngestionRunError) as raised:
        run_ingestion(
            root=tmp_path,
            source_id="source",
            fetch=lambda: b"raw-candidate",
            normalize=lambda _raw: b"normalized-candidate",
            validate_activated=reject_activated,
            clock=_clock,
            attempt_id="activated-first-failure",
        )

    source_root = tmp_path / "source"
    assert not (source_root / "normalized" / "current.json").exists()
    failure = _receipt(raised.value.receipt_path)
    assert failure["status"] == "failure"
    assert failure["activated"] is False
    assert failure["error"] == {
        "message": "activated artifact validation failed",
        "type": "ValueError",
    }
    assert raised.value.receipt_path.name == "activated-first-failure.json"
    assert secret not in raised.value.receipt_path.read_text(encoding="utf-8")
    assert secret not in str(raised.value)
    assert secret not in "".join(traceback.format_exception(raised.value))
    assert not (source_root / ".ingestion.lock").exists()


def test_later_activated_validator_failure_restores_exact_prior_marker(
    tmp_path: Path,
) -> None:
    initial = run_ingestion(
        root=tmp_path,
        source_id="source",
        fetch=lambda: b"raw-initial",
        normalize=lambda _raw: b"normalized-initial",
        clock=_clock,
        attempt_id="activated-prior",
    )
    marker_before = initial.current_path.read_bytes()

    def reject_activated(_source_root: Path, _candidate: bytes, _marker: bytes) -> None:
        raise RuntimeError("private post-activation detail")

    with pytest.raises(IngestionRunError) as raised:
        run_ingestion(
            root=tmp_path,
            source_id="source",
            fetch=lambda: b"raw-replacement",
            normalize=lambda _raw: b"normalized-replacement",
            validate_activated=reject_activated,
            clock=_clock,
            attempt_id="activated-later-failure",
        )

    assert initial.current_path.read_bytes() == marker_before
    failure = _receipt(raised.value.receipt_path)
    assert failure["status"] == "failure"
    assert failure["activated"] is False
    assert failure["error"] == {
        "message": "activated artifact validation failed",
        "type": "Exception",
    }
    assert not (tmp_path / "source" / "receipts" / "activated-later-failure.failure.json").exists()
    assert not (tmp_path / "source" / ".ingestion.lock").exists()


def test_activated_validator_mutation_is_detected_and_candidate_refs_are_cleared(
    tmp_path: Path,
) -> None:
    initial = run_ingestion(
        root=tmp_path,
        source_id="source",
        fetch=lambda: b"raw-initial",
        normalize=lambda _raw: b"normalized-initial",
        clock=_clock,
        attempt_id="activated-mutation-prior",
    )
    marker_before = initial.current_path.read_bytes()

    def mutate_candidate(source_root: Path, candidate: bytes, _success_marker: bytes) -> None:
        digest = hashlib.sha256(candidate).hexdigest()
        target = source_root / "normalized" / "sha256" / f"{digest}.bin"
        target.chmod(0o600)
        target.write_bytes(b"x" * len(candidate))
        target.chmod(0o400)

    with pytest.raises(IngestionRunError) as raised:
        run_ingestion(
            root=tmp_path,
            source_id="source",
            fetch=lambda: b"raw-candidate",
            normalize=lambda _raw: b"normalized-candidate",
            validate_activated=mutate_candidate,
            clock=_clock,
            attempt_id="activated-mutation",
        )

    assert initial.current_path.read_bytes() == marker_before
    failure = _receipt(raised.value.receipt_path)
    assert failure["error"] == {
        "message": "activated artifact validation failed",
        "type": "IngestionError",
    }
    assert failure["raw_sha256"] is None
    assert failure["raw_snapshot"] is None
    assert failure["normalized_sha256"] is None
    assert failure["normalized_path"] is None
    assert not (tmp_path / "source" / ".ingestion.lock").exists()


def test_activated_validator_is_optional_for_backward_compatible_calls(
    tmp_path: Path,
) -> None:
    result = run_ingestion(
        root=tmp_path,
        source_id="source",
        fetch=lambda: b"raw-without-activated-validator",
        normalize=lambda raw: raw,
        clock=_clock,
        attempt_id="activated-optional",
    )

    assert result.current_path.read_bytes() == result.receipt_path.read_bytes()


def test_invalid_payload_limits_fail_before_lock_or_fetch(tmp_path: Path) -> None:
    called = False

    def fetch() -> bytes:
        nonlocal called
        called = True
        return b"raw"

    with pytest.raises(IngestionError, match="must be positive"):
        run_ingestion(
            root=tmp_path,
            source_id="source",
            fetch=fetch,
            normalize=lambda raw: raw,
            max_raw_bytes=0,
            clock=_clock,
        )
    assert called is False
    assert not (tmp_path / "source" / ".ingestion.lock").exists()


def test_rollback_failure_is_truthful_redacted_and_retains_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    secret = "postgres://operator:secret@example.test/private"
    original_install = ingestion._install_immutable
    receipt_writes = 0

    def fail_first_receipt(source_root: Path, destination: Path, payload: bytes) -> None:
        nonlocal receipt_writes
        if destination.parent.name == "receipts":
            receipt_writes += 1
            if receipt_writes == 1:
                raise RuntimeError(secret)
        original_install(source_root, destination, payload)

    def fail_rollback(_source_root: Path, _normalized_path: Path, _previous: bytes | None) -> None:
        raise OSError(secret)

    monkeypatch.setattr(ingestion, "_rollback_activation", fail_rollback)
    monkeypatch.setattr(ingestion, "_install_immutable", fail_first_receipt)
    with pytest.raises(IngestionRunError, match="operator intervention") as raised:
        run_ingestion(
            root=tmp_path,
            source_id="source",
            fetch=lambda: b"raw",
            normalize=lambda _raw: b"candidate",
            clock=_clock,
            attempt_id="rollback-failure",
        )

    receipt_text = raised.value.receipt_path.read_text(encoding="utf-8")
    receipt = _receipt(raised.value.receipt_path)
    assert raised.value.receipt_path.name == "rollback-failure.failure.json"
    assert secret not in receipt_text
    assert secret not in str(raised.value)
    assert secret not in "".join(traceback.format_exception(raised.value))
    assert receipt["status"] == "failure"
    assert receipt["activated"] is True
    assert receipt["error"] == {
        "message": "success receipt finalization failed; rollback also failed",
        "type": "RollbackError",
    }
    marker = _receipt(tmp_path / "source" / "normalized" / "current.json")
    assert marker["normalized_sha256"] == hashlib.sha256(b"candidate").hexdigest()
    lock_path = tmp_path / "source" / ".ingestion.lock"
    assert lock_path.is_dir()

    candidate_marker = (tmp_path / "source" / "normalized" / "current.json").read_bytes()
    lock_path.rmdir()
    recovered = run_ingestion(
        root=tmp_path,
        source_id="source",
        fetch=lambda: b"raw-after-recovery",
        normalize=lambda _raw: b"normalized-after-recovery",
        clock=_clock,
        attempt_id="after-recovery",
    )

    committed_history = tmp_path / "source" / "receipts" / "rollback-failure.json"
    assert committed_history.read_bytes() == candidate_marker
    assert _receipt(committed_history)["status"] == "success"
    assert _receipt(raised.value.receipt_path)["status"] == "failure"
    assert recovered.normalized_path.read_bytes() == b"normalized-after-recovery"
    candidate_path = marker["normalized_path"]
    assert isinstance(candidate_path, str)
    assert (tmp_path / "source" / candidate_path).read_bytes() == b"candidate"


def test_two_successes_keep_historical_receipts_bound_to_immutable_payloads(
    tmp_path: Path,
) -> None:
    first = run_ingestion(
        root=tmp_path,
        source_id="source",
        fetch=lambda: b"raw-v1",
        normalize=lambda _raw: b"normalized-v1",
        clock=_clock,
        attempt_id="first",
    )
    first_receipt_bytes = first.receipt_path.read_bytes()
    second = run_ingestion(
        root=tmp_path,
        source_id="source",
        fetch=lambda: b"raw-v2",
        normalize=lambda _raw: b"normalized-v2",
        clock=_clock,
        attempt_id="second",
    )

    for result, expected in ((first, b"normalized-v1"), (second, b"normalized-v2")):
        receipt = _receipt(result.receipt_path)
        relative = receipt["normalized_path"]
        assert isinstance(relative, str)
        assert relative != "normalized/current.json"
        artifact = tmp_path / "source" / relative
        assert artifact.read_bytes() == expected
        assert hashlib.sha256(expected).hexdigest() == receipt["normalized_sha256"]
    assert first.receipt_path.read_bytes() == first_receipt_bytes
    assert second.current_path.read_bytes() == second.receipt_path.read_bytes()

    active = ingestion._load_active_marker(tmp_path / "source", second.current_path, "source")
    assert active is not None
    assert active.normalized == b"normalized-v2"
    assert active.receipt["raw_sha256"] == hashlib.sha256(b"raw-v2").hexdigest()


@pytest.mark.parametrize("interrupt_stage", ["commit", "finalization"])
def test_base_exception_leaves_a_valid_self_contained_marker_and_releases_lock(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    interrupt_stage: str,
) -> None:
    source_root = tmp_path / "source"
    original_replace = ingestion._atomic_replace
    original_install = ingestion._install_immutable

    if interrupt_stage == "commit":

        def interrupt_after_replace(root: Path, destination: Path, payload: bytes) -> None:
            original_replace(root, destination, payload)
            raise KeyboardInterrupt

        monkeypatch.setattr(ingestion, "_atomic_replace", interrupt_after_replace)
        expected_exception: type[BaseException] = KeyboardInterrupt
    else:

        def interrupt_receipt_finalization(root: Path, destination: Path, payload: bytes) -> None:
            if destination.parent.name == "receipts":
                raise SystemExit(23)
            original_install(root, destination, payload)

        monkeypatch.setattr(ingestion, "_install_immutable", interrupt_receipt_finalization)
        expected_exception = SystemExit

    with pytest.raises(expected_exception):
        run_ingestion(
            root=tmp_path,
            source_id="source",
            fetch=lambda: b"raw",
            normalize=lambda _raw: b"normalized",
            clock=_clock,
            attempt_id=f"interrupted-{interrupt_stage}",
        )

    current_path = source_root / "normalized" / "current.json"
    marker = _receipt(current_path)
    normalized_path = marker["normalized_path"]
    raw_path = marker["raw_snapshot"]
    assert isinstance(normalized_path, str)
    assert isinstance(raw_path, str)
    assert (source_root / normalized_path).read_bytes() == b"normalized"
    assert (source_root / raw_path).read_bytes() == b"raw"
    assert not (source_root / ".ingestion.lock").exists()
    assert not (source_root / "receipts" / f"interrupted-{interrupt_stage}.json").exists()


def test_ingestion_tree_defaults_to_private_permissions_and_tightens_owned_dirs(
    tmp_path: Path,
) -> None:
    tmp_path.chmod(0o755)
    source_root = tmp_path / "source"
    (source_root / "raw").mkdir(parents=True, mode=0o755)
    (source_root / "raw").chmod(0o755)

    result = run_ingestion(
        root=tmp_path,
        source_id="source",
        fetch=lambda: b"raw",
        normalize=lambda raw: raw,
        clock=_clock,
        attempt_id="private",
    )

    for path in source_root.rglob("*"):
        mode = stat.S_IMODE(path.stat(follow_symlinks=False).st_mode)
        assert mode & 0o077 == 0, path
        if path.is_dir():
            assert mode == 0o700
        else:
            assert mode == 0o400
    assert stat.S_IMODE(tmp_path.stat().st_mode) == 0o700
    assert stat.S_IMODE(result.current_path.stat().st_mode) == 0o400


def test_next_preflight_archives_an_interrupted_committed_marker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original_install = ingestion._install_immutable

    def interrupt_receipt_finalization(root: Path, destination: Path, payload: bytes) -> None:
        if destination.parent.name == "receipts":
            raise KeyboardInterrupt
        original_install(root, destination, payload)

    monkeypatch.setattr(ingestion, "_install_immutable", interrupt_receipt_finalization)
    with pytest.raises(KeyboardInterrupt):
        run_ingestion(
            root=tmp_path,
            source_id="source",
            fetch=lambda: b"raw-v1",
            normalize=lambda _raw: b"normalized-v1",
            clock=_clock,
            attempt_id="interrupted-first",
        )

    current_path = tmp_path / "source" / "normalized" / "current.json"
    first_marker = current_path.read_bytes()
    first_history = tmp_path / "source" / "receipts" / "interrupted-first.json"
    assert not first_history.exists()

    monkeypatch.setattr(ingestion, "_install_immutable", original_install)
    run_ingestion(
        root=tmp_path,
        source_id="source",
        fetch=lambda: b"raw-v2",
        normalize=lambda _raw: b"normalized-v2",
        clock=_clock,
        attempt_id="second",
    )

    assert first_history.read_bytes() == first_marker
    assert (
        _receipt(first_history)["normalized_sha256"] == hashlib.sha256(b"normalized-v1").hexdigest()
    )
