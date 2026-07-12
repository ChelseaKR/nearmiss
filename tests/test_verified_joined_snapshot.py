"""Private snapshot handoff tests for the active joined-FARS verifier."""

from __future__ import annotations

import dataclasses
import datetime as dt
import hashlib
import io
import json
import os
import zipfile
from pathlib import Path
from typing import Any

import pytest

import nearmiss.verified_outcomes as verifier
from nearmiss.adapters.fars_joined import collect_joined, read_joined_export_bytes
from nearmiss.ingestion import run_ingestion
from nearmiss.joined_outcome_artifacts import (
    build_joined_outcome_artifact,
    canonical_joined_outcome_artifact_bytes,
)
from nearmiss.verified_outcomes import VerificationError, verify_active_fars_joined

REPOSITORY = Path(__file__).resolve().parents[1]
ACCIDENT = (
    (REPOSITORY / "tests" / "fixtures" / "fars" / "accident.csv")
    .read_bytes()
    .replace(b",2023,", b",2024,")
)
PERSON = b"""STATE,ST_CASE,VEH_NO,PER_NO,PER_TYP,INJ_SEV,BODY_TYP
6,100001,1,1,1,4,4
6,100001,0,1,5,2,
6,100002,1,1,1,4,80
6,100002,0,1,6,4,
6,100003,0,1,5,4,
"""
URL = "https://static.nhtsa.gov/nhtsa/downloads/FARS/2024/National/FARS2024.zip"


def _raw() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("FARS/accident.csv", ACCIDENT)
        archive.writestr("FARS/person.csv", PERSON)
    return buffer.getvalue()


def _normalized(raw: bytes) -> bytes:
    outcomes, summaries, crash, person = collect_joined(
        read_joined_export_bytes(raw), release_status="final"
    )
    artifact = build_joined_outcome_artifact(
        outcomes,
        summaries,
        person,
        crash,
        distribution_url=URL,
        max_invalid_fraction=0.34,
    )
    return canonical_joined_outcome_artifact_bytes(artifact)


def _store(tmp_path: Path) -> tuple[Path, Any, bytes]:
    raw = _raw()
    normalized = _normalized(raw)
    root = tmp_path / "store"
    result = run_ingestion(
        root=root,
        source_id="fars-joined",
        fetch=lambda: raw,
        normalize=lambda _payload: normalized,
        attempt_id="snapshot-attempt",
        clock=lambda: dt.datetime(2026, 7, 12, 18, tzinfo=dt.UTC),
    )
    return root, result, normalized


def _replace_private(path: Path, payload: bytes) -> None:
    path.chmod(0o600)
    path.write_bytes(payload)
    path.chmod(0o400)


def test_private_snapshot_is_exact_immutable_verified_bytes_without_new_files(
    tmp_path: Path,
) -> None:
    root, result, normalized = _store(tmp_path)
    files_before = sorted(path.relative_to(root) for path in root.rglob("*") if path.is_file())

    snapshot = verifier._load_verified_active_fars_joined_snapshot(root)

    assert type(snapshot.normalized_bytes) is bytes
    assert snapshot.normalized_bytes == normalized == result.normalized_path.read_bytes()
    assert (
        hashlib.sha256(snapshot.normalized_bytes).hexdigest() == snapshot.evidence.normalized_sha256
    )
    decoded = json.loads(snapshot.normalized_bytes)
    assert canonical_joined_outcome_artifact_bytes(decoded) == snapshot.normalized_bytes
    assert not hasattr(snapshot.evidence, "records")
    with pytest.raises(dataclasses.FrozenInstanceError):
        snapshot.normalized_bytes = b"forged"  # type: ignore[misc]
    files_after = sorted(path.relative_to(root) for path in root.rglob("*") if path.is_file())
    assert files_after == files_before


