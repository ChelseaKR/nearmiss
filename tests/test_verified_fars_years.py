# SPDX-License-Identifier: Apache-2.0
"""Security tests for exact fixed-year FARS lineage verification."""

from __future__ import annotations

import dataclasses
import datetime as dt
import hashlib
import io
import json
import os
import zipfile
from dataclasses import replace
from functools import cache
from pathlib import Path
from typing import Any, cast

import pytest
from jsonschema import Draft202012Validator, FormatChecker

import nearmiss.fars_national_context as national_context
import nearmiss.fars_year_contracts as year_contracts
import nearmiss.joined_outcome_artifacts_v2 as artifacts_v2
import nearmiss.verified_fars_years as verifier
import nearmiss.verified_outcomes as lineage
from nearmiss.fars_year_contracts import (
    FARS_YEAR_CONTRACT_HISTORY,
    fars_year_contract,
    fars_year_contract_sha256,
)
from nearmiss.ingestion import IngestionRunError, run_ingestion
from nearmiss.joined_outcome_artifacts_v2 import (
    canonical_joined_outcome_artifact_v2_from_pinned_archive,
)
from nearmiss.verified_outcomes import VerificationError

ROOT = Path(__file__).resolve().parents[1]
BASE_ACCIDENT = (
    (ROOT / "tests" / "fixtures" / "fars" / "accident.csv")
    .read_bytes()
    .replace(b",2023,", b",2024,")
)
PERSON = b"""STATE,ST_CASE,VEH_NO,PER_NO,PER_TYP,INJ_SEV,BODY_TYP
6,100001,1,1,1,4,4
6,100001,0,1,5,2,
6,100002,1,1,1,4,80
6,100002,0,1,6,4,
"""
FIRST = dt.datetime(2026, 7, 12, 18, tzinfo=dt.UTC)
SECOND = dt.datetime(2026, 7, 12, 19, tzinfo=dt.UTC)


def _accident(year: int) -> bytes:
    lines = BASE_ACCIDENT.decode().replace(",2024,", f",{year},").splitlines()
    result = [lines[0].replace(",FATALS", ",COUNTY,FATALS")]
    for line, county in zip(lines[1:3], ("113", "997"), strict=True):
        values = line.split(",")
        values.insert(-1, county)
        result.append(",".join(values))
    encoding = "cp1252" if year == 2020 else "utf-8-sig"
    return ("\n".join(result) + "\n").encode(encoding)


@cache
def _archive(year: int) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("National/accident.csv", _accident(year))
        archive.writestr("National/person.csv", PERSON)
    return buffer.getvalue()


def _reposted_archive(year: int) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("National/accident.csv", _accident(year))
        archive.writestr("National/person.csv", PERSON)
        archive.writestr("National/readme.txt", b"reviewed repost\n")
    return buffer.getvalue()


@pytest.fixture(autouse=True)
def _register_fixture_contracts(monkeypatch: pytest.MonkeyPatch) -> None:
    history: dict[int, tuple[Any, ...]] = {}
    contracts: dict[int, Any] = {}
    for year, registered in FARS_YEAR_CONTRACT_HISTORY.items():
        raw = _archive(year)
        raw_sha256 = hashlib.sha256(raw).hexdigest()
        contract = replace(
            registered[0],
            source_revision_id=f"reviewed-20260712-{raw_sha256[:12]}",
            raw_size_bytes=len(raw),
            raw_sha256=raw_sha256,
        )
        history[year] = (contract,)
        contracts[year] = contract
    monkeypatch.setattr(year_contracts, "FARS_YEAR_CONTRACT_HISTORY", history)
    monkeypatch.setattr(year_contracts, "FARS_YEAR_CONTRACTS", contracts)
    monkeypatch.setattr(artifacts_v2, "FARS_YEAR_CONTRACT_HISTORY", history)
    monkeypatch.setattr(
        artifacts_v2,
        "_VALIDATOR",
        Draft202012Validator(artifacts_v2._schema(), format_checker=FormatChecker()),
    )


def _normalized(year: int = 2024) -> bytes:
    return canonical_joined_outcome_artifact_v2_from_pinned_archive(
        _archive(year),
        year=year,
        contract_revision=1,
    )


