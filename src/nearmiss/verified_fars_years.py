# SPDX-License-Identifier: Apache-2.0
"""Read-only verification of one exact fixed-year FARS v2 lineage."""

from __future__ import annotations

import datetime as dt
import hashlib
import os
from collections.abc import Mapping
from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path
from typing import NoReturn, cast

from . import verified_outcomes as lineage
from .fars_year_contracts import (
    FARS_RAW_ARCHIVE_MAX_BYTES,
    FarsYearContract,
    fars_release_stage_rank,
    fars_year_contract_from_descriptor,
    fars_year_contract_revision,
    fars_year_contract_sha256,
    is_fars_provenance_only_same_archive_correction,
)
from .joined_outcome_artifacts_v2 import (
    canonical_joined_outcome_artifact_v2_bytes,
    canonical_joined_outcome_artifact_v2_from_pinned_archive,
    validate_joined_outcome_artifact_v2,
)
from .verified_outcomes import VerificationError

_MAX_NORMALIZED_BYTES = 512 * 1024 * 1024
# These package-private objects guard against accidental constructor misuse.
# They are not cryptographic capabilities; authority comes only from exact raw
# replay inside this module.
_EVIDENCE_PROOF = object()
_SNAPSHOT_PROOF = object()
_LockIdentity = tuple[int, int]
_ReceiptDirectoryIdentity = tuple[int, int] | None
_ReceiptHistoryIdentity = tuple[
    _ReceiptDirectoryIdentity,
    tuple[tuple[str, bytes], ...],
]


@dataclass(frozen=True, slots=True)
class _FarsYearIngestionPreflight:
    """Exact lock and receipt-history state reserved before annual ingestion."""

    lock_identity: _LockIdentity
    history_identity: _ReceiptHistoryIdentity


@dataclass(frozen=True, init=False, slots=True)
class VerifiedFarsYearEvidence:
    """Frozen aggregate evidence from an exact replayed annual lineage."""

    source_id: str
    dataset_year: int
    contract_revision: int
    source_revision_id: str
    contract_sha256: str
    crash_mapping_version: str
    person_mapping_version: str
    release_status: str
    crash_records_read: int
    crash_records_accepted: int
    crash_records_rejected: int
    person_records_read: int
    person_records_accepted: int
    person_records_excluded: int
    cases_joined: int
    cases_excluded: int
    raw_sha256: str
    accident_sha256: str
    person_sha256: str
    normalized_sha256: str
    attempt_id: str

    def __init__(
        self,
        *,
        source_id: str,
        dataset_year: int,
        contract_revision: int,
        source_revision_id: str,
        contract_sha256: str,
        crash_mapping_version: str,
        person_mapping_version: str,
        release_status: str,
        crash_records_read: int,
        crash_records_accepted: int,
        crash_records_rejected: int,
        person_records_read: int,
        person_records_accepted: int,
        person_records_excluded: int,
        cases_joined: int,
        cases_excluded: int,
        raw_sha256: str,
        accident_sha256: str,
        person_sha256: str,
        normalized_sha256: str,
        attempt_id: str,
        _proof: object,
    ) -> None:
        try:
            contract = fars_year_contract_revision(dataset_year, contract_revision)
        except (TypeError, ValueError) as exc:
            raise VerificationError("verified FARS year evidence contract is invalid") from exc
        counts = (
            crash_records_read,
            crash_records_accepted,
            crash_records_rejected,
            person_records_read,
            person_records_accepted,
            person_records_excluded,
            cases_joined,
            cases_excluded,
        )
        digests = (
            contract_sha256,
            raw_sha256,
            accident_sha256,
            person_sha256,
            normalized_sha256,
        )
        if (
            _proof is not _EVIDENCE_PROOF
            or source_id != contract.source_id
            or source_revision_id != contract.source_revision_id
            or contract_sha256 != fars_year_contract_sha256(contract)
            or crash_mapping_version != contract.crash_mapping_version
            or person_mapping_version != contract.person_mapping_version
            or release_status != contract.release_stage
            or any(type(value) is not int or value < 0 for value in counts)
            or crash_records_read != crash_records_accepted + crash_records_rejected
            or person_records_read != person_records_accepted + person_records_excluded
            or cases_joined != crash_records_accepted
            or cases_excluded != crash_records_rejected
            or raw_sha256 != contract.raw_sha256
            or any(
                not isinstance(value, str) or lineage._SHA256_RE.fullmatch(value) is None
                for value in digests
            )
            or not isinstance(attempt_id, str)
            or lineage._SAFE_ATTEMPT_ID.fullmatch(attempt_id) is None
        ):
            raise VerificationError("verified FARS year evidence invariants are invalid")
        values = locals()
        for name in self.__dataclass_fields__:
            object.__setattr__(self, name, values[name])

    @property
    def receipt_id(self) -> str:
        """Return the immutable ingestion-attempt identity."""
        return self.attempt_id

    def as_dict(self) -> dict[str, object]:
        """Project safe aggregate metadata without normalized record data."""
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True, init=False, slots=True)
class _VerifiedFarsYearSnapshot:
    """Private canonical bytes captured by the replaying verifier."""

    evidence: VerifiedFarsYearEvidence
    normalized_bytes: bytes

    def __init__(
        self,
        *,
        evidence: VerifiedFarsYearEvidence,
        normalized_bytes: bytes,
        _proof: object,
    ) -> None:
        if (
            _proof is not _SNAPSHOT_PROOF
            or type(normalized_bytes) is not bytes
            or hashlib.sha256(normalized_bytes).hexdigest() != evidence.normalized_sha256
        ):
            raise VerificationError("verified FARS year snapshot invariants are invalid")
        object.__setattr__(self, "evidence", evidence)
        object.__setattr__(self, "normalized_bytes", normalized_bytes)


