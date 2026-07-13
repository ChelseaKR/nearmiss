# SPDX-License-Identifier: Apache-2.0
"""Locked activation of one exact, private, fixed-year FARS artifact."""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from typing import cast

from . import verified_fars_years as year_verifier
from .fars_year_contracts import (
    FARS_RAW_ARCHIVE_MAX_BYTES,
    FarsYearContract,
    fars_year_contract_from_descriptor,
    fars_year_contract_revision,
)
from .ingestion import Clock, IngestionError, run_ingestion
from .joined_outcome_artifacts_v2 import (
    canonical_joined_outcome_artifact_v2_bytes,
    canonical_joined_outcome_artifact_v2_from_pinned_archive,
)
from .private_paths import (
    PrivateRootPreflightError,
    RepositoryContainmentError,
    RepositoryRootPreflightError,
    require_private_root_outside_repository,
)

MAX_FARS_YEAR_ARTIFACT_BYTES = 512 * 1024 * 1024


class _DuplicateJSONKeyError(ValueError):
    """A private artifact contained an ambiguous JSON object."""


def _strict_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise _DuplicateJSONKeyError
        value[key] = item
    return value


def _artifact(payload: bytes, *, contract: FarsYearContract) -> dict[str, object]:
    if not isinstance(payload, bytes):
        raise TypeError("private FARS year artifact must be bytes")
    if not payload or len(payload) > MAX_FARS_YEAR_ARTIFACT_BYTES:
        raise ValueError("private FARS year artifact exceeds its closed byte bounds")
    try:
        decoded = json.loads(payload, object_pairs_hook=_strict_object)
    except (UnicodeDecodeError, json.JSONDecodeError, _DuplicateJSONKeyError):
        raise ValueError("private FARS year artifact is not unambiguous JSON") from None
    if not isinstance(decoded, dict) or not all(isinstance(key, str) for key in decoded):
        raise ValueError("private FARS year artifact must be a JSON object")
    artifact = cast(dict[str, object], decoded)
    try:
        canonical = canonical_joined_outcome_artifact_v2_bytes(artifact)
        source_contract = artifact["source_contract"]
        if not isinstance(source_contract, dict):
            raise ValueError
        resolved = fars_year_contract_from_descriptor(source_contract)
    except (KeyError, TypeError, ValueError):
        raise ValueError(
            "private FARS year artifact is not an exact registered v2 artifact"
        ) from None
    if canonical != payload:
        raise ValueError("private FARS year artifact is not canonical JSON")
    if resolved is not contract:
        raise ValueError("private FARS year artifact does not match the selected revision")
    return artifact


def _required_open_flag(name: str) -> int:
    value = getattr(os, name, None)
    if not isinstance(value, int) or value == 0:
        raise ValueError("platform does not support secure FARS archive reads")
    return value


def _stable_metadata(metadata: os.stat_result) -> tuple[int, ...]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_size,
        metadata.st_mode,
        metadata.st_uid,
        metadata.st_nlink,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
    )


def _read_raw_archive(path: Path, *, contract: FarsYearContract) -> bytes:
    """Read one owned regular file once, without following a final symlink."""

    flags = (
        os.O_RDONLY
        | _required_open_flag("O_NOFOLLOW")
        | _required_open_flag("O_NONBLOCK")
        | getattr(os, "O_CLOEXEC", 0)
    )
    try:
        descriptor = os.open(path, flags)
    except OSError:
        raise ValueError("FARS raw archive is not safely readable") from None
    try:
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_uid != os.geteuid()
            or before.st_nlink != 1
            or before.st_size <= 0
            or before.st_size > FARS_RAW_ARCHIVE_MAX_BYTES
            or before.st_size != contract.raw_size_bytes
        ):
            raise ValueError("FARS raw archive metadata does not match the selected revision")
        with os.fdopen(descriptor, "rb") as handle:
            descriptor = -1
            payload = handle.read(contract.raw_size_bytes + 1)
            after = os.fstat(handle.fileno())
        if len(payload) != contract.raw_size_bytes or _stable_metadata(before) != _stable_metadata(
            after
        ):
            raise ValueError("FARS raw archive changed while it was read")
        contract.validate_raw_package(payload)
        return payload
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def require_private_fars_year_root(
    root: str | Path,
    repository_root: str | Path,
) -> Path:
    """Resolve storage and reject the repository itself or any of its children."""

    try:
        return require_private_root_outside_repository(root, repository_root)
    except PrivateRootPreflightError:
        raise ValueError("private FARS year activation root preflight failed") from None
    except RepositoryRootPreflightError:
        raise ValueError("private FARS year activation repository root preflight failed") from None
    except RepositoryContainmentError:
        raise ValueError(
            "private FARS year activation root must remain outside the repository"
        ) from None