def _ingest(
    tmp_path: Path,
    *,
    year: int = 2024,
    attempt_id: str = "year-1",
    now: dt.datetime = FIRST,
) -> tuple[Path, Any, bytes, list[Any]]:
    contract = fars_year_contract(year)
    raw = _archive(year)
    normalized = _normalized(year)
    root = tmp_path / "private"
    captured: list[Any] = []
    preflights: list[verifier._FarsYearIngestionPreflight] = []

    def locked_preflight(source_root: Path) -> None:
        assert not preflights
        preflights.append(
            verifier._preflight_fars_year_ingestion_locked(
                source_root,
                year=year,
                contract_revision=1,
            )
        )

    def validate_history(source_root: Path, candidate: bytes, started_at: str) -> None:
        assert len(preflights) == 1
        verifier._validate_fars_year_history_candidate_locked(
            source_root,
            candidate,
            year=year,
            contract_revision=1,
            started_at=started_at,
            expected_preflight=preflights[0],
        )

    def validate_activated(source_root: Path, candidate: bytes, marker: bytes) -> None:
        assert len(preflights) == 1
        captured.append(
            verifier._verify_activated_fars_year_locked(
                source_root,
                candidate,
                marker,
                year=year,
                contract_revision=1,
                expected_preflight=preflights[0],
            )
        )

    result = run_ingestion(
        root=root,
        source_id=contract.source_id,
        fetch=lambda: raw,
        normalize=lambda _raw: normalized,
        locked_preflight=locked_preflight,
        validate_history=validate_history,
        validate_activated=validate_activated,
        attempt_id=attempt_id,
        clock=lambda: now,
        max_raw_bytes=year_contracts.FARS_RAW_ARCHIVE_MAX_BYTES,
        max_normalized_bytes=verifier._MAX_NORMALIZED_BYTES,
    )
    return root, result, normalized, captured


def _replace_private(path: Path, payload: bytes) -> None:
    path.chmod(0o600)
    path.write_bytes(payload)
    path.chmod(0o400)


def _receipt_paths(root: Path, year: int = 2024) -> tuple[dict[str, Any], Path, Path]:
    source = root / fars_year_contract(year).source_id
    current = source / "normalized" / "current.json"
    receipt = cast(dict[str, Any], json.loads(current.read_bytes()))
    history = source / "receipts" / f"{receipt['attempt_id']}.json"
    return receipt, current, history


def _rebind_normalized(root: Path, payload: bytes, year: int = 2024) -> None:
    receipt, current, history = _receipt_paths(root, year)
    digest = hashlib.sha256(payload).hexdigest()
    normalized = current.parent / "sha256" / f"{digest}.bin"
    normalized.write_bytes(payload)
    normalized.chmod(0o400)
    receipt["normalized_sha256"] = digest
    receipt["normalized_path"] = f"normalized/sha256/{digest}.bin"
    marker = (json.dumps(receipt, indent=2, sort_keys=True) + "\n").encode()
    _replace_private(current, marker)
    _replace_private(history, marker)


def test_first_activation_without_receipts_then_public_full_replay(tmp_path: Path) -> None:
    root, result, normalized, captured = _ingest(tmp_path)
    assert len(captured) == 1
    assert captured[0].normalized_bytes == normalized
    evidence = verifier.verify_active_fars_year(root, year=2024, contract_revision=1)
    contract = fars_year_contract(2024)
    assert evidence.source_id == "fars-joined-2024"
    assert evidence.dataset_year == 2024
    assert evidence.contract_revision == 1
    assert evidence.source_revision_id == contract.source_revision_id
    assert evidence.contract_sha256 == year_contracts.fars_year_contract_sha256(contract)
    assert evidence.raw_sha256 == result.raw_sha256 == contract.raw_sha256
    assert evidence.normalized_sha256 == result.normalized_sha256
    assert evidence.receipt_id == "year-1"
    assert evidence.crash_records_read == 2
    assert evidence.crash_records_accepted == evidence.cases_joined == 2
    assert evidence.person_records_read == evidence.person_records_accepted == 4
    assert not hasattr(evidence, "records")
    assert not hasattr(evidence, "normalized_bytes")
    assert not hasattr(evidence, "__dict__")
    assert all("proof" not in key for key in evidence.as_dict())
    with pytest.raises(dataclasses.FrozenInstanceError):
        evidence.attempt_id = "forged"  # type: ignore[misc]