@dataclass(frozen=True)
class _VerifiedGeneration:
    receipt: lineage._ReceiptRecord
    artifact: Mapping[str, object]
    contract: FarsYearContract
    normalized_bytes: bytes


def _fail(message: str) -> NoReturn:
    raise VerificationError(message)


def _artifact_contract(artifact: Mapping[str, object]) -> FarsYearContract:
    try:
        descriptor = cast(Mapping[str, object], artifact["source_contract"])
        return fars_year_contract_from_descriptor(descriptor)
    except (KeyError, TypeError, ValueError) as exc:
        raise VerificationError(
            "fixed-year FARS artifact does not select an exact contract revision"
        ) from exc


def _verify_generation(
    receipt: lineage._ReceiptRecord,
    raw_hashes: int,
    normalized_hashes: int,
    *,
    expected_year: int,
    expected_source_id: str,
) -> _VerifiedGeneration:
    raw_digest, normalized_digest = lineage._generation_key(receipt)
    raw, observed_raw = lineage._read_file(
        raw_hashes,
        f"{raw_digest}.bin",
        maximum=FARS_RAW_ARCHIVE_MAX_BYTES,
    )
    if observed_raw != raw_digest:
        _fail("fixed-year FARS raw artifact hash mismatch")
    normalized, observed_normalized = lineage._read_file(
        normalized_hashes,
        f"{normalized_digest}.bin",
        maximum=_MAX_NORMALIZED_BYTES,
    )
    if observed_normalized != normalized_digest:
        _fail("fixed-year FARS normalized artifact hash mismatch")
    artifact = lineage._strict_json(normalized)
    try:
        validate_joined_outcome_artifact_v2(artifact)
        canonical = canonical_joined_outcome_artifact_v2_bytes(artifact)
    except (KeyError, TypeError, ValueError):
        _fail("fixed-year FARS normalized artifact validation failed")
    if canonical != normalized:
        _fail("fixed-year FARS normalized artifact encoding is not canonical")
    contract = _artifact_contract(artifact)
    if contract.year != expected_year or contract.source_id != expected_source_id:
        _fail("fixed-year FARS artifact contract does not match its store")
    crash = cast(Mapping[str, object], artifact["crash_provenance"])
    person = cast(Mapping[str, object], artifact["person_join"])
    if (
        raw_digest != contract.raw_sha256
        or crash["input_sha256"] != raw_digest
        or person["input_sha256"] != raw_digest
    ):
        _fail("fixed-year FARS artifact provenance does not match its raw archive")

    # This replay is the authority boundary. Structural validation and a closed
    # descriptor alone are intentionally insufficient to mint verified evidence.
    try:
        replayed = canonical_joined_outcome_artifact_v2_from_pinned_archive(
            raw,
            year=contract.year,
            contract_revision=contract.revision,
        )
    except (OSError, TypeError, ValueError):
        _fail("fixed-year FARS deterministic replay failed")
    if replayed != normalized:
        _fail("fixed-year FARS normalized artifact does not match deterministic replay")
    return _VerifiedGeneration(receipt, artifact, contract, normalized)