def activate_fars_year(  # noqa: C901 - keep the locked transaction callbacks adjacent
    *,
    root: str | Path,
    repository_root: str | Path,
    raw_archive_path: str | Path,
    year: int,
    contract_revision: int,
    clock: Clock | None = None,
    attempt_id: str | None = None,
) -> year_verifier.VerifiedFarsYearEvidence:
    """Activate one exact annual revision and return aggregate verification evidence.

    Source selection and every regression policy come exclusively from the
    registered immutable contract.  This API intentionally has no latest-year,
    mapping, policy, or regression override.
    """

    contract = fars_year_contract_revision(year, contract_revision)
    private_root = require_private_fars_year_root(root, repository_root)
    require_private_fars_year_root(private_root / contract.source_id, repository_root)
    archive_path = Path(raw_archive_path).expanduser()
    captured: list[year_verifier.VerifiedFarsYearEvidence] = []
    preflights: list[year_verifier._FarsYearIngestionPreflight] = []
    run_kwargs: dict[str, object] = {}
    if clock is not None:
        run_kwargs["clock"] = clock
    if attempt_id is not None:
        run_kwargs["attempt_id"] = attempt_id

    def fetch() -> bytes:
        return _read_raw_archive(archive_path, contract=contract)

    def normalize(raw: bytes) -> bytes:
        return canonical_joined_outcome_artifact_v2_from_pinned_archive(
            raw,
            year=year,
            contract_revision=contract_revision,
        )

    def validate_candidate(candidate: bytes, _previous: bytes | None) -> None:
        _artifact(candidate, contract=contract)

    def locked_preflight(source_root: Path) -> None:
        if preflights:
            raise IngestionError("FARS year activation preflight ran more than once")
        preflights.append(
            year_verifier._preflight_fars_year_ingestion_locked(
                source_root,
                year=year,
                contract_revision=contract_revision,
            )
        )

    def preflight() -> year_verifier._FarsYearIngestionPreflight:
        if len(preflights) != 1:
            raise IngestionError("FARS year activation preflight evidence is unavailable")
        return preflights[0]

    def validate_receipt_finalization(source_root: Path) -> None:
        year_verifier._validate_fars_year_receipt_finalization_locked(
            source_root,
            year=year,
            contract_revision=contract_revision,
            expected_preflight=preflight(),
        )

    def validate_history(source_root: Path, candidate: bytes, started_at: str) -> None:
        year_verifier._validate_fars_year_history_candidate_locked(
            source_root,
            candidate,
            year=year,
            contract_revision=contract_revision,
            started_at=started_at,
            expected_preflight=preflight(),
        )

    def validate_activated(
        source_root: Path,
        candidate: bytes,
        success_marker: bytes,
    ) -> None:
        if captured:
            raise IngestionError("FARS year activation evidence was captured more than once")
        snapshot = year_verifier._verify_activated_fars_year_locked(
            source_root,
            candidate,
            success_marker,
            year=year,
            contract_revision=contract_revision,
            expected_preflight=preflight(),
        )
        captured.append(snapshot.evidence)

    result = run_ingestion(
        root=private_root,
        source_id=contract.source_id,
        fetch=fetch,
        normalize=normalize,
        locked_preflight=locked_preflight,
        validate_normalized=validate_candidate,
        validate_history=validate_history,
        validate_activated=validate_activated,
        validate_receipt_finalization=validate_receipt_finalization,
        max_raw_bytes=FARS_RAW_ARCHIVE_MAX_BYTES,
        max_normalized_bytes=MAX_FARS_YEAR_ARTIFACT_BYTES,
        **run_kwargs,  # type: ignore[arg-type]
    )
    if len(captured) != 1:
        raise IngestionError("FARS year activation evidence was not captured")
    evidence = captured[0]
    try:
        public_evidence = year_verifier.verify_active_fars_year(
            private_root,
            year=year,
            contract_revision=contract_revision,
        )
    except Exception:
        raise IngestionError(
            "FARS year activation failed post-commit public verification"
        ) from None
    if (
        public_evidence != evidence
        or evidence.source_id != contract.source_id
        or evidence.dataset_year != year
        or evidence.contract_revision != contract_revision
        or evidence.raw_sha256 != result.raw_sha256
        or evidence.normalized_sha256 != result.normalized_sha256
        or evidence.attempt_id != result.receipt_path.stem
    ):
        raise IngestionError("FARS year activation evidence does not match the committed result")
    return public_evidence


__all__ = [
    "MAX_FARS_YEAR_ARTIFACT_BYTES",
    "activate_fars_year",
    "require_private_fars_year_root",
]
