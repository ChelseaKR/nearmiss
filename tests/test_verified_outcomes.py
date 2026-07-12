"""Adversarial tests for read-only active FARS lineage verification."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import pytest

import nearmiss.verified_outcomes as verified_outcomes
from nearmiss.adapters.fars import FarsAdapter, read_export_bytes
from nearmiss.ingestion import IngestionRunError, run_ingestion
from nearmiss.outcome_artifacts import build_outcome_artifact, canonical_outcome_artifact_bytes
from nearmiss.verified_outcomes import (
    VerificationError,
    VerifiedOutcomeEvidence,
    verify_active_fars,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "fars" / "accident.csv"
URL = "https://static.nhtsa.gov/nhtsa/downloads/FARS/2023/National/FARS2023.zip"
FIRST = dt.datetime(2026, 7, 12, 18, 0, tzinfo=dt.UTC)
SECOND = dt.datetime(2026, 7, 12, 19, 0, tzinfo=dt.UTC)
THIRD = dt.datetime(2026, 7, 12, 20, 0, tzinfo=dt.UTC)


def _artifact(
    raw: bytes,
    *,
    year: int = 2023,
    allow_record_regression: bool = False,
    allow_year_regression: bool = False,
) -> dict[str, object]:
    outcomes, provenance = FarsAdapter().parse(read_export_bytes(raw), release_status="final")
    return build_outcome_artifact(
        outcomes,
        provenance,
        expected_year=year,
        distribution_url=URL.replace("/2023/", f"/{year}/"),
        max_invalid_fraction=0.34,
        allow_record_regression=allow_record_regression,
        allow_year_regression=allow_year_regression,
    )


def _ingest(
    tmp_path: Path,
    *,
    raw: bytes | None = None,
    attempt_id: str = "attempt-1",
    now: dt.datetime = FIRST,
    year: int = 2023,
    allow_record_regression: bool = False,
    allow_year_regression: bool = False,
) -> tuple[Path, Any, dict[str, object]]:
    payload = FIXTURE.read_bytes() if raw is None else raw
    artifact = _artifact(
        payload,
        year=year,
        allow_record_regression=allow_record_regression,
        allow_year_regression=allow_year_regression,
    )
    root = tmp_path / "store"
    result = run_ingestion(
        root=root,
        source_id="fars",
        fetch=lambda: payload,
        normalize=lambda _raw: canonical_outcome_artifact_bytes(artifact),
        attempt_id=attempt_id,
        clock=lambda: now,
    )
    return root, result, artifact


def _canonical(value: dict[str, object]) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def _replace_file(path: Path, payload: bytes) -> None:
    path.chmod(0o600)
    path.write_bytes(payload)
    path.chmod(0o400)


def _install_file(path: Path, payload: bytes) -> None:
    path.write_bytes(payload)
    path.chmod(0o400)


def _receipt(root: Path) -> tuple[dict[str, object], Path, Path]:
    current = root / "fars" / "normalized" / "current.json"
    value = cast(dict[str, object], json.loads(current.read_bytes()))
    history = root / "fars" / "receipts" / f"{value['attempt_id']}.json"
    return value, current, history


def _three_ingests(tmp_path: Path) -> tuple[Path, Any, Any, Any]:
    root, first, _first_artifact = _ingest(tmp_path, attempt_id="attempt-1")
    second_raw = FIXTURE.read_bytes().replace(b"38.544907", b"38.544307", 1)
    _root, second, _second_artifact = _ingest(
        tmp_path, raw=second_raw, attempt_id="attempt-2", now=SECOND
    )
    third_raw = FIXTURE.read_bytes().replace(b"38.544907", b"38.544507", 1)
    _root, third, _third_artifact = _ingest(
        tmp_path, raw=third_raw, attempt_id="attempt-3", now=THIRD
    )
    return root, first, second, third


def _replace_receipt_pair(root: Path, receipt: dict[str, object]) -> None:
    _value, current, history = _receipt(root)
    payload = _canonical(receipt)
    _replace_file(current, payload)
    _replace_file(history, payload)


def test_verifies_real_ingestion_transaction_and_returns_only_safe_aggregates(
    tmp_path: Path,
) -> None:
    root, result, _artifact_value = _ingest(tmp_path)
    evidence = verify_active_fars(root)
    assert evidence.source_id == "fars"
    assert evidence.dataset_year == 2023
    assert evidence.adapter_version == "1.0.0"
    assert evidence.release_status == "final"
    assert evidence.records_read == 3
    assert evidence.records_accepted == 2
    assert evidence.records_rejected == 1
    assert evidence.raw_sha256 == result.raw_sha256
    assert evidence.normalized_sha256 == result.normalized_sha256
    assert evidence.attempt_id == "attempt-1"
    assert evidence.receipt_id == "attempt-1"
    assert not hasattr(evidence, "outcomes")
    assert not hasattr(evidence, "root")


@pytest.mark.parametrize("target", ["raw", "normalized"])
def test_rejects_content_tampering(tmp_path: Path, target: str) -> None:
    root, result, _artifact_value = _ingest(tmp_path)
    path = result.raw_snapshot if target == "raw" else result.normalized_path
    _replace_file(path, path.read_bytes() + b"tamper")
    with pytest.raises(VerificationError, match="hash mismatch"):
        verify_active_fars(root)


def test_rejects_active_history_substitution_and_missing_history(tmp_path: Path) -> None:
    root, _result, _artifact_value = _ingest(tmp_path)
    receipt, _current, history = _receipt(root)
    changed = dict(receipt)
    changed["started_at"] = "2026-07-12T17:59:00Z"
    _replace_file(history, _canonical(changed))
    with pytest.raises(VerificationError, match="active and historical"):
        verify_active_fars(root)

    history.unlink()
    with pytest.raises(VerificationError):
        verify_active_fars(root)


def test_rejects_receipt_traversal_even_when_current_and_history_match(tmp_path: Path) -> None:
    root, _result, _artifact_value = _ingest(tmp_path)
    receipt, _current, _history = _receipt(root)
    receipt["raw_snapshot"] = "../../outside.bin"
    _replace_receipt_pair(root, receipt)
    with pytest.raises(VerificationError, match="receipt validation"):
        verify_active_fars(root)


@pytest.mark.skipif(not hasattr(os, "O_NOFOLLOW"), reason="requires POSIX O_NOFOLLOW")
def test_rejects_symlinked_artifact_and_source_directory(tmp_path: Path) -> None:
    root, result, _artifact_value = _ingest(tmp_path)
    target = tmp_path / "target.bin"
    target.write_bytes(result.raw_snapshot.read_bytes())
    target.chmod(0o400)
    result.raw_snapshot.unlink()
    result.raw_snapshot.symlink_to(target)
    with pytest.raises(VerificationError, match="filesystem"):
        verify_active_fars(root)

    other = tmp_path / "other-root"
    other.mkdir(mode=0o700)
    alias = tmp_path / "alias-root"
    alias.mkdir(mode=0o700)
    (alias / "fars").symlink_to(other)
    with pytest.raises(VerificationError, match="filesystem"):
        verify_active_fars(alias)


def test_rejects_unsafe_mode_and_hardlinked_file(tmp_path: Path) -> None:
    root, result, _artifact_value = _ingest(tmp_path)
    result.normalized_path.chmod(0o600)
    with pytest.raises(VerificationError, match="filesystem"):
        verify_active_fars(root)

    result.normalized_path.chmod(0o400)
    os.link(result.normalized_path, tmp_path / "extra-link")
    with pytest.raises(VerificationError, match="filesystem"):
        verify_active_fars(root)


def test_rejects_duplicate_key_receipt_and_nonfinite_artifact_json(tmp_path: Path) -> None:
    root, result, _artifact_value = _ingest(tmp_path)
    receipt, current, history = _receipt(root)
    duplicate = _canonical(receipt).replace(
        b'  "source_id": "fars",\n',
        b'  "source_id": "fars",\n  "source_id": "fars",\n',
    )
    _replace_file(current, duplicate)
    _replace_file(history, duplicate)
    with pytest.raises(VerificationError, match="JSON decoding"):
        verify_active_fars(root)

    _replace_receipt_pair(root, receipt)
    invalid = result.normalized_path.read_bytes().replace(
        b'"max_invalid_fraction":0.34', b'"max_invalid_fraction":NaN'
    )
    digest = hashlib.sha256(invalid).hexdigest()
    invalid_path = result.normalized_path.parent / f"{digest}.bin"
    _install_file(invalid_path, invalid)
    receipt["normalized_sha256"] = digest
    receipt["normalized_path"] = f"normalized/sha256/{digest}.bin"
    _replace_receipt_pair(root, receipt)
    with pytest.raises(VerificationError, match="JSON decoding"):
        verify_active_fars(root)


def test_rejects_self_consistent_artifact_not_derived_from_raw(tmp_path: Path) -> None:
    root, result, _artifact_value = _ingest(tmp_path)
    other_raw = FIXTURE.read_bytes().replace(b"100001", b"200001", 1)
    outcomes, other_provenance = FarsAdapter().parse(
        read_export_bytes(other_raw), release_status="final"
    )
    forged_provenance = replace(other_provenance, input_sha256=result.raw_sha256)
    forged = build_outcome_artifact(
        outcomes,
        forged_provenance,
        expected_year=2023,
        distribution_url=URL,
        max_invalid_fraction=0.34,
    )
    forged_bytes = canonical_outcome_artifact_bytes(forged)
    digest = hashlib.sha256(forged_bytes).hexdigest()
    forged_path = result.normalized_path.parent / f"{digest}.bin"
    _install_file(forged_path, forged_bytes)
    receipt, _current, _history = _receipt(root)
    receipt["normalized_sha256"] = digest
    receipt["normalized_path"] = f"normalized/sha256/{digest}.bin"
    _replace_receipt_pair(root, receipt)
    with pytest.raises(VerificationError, match="deterministic replay"):
        verify_active_fars(root)


def test_refuses_active_lock_and_noncanonical_history_filename(tmp_path: Path) -> None:
    root, _result, _artifact_value = _ingest(tmp_path)
    lock = root / "fars" / ".ingestion.lock"
    lock.mkdir(mode=0o700)
    with pytest.raises(VerificationError, match="locked"):
        verify_active_fars(root)
    lock.rmdir()

    stray = root / "fars" / "receipts" / "not canonical.json"
    _install_file(stray, b"{}")
    with pytest.raises(VerificationError, match="filename"):
        verify_active_fars(root)


def test_current_must_be_latest_success_but_later_failure_is_allowed(tmp_path: Path) -> None:
    root, _result, _artifact_value = _ingest(tmp_path)
    receipt, _current, _history = _receipt(root)
    later = dict(receipt)
    later["attempt_id"] = "attempt-2"
    later["started_at"] = "2026-07-12T19:00:00Z"
    later["completed_at"] = "2026-07-12T19:00:00Z"
    _install_file(root / "fars" / "receipts" / "attempt-2.json", _canonical(later))
    with pytest.raises(VerificationError, match="latest successful"):
        verify_active_fars(root)

    (root / "fars" / "receipts" / "attempt-2.json").unlink()

    def fail_fetch() -> bytes:
        raise RuntimeError("private")

    with pytest.raises(IngestionRunError):
        run_ingestion(
            root=root,
            source_id="fars",
            fetch=fail_fetch,
            normalize=lambda raw: raw,
            attempt_id="attempt-failure",
            clock=lambda: SECOND,
        )
    assert verify_active_fars(root).attempt_id == "attempt-1"


def test_previous_success_and_blob_are_required(tmp_path: Path) -> None:
    root, first_result, _first_artifact = _ingest(tmp_path)
    second_raw = FIXTURE.read_bytes().replace(b"38.5442", b"38.5443", 1)
    _root, _second_result, _second_artifact = _ingest(
        tmp_path,
        raw=second_raw,
        attempt_id="attempt-2",
        now=SECOND,
    )
    assert verify_active_fars(root).attempt_id == "attempt-2"
    first_result.normalized_path.unlink()
    with pytest.raises(VerificationError):
        verify_active_fars(root)


def test_current_receipt_must_link_the_immediate_successful_predecessor(tmp_path: Path) -> None:
    root, _first_result, _first_artifact = _ingest(tmp_path)
    second_raw = FIXTURE.read_bytes().replace(b"38.5442", b"38.5443", 1)
    _ingest(tmp_path, raw=second_raw, attempt_id="attempt-2", now=SECOND)
    receipt, _current, _history = _receipt(root)
    receipt["previous_normalized_sha256"] = None
    _replace_receipt_pair(root, receipt)
    with pytest.raises(VerificationError, match="predecessor link"):
        verify_active_fars(root)


@pytest.mark.parametrize("allowed", [False, True])
def test_year_regression_requires_recorded_authorization(tmp_path: Path, allowed: bool) -> None:
    root, _first_result, _first_artifact = _ingest(tmp_path)
    older_raw = FIXTURE.read_bytes().replace(b",2023,", b",2022,")
    _ingest(
        tmp_path,
        raw=older_raw,
        attempt_id="attempt-2",
        now=SECOND,
        year=2022,
        allow_year_regression=allowed,
    )
    if allowed:
        assert verify_active_fars(root).dataset_year == 2022
    else:
        with pytest.raises(VerificationError, match="dataset year regressed"):
            verify_active_fars(root)


@pytest.mark.parametrize("allowed", [False, True])
def test_record_regression_requires_recorded_authorization(tmp_path: Path, allowed: bool) -> None:
    root, _first_result, _first_artifact = _ingest(tmp_path)
    rows = FIXTURE.read_bytes().splitlines()
    smaller_raw = b"\n".join(rows[:2]) + b"\n"
    _ingest(
        tmp_path,
        raw=smaller_raw,
        attempt_id="attempt-2",
        now=SECOND,
        allow_record_regression=allowed,
    )
    if allowed:
        assert verify_active_fars(root).records_accepted == 1
    else:
        with pytest.raises(VerificationError, match="accepted-record count regressed"):
            verify_active_fars(root)


def test_forged_predecessor_cannot_bypass_record_regression_gate(tmp_path: Path) -> None:
    root, first_result, _first_artifact = _ingest(tmp_path, attempt_id="one")
    rows = FIXTURE.read_bytes().splitlines()
    smaller_raw = b"\n".join(rows[:2]) + b"\n"
    _ingest(tmp_path, raw=smaller_raw, attempt_id="two", now=SECOND)
    with pytest.raises(VerificationError, match="accepted-record count regressed"):
        verify_active_fars(root)

    outcomes, smaller_provenance = FarsAdapter().parse(
        read_export_bytes(smaller_raw), release_status="final"
    )
    forged_provenance = replace(smaller_provenance, input_sha256=first_result.raw_sha256)
    forged = build_outcome_artifact(
        outcomes,
        forged_provenance,
        expected_year=2023,
        distribution_url=URL,
        max_invalid_fraction=0.34,
    )
    forged_bytes = canonical_outcome_artifact_bytes(forged)
    forged_digest = hashlib.sha256(forged_bytes).hexdigest()
    _install_file(first_result.normalized_path.parent / f"{forged_digest}.bin", forged_bytes)

    first_history = root / "fars" / "receipts" / "one.json"
    first_receipt = cast(dict[str, object], json.loads(first_history.read_bytes()))
    first_receipt["normalized_sha256"] = forged_digest
    first_receipt["normalized_path"] = f"normalized/sha256/{forged_digest}.bin"
    _replace_file(first_history, _canonical(first_receipt))

    current_receipt, _current, _current_history = _receipt(root)
    current_receipt["previous_normalized_sha256"] = forged_digest
    _replace_receipt_pair(root, current_receipt)

    with pytest.raises(VerificationError, match="deterministic replay"):
        verify_active_fars(root)


def test_error_messages_do_not_leak_paths_or_payloads(tmp_path: Path) -> None:
    secret_root = tmp_path / "secret-token-root"
    secret_root.mkdir(mode=0o700)
    with pytest.raises(VerificationError) as raised:
        verify_active_fars(secret_root)
    assert "secret-token-root" not in str(raised.value)


@pytest.mark.parametrize("limit_name", ["_MAX_RAW_BYTES", "_MAX_NORMALIZED_BYTES"])
def test_large_artifacts_are_rejected_before_unbounded_allocation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, limit_name: str
) -> None:
    root, _result, _artifact_value = _ingest(tmp_path)
    monkeypatch.setattr(f"nearmiss.verified_outcomes.{limit_name}", 1)
    with pytest.raises(VerificationError, match="size limit"):
        verify_active_fars(root)


def test_fails_closed_without_secure_posix_primitives(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, _result, _artifact_value = _ingest(tmp_path)
    monkeypatch.setattr(os, "supports_dir_fd", set())
    with pytest.raises(VerificationError, match="secure POSIX"):
        verify_active_fars(root)


def test_three_success_chain_rejects_deleted_oldest_generation(tmp_path: Path) -> None:
    root, first, _second, _third = _three_ingests(tmp_path)
    assert verify_active_fars(root).attempt_id == "attempt-3"
    first.raw_snapshot.unlink()
    with pytest.raises(VerificationError, match="filesystem"):
        verify_active_fars(root)


def test_three_success_chain_replays_and_rejects_forged_oldest_generation(
    tmp_path: Path,
) -> None:
    root, first, _second, _third = _three_ingests(tmp_path)
    other_raw = FIXTURE.read_bytes().replace(b"100001", b"900001", 1)
    outcomes, provenance = FarsAdapter().parse(read_export_bytes(other_raw), release_status="final")
    forged_provenance = replace(provenance, input_sha256=first.raw_sha256)
    forged = build_outcome_artifact(
        outcomes,
        forged_provenance,
        expected_year=2023,
        distribution_url=URL,
        max_invalid_fraction=0.34,
    )
    forged_bytes = canonical_outcome_artifact_bytes(forged)
    forged_digest = hashlib.sha256(forged_bytes).hexdigest()
    _install_file(first.normalized_path.parent / f"{forged_digest}.bin", forged_bytes)

    first_history = root / "fars" / "receipts" / "attempt-1.json"
    first_receipt = cast(dict[str, object], json.loads(first_history.read_bytes()))
    first_receipt["normalized_sha256"] = forged_digest
    first_receipt["normalized_path"] = f"normalized/sha256/{forged_digest}.bin"
    _replace_file(first_history, _canonical(first_receipt))
    second_history = root / "fars" / "receipts" / "attempt-2.json"
    second_receipt = cast(dict[str, object], json.loads(second_history.read_bytes()))
    second_receipt["previous_normalized_sha256"] = forged_digest
    _replace_file(second_history, _canonical(second_receipt))

    with pytest.raises(VerificationError, match="deterministic replay"):
        verify_active_fars(root)


def test_three_success_chain_rejects_broken_middle_edge(tmp_path: Path) -> None:
    root, first, _second, _third = _three_ingests(tmp_path)
    receipt, _current, _history = _receipt(root)
    receipt["previous_normalized_sha256"] = first.normalized_sha256
    _replace_receipt_pair(root, receipt)
    with pytest.raises(VerificationError, match="predecessor link"):
        verify_active_fars(root)


def test_repeated_identical_generations_reuse_one_bounded_artifact_pair(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, _first, _artifact_value = _ingest(tmp_path, attempt_id="attempt-1", now=FIRST)
    _ingest(tmp_path, attempt_id="attempt-2", now=SECOND)
    _ingest(tmp_path, attempt_id="attempt-3", now=THIRD)
    original = verified_outcomes._read_file
    bin_reads: list[str] = []

    def observe(parent: int, name: str, *, maximum: int) -> tuple[bytes, str]:
        if name.endswith(".bin"):
            bin_reads.append(name)
        return original(parent, name, maximum=maximum)

    monkeypatch.setattr(verified_outcomes, "_read_file", observe)
    assert verify_active_fars(root).attempt_id == "attempt-3"
    assert len(bin_reads) == 2


def test_receipt_chronology_is_validated_before_history_ordering(tmp_path: Path) -> None:
    root, _result, _artifact_value = _ingest(tmp_path)
    receipt, _current, _history = _receipt(root)
    receipt["started_at"] = "2026-07-12T19:00:00Z"
    receipt["completed_at"] = "2026-07-12T18:00:00Z"
    _replace_receipt_pair(root, receipt)
    with pytest.raises(VerificationError, match="chronology"):
        verify_active_fars(root)


def test_evidence_requires_internal_proof_and_exports_only_safe_fields(tmp_path: Path) -> None:
    root, _result, _artifact_value = _ingest(tmp_path)
    evidence = verify_active_fars(root)
    exported = evidence.as_dict()
    assert exported["attempt_id"] == evidence.attempt_id
    assert "receipt_id" not in exported
    assert all("proof" not in key for key in exported)
    with pytest.raises(VerificationError, match="internal proof"):
        VerifiedOutcomeEvidence(
            source_id="fars",
            dataset_year=2023,
            adapter_version="1.0.0",
            release_status="final",
            records_read=3,
            records_accepted=2,
            records_rejected=1,
            raw_sha256="a" * 64,
            normalized_sha256="b" * 64,
            attempt_id="forged",
            _proof_token=object(),
        )