def _mode_totals(artifact: Mapping[str, object]) -> dict[str, int]:
    totals: dict[str, int] = {}
    for record in cast(list[Mapping[str, object]], artifact["records"]):
        summary = cast(Mapping[str, object], record["mode_summary"])
        for field in ("involved_person_count_by_mode", "fatality_count_by_mode"):
            for mode, count in cast(Mapping[str, int], summary[field]).items():
                key = f"{field}:{mode}"
                totals[key] = totals.get(key, 0) + count
    return totals


def _validate_transition(current: _VerifiedGeneration, previous: _VerifiedGeneration) -> None:
    if current.contract.revision < previous.contract.revision:
        _fail("fixed-year FARS contract revision regressed")
    if (
        current.contract.revision != previous.contract.revision
        and current.contract.revision != previous.contract.revision + 1
    ):
        _fail("fixed-year FARS contract revision skipped recorded history")
    if fars_release_stage_rank(current.contract.release_stage) < fars_release_stage_rank(
        previous.contract.release_stage
    ) and not is_fars_provenance_only_same_archive_correction(
        current.contract,
        previous.contract,
    ):
        _fail("fixed-year FARS release stage regressed without a provenance-only correction")
    current_crash = cast(Mapping[str, int], current.artifact["crash_provenance"])
    previous_crash = cast(Mapping[str, int], previous.artifact["crash_provenance"])
    current_person = cast(Mapping[str, int], current.artifact["person_join"])
    previous_person = cast(Mapping[str, int], previous.artifact["person_join"])
    record_metrics = (
        (current_crash, previous_crash, "records_read"),
        (current_crash, previous_crash, "records_accepted"),
        (current_person, previous_person, "records_read"),
        (current_person, previous_person, "records_accepted"),
        (current_person, previous_person, "cases_joined"),
    )
    if (
        any(
            current_values[key] < previous_values[key]
            for current_values, previous_values, key in record_metrics
        )
        and "record_counts" not in current.contract.allowed_regressions
    ):
        _fail("fixed-year FARS aggregate record counts regressed without contract review")
    current_modes = _mode_totals(current.artifact)
    previous_modes = _mode_totals(previous.artifact)
    if (
        any(current_modes.get(key, 0) < value for key, value in previous_modes.items())
        and "mode_counts" not in current.contract.allowed_regressions
    ):
        _fail("fixed-year FARS aggregate mode counts regressed without contract review")


def _verify_chain(
    receipts: list[lineage._ReceiptRecord],
    raw_hashes: int,
    normalized_hashes: int,
    *,
    expected_year: int,
    expected_source_id: str,
    required_active_contract: FarsYearContract | None,
) -> _VerifiedGeneration:
    previous: _VerifiedGeneration | None = None
    seen_normalized: set[str] = set()
    for receipt in receipts:
        expected_previous = (
            None if previous is None else previous.receipt.receipt["normalized_sha256"]
        )
        if receipt.receipt["previous_normalized_sha256"] != expected_previous:
            _fail("fixed-year FARS lineage predecessor link is invalid")
        generation_key = lineage._generation_key(receipt)
        normalized_digest = generation_key[1]
        if previous is not None and generation_key == lineage._generation_key(previous.receipt):
            generation = _VerifiedGeneration(
                receipt,
                previous.artifact,
                previous.contract,
                previous.normalized_bytes,
            )
        elif normalized_digest in seen_normalized:
            _fail("fixed-year FARS lineage reused an older normalized generation")
        else:
            generation = _verify_generation(
                receipt,
                raw_hashes,
                normalized_hashes,
                expected_year=expected_year,
                expected_source_id=expected_source_id,
            )
        if previous is not None:
            _validate_transition(generation, previous)
        elif generation.contract.revision != 1:
            _fail("fixed-year FARS lineage must begin at contract revision 1")
        seen_normalized.add(normalized_digest)
        previous = generation
    if previous is None:
        _fail("fixed-year FARS receipt history has no successful receipt")
    if required_active_contract is not None and previous.contract != required_active_contract:
        _fail("fixed-year FARS active artifact is not the requested contract revision")
    return previous


