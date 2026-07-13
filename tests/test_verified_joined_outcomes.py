"""Security and lineage tests for the active joined-FARS verifier."""

from __future__ import annotations

import datetime as dt
import hashlib
import io
import json
import zipfile
from pathlib import Path
from typing import Any, cast

import pytest

import nearmiss.verified_outcomes as verifier
from nearmiss.adapters.fars_joined import collect_joined, read_joined_export_bytes
from nearmiss.ingestion import run_ingestion
from nearmiss.joined_outcome_artifacts import (
    build_joined_outcome_artifact,
    canonical_joined_outcome_artifact_bytes,
)
from nearmiss.verified_outcomes import (
    VerificationError,
    VerifiedJoinedOutcomeEvidence,
    verify_active_fars_joined,
)

ROOT = Path(__file__).resolve().parents[1]
ACCIDENT = (
    (ROOT / "tests" / "fixtures" / "fars" / "accident.csv")
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
FIRST = dt.datetime(2026, 7, 12, 18, tzinfo=dt.UTC)
SECOND = dt.datetime(2026, 7, 12, 19, tzinfo=dt.UTC)


def _raw(*, accident: bytes = ACCIDENT, person: bytes = PERSON) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("FARS/accident.csv", accident)
        archive.writestr("FARS/person.csv", person)
    return buffer.getvalue()


def _normalized(
    raw: bytes,
    *,
    release_status: str,
    schema_version: str | None = None,
    allow_record_regression: bool = False,
    allow_mode_regression: bool = False,
    allow_release_regression: bool = False,
) -> bytes:
    outcomes, summaries, crash, person = collect_joined(
        read_joined_export_bytes(raw), release_status=release_status
    )
    artifact = build_joined_outcome_artifact(
        outcomes,
        summaries,
        person,
        crash,
        distribution_url=URL,
        max_invalid_fraction=0.34,
        allow_record_regression=allow_record_regression,
        allow_mode_regression=allow_mode_regression,
        allow_release_regression=allow_release_regression,
        schema_version=schema_version,
    )
    return canonical_joined_outcome_artifact_bytes(artifact)


def _ingest(
    tmp_path: Path,
    *,
    raw: bytes | None = None,
    release_status: str = "final",
    attempt_id: str = "attempt-1",
    now: dt.datetime = FIRST,
    allow_record_regression: bool = False,
    allow_mode_regression: bool = False,
    allow_release_regression: bool = False,
    schema_version: str | None = None,
) -> tuple[Path, Any]:
    payload = _raw() if raw is None else raw
    normalized = _normalized(
        payload,
        release_status=release_status,
        allow_record_regression=allow_record_regression,
        allow_mode_regression=allow_mode_regression,
        allow_release_regression=allow_release_regression,
        schema_version=schema_version,
    )
    root = tmp_path / "store"
    result = run_ingestion(
        root=root,
        source_id="fars-joined",
        fetch=lambda: payload,
        normalize=lambda _raw_bytes: normalized,
        attempt_id=attempt_id,
        clock=lambda: now,
    )
    return root, result


def _accident_with_county() -> bytes:
    lines = ACCIDENT.decode().splitlines()
    output = [lines[0].replace(",FATALS", ",COUNTY,FATALS")]
    for line in lines[1:]:
        values = line.split(",")
        values.insert(-1, "113")
        output.append(",".join(values))
    return ("\n".join(output) + "\n").encode()


def _replace(path: Path, payload: bytes) -> None:
    path.chmod(0o600)
    path.write_bytes(payload)
    path.chmod(0o400)


def _receipt(root: Path) -> tuple[dict[str, Any], Path, Path]:
    current = root / "fars-joined" / "normalized" / "current.json"
    receipt = cast(dict[str, Any], json.loads(current.read_bytes()))
    history = root / "fars-joined" / "receipts" / f"{receipt['attempt_id']}.json"
    return receipt, current, history


def test_verifies_joined_transaction_and_returns_only_safe_aggregates(tmp_path: Path) -> None:
    root, result = _ingest(tmp_path)
    evidence = verify_active_fars_joined(root)
    assert evidence.source_id == "fars-joined"
    assert evidence.dataset_year == 2024
    assert evidence.crash_mapping_version == "1.0.0"
    assert evidence.person_mapping_version == "1.0.0"
    assert evidence.release_status == "final"
    assert (evidence.crash_records_read, evidence.crash_records_accepted) == (3, 2)
    assert (evidence.person_records_read, evidence.person_records_accepted) == (5, 4)
    assert (evidence.cases_joined, evidence.cases_excluded) == (2, 1)
    assert evidence.raw_sha256 == result.raw_sha256
    assert evidence.normalized_sha256 == result.normalized_sha256
    assert evidence.receipt_id == "attempt-1"
    assert not hasattr(evidence, "records")
    assert not hasattr(evidence, "coordinates")
    assert all("proof" not in key for key in evidence.as_dict())


def test_replay_preserves_legacy_schema_when_raw_now_supports_v11(tmp_path: Path) -> None:
    raw = _raw(accident=_accident_with_county())
    root, result = _ingest(tmp_path, raw=raw, schema_version="1.0.0")
    artifact = cast(dict[str, Any], json.loads(result.normalized_path.read_bytes()))
    assert artifact["schema_version"] == "1.0.0"
    assert verify_active_fars_joined(root).normalized_sha256 == result.normalized_sha256


def test_tampering_lock_and_unsafe_mode_fail_closed(tmp_path: Path) -> None:
    root, result = _ingest(tmp_path)
    original_raw = result.raw_snapshot.read_bytes()
    _replace(result.raw_snapshot, original_raw + b"tamper")
    with pytest.raises(VerificationError, match="raw artifact hash mismatch"):
        verify_active_fars_joined(root)
    _replace(result.raw_snapshot, original_raw)
    result.normalized_path.chmod(0o600)
    with pytest.raises(VerificationError, match="filesystem"):
        verify_active_fars_joined(root)
    result.normalized_path.chmod(0o400)
    lock = root / "fars-joined" / ".ingestion.lock"
    lock.mkdir(mode=0o700)
    with pytest.raises(VerificationError, match="locked"):
        verify_active_fars_joined(root)


def test_descriptor_forgery_is_rejected_by_deterministic_replay(tmp_path: Path) -> None:
    root, result = _ingest(tmp_path)
    artifact = cast(dict[str, Any], json.loads(result.normalized_path.read_bytes()))
    artifact["person_join"]["person_member"]["crc32"] = "00000000"
    normalized = canonical_joined_outcome_artifact_bytes(artifact)
    digest = hashlib.sha256(normalized).hexdigest()
    path = result.normalized_path.parent / f"{digest}.bin"
    path.write_bytes(normalized)
    path.chmod(0o400)
    receipt, current, history = _receipt(root)
    receipt["normalized_sha256"] = digest
    receipt["normalized_path"] = f"normalized/sha256/{digest}.bin"
    receipt_bytes = (json.dumps(receipt, indent=2, sort_keys=True) + "\n").encode()
    _replace(current, receipt_bytes)
    _replace(history, receipt_bytes)
    with pytest.raises(VerificationError, match="deterministic replay"):
        verify_active_fars_joined(root)


@pytest.mark.parametrize("allowed", [False, True])
def test_final_to_preliminary_requires_recorded_release_override(
    tmp_path: Path, allowed: bool
) -> None:
    root, _first = _ingest(tmp_path)
    _ingest(
        tmp_path,
        release_status="preliminary",
        attempt_id="attempt-2",
        now=SECOND,
        allow_release_regression=allowed,
    )
    if allowed:
        assert verify_active_fars_joined(root).release_status == "preliminary"
    else:
        with pytest.raises(VerificationError, match="downgraded from final"):
            verify_active_fars_joined(root)


@pytest.mark.parametrize("allowed", [False, True])
def test_mode_count_regression_requires_recorded_mode_override(
    tmp_path: Path, allowed: bool
) -> None:
    root, _first = _ingest(tmp_path)
    changed_person = PERSON.replace(b"6,100001,0,1,5,2,", b"6,100001,1,2,2,2,4")
    _ingest(
        tmp_path,
        raw=_raw(person=changed_person),
        attempt_id="attempt-2",
        now=SECOND,
        allow_mode_regression=allowed,
    )
    if allowed:
        assert verify_active_fars_joined(root).attempt_id == "attempt-2"
    else:
        with pytest.raises(VerificationError, match="mode counts regressed"):
            verify_active_fars_joined(root)


@pytest.mark.parametrize("allowed", [False, True])
def test_crash_person_case_regression_requires_recorded_record_override(
    tmp_path: Path, allowed: bool
) -> None:
    root, _first = _ingest(tmp_path)
    accident_rows = ACCIDENT.splitlines()
    smaller_accident = b"\n".join(accident_rows[:2]) + b"\n"
    person_rows = PERSON.splitlines()
    smaller_person = b"\n".join(person_rows[:3]) + b"\n"
    _ingest(
        tmp_path,
        raw=_raw(accident=smaller_accident, person=smaller_person),
        attempt_id="attempt-2",
        now=SECOND,
        allow_record_regression=allowed,
        allow_mode_regression=True,
    )
    if allowed:
        assert verify_active_fars_joined(root).cases_joined == 1
    else:
        with pytest.raises(VerificationError, match="aggregate counts regressed"):
            verify_active_fars_joined(root)


def test_full_history_rejects_broken_middle_predecessor(tmp_path: Path) -> None:
    root, _first = _ingest(tmp_path)
    changed = ACCIDENT.replace(b"38.544907", b"38.544507", 1)
    _ingest(tmp_path, raw=_raw(accident=changed), attempt_id="attempt-2", now=SECOND)
    changed_again = ACCIDENT.replace(b"38.544907", b"38.544607", 1)
    _ingest(
        tmp_path,
        raw=_raw(accident=changed_again),
        attempt_id="attempt-3",
        now=SECOND + dt.timedelta(hours=1),
    )
    middle = root / "fars-joined" / "receipts" / "attempt-2.json"
    receipt = cast(dict[str, Any], json.loads(middle.read_bytes()))
    receipt["previous_normalized_sha256"] = None
    _replace(middle, (json.dumps(receipt, indent=2, sort_keys=True) + "\n").encode())
    with pytest.raises(VerificationError, match="predecessor link"):
        verify_active_fars_joined(root)


def test_many_unique_generations_are_replayed_without_artifact_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root: Path | None = None
    for index in range(8):
        latitude = f"38.544{index:03d}".encode()
        accident = ACCIDENT.replace(b"38.544907", latitude, 1)
        root, _result = _ingest(
            tmp_path,
            raw=_raw(accident=accident),
            attempt_id=f"attempt-{index}",
            now=FIRST + dt.timedelta(minutes=index),
        )
    calls = 0
    original = verifier._replay_joined

    def counted(raw: bytes, normalized: bytes, artifact: Any) -> None:
        nonlocal calls
        calls += 1
        original(raw, normalized, artifact)

    monkeypatch.setattr(verifier, "_replay_joined", counted)
    assert root is not None
    assert verify_active_fars_joined(root).attempt_id == "attempt-7"
    assert calls == 8


def test_nonconsecutive_generation_reuse_is_rejected_as_rollback(tmp_path: Path) -> None:
    original = _raw()
    root, _first = _ingest(tmp_path, raw=original)
    changed = ACCIDENT.replace(b"38.544907", b"38.544507", 1)
    _ingest(tmp_path, raw=_raw(accident=changed), attempt_id="attempt-2", now=SECOND)
    _ingest(
        tmp_path,
        raw=original,
        attempt_id="attempt-3",
        now=SECOND + dt.timedelta(hours=1),
    )
    with pytest.raises(VerificationError, match="reused an older normalized generation"):
        verify_active_fars_joined(root)


def test_joined_evidence_cannot_be_forged_directly() -> None:
    with pytest.raises(VerificationError, match="invariants"):
        VerifiedJoinedOutcomeEvidence(
            source_id="fars-joined",
            dataset_year=2024,
            crash_mapping_version="1.0.0",
            person_mapping_version="1.0.0",
            release_status="final",
            crash_records_read=1,
            crash_records_accepted=1,
            crash_records_rejected=0,
            person_records_read=1,
            person_records_accepted=1,
            person_records_excluded=0,
            cases_joined=1,
            cases_excluded=0,
            raw_sha256="a" * 64,
            accident_sha256="b" * 64,
            person_sha256="c" * 64,
            normalized_sha256="d" * 64,
            attempt_id="forged",
            _proof_token=object(),
        )


@pytest.mark.parametrize("limit_name", ["_MAX_JOINED_RAW_BYTES", "_MAX_JOINED_NORMALIZED_BYTES"])
def test_joined_artifacts_have_source_specific_hard_caps(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, limit_name: str
) -> None:
    root, _result = _ingest(tmp_path)
    monkeypatch.setattr(f"nearmiss.verified_outcomes.{limit_name}", 1)
    with pytest.raises(VerificationError, match="size limit"):
        verify_active_fars_joined(root)
