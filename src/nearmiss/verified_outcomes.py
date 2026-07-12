# SPDX-License-Identifier: Apache-2.0
"""Read-only verification of the active FARS ingestion lineage."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
import stat
from collections.abc import Mapping
from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path
from typing import Any, NoReturn, cast

from jsonschema import Draft202012Validator, FormatChecker

from .adapters.fars import FarsAdapter, read_export_bytes
from .adapters.fars_joined import collect_joined, read_joined_export_bytes
from .ingestion import RECEIPT_SCHEMA
from .joined_outcome_artifacts import (
    build_joined_outcome_artifact,
    canonical_joined_outcome_artifact_bytes,
    validate_joined_outcome_artifact,
)
from .outcome_artifacts import (
    build_outcome_artifact,
    canonical_outcome_artifact_bytes,
    validate_outcome_artifact,
)

_MAX_RECEIPT_BYTES = 1024 * 1024
_MAX_RECEIPTS = 10_000
_MAX_SUCCESS_GENERATIONS = 1_000
_MAX_RAW_BYTES = 256 * 1024 * 1024
_MAX_NORMALIZED_BYTES = 512 * 1024 * 1024
_MAX_JOINED_RAW_BYTES = 64 * 1024 * 1024
_MAX_JOINED_NORMALIZED_BYTES = 64 * 1024 * 1024
_DIRECTORY_MODE = 0o700
_FILE_MODE = 0o400
_SAFE_RECEIPT_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}\.json$")
_RECEIPT_VALIDATOR = Draft202012Validator(RECEIPT_SCHEMA, format_checker=FormatChecker())
_DIRECTORY_FLAGS = (
    os.O_RDONLY
    | getattr(os, "O_DIRECTORY", 0)
    | getattr(os, "O_NOFOLLOW", 0)
    | getattr(os, "O_CLOEXEC", 0)
)
_FILE_FLAGS = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
_PROOF_TOKEN = object()
_JOINED_PROOF_TOKEN = object()
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_SEMVER_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
_SAFE_ATTEMPT_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class VerificationError(Exception):
    """An active official-outcome lineage could not be authenticated."""


@dataclass(frozen=True, init=False)
class VerifiedOutcomeEvidence:
    """Safe aggregate metadata from a fully verified active FARS transaction."""

    source_id: str
    dataset_year: int
    adapter_version: str
    release_status: str
    records_read: int
    records_accepted: int
    records_rejected: int
    raw_sha256: str
    normalized_sha256: str
    attempt_id: str

    def __init__(
        self,
        *,
        source_id: str,
        dataset_year: int,
        adapter_version: str,
        release_status: str,
        records_read: int,
        records_accepted: int,
        records_rejected: int,
        raw_sha256: str,
        normalized_sha256: str,
        attempt_id: str,
        _proof_token: object,
    ) -> None:
        if _proof_token is not _PROOF_TOKEN:
            raise VerificationError("verified outcome evidence requires an internal proof")
        if (
            source_id != "fars"
            or isinstance(dataset_year, bool)
            or not 1975 <= dataset_year <= 9999
            or _SEMVER_RE.fullmatch(adapter_version) is None
            or release_status not in {"preliminary", "final"}
            or any(
                isinstance(value, bool)
                for value in (records_read, records_accepted, records_rejected)
            )
            or records_read < 1
            or records_accepted < 1
            or records_rejected < 0
            or records_accepted + records_rejected != records_read
            or _SHA256_RE.fullmatch(raw_sha256) is None
            or _SHA256_RE.fullmatch(normalized_sha256) is None
            or _SAFE_ATTEMPT_ID.fullmatch(attempt_id) is None
        ):
            raise VerificationError("verified outcome evidence invariants are invalid")
        for name, value in (
            ("source_id", source_id),
            ("dataset_year", dataset_year),
            ("adapter_version", adapter_version),
            ("release_status", release_status),
            ("records_read", records_read),
            ("records_accepted", records_accepted),
            ("records_rejected", records_rejected),
            ("raw_sha256", raw_sha256),
            ("normalized_sha256", normalized_sha256),
            ("attempt_id", attempt_id),
        ):
            object.__setattr__(self, name, value)

    @property
    def receipt_id(self) -> str:
        """Alias the ingestion attempt identity for audit-oriented callers."""
        return self.attempt_id

    def as_dict(self) -> dict[str, object]:
        """Return safe aggregate metadata without verifier internals."""
        return {
            "source_id": self.source_id,
            "dataset_year": self.dataset_year,
            "adapter_version": self.adapter_version,
            "release_status": self.release_status,
            "records_read": self.records_read,
            "records_accepted": self.records_accepted,
            "records_rejected": self.records_rejected,
            "raw_sha256": self.raw_sha256,
            "normalized_sha256": self.normalized_sha256,
            "attempt_id": self.attempt_id,
        }


@dataclass(frozen=True, init=False)
class VerifiedJoinedOutcomeEvidence:
    """Safe aggregate metadata from a fully verified joined FARS transaction."""

    source_id: str
    dataset_year: int
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
        _proof_token: object,
    ) -> None:
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
        if (
            _proof_token is not _JOINED_PROOF_TOKEN
            or source_id != "fars-joined"
            or dataset_year != 2024
            or _SEMVER_RE.fullmatch(crash_mapping_version) is None
            or _SEMVER_RE.fullmatch(person_mapping_version) is None
            or not release_status
            or any(isinstance(value, bool) or value < 0 for value in counts)
            or crash_records_read != crash_records_accepted + crash_records_rejected
            or person_records_read != person_records_accepted + person_records_excluded
            or cases_joined != crash_records_accepted
            or cases_excluded != crash_records_rejected
            or any(
                _SHA256_RE.fullmatch(value) is None
                for value in (raw_sha256, accident_sha256, person_sha256, normalized_sha256)
            )
            or _SAFE_ATTEMPT_ID.fullmatch(attempt_id) is None
        ):
            raise VerificationError("verified joined outcome evidence invariants are invalid")
        values = locals()
        for name in self.__dataclass_fields__:
            object.__setattr__(self, name, values[name])

    @property
    def receipt_id(self) -> str:
        return self.attempt_id

    def as_dict(self) -> dict[str, object]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True)
class _ReceiptRecord:
    attempt_id: str
    started_at: dt.datetime
    completed_at: dt.datetime | None
    receipt: Mapping[str, object]
    payload: bytes


@dataclass(frozen=True)
class _VerifiedGeneration:
    receipt: _ReceiptRecord
    artifact: Mapping[str, object]


def _fail(message: str) -> NoReturn:
    raise VerificationError(message)


def _effective_uid() -> int | None:
    getter = getattr(os, "geteuid", None)
    return cast(int, getter()) if getter is not None else None


def _require_posix_filesystem_support() -> None:
    if (
        not hasattr(os, "O_NOFOLLOW")
        or not hasattr(os, "O_DIRECTORY")
        or os.open not in os.supports_dir_fd
        or os.stat not in os.supports_dir_fd
        or os.listdir not in os.supports_fd
    ):
        _fail("FARS lineage verification requires secure POSIX filesystem primitives")


def _validate_metadata(metadata: os.stat_result, *, directory: bool) -> None:
    expected_kind = stat.S_ISDIR if directory else stat.S_ISREG
    expected_mode = _DIRECTORY_MODE if directory else _FILE_MODE
    owner = _effective_uid()
    if (
        not expected_kind(metadata.st_mode)
        or (owner is not None and metadata.st_uid != owner)
        or stat.S_IMODE(metadata.st_mode) != expected_mode
        or (not directory and metadata.st_nlink != 1)
    ):
        _fail("FARS lineage filesystem verification failed")


def _open_root(root: str | Path) -> int:
    try:
        descriptor = os.open(os.fspath(root), _DIRECTORY_FLAGS)
    except (TypeError, ValueError, OSError):
        _fail("FARS lineage filesystem verification failed")
    try:
        _validate_metadata(os.fstat(descriptor), directory=True)
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _open_directory(parent: int, name: str) -> int:
    if not name or "/" in name or name in {".", ".."}:
        _fail("FARS lineage filesystem verification failed")
    try:
        descriptor = os.open(name, _DIRECTORY_FLAGS, dir_fd=parent)
    except OSError:
        _fail("FARS lineage filesystem verification failed")
    try:
        _validate_metadata(os.fstat(descriptor), directory=True)
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _open_file(parent: int, name: str) -> int:
    if not name or "/" in name or name in {".", ".."}:
        _fail("FARS lineage filesystem verification failed")
    try:
        descriptor = os.open(name, _FILE_FLAGS, dir_fd=parent)
    except OSError:
        _fail("FARS lineage filesystem verification failed")
    try:
        _validate_metadata(os.fstat(descriptor), directory=False)
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _read_file(parent: int, name: str, *, maximum: int) -> tuple[bytes, str]:
    descriptor = _open_file(parent, name)
    digest = hashlib.sha256()
    payload = bytearray()
    try:
        size = os.fstat(descriptor).st_size
        if size < 0 or size > maximum:
            _fail("FARS lineage file exceeds its verification size limit")
        with os.fdopen(descriptor, "rb") as handle:
            descriptor = -1
            while block := handle.read(min(1024 * 1024, maximum + 1 - len(payload))):
                payload.extend(block)
                digest.update(block)
                if len(payload) > maximum:
                    _fail("FARS lineage file exceeds its verification size limit")
        return bytes(payload), digest.hexdigest()
    except OSError:
        _fail("FARS lineage filesystem verification failed")
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _lock_absent(source: int) -> None:
    try:
        os.stat(".ingestion.lock", dir_fd=source, follow_symlinks=False)
    except FileNotFoundError:
        return
    except OSError:
        _fail("FARS lineage lock verification failed")
    _fail("FARS lineage verification refused while ingestion is locked")


def _reject_constant(_value: str) -> NoReturn:
    _fail("FARS lineage JSON decoding failed")


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _fail("FARS lineage JSON decoding failed")
        result[key] = value
    return result


def _strict_json(payload: bytes) -> Mapping[str, object]:
    try:
        value = json.loads(
            payload.decode("utf-8", errors="strict"),
            object_pairs_hook=_strict_object,
            parse_constant=_reject_constant,
        )
    except VerificationError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError):
        _fail("FARS lineage JSON decoding failed")
    if not isinstance(value, dict):
        _fail("FARS lineage JSON decoding failed")
    return cast(Mapping[str, object], value)


def _validate_receipt(receipt: Mapping[str, object], *, expected_source_id: str = "fars") -> None:
    if any(_RECEIPT_VALIDATOR.iter_errors(receipt)):
        _fail("FARS lineage receipt validation failed")
    if receipt["source_id"] != expected_source_id:
        _fail("FARS lineage receipt source is invalid")
    raw_digest = receipt["raw_sha256"]
    raw_path = receipt["raw_snapshot"]
    if raw_path is not None and raw_path != f"raw/sha256/{raw_digest}.bin":
        _fail("FARS lineage receipt raw identity is invalid")
    normalized_digest = receipt["normalized_sha256"]
    normalized_path = receipt["normalized_path"]
    if (
        normalized_path is not None
        and normalized_path != f"normalized/sha256/{normalized_digest}.bin"
    ):
        _fail("FARS lineage receipt normalized identity is invalid")


def _active_success(receipt: Mapping[str, object]) -> None:
    if (
        receipt["status"] != "success"
        or receipt["activated"] is not True
        or receipt["error"] is not None
    ):
        _fail("FARS lineage active receipt is not successful")


def _canonical_receipt_bytes(receipt: Mapping[str, object]) -> bytes:
    return (json.dumps(receipt, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _timestamp(value: str) -> dt.datetime:
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        _fail("FARS lineage receipt chronology is invalid")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        _fail("FARS lineage receipt chronology is invalid")
    return parsed.astimezone(dt.UTC)


def _parse_receipt(
    payload: bytes,
    filename: str | None = None,
    *,
    expected_source_id: str = "fars",
) -> _ReceiptRecord:
    receipt = _strict_json(payload)
    _validate_receipt(receipt, expected_source_id=expected_source_id)
    if payload != _canonical_receipt_bytes(receipt):
        _fail("FARS lineage receipt encoding is not canonical")
    attempt_id = cast(str, receipt["attempt_id"])
    if filename is not None and filename != f"{attempt_id}.json":
        _fail("FARS lineage receipt filename is not canonical")
    started_at = _timestamp(cast(str, receipt["started_at"]))
    completed_raw = receipt["completed_at"]
    completed_at = _timestamp(cast(str, completed_raw)) if completed_raw is not None else None
    if completed_at is not None and started_at > completed_at:
        _fail("FARS lineage receipt chronology is invalid")
    return _ReceiptRecord(
        attempt_id=attempt_id,
        started_at=started_at,
        completed_at=completed_at,
        receipt=receipt,
        payload=payload,
    )


def _scan_receipts(receipts: int, *, expected_source_id: str = "fars") -> list[_ReceiptRecord]:
    try:
        names = sorted(os.listdir(receipts))
    except OSError:
        _fail("FARS lineage receipt history scan failed")
    if len(names) > _MAX_RECEIPTS:
        _fail("FARS lineage receipt history exceeds its verification limit")
    records: list[_ReceiptRecord] = []
    for name in names:
        if _SAFE_RECEIPT_NAME.fullmatch(name) is None:
            _fail("FARS lineage receipt filename is not canonical")
        payload, _digest = _read_file(receipts, name, maximum=_MAX_RECEIPT_BYTES)
        records.append(_parse_receipt(payload, name, expected_source_id=expected_source_id))
    return records


def _ordered_successes(
    current: _ReceiptRecord,
    history: list[_ReceiptRecord],
) -> list[_ReceiptRecord]:
    if current.completed_at is None:
        _fail("FARS lineage active receipt completion time is invalid")
    matches = [record for record in history if record.attempt_id == current.attempt_id]
    if len(matches) != 1 or matches[0].payload != current.payload:
        _fail("FARS lineage active and historical receipt mismatch")
    successful = [record for record in history if record.receipt["status"] == "success"]
    if not successful:
        _fail("FARS lineage receipt history has no successful receipt")
    if len(successful) > _MAX_SUCCESS_GENERATIONS:
        _fail("FARS lineage successful history exceeds its verification limit")
    if any(
        record.attempt_id != current.attempt_id
        and record.completed_at is not None
        and record.completed_at >= current.completed_at
        for record in successful
    ):
        _fail("FARS lineage active receipt is not the latest successful receipt")
    return sorted(
        successful,
        key=lambda record: (cast(dt.datetime, record.completed_at), record.attempt_id),
    )


def _validate_regression_policy(
    current_artifact: Mapping[str, object],
    previous_artifact: Mapping[str, object],
) -> None:
    current_policy = cast(Mapping[str, object], current_artifact["normalization"])
    previous_policy = cast(Mapping[str, object], previous_artifact["normalization"])
    current_provenance = cast(Mapping[str, object], current_artifact["provenance"])
    previous_provenance = cast(Mapping[str, object], previous_artifact["provenance"])
    if (
        cast(int, current_policy["expected_year"]) < cast(int, previous_policy["expected_year"])
        and current_policy["allow_year_regression"] is not True
    ):
        _fail("FARS lineage dataset year regressed without recorded authorization")
    if (
        cast(int, current_provenance["records_accepted"])
        < cast(int, previous_provenance["records_accepted"])
        and current_policy["allow_record_regression"] is not True
    ):
        _fail("FARS lineage accepted-record count regressed without recorded authorization")


def _verify_generation(
    receipt: _ReceiptRecord,
    raw_hashes: int,
    normalized_hashes: int,
) -> _VerifiedGeneration:
    raw_digest = cast(str, receipt.receipt["raw_sha256"])
    normalized_digest = cast(str, receipt.receipt["normalized_sha256"])
    raw, observed_raw = _read_file(raw_hashes, f"{raw_digest}.bin", maximum=_MAX_RAW_BYTES)
    if observed_raw != raw_digest:
        _fail("FARS lineage raw artifact hash mismatch")
    normalized, observed_normalized = _read_file(
        normalized_hashes,
        f"{normalized_digest}.bin",
        maximum=_MAX_NORMALIZED_BYTES,
    )
    if observed_normalized != normalized_digest:
        _fail("FARS lineage normalized artifact hash mismatch")
    artifact = _strict_json(normalized)
    try:
        validate_outcome_artifact(artifact, expected_source_id="fars")
        canonical = canonical_outcome_artifact_bytes(artifact)
    except (TypeError, ValueError):
        _fail("FARS lineage normalized artifact validation failed")
    if canonical != normalized:
        _fail("FARS lineage normalized artifact encoding is not canonical")
    provenance = cast(Mapping[str, object], artifact["provenance"])
    if provenance["input_sha256"] != raw_digest:
        _fail("FARS lineage artifact provenance does not match the raw artifact")
    _replay(raw, normalized, artifact)
    return _VerifiedGeneration(receipt=receipt, artifact=artifact)


def _generation_key(receipt: _ReceiptRecord) -> tuple[str, str]:
    return (
        cast(str, receipt.receipt["raw_sha256"]),
        cast(str, receipt.receipt["normalized_sha256"]),
    )


def _verify_success_chain(
    receipts: list[_ReceiptRecord],
    raw_hashes: int,
    normalized_hashes: int,
) -> _VerifiedGeneration:
    previous: _VerifiedGeneration | None = None
    for receipt in receipts:
        expected_previous = (
            None if previous is None else previous.receipt.receipt["normalized_sha256"]
        )
        if receipt.receipt["previous_normalized_sha256"] != expected_previous:
            _fail("FARS lineage predecessor link is invalid")
        if previous is not None and _generation_key(receipt) == _generation_key(previous.receipt):
            generation = _VerifiedGeneration(receipt=receipt, artifact=previous.artifact)
        else:
            generation = _verify_generation(receipt, raw_hashes, normalized_hashes)
        if previous is not None:
            _validate_regression_policy(generation.artifact, previous.artifact)
        previous = generation
    if previous is None:
        _fail("FARS lineage receipt history has no successful receipt")
    return previous


def _replay(
    raw: bytes,
    normalized: bytes,
    artifact: Mapping[str, object],
) -> None:
    provenance = cast(Mapping[str, object], artifact["provenance"])
    policy = cast(Mapping[str, object], artifact["normalization"])
    try:
        batch = read_export_bytes(raw)
        outcomes, replayed_provenance = FarsAdapter().parse(
            batch,
            release_status=cast(str, provenance["release_status"]),
        )
        rebuilt = build_outcome_artifact(
            outcomes,
            replayed_provenance,
            expected_year=cast(int, policy["expected_year"]),
            distribution_url=cast(str, policy["distribution_url"]),
            adapter_version=cast(str, policy["adapter_version"]),
            max_invalid_fraction=cast(float, policy["max_invalid_fraction"]),
            allow_record_regression=cast(bool, policy["allow_record_regression"]),
            allow_year_regression=cast(bool, policy["allow_year_regression"]),
        )
        replayed = canonical_outcome_artifact_bytes(rebuilt)
    except (OSError, TypeError, ValueError):
        _fail("FARS lineage deterministic replay failed")
    if replayed != normalized:
        _fail("FARS lineage normalized artifact does not match deterministic replay")


def _evidence_from(
    current: _ReceiptRecord,
    artifact: Mapping[str, object],
) -> VerifiedOutcomeEvidence:
    provenance = cast(Mapping[str, object], artifact["provenance"])
    policy = cast(Mapping[str, object], artifact["normalization"])
    rejection_reasons = cast(Mapping[str, int], provenance["rejection_reasons"])
    return VerifiedOutcomeEvidence(
        source_id="fars",
        dataset_year=cast(int, policy["expected_year"]),
        adapter_version=cast(str, policy["adapter_version"]),
        release_status=cast(str, provenance["release_status"]),
        records_read=cast(int, provenance["records_read"]),
        records_accepted=cast(int, provenance["records_accepted"]),
        records_rejected=sum(rejection_reasons.values()),
        raw_sha256=cast(str, current.receipt["raw_sha256"]),
        normalized_sha256=cast(str, current.receipt["normalized_sha256"]),
        attempt_id=current.attempt_id,
        _proof_token=_PROOF_TOKEN,
    )


def verify_active_fars(root: str | Path) -> VerifiedOutcomeEvidence:
    """Verify active FARS bytes and replay their derivation without mutation."""
    _require_posix_filesystem_support()
    with ExitStack() as stack:
        root_fd = _open_root(root)
        stack.callback(os.close, root_fd)
        source_fd = _open_directory(root_fd, "fars")
        stack.callback(os.close, source_fd)
        _lock_absent(source_fd)
        raw_fd = _open_directory(source_fd, "raw")
        stack.callback(os.close, raw_fd)
        raw_hashes_fd = _open_directory(raw_fd, "sha256")
        stack.callback(os.close, raw_hashes_fd)
        normalized_fd = _open_directory(source_fd, "normalized")
        stack.callback(os.close, normalized_fd)
        normalized_hashes_fd = _open_directory(normalized_fd, "sha256")
        stack.callback(os.close, normalized_hashes_fd)
        receipts_fd = _open_directory(source_fd, "receipts")
        stack.callback(os.close, receipts_fd)

        current_bytes, current_digest = _read_file(
            normalized_fd, "current.json", maximum=_MAX_RECEIPT_BYTES
        )
        current = _parse_receipt(current_bytes)
        _active_success(current.receipt)
        history = _scan_receipts(receipts_fd)
        successful = _ordered_successes(current, history)
        active = _verify_success_chain(
            successful,
            raw_hashes_fd,
            normalized_hashes_fd,
        )
        if active.receipt.attempt_id != current.attempt_id:
            _fail("FARS lineage active receipt is not the final successful generation")
        final_current, final_digest = _read_file(
            normalized_fd, "current.json", maximum=_MAX_RECEIPT_BYTES
        )
        if final_digest != current_digest or final_current != current_bytes:
            _fail("FARS lineage active receipt changed during verification")
        _lock_absent(source_fd)
        return _evidence_from(current, active.artifact)


def _joined_sections(
    artifact: Mapping[str, object],
) -> tuple[
    Mapping[str, object],
    Mapping[str, object],
    Mapping[str, object],
    Mapping[str, object],
]:
    return (
        cast(Mapping[str, object], artifact["crash_normalization"]),
        cast(Mapping[str, object], artifact["crash_provenance"]),
        cast(Mapping[str, object], artifact["join_policy"]),
        cast(Mapping[str, object], artifact["person_join"]),
    )


def _joined_mode_totals(artifact: Mapping[str, object]) -> dict[str, int]:
    totals: dict[str, int] = {}
    records = cast(list[Mapping[str, object]], artifact["records"])
    for record in records:
        summary = cast(Mapping[str, object], record["mode_summary"])
        for field in ("involved_person_count_by_mode", "fatality_count_by_mode"):
            counts = cast(Mapping[str, int], summary[field])
            for mode, count in counts.items():
                key = f"{field}:{mode}"
                totals[key] = totals.get(key, 0) + count
    return totals


def _validate_joined_regression(
    current: Mapping[str, object], previous: Mapping[str, object]
) -> None:
    current_policy, current_crash, current_join_policy, current_person = _joined_sections(current)
    previous_policy, previous_crash, _previous_join_policy, previous_person = _joined_sections(
        previous
    )
    if (
        str(previous_crash["release_status"]).casefold() == "final"
        and str(current_crash["release_status"]).casefold() != "final"
        and current_join_policy["allow_release_regression"] is not True
    ):
        _fail("joined FARS lineage release status downgraded from final")
    if (
        cast(int, current_policy["expected_year"]) < cast(int, previous_policy["expected_year"])
        and current_policy["allow_year_regression"] is not True
    ):
        _fail("joined FARS lineage dataset year regressed without authorization")
    positive_metrics = (
        (current_crash, previous_crash, "records_read"),
        (current_crash, previous_crash, "records_accepted"),
        (current_person, previous_person, "records_read"),
        (current_person, previous_person, "records_accepted"),
        (current_person, previous_person, "cases_joined"),
    )
    exclusion_metrics = (
        "records_excluded_with_rejected_crash",
        "cases_excluded_with_rejected_crash",
    )
    aggregate_regressed = any(
        cast(int, current_values[key]) < cast(int, previous_values[key])
        for current_values, previous_values, key in positive_metrics
    ) or any(
        cast(int, current_person[key]) > cast(int, previous_person[key])
        for key in exclusion_metrics
    )
    if aggregate_regressed and current_policy["allow_record_regression"] is not True:
        _fail("joined FARS lineage aggregate counts regressed without authorization")
    current_modes = _joined_mode_totals(current)
    previous_modes = _joined_mode_totals(previous)
    if (
        any(current_modes[key] < count for key, count in previous_modes.items())
        and current_join_policy["allow_mode_regression"] is not True
    ):
        _fail("joined FARS lineage mode counts regressed without authorization")


def _replay_joined(raw: bytes, normalized: bytes, artifact: Mapping[str, object]) -> None:
    policy, crash, join_policy, _person = _joined_sections(artifact)
    try:
        batch = read_joined_export_bytes(raw)
        outcomes, summaries, replayed_crash, replayed_person = collect_joined(
            batch,
            release_status=cast(str, crash["release_status"]),
        )
        rebuilt = build_joined_outcome_artifact(
            outcomes,
            summaries,
            replayed_person,
            replayed_crash,
            distribution_url=cast(str, policy["distribution_url"]),
            max_invalid_fraction=cast(float, policy["max_invalid_fraction"]),
            allow_record_regression=cast(bool, policy["allow_record_regression"]),
            allow_mode_regression=cast(bool, join_policy["allow_mode_regression"]),
            allow_release_regression=cast(bool, join_policy["allow_release_regression"]),
            allow_year_regression=cast(bool, policy["allow_year_regression"]),
        )
        replayed = canonical_joined_outcome_artifact_bytes(rebuilt)
    except (OSError, TypeError, ValueError):
        _fail("joined FARS lineage deterministic replay failed")
    if replayed != normalized:
        _fail("joined FARS normalized artifact does not match deterministic replay")


def _verify_joined_generation(
    receipt: _ReceiptRecord,
    raw_hashes: int,
    normalized_hashes: int,
) -> _VerifiedGeneration:
    raw_digest, normalized_digest = _generation_key(receipt)
    raw, observed_raw = _read_file(raw_hashes, f"{raw_digest}.bin", maximum=_MAX_JOINED_RAW_BYTES)
    if observed_raw != raw_digest:
        _fail("joined FARS raw artifact hash mismatch")
    normalized, observed_normalized = _read_file(
        normalized_hashes,
        f"{normalized_digest}.bin",
        maximum=_MAX_JOINED_NORMALIZED_BYTES,
    )
    if observed_normalized != normalized_digest:
        _fail("joined FARS normalized artifact hash mismatch")
    artifact = _strict_json(normalized)
    try:
        validate_joined_outcome_artifact(artifact)
        canonical = canonical_joined_outcome_artifact_bytes(artifact)
    except (TypeError, ValueError):
        _fail("joined FARS normalized artifact validation failed")
    if canonical != normalized:
        _fail("joined FARS normalized artifact encoding is not canonical")
    _policy, crash, _join_policy, person = _joined_sections(artifact)
    if crash["input_sha256"] != raw_digest or person["input_sha256"] != raw_digest:
        _fail("joined FARS artifact provenance does not match the raw artifact")
    _replay_joined(raw, normalized, artifact)
    return _VerifiedGeneration(receipt=receipt, artifact=artifact)


def _verify_joined_chain(
    receipts: list[_ReceiptRecord], raw_hashes: int, normalized_hashes: int
) -> _VerifiedGeneration:
    previous: _VerifiedGeneration | None = None
    seen_normalized: set[str] = set()
    for receipt in receipts:
        expected_previous = (
            None if previous is None else previous.receipt.receipt["normalized_sha256"]
        )
        if receipt.receipt["previous_normalized_sha256"] != expected_previous:
            _fail("joined FARS lineage predecessor link is invalid")
        generation_key = _generation_key(receipt)
        normalized_digest = generation_key[1]
        if previous is not None and generation_key == _generation_key(previous.receipt):
            generation = _VerifiedGeneration(receipt=receipt, artifact=previous.artifact)
        elif normalized_digest in seen_normalized:
            _fail("joined FARS lineage reused an older normalized generation")
        else:
            generation = _verify_joined_generation(receipt, raw_hashes, normalized_hashes)
        if previous is not None:
            _validate_joined_regression(generation.artifact, previous.artifact)
        seen_normalized.add(normalized_digest)
        previous = generation
    if previous is None:
        _fail("joined FARS lineage receipt history has no successful receipt")
    return previous


def _joined_evidence_from(
    current: _ReceiptRecord, artifact: Mapping[str, object]
) -> VerifiedJoinedOutcomeEvidence:
    policy, crash, _join_policy, person = _joined_sections(artifact)
    crash_rejected = sum(cast(Mapping[str, int], crash["rejection_reasons"]).values())
    return VerifiedJoinedOutcomeEvidence(
        source_id="fars-joined",
        dataset_year=cast(int, policy["expected_year"]),
        crash_mapping_version=cast(str, policy["adapter_version"]),
        person_mapping_version=cast(str, person["mapping_version"]),
        release_status=cast(str, crash["release_status"]),
        crash_records_read=cast(int, crash["records_read"]),
        crash_records_accepted=cast(int, crash["records_accepted"]),
        crash_records_rejected=crash_rejected,
        person_records_read=cast(int, person["records_read"]),
        person_records_accepted=cast(int, person["records_accepted"]),
        person_records_excluded=cast(int, person["records_excluded_with_rejected_crash"]),
        cases_joined=cast(int, person["cases_joined"]),
        cases_excluded=cast(int, person["cases_excluded_with_rejected_crash"]),
        raw_sha256=cast(str, current.receipt["raw_sha256"]),
        accident_sha256=cast(str, person["accident_sha256"]),
        person_sha256=cast(str, person["person_sha256"]),
        normalized_sha256=cast(str, current.receipt["normalized_sha256"]),
        attempt_id=current.attempt_id,
        _proof_token=_JOINED_PROOF_TOKEN,
    )


def verify_active_fars_joined(root: str | Path) -> VerifiedJoinedOutcomeEvidence:
    """Verify the complete active joined-FARS lineage without returning record data."""
    _require_posix_filesystem_support()
    with ExitStack() as stack:
        root_fd = _open_root(root)
        stack.callback(os.close, root_fd)
        source_fd = _open_directory(root_fd, "fars-joined")
        stack.callback(os.close, source_fd)
        _lock_absent(source_fd)
        raw_fd = _open_directory(source_fd, "raw")
        stack.callback(os.close, raw_fd)
        raw_hashes_fd = _open_directory(raw_fd, "sha256")
        stack.callback(os.close, raw_hashes_fd)
        normalized_fd = _open_directory(source_fd, "normalized")
        stack.callback(os.close, normalized_fd)
        normalized_hashes_fd = _open_directory(normalized_fd, "sha256")
        stack.callback(os.close, normalized_hashes_fd)
        receipts_fd = _open_directory(source_fd, "receipts")
        stack.callback(os.close, receipts_fd)

        current_bytes, current_digest = _read_file(
            normalized_fd, "current.json", maximum=_MAX_RECEIPT_BYTES
        )
        current = _parse_receipt(current_bytes, expected_source_id="fars-joined")
        _active_success(current.receipt)
        history = _scan_receipts(receipts_fd, expected_source_id="fars-joined")
        active = _verify_joined_chain(
            _ordered_successes(current, history), raw_hashes_fd, normalized_hashes_fd
        )
        if active.receipt.attempt_id != current.attempt_id:
            _fail("joined FARS active receipt is not the final successful generation")
        final_current, final_digest = _read_file(
            normalized_fd, "current.json", maximum=_MAX_RECEIPT_BYTES
        )
        if final_digest != current_digest or final_current != current_bytes:
            _fail("joined FARS active receipt changed during verification")
        _lock_absent(source_fd)
        return _joined_evidence_from(current, active.artifact)