def _evidence(generation: _VerifiedGeneration) -> VerifiedFarsYearEvidence:
    receipt = generation.receipt
    contract = generation.contract
    crash = cast(Mapping[str, object], generation.artifact["crash_provenance"])
    person = cast(Mapping[str, object], generation.artifact["person_join"])
    rejected = sum(cast(Mapping[str, int], crash["rejection_reasons"]).values())
    return VerifiedFarsYearEvidence(
        source_id=contract.source_id,
        dataset_year=contract.year,
        contract_revision=contract.revision,
        source_revision_id=contract.source_revision_id,
        contract_sha256=fars_year_contract_sha256(contract),
        crash_mapping_version=contract.crash_mapping_version,
        person_mapping_version=contract.person_mapping_version,
        release_status=contract.release_stage,
        crash_records_read=cast(int, crash["records_read"]),
        crash_records_accepted=cast(int, crash["records_accepted"]),
        crash_records_rejected=rejected,
        person_records_read=cast(int, person["records_read"]),
        person_records_accepted=cast(int, person["records_accepted"]),
        person_records_excluded=cast(int, person["records_excluded_with_rejected_crash"]),
        cases_joined=cast(int, person["cases_joined"]),
        cases_excluded=cast(int, person["cases_excluded_with_rejected_crash"]),
        raw_sha256=cast(str, receipt.receipt["raw_sha256"]),
        accident_sha256=cast(str, person["accident_sha256"]),
        person_sha256=cast(str, person["person_sha256"]),
        normalized_sha256=cast(str, receipt.receipt["normalized_sha256"]),
        attempt_id=receipt.attempt_id,
        _proof=_EVIDENCE_PROOF,
    )


def _snapshot(generation: _VerifiedGeneration) -> _VerifiedFarsYearSnapshot:
    return _VerifiedFarsYearSnapshot(
        evidence=_evidence(generation),
        normalized_bytes=generation.normalized_bytes,
        _proof=_SNAPSHOT_PROOF,
    )


def _lock_identity(source: int) -> _LockIdentity:
    try:
        metadata = os.stat(".ingestion.lock", dir_fd=source, follow_symlinks=False)
    except OSError:
        _fail("fixed-year FARS ingestion lock is not held")
    lineage._validate_metadata(metadata, directory=True)
    return metadata.st_dev, metadata.st_ino


def _scan_optional_receipts(
    source: int,
    *,
    source_id: str,
) -> tuple[_ReceiptDirectoryIdentity, list[lineage._ReceiptRecord]]:
    try:
        metadata = os.stat("receipts", dir_fd=source, follow_symlinks=False)
    except FileNotFoundError:
        return None, []
    except OSError:
        _fail("fixed-year FARS receipt history scan failed")
    lineage._validate_metadata(metadata, directory=True)
    receipts = lineage._open_directory(source, "receipts")
    try:
        opened = os.fstat(receipts)
        return (
            (opened.st_dev, opened.st_ino),
            lineage._scan_receipts(receipts, expected_source_id=source_id),
        )
    finally:
        os.close(receipts)


def _history_identity(
    directory: _ReceiptDirectoryIdentity,
    records: list[lineage._ReceiptRecord],
) -> _ReceiptHistoryIdentity:
    return directory, tuple((record.attempt_id, record.payload) for record in records)