def test_annual_national_projector_opens_only_exact_v2_snapshot(
    tmp_path: Path,
) -> None:
    _root, _result, normalized, captured = _ingest(tmp_path, year=2020)
    joined, evidence, contract = national_context._verified_annual_joined_artifact(
        captured[0],
        year=2020,
        contract_revision=1,
    )
    assert joined["schema_version"] == "2.0.0"
    assert evidence is captured[0].evidence
    assert contract is fars_year_contract(2020)
    assert hashlib.sha256(normalized).hexdigest() == evidence.normalized_sha256

    with pytest.raises(ValueError, match="selected revision"):
        national_context._verified_annual_joined_artifact(
            captured[0],
            year=2021,
            contract_revision=1,
        )
    with pytest.raises(TypeError, match="proof-bound annual snapshot"):
        national_context._verified_annual_joined_artifact(
            object(),
            year=2020,
            contract_revision=1,
        )


def test_annual_national_projector_aggregates_in_memory_without_rows(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _root, _result, _normalized, captured = _ingest(tmp_path, year=2020)
    validated: list[dict[str, object]] = []
    monkeypatch.setattr(national_context, "_MIN_NATIONAL_CASES", 1)
    monkeypatch.setattr(national_context, "_NATIONAL_REQUIRED_STATE_CODES", frozenset({"6"}))
    monkeypatch.setattr(
        national_context,
        "validate_fars_national_context_artifact",
        lambda artifact: validated.append(artifact),
    )

    artifact = national_context.build_verified_fars_year_national_context(
        captured[0],
        year=2020,
        contract_revision=1,
        requested_k=1,
    )
    assert validated == [artifact]
    assert artifact["visibility"] == "private"
    source = cast(dict[str, Any], artifact["source_lineage"])
    assert source["source_id"] == "fars-joined-2020"
    assert source["dataset_year"] == 2020
    assert source["contract_revision"] == 1
    method = cast(dict[str, Any], artifact["method"])
    assert method["coverage"] == "official_2020_national_50_states_and_dc"
    assert method["effective_k"] == 5
    accounting = cast(dict[str, int], artifact["accounting"])
    assert accounting["case_count"] == 2
    assert accounting["states_with_records"] == 1
    assert accounting["positive_candidate_cell_count"] >= 2
    assert accounting["eligible_cell_count"] == 0
    assert artifact["cells"] == []
    payload = json.dumps(artifact, sort_keys=True).encode()
    assert all(
        token not in payload
        for token in (
            b'"records"',
            b'"source_record_id"',
            b'"occurred_on"',
            b'"location"',
            b'"jurisdiction"',
            b'"county_code"',
        )
    )


@pytest.mark.parametrize("requested_k", [True, 1.0, "10"])
def test_annual_national_projector_rejects_non_integer_k(requested_k: object) -> None:
    with pytest.raises(TypeError, match="requested_k must be an integer"):
        national_context.build_verified_fars_year_national_context(
            object(),
            year=2020,
            contract_revision=1,
            requested_k=cast(Any, requested_k),
        )


@pytest.mark.parametrize("requested_k", [0, 45_001])
def test_annual_national_projector_bounds_k(requested_k: int) -> None:
    with pytest.raises(ValueError, match="between 1 and 45000"):
        national_context.build_verified_fars_year_national_context(
            object(),
            year=2020,
            contract_revision=1,
            requested_k=requested_k,
        )


def test_repeated_activation_replays_history_and_retains_exact_snapshot(tmp_path: Path) -> None:
    root, _first, normalized, _captured = _ingest(tmp_path)
    _root, second, _normalized, captured = _ingest(
        tmp_path,
        attempt_id="year-2",
        now=SECOND,
    )
    assert _root == root
    assert captured[0].normalized_bytes == normalized
    snapshot = verifier._load_verified_active_fars_year_snapshot(
        root,
        year=2024,
        contract_revision=1,
    )
    assert snapshot.normalized_bytes == normalized
    assert snapshot.evidence.attempt_id == "year-2"
    assert snapshot.evidence.normalized_sha256 == second.normalized_sha256
    assert not hasattr(snapshot, "__dict__")
    with pytest.raises(dataclasses.FrozenInstanceError):
        snapshot.normalized_bytes = b"forged"  # type: ignore[misc]


def test_lineage_cannot_begin_at_a_later_contract_revision(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = fars_year_contract(2024)
    raw = _reposted_archive(2024)
    raw_sha256 = hashlib.sha256(raw).hexdigest()
    second = replace(
        first,
        revision=2,
        predecessor_contract_sha256=fars_year_contract_sha256(first),
        transition_review_reference="reviewed-r2-source-transition",
        source_revision_id=f"reviewed-20260713-{raw_sha256[:12]}",
        raw_size_bytes=len(raw),
        raw_sha256=raw_sha256,
    )
    history = dict(year_contracts.FARS_YEAR_CONTRACT_HISTORY)
    history[2024] = (first, second)
    contracts = dict(year_contracts.FARS_YEAR_CONTRACTS)
    contracts[2024] = second
    year_contracts.validate_fars_year_contract_registry(history)
    monkeypatch.setattr(year_contracts, "FARS_YEAR_CONTRACT_HISTORY", history)
    monkeypatch.setattr(year_contracts, "FARS_YEAR_CONTRACTS", contracts)
    monkeypatch.setattr(artifacts_v2, "FARS_YEAR_CONTRACT_HISTORY", history)
    monkeypatch.setattr(
        artifacts_v2,
        "_VALIDATOR",
        Draft202012Validator(artifacts_v2._schema(), format_checker=FormatChecker()),
    )
    normalized = canonical_joined_outcome_artifact_v2_from_pinned_archive(
        raw,
        year=2024,
        contract_revision=2,
    )
    root = tmp_path / "private"
    preflights: list[verifier._FarsYearIngestionPreflight] = []

    def locked_preflight(source_root: Path) -> None:
        preflights.append(
            verifier._preflight_fars_year_ingestion_locked(
                source_root,
                year=2024,
                contract_revision=2,
            )
        )

    def validate_history(source_root: Path, candidate: bytes, started_at: str) -> None:
        verifier._validate_fars_year_history_candidate_locked(
            source_root,
            candidate,
            year=2024,
            contract_revision=2,
            started_at=started_at,
            expected_preflight=preflights[0],
        )

    with pytest.raises(IngestionRunError):
        run_ingestion(
            root=root,
            source_id=second.source_id,
            fetch=lambda: raw,
            normalize=lambda _raw: normalized,
            locked_preflight=locked_preflight,
            validate_history=validate_history,
            attempt_id="illicit-r2-root",
            clock=lambda: FIRST,
        )
    assert not (root / second.source_id / "normalized" / "current.json").exists()


def test_authority_requires_replay_not_a_valid_artifact_or_private_token(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, _result, _normalized_bytes, _captured = _ingest(tmp_path)
    calls = 0

    def reject_replay(raw: bytes, *, year: int, contract_revision: int) -> bytes:
        nonlocal calls
        calls += 1
        raise ValueError((len(raw), year, contract_revision))

    monkeypatch.setattr(
        verifier,
        "canonical_joined_outcome_artifact_v2_from_pinned_archive",
        reject_replay,
    )
    with pytest.raises(VerificationError, match="deterministic replay failed"):
        verifier.verify_active_fars_year(root, year=2024, contract_revision=1)
    assert calls == 1
    evidence = verifier.VerifiedFarsYearEvidence
    with pytest.raises(VerificationError, match=r"requires|invariants"):
        cast(Any, evidence)(
            **_captured[0].evidence.as_dict(),
            _proof=object(),
        )


@pytest.mark.parametrize(
    ("field", "malformed"),
    [
        ("crash_records_read", 2.0),
        ("accident_sha256", 7),
        ("attempt_id", 7),
    ],
)
def test_evidence_constructor_rejects_malformed_field_types_uniformly(
    tmp_path: Path,
    field: str,
    malformed: object,
) -> None:
    _root, _result, _normalized_bytes, captured = _ingest(tmp_path)
    values = captured[0].evidence.as_dict()
    values[field] = malformed

    with pytest.raises(VerificationError, match="evidence invariants"):
        cast(Any, verifier.VerifiedFarsYearEvidence)(
            **values,
            _proof=verifier._EVIDENCE_PROOF,
        )


@pytest.mark.parametrize(
    "mutate",
    [
        lambda payload: payload + b" ",
        lambda payload: b'{"artifact_type":"duplicate",' + payload[1:],
        lambda payload: payload.replace(b'"records":[', b'"records":[NaN,', 1),
    ],
    ids=["noncanonical", "duplicate-key", "nonfinite"],
)
def test_strict_json_rejects_noncanonical_duplicate_and_nonfinite_values(
    tmp_path: Path,
    mutate: Any,
) -> None:
    root, _result, normalized, _captured = _ingest(tmp_path)
    _rebind_normalized(root, mutate(normalized))
    with pytest.raises(VerificationError, match=r"JSON decoding|validation|canonical"):
        verifier.verify_active_fars_year(root, year=2024, contract_revision=1)


def test_tampering_permissions_lock_and_requested_contract_fail_closed(tmp_path: Path) -> None:
    root, result, _normalized_bytes, _captured = _ingest(tmp_path)
    result.normalized_path.chmod(0o600)
    with pytest.raises(VerificationError, match="filesystem"):
        verifier.verify_active_fars_year(root, year=2024, contract_revision=1)
    result.normalized_path.chmod(0o400)
    lock = root / "fars-joined-2024" / ".ingestion.lock"
    lock.mkdir(mode=0o700)
    with pytest.raises(VerificationError, match="locked"):
        verifier.verify_active_fars_year(root, year=2024, contract_revision=1)
    lock.rmdir()
    with pytest.raises(ValueError, match="not registered"):
        verifier.verify_active_fars_year(root, year=2024, contract_revision=2)


def test_final_marker_and_history_rechecks_detect_races(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, _result, _normalized_bytes, _captured = _ingest(tmp_path)
    _receipt, current, history = _receipt_paths(root)
    original = verifier._verify_chain

    def mutate_marker(*args: Any, **kwargs: Any) -> Any:
        active = original(*args, **kwargs)
        _replace_private(current, current.read_bytes() + b" ")
        return active

    monkeypatch.setattr(verifier, "_verify_chain", mutate_marker)
    with pytest.raises(VerificationError, match="active receipt changed"):
        verifier.verify_active_fars_year(root, year=2024, contract_revision=1)

    monkeypatch.setattr(verifier, "_verify_chain", original)
    _replace_private(current, history.read_bytes())

    def mutate_history(*args: Any, **kwargs: Any) -> Any:
        active = original(*args, **kwargs)
        _replace_private(history, history.read_bytes() + b" ")
        return active

    monkeypatch.setattr(verifier, "_verify_chain", mutate_history)
    with pytest.raises(VerificationError, match=r"encoding|history"):
        verifier.verify_active_fars_year(root, year=2024, contract_revision=1)


def test_snapshot_never_reopens_verified_bytes_through_pathlib(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, _result, normalized, _captured = _ingest(tmp_path)

    def forbidden(_path: Path) -> bytes:
        raise AssertionError("verified bytes must remain descriptor-held")

    monkeypatch.setattr(Path, "read_bytes", forbidden)
    snapshot = verifier._load_verified_active_fars_year_snapshot(
        root,
        year=2024,
        contract_revision=1,
    )
    assert snapshot.normalized_bytes == normalized


def test_symlink_hardlink_and_bounded_reads_fail_closed(tmp_path: Path) -> None:
    root, result, normalized, _captured = _ingest(tmp_path)
    target = tmp_path / "outside.bin"
    target.write_bytes(normalized)
    target.chmod(0o400)
    result.normalized_path.unlink()
    result.normalized_path.symlink_to(target)
    with pytest.raises(VerificationError, match="filesystem"):
        verifier.verify_active_fars_year(root, year=2024, contract_revision=1)

    result.normalized_path.unlink()
    result.normalized_path.write_bytes(normalized)
    result.normalized_path.chmod(0o400)
    os.link(result.normalized_path, tmp_path / "hardlink.bin")
    with pytest.raises(VerificationError, match="filesystem"):
        verifier.verify_active_fars_year(root, year=2024, contract_revision=1)


def test_normalized_size_cap_is_enforced(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, _result, _normalized_bytes, _captured = _ingest(tmp_path)
    monkeypatch.setattr(verifier, "_MAX_NORMALIZED_BYTES", 1)
    with pytest.raises(VerificationError, match="size limit"):
        verifier.verify_active_fars_year(root, year=2024, contract_revision=1)


def test_locked_preflight_reserves_exactly_one_receipt_slot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, _result, _normalized_bytes, _captured = _ingest(tmp_path)
    source = root / fars_year_contract(2024).source_id
    lock = source / ".ingestion.lock"
    lock.mkdir(mode=0o700)
    monkeypatch.setattr(lineage, "_MAX_RECEIPTS", 2)
    preflight = verifier._preflight_fars_year_ingestion_locked(
        source,
        year=2024,
        contract_revision=1,
    )
    metadata = lock.stat(follow_symlinks=False)
    assert preflight.lock_identity == (metadata.st_dev, metadata.st_ino)
    assert not hasattr(preflight, "__dict__")

    monkeypatch.setattr(lineage, "_MAX_RECEIPTS", 1)
    with pytest.raises(VerificationError, match="no capacity"):
        verifier._preflight_fars_year_ingestion_locked(
            source,
            year=2024,
            contract_revision=1,
        )


@pytest.mark.parametrize("stage", ["history", "activated"])
def test_locked_hooks_reject_replaced_preflight_lock_identity(
    tmp_path: Path,
    stage: str,
) -> None:
    root, result, normalized, _captured = _ingest(tmp_path)
    source = root / fars_year_contract(2024).source_id
    lock = source / ".ingestion.lock"
    lock.mkdir(mode=0o700)
    expected = verifier._preflight_fars_year_ingestion_locked(
        source,
        year=2024,
        contract_revision=1,
    )
    replacement = source / ".replacement-lock"
    replacement.mkdir(mode=0o700)
    lock.rmdir()
    replacement.rename(lock)
    if stage == "history":
        with pytest.raises(VerificationError, match="locked state does not match"):
            verifier._validate_fars_year_history_candidate_locked(
                source,
                normalized,
                year=2024,
                contract_revision=1,
                started_at="2026-07-12T19:00:00Z",
                expected_preflight=expected,
            )
    else:
        marker = result.current_path.read_bytes()
        with pytest.raises(VerificationError, match="locked state does not match"):
            verifier._verify_activated_fars_year_locked(
                source,
                normalized,
                marker,
                year=2024,
                contract_revision=1,
                expected_preflight=expected,
            )


@pytest.mark.parametrize("stage", ["history", "activated"])
def test_locked_hooks_reject_receipt_history_drift_since_preflight(
    tmp_path: Path,
    stage: str,
) -> None:
    root, result, normalized, _captured = _ingest(tmp_path)
    source = root / fars_year_contract(2024).source_id
    lock = source / ".ingestion.lock"
    lock.mkdir(mode=0o700)
    expected = verifier._preflight_fars_year_ingestion_locked(
        source,
        year=2024,
        contract_revision=1,
    )
    receipt, _current, history = _receipt_paths(root)
    receipt["attempt_id"] = "injected-after-preflight"
    injected = history.parent / "injected-after-preflight.json"
    injected.write_bytes((json.dumps(receipt, indent=2, sort_keys=True) + "\n").encode())
    injected.chmod(0o400)

    with pytest.raises(VerificationError, match="locked state does not match"):
        if stage == "history":
            verifier._validate_fars_year_history_candidate_locked(
                source,
                normalized,
                year=2024,
                contract_revision=1,
                started_at="2026-07-12T19:00:00Z",
                expected_preflight=expected,
            )
        else:
            verifier._verify_activated_fars_year_locked(
                source,
                normalized,
                result.current_path.read_bytes(),
                year=2024,
                contract_revision=1,
                expected_preflight=expected,
            )