def test_snapshot_does_not_reopen_a_path_after_descriptor_verification(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, _result, normalized = _store(tmp_path)

    def forbidden_path_read(_path: Path) -> bytes:
        raise AssertionError("verified snapshot must not reopen through pathlib")

    monkeypatch.setattr(Path, "read_bytes", forbidden_path_read)
    assert verifier._load_verified_active_fars_joined_snapshot(root).normalized_bytes == normalized


def test_normalized_path_swap_after_replay_cannot_poison_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, result, normalized = _store(tmp_path)
    original_replay = verifier._replay_joined
    swapped = False

    def replay_then_swap(raw: bytes, payload: bytes, artifact: Any) -> None:
        nonlocal swapped
        original_replay(raw, payload, artifact)
        if swapped:
            return
        replacement = result.normalized_path.with_name("replacement.bin")
        replacement.write_bytes(b"unverified replacement\n")
        replacement.chmod(0o400)
        replacement.replace(result.normalized_path)
        swapped = True

    monkeypatch.setattr(verifier, "_replay_joined", replay_then_swap)
    snapshot = verifier._load_verified_active_fars_joined_snapshot(root)
    assert swapped is True
    assert snapshot.normalized_bytes == normalized
    assert snapshot.normalized_bytes != result.normalized_path.read_bytes()


def test_current_mutation_during_verification_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, _result, _normalized_bytes = _store(tmp_path)
    current = root / "fars-joined" / "normalized" / "current.json"
    original_chain = verifier._verify_joined_chain

    def verify_then_mutate(*args: Any, **kwargs: Any) -> Any:
        active = original_chain(*args, **kwargs)
        _replace_private(current, current.read_bytes() + b" ")
        return active

    monkeypatch.setattr(verifier, "_verify_joined_chain", verify_then_mutate)
    with pytest.raises(VerificationError, match="active receipt changed"):
        verifier._load_verified_active_fars_joined_snapshot(root)


def test_snapshot_rejects_symlink_and_hardlink_artifacts(tmp_path: Path) -> None:
    root, result, normalized = _store(tmp_path)
    target = tmp_path / "outside.bin"
    target.write_bytes(normalized)
    target.chmod(0o400)
    result.normalized_path.unlink()
    result.normalized_path.symlink_to(target)
    with pytest.raises(VerificationError, match="filesystem"):
        verifier._load_verified_active_fars_joined_snapshot(root)

    result.normalized_path.unlink()
    result.normalized_path.write_bytes(normalized)
    result.normalized_path.chmod(0o400)
    os.link(result.normalized_path, tmp_path / "second-link.bin")
    with pytest.raises(VerificationError, match="filesystem"):
        verifier._load_verified_active_fars_joined_snapshot(root)


@pytest.mark.parametrize("target", ["raw_snapshot", "normalized_path"])
def test_snapshot_rejects_unsafe_artifact_permissions(tmp_path: Path, target: str) -> None:
    root, result, _normalized_bytes = _store(tmp_path)
    getattr(result, target).chmod(0o600)
    with pytest.raises(VerificationError, match="filesystem"):
        verifier._load_verified_active_fars_joined_snapshot(root)


@pytest.mark.parametrize("limit", ["_MAX_JOINED_RAW_BYTES", "_MAX_JOINED_NORMALIZED_BYTES"])
def test_snapshot_enforces_joined_source_caps(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, limit: str
) -> None:
    root, _result, _normalized_bytes = _store(tmp_path)
    monkeypatch.setattr(verifier, limit, 1)
    with pytest.raises(VerificationError, match="size limit"):
        verifier._load_verified_active_fars_joined_snapshot(root)


def test_public_joined_verifier_still_returns_only_safe_evidence(tmp_path: Path) -> None:
    root, _result, _normalized_bytes = _store(tmp_path)
    evidence = verify_active_fars_joined(root)
    assert evidence.attempt_id == "snapshot-attempt"
    assert not hasattr(evidence, "normalized_bytes")
    assert not hasattr(evidence, "records")


def test_private_snapshot_cannot_be_forged_from_safe_evidence(tmp_path: Path) -> None:
    root, _result, normalized = _store(tmp_path)
    evidence = verify_active_fars_joined(root)
    with pytest.raises(VerificationError, match="snapshot invariants"):
        verifier._VerifiedJoinedSnapshot(
            evidence=evidence,
            normalized_bytes=normalized,
            _proof_token=object(),
        )