def _require_expected_preflight(
    observed_lock: _LockIdentity,
    observed_history: _ReceiptHistoryIdentity,
    expected: _FarsYearIngestionPreflight,
) -> None:
    if (
        not isinstance(expected, _FarsYearIngestionPreflight)
        or observed_lock != expected.lock_identity
        or observed_history != expected.history_identity
    ):
        _fail("fixed-year FARS locked state does not match ingestion preflight")


def _locked_successes(
    current: lineage._ReceiptRecord,
    history: list[lineage._ReceiptRecord],
) -> list[lineage._ReceiptRecord]:
    if current.completed_at is None:
        _fail("fixed-year FARS active receipt completion time is invalid")
    if any(record.attempt_id == current.attempt_id for record in history):
        _fail("fixed-year FARS activation receipt was finalized before validation")
    successes = [record for record in history if record.receipt["status"] == "success"]
    if len(successes) >= lineage._MAX_SUCCESS_GENERATIONS:
        _fail("fixed-year FARS successful history exceeds its verification limit")
    if any(
        record.completed_at is not None and record.completed_at >= current.completed_at
        for record in successes
    ):
        _fail("fixed-year FARS candidate is not later than successful history")
    return sorted(
        [*successes, current],
        key=lambda record: (cast(dt.datetime, record.completed_at), record.attempt_id),
    )


def _load_verified_active_fars_year_snapshot(
    root: str | Path,
    *,
    year: int,
    contract_revision: int,
) -> _VerifiedFarsYearSnapshot:
    """Return exact canonical bytes after a descriptor-held full-history replay."""
    contract = fars_year_contract_revision(year, contract_revision)
    lineage._require_posix_filesystem_support()
    with ExitStack() as stack:
        root_fd = lineage._open_root(root)
        stack.callback(os.close, root_fd)
        source_fd = lineage._open_directory(root_fd, contract.source_id)
        stack.callback(os.close, source_fd)
        lineage._lock_absent(source_fd)
        raw_fd = lineage._open_directory(source_fd, "raw")
        stack.callback(os.close, raw_fd)
        raw_hashes_fd = lineage._open_directory(raw_fd, "sha256")
        stack.callback(os.close, raw_hashes_fd)
        normalized_fd = lineage._open_directory(source_fd, "normalized")
        stack.callback(os.close, normalized_fd)
        normalized_hashes_fd = lineage._open_directory(normalized_fd, "sha256")
        stack.callback(os.close, normalized_hashes_fd)
        current_bytes, current_digest = lineage._read_file(
            normalized_fd,
            "current.json",
            maximum=lineage._MAX_RECEIPT_BYTES,
        )
        current = lineage._parse_receipt(current_bytes, expected_source_id=contract.source_id)
        lineage._active_success(current.receipt)
        receipt_directory, history = _scan_optional_receipts(
            source_fd,
            source_id=contract.source_id,
        )
        initial_history = _history_identity(receipt_directory, history)
        active = _verify_chain(
            lineage._ordered_successes(current, history),
            raw_hashes_fd,
            normalized_hashes_fd,
            expected_year=contract.year,
            expected_source_id=contract.source_id,
            required_active_contract=contract,
        )
        if active.receipt.attempt_id != current.attempt_id:
            _fail("fixed-year FARS active receipt is not the final successful generation")
        final_current, final_digest = lineage._read_file(
            normalized_fd,
            "current.json",
            maximum=lineage._MAX_RECEIPT_BYTES,
        )
        if final_digest != current_digest or final_current != current_bytes:
            _fail("fixed-year FARS active receipt changed during verification")
        final_receipt_directory, final_history = _scan_optional_receipts(
            source_fd,
            source_id=contract.source_id,
        )
        if _history_identity(final_receipt_directory, final_history) != initial_history:
            _fail("fixed-year FARS receipt history changed during verification")
        lineage._lock_absent(source_fd)
        return _snapshot(active)


def _preflight_fars_year_ingestion_locked(
    source_root: Path,
    *,
    year: int,
    contract_revision: int,
) -> _FarsYearIngestionPreflight:
    """Reserve receipt capacity and bind one securely scanned ingestion lock."""
    contract = fars_year_contract_revision(year, contract_revision)
    lineage._require_posix_filesystem_support()
    with ExitStack() as stack:
        source_fd = lineage._open_root(source_root)
        stack.callback(os.close, source_fd)
        initial_lock = _lock_identity(source_fd)
        receipt_directory, history = _scan_optional_receipts(
            source_fd,
            source_id=contract.source_id,
        )
        if len(history) >= lineage._MAX_RECEIPTS:
            _fail("fixed-year FARS receipt history has no capacity for this attempt")
        if sum(record.receipt["status"] == "success" for record in history) >= (
            lineage._MAX_SUCCESS_GENERATIONS
        ):
            _fail("fixed-year FARS successful history has no capacity for this attempt")
        initial_history = _history_identity(receipt_directory, history)
        final_directory, final_history = _scan_optional_receipts(
            source_fd,
            source_id=contract.source_id,
        )
        final_history_identity = _history_identity(final_directory, final_history)
        if final_history_identity != initial_history:
            _fail("fixed-year FARS receipt history changed during ingestion preflight")
        final_lock = _lock_identity(source_fd)
        if final_lock != initial_lock:
            _fail("fixed-year FARS ingestion lock changed during ingestion preflight")
        return _FarsYearIngestionPreflight(initial_lock, initial_history)


def _validate_fars_year_receipt_finalization_locked(
    source_root: Path,
    *,
    year: int,
    contract_revision: int,
    expected_preflight: _FarsYearIngestionPreflight,
) -> None:
    """Authorize exactly one receipt write against the reserved locked state."""
    contract = fars_year_contract_revision(year, contract_revision)
    lineage._require_posix_filesystem_support()
    with ExitStack() as stack:
        source_fd = lineage._open_root(source_root)
        stack.callback(os.close, source_fd)
        initial_lock = _lock_identity(source_fd)
        receipt_directory, history = _scan_optional_receipts(
            source_fd,
            source_id=contract.source_id,
        )
        initial_history = _history_identity(receipt_directory, history)
        _require_expected_preflight(initial_lock, initial_history, expected_preflight)
        if len(history) >= lineage._MAX_RECEIPTS:
            _fail("fixed-year FARS receipt history has no capacity for this attempt")
        final_directory, final_history = _scan_optional_receipts(
            source_fd,
            source_id=contract.source_id,
        )
        final_history_identity = _history_identity(final_directory, final_history)
        if final_history_identity != initial_history:
            _fail("fixed-year FARS receipt history changed before receipt finalization")
        final_lock = _lock_identity(source_fd)
        _require_expected_preflight(final_lock, final_history_identity, expected_preflight)
        if final_lock != initial_lock:
            _fail("fixed-year FARS ingestion lock changed before receipt finalization")


def _validate_fars_year_history_candidate_locked(  # noqa: C901 - one held-FD transaction
    source_root: Path,
    candidate_normalized: bytes,
    *,
    year: int,
    contract_revision: int,
    started_at: str,
    expected_preflight: _FarsYearIngestionPreflight,
) -> None:
    """Replay a preserved candidate and its prior lineage before activation."""
    if type(candidate_normalized) is not bytes:
        _fail("fixed-year FARS history candidate bytes are invalid")
    contract = fars_year_contract_revision(year, contract_revision)
    started = lineage._timestamp(started_at)
    if started.isoformat().replace("+00:00", "Z") != started_at:
        _fail("fixed-year FARS candidate start timestamp is not canonical")
    normalized_digest = hashlib.sha256(candidate_normalized).hexdigest()
    synthetic = lineage._ReceiptRecord(
        attempt_id="candidate-history-check",
        started_at=started,
        completed_at=started,
        receipt={
            "raw_sha256": contract.raw_sha256,
            "normalized_sha256": normalized_digest,
        },
        payload=b"",
    )

    lineage._require_posix_filesystem_support()
    with ExitStack() as stack:
        source_fd = lineage._open_root(source_root)
        stack.callback(os.close, source_fd)
        initial_lock = _lock_identity(source_fd)
        raw_fd = lineage._open_directory(source_fd, "raw")
        stack.callback(os.close, raw_fd)
        raw_hashes_fd = lineage._open_directory(raw_fd, "sha256")
        stack.callback(os.close, raw_hashes_fd)
        normalized_fd = lineage._open_directory(source_fd, "normalized")
        stack.callback(os.close, normalized_fd)
        normalized_hashes_fd = lineage._open_directory(normalized_fd, "sha256")
        stack.callback(os.close, normalized_hashes_fd)
        receipt_directory, history = _scan_optional_receipts(
            source_fd,
            source_id=contract.source_id,
        )
        initial_history = _history_identity(receipt_directory, history)
        _require_expected_preflight(initial_lock, initial_history, expected_preflight)
        if len(history) >= lineage._MAX_RECEIPTS:
            _fail("fixed-year FARS receipt history has no capacity for this attempt")
        current_bytes: bytes | None
        current_digest: str | None
        try:
            current_bytes, current_digest = lineage._read_file(
                normalized_fd,
                "current.json",
                maximum=lineage._MAX_RECEIPT_BYTES,
            )
        except VerificationError:
            try:
                os.stat("current.json", dir_fd=normalized_fd, follow_symlinks=False)
            except FileNotFoundError:
                current_bytes = None
                current_digest = None
            except OSError:
                _fail("fixed-year FARS history preflight failed")
            else:
                raise

        previous: _VerifiedGeneration | None = None
        successes = [record for record in history if record.receipt["status"] == "success"]
        if current_bytes is None:
            if successes:
                _fail("fixed-year FARS history has successful receipts without an active marker")
        else:
            current = lineage._parse_receipt(
                current_bytes,
                expected_source_id=contract.source_id,
            )
            lineage._active_success(current.receipt)
            ordered = lineage._ordered_successes(current, history)
            previous = _verify_chain(
                ordered,
                raw_hashes_fd,
                normalized_hashes_fd,
                expected_year=contract.year,
                expected_source_id=contract.source_id,
                required_active_contract=None,
            )
            if previous.receipt.completed_at is None or previous.receipt.completed_at >= started:
                _fail("fixed-year FARS candidate is not later than active history")
            latest_digest = cast(str, previous.receipt.receipt["normalized_sha256"])
            if normalized_digest != latest_digest and any(
                record.receipt["normalized_sha256"] == normalized_digest for record in ordered[:-1]
            ):
                _fail("fixed-year FARS candidate reuses an older normalized generation")

        candidate = _verify_generation(
            synthetic,
            raw_hashes_fd,
            normalized_hashes_fd,
            expected_year=contract.year,
            expected_source_id=contract.source_id,
        )
        if candidate.contract != contract or candidate.normalized_bytes != candidate_normalized:
            _fail("fixed-year FARS history candidate does not match its requested contract")
        if previous is not None:
            _validate_transition(candidate, previous)
        elif candidate.contract.revision != 1:
            _fail("fixed-year FARS lineage must begin at contract revision 1")

        if current_bytes is None:
            try:
                os.stat("current.json", dir_fd=normalized_fd, follow_symlinks=False)
            except FileNotFoundError:
                pass
            except OSError:
                _fail("fixed-year FARS active marker changed during history validation")
            else:
                _fail("fixed-year FARS active marker changed during history validation")
        else:
            final_current, final_digest = lineage._read_file(
                normalized_fd,
                "current.json",
                maximum=lineage._MAX_RECEIPT_BYTES,
            )
            if final_digest != current_digest or final_current != current_bytes:
                _fail("fixed-year FARS active marker changed during history validation")
        final_directory, final_history = _scan_optional_receipts(
            source_fd,
            source_id=contract.source_id,
        )
        if _history_identity(final_directory, final_history) != initial_history:
            _fail("fixed-year FARS receipt history changed during history validation")
        final_lock = _lock_identity(source_fd)
        _require_expected_preflight(
            final_lock,
            _history_identity(final_directory, final_history),
            expected_preflight,
        )
        if final_lock != initial_lock:
            _fail("fixed-year FARS ingestion lock changed during history validation")


def _verify_activated_fars_year_locked(
    source_root: Path,
    candidate_normalized: bytes,
    success_marker: bytes,
    *,
    year: int,
    contract_revision: int,
    expected_preflight: _FarsYearIngestionPreflight,
) -> _VerifiedFarsYearSnapshot:
    """Replay a just-activated candidate while its ingestion lock is held."""
    if type(candidate_normalized) is not bytes or type(success_marker) is not bytes:
        _fail("fixed-year FARS activated candidate bytes are invalid")
    contract = fars_year_contract_revision(year, contract_revision)
    marker = lineage._parse_receipt(success_marker, expected_source_id=contract.source_id)
    lineage._active_success(marker.receipt)
    if marker.receipt["normalized_sha256"] != hashlib.sha256(candidate_normalized).hexdigest():
        _fail("fixed-year FARS activated candidate binding failed")

    lineage._require_posix_filesystem_support()
    with ExitStack() as stack:
        source_fd = lineage._open_root(source_root)
        stack.callback(os.close, source_fd)
        initial_lock = _lock_identity(source_fd)
        raw_fd = lineage._open_directory(source_fd, "raw")
        stack.callback(os.close, raw_fd)
        raw_hashes_fd = lineage._open_directory(raw_fd, "sha256")
        stack.callback(os.close, raw_hashes_fd)
        normalized_fd = lineage._open_directory(source_fd, "normalized")
        stack.callback(os.close, normalized_fd)
        normalized_hashes_fd = lineage._open_directory(normalized_fd, "sha256")
        stack.callback(os.close, normalized_hashes_fd)
        current_bytes, current_digest = lineage._read_file(
            normalized_fd,
            "current.json",
            maximum=lineage._MAX_RECEIPT_BYTES,
        )
        if current_bytes != success_marker:
            _fail("fixed-year FARS activated marker does not match the locked store")
        receipt_directory, history = _scan_optional_receipts(
            source_fd,
            source_id=contract.source_id,
        )
        initial_history = _history_identity(receipt_directory, history)
        _require_expected_preflight(initial_lock, initial_history, expected_preflight)
        if len(history) >= lineage._MAX_RECEIPTS:
            _fail("fixed-year FARS receipt history has no capacity for this attempt")
        active = _verify_chain(
            _locked_successes(marker, history),
            raw_hashes_fd,
            normalized_hashes_fd,
            expected_year=contract.year,
            expected_source_id=contract.source_id,
            required_active_contract=contract,
        )
        if active.normalized_bytes != candidate_normalized:
            _fail("fixed-year FARS activated normalized bytes do not match the locked store")
        final_current, final_digest = lineage._read_file(
            normalized_fd,
            "current.json",
            maximum=lineage._MAX_RECEIPT_BYTES,
        )
        if final_digest != current_digest or final_current != current_bytes:
            _fail("fixed-year FARS active receipt changed during activation verification")
        final_directory, final_history = _scan_optional_receipts(
            source_fd,
            source_id=contract.source_id,
        )
        if _history_identity(final_directory, final_history) != initial_history:
            _fail("fixed-year FARS receipt history changed during activation verification")
        final_lock = _lock_identity(source_fd)
        _require_expected_preflight(
            final_lock,
            _history_identity(final_directory, final_history),
            expected_preflight,
        )
        if final_lock != initial_lock:
            _fail("fixed-year FARS ingestion lock changed during activation verification")
        return _snapshot(active)


def verify_active_fars_year(
    root: str | Path,
    *,
    year: int,
    contract_revision: int,
) -> VerifiedFarsYearEvidence:
    """Verify one exact annual contract and return aggregate-only evidence."""
    return _load_verified_active_fars_year_snapshot(
        root,
        year=year,
        contract_revision=contract_revision,
    ).evidence


__all__ = ["VerifiedFarsYearEvidence", "verify_active_fars_year"]
