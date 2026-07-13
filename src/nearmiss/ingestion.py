"""Fail-closed, filesystem-backed ingestion primitives.

This module deliberately knows nothing about particular data providers.  A
caller injects a byte-producing ``fetch`` function and a deterministic
``normalize`` function.  The runner preserves the fetched bytes as an
immutable, content-addressed snapshot and activates normalized bytes only
after both functions complete successfully.

The on-disk layout for a source is::

    <root>/<source>/raw/sha256/<digest>.bin
    <root>/<source>/normalized/sha256/<digest>.bin
    <root>/<source>/normalized/current.json  # active success receipt/commit marker
    <root>/<source>/receipts/<attempt-id>.json

Normalized payloads and historical receipts are immutable. ``current.json`` is
a small, self-contained success receipt whose atomic replacement is the commit
point. A failure before that replacement never changes the active dataset; a
later finalization failure rolls the marker back or retains the lock.
The per-source directory lock is intentionally fail-closed: a lock left behind
by a crashed process or failed rollback requires operator inspection rather
than risking two writers.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
import stat
import tempfile
import uuid
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, TypedDict, cast

from jsonschema import Draft202012Validator, FormatChecker

RECEIPT_SCHEMA_VERSION = "1.0.0"
_MAX_ACTIVE_RECEIPT_BYTES = 1024 * 1024
_MAX_ACTIVE_ARTIFACT_BYTES = 512 * 1024 * 1024
_SAFE_SOURCE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_RECEIPT_ERROR_TYPES = (
    "Exception",
    "IngestionError",
    "OSError",
    "RollbackError",
    "TimeoutError",
    "TypeError",
    "ValueError",
)

# Keep the runtime contract embedded: wheels and source distributions must not
# depend on the repository-level ``schema/`` directory being present. A test
# asserts that this value remains identical to ingestion-receipt.schema.json.
RECEIPT_SCHEMA: dict[str, object] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "https://nearmiss.dev/schema/ingestion-receipt.schema.json",
    "title": "NearMiss ingestion receipt",
    "type": "object",
    "additionalProperties": False,
    "required": [
        "schema_version",
        "attempt_id",
        "source_id",
        "status",
        "started_at",
        "completed_at",
        "raw_sha256",
        "raw_snapshot",
        "normalized_sha256",
        "normalized_path",
        "previous_normalized_sha256",
        "activated",
        "error",
    ],
    "$defs": {
        "safe_id": {
            "type": "string",
            "pattern": "^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$",
        },
        "sha256": {"type": "string", "pattern": "^[a-f0-9]{64}$"},
        "utc_datetime": {
            "type": "string",
            "format": "date-time",
            "pattern": "Z$",
        },
        "error": {
            "type": "object",
            "additionalProperties": False,
            "required": ["type", "message"],
            "properties": {
                "type": {
                    "type": "string",
                    "enum": list(_RECEIPT_ERROR_TYPES),
                },
                "message": {
                    "type": "string",
                    "enum": [
                        "active artifact preflight failed",
                        "fetch failed",
                        "raw snapshot preservation failed",
                        "normalization failed",
                        "normalized artifact validation failed",
                        "normalized artifact preservation failed",
                        "active marker commit failed",
                        "active marker commit failed; rollback also failed",
                        "activated artifact validation failed",
                        "activated artifact validation failed; rollback also failed",
                        "success receipt finalization failed",
                        "success receipt finalization failed; rollback also failed",
                    ],
                },
            },
        },
    },
    "properties": {
        "schema_version": {"const": RECEIPT_SCHEMA_VERSION},
        "attempt_id": {"$ref": "#/$defs/safe_id"},
        "source_id": {"$ref": "#/$defs/safe_id"},
        "status": {"enum": ["success", "failure"]},
        "started_at": {"$ref": "#/$defs/utc_datetime"},
        "completed_at": {
            "oneOf": [{"$ref": "#/$defs/utc_datetime"}, {"type": "null"}],
        },
        "raw_sha256": {
            "oneOf": [{"$ref": "#/$defs/sha256"}, {"type": "null"}],
        },
        "raw_snapshot": {
            "oneOf": [
                {
                    "type": "string",
                    "pattern": "^raw/sha256/[a-f0-9]{64}\\.bin$",
                },
                {"type": "null"},
            ],
        },
        "normalized_sha256": {
            "oneOf": [{"$ref": "#/$defs/sha256"}, {"type": "null"}],
        },
        "normalized_path": {
            "oneOf": [
                {
                    "type": "string",
                    "pattern": "^normalized/sha256/[a-f0-9]{64}\\.bin$",
                },
                {"type": "null"},
            ],
        },
        "previous_normalized_sha256": {
            "oneOf": [{"$ref": "#/$defs/sha256"}, {"type": "null"}],
        },
        "activated": {"type": "boolean"},
        "error": {"oneOf": [{"$ref": "#/$defs/error"}, {"type": "null"}]},
    },
    "allOf": [
        {
            "if": {"properties": {"status": {"const": "success"}}},
            "then": {
                "properties": {
                    "raw_sha256": {"$ref": "#/$defs/sha256"},
                    "raw_snapshot": {
                        "type": "string",
                        "pattern": "^raw/sha256/[a-f0-9]{64}\\.bin$",
                    },
                    "normalized_sha256": {"$ref": "#/$defs/sha256"},
                    "normalized_path": {
                        "type": "string",
                        "pattern": "^normalized/sha256/[a-f0-9]{64}\\.bin$",
                    },
                    "activated": {"const": True},
                    "completed_at": {"$ref": "#/$defs/utc_datetime"},
                    "error": {"type": "null"},
                }
            },
            "else": {
                "properties": {"error": {"$ref": "#/$defs/error"}},
            },
        },
        {
            "if": {
                "properties": {
                    "status": {"const": "failure"},
                    "activated": {"const": True},
                },
                "required": ["status", "activated"],
            },
            "then": {
                "properties": {
                    "raw_sha256": {"$ref": "#/$defs/sha256"},
                    "raw_snapshot": {
                        "type": "string",
                        "pattern": "^raw/sha256/[a-f0-9]{64}\\.bin$",
                    },
                    "normalized_sha256": {"$ref": "#/$defs/sha256"},
                    "normalized_path": {
                        "type": "string",
                        "pattern": "^normalized/sha256/[a-f0-9]{64}\\.bin$",
                    },
                    "error": {
                        "type": "object",
                        "properties": {
                            "type": {"const": "RollbackError"},
                            "message": {
                                "enum": [
                                    "active marker commit failed; rollback also failed",
                                    "activated artifact validation failed; rollback also failed",
                                    "success receipt finalization failed; rollback also failed",
                                ]
                            },
                        },
                    },
                }
            },
        },
        {
            "if": {
                "properties": {
                    "status": {"const": "failure"},
                    "activated": {"const": False},
                },
                "required": ["status", "activated"],
            },
            "then": {
                "properties": {
                    "error": {
                        "type": "object",
                        "properties": {
                            "type": {"not": {"const": "RollbackError"}},
                            "message": {
                                "not": {
                                    "enum": [
                                        "active marker commit failed; rollback also failed",
                                        "activated artifact validation failed; "
                                        "rollback also failed",
                                        "success receipt finalization failed; rollback also failed",
                                    ]
                                }
                            },
                        },
                    }
                }
            },
        },
        {
            "if": {
                "properties": {"raw_snapshot": {"type": "string"}},
                "required": ["raw_snapshot"],
            },
            "then": {"properties": {"raw_sha256": {"$ref": "#/$defs/sha256"}}},
        },
        {
            "if": {
                "properties": {"normalized_sha256": {"type": "string"}},
                "required": ["normalized_sha256"],
            },
            "then": {
                "properties": {
                    "raw_sha256": {"$ref": "#/$defs/sha256"},
                    "raw_snapshot": {
                        "type": "string",
                        "pattern": "^raw/sha256/[a-f0-9]{64}\\.bin$",
                    },
                    "normalized_path": {
                        "type": "string",
                        "pattern": "^normalized/sha256/[a-f0-9]{64}\\.bin$",
                    },
                }
            },
        },
    ],
}
_RECEIPT_VALIDATOR = Draft202012Validator(RECEIPT_SCHEMA, format_checker=FormatChecker())

Fetch = Callable[[], bytes]
Normalize = Callable[[bytes], bytes]
ValidateNormalized = Callable[[bytes, bytes | None], None]
ValidateHistory = Callable[[Path, bytes, str], None]
ValidateActivated = Callable[[Path, bytes, bytes], None]
Clock = Callable[[], dt.datetime]
LockIdentity = tuple[int, int]


class IngestionError(Exception):
    """Base error for ingestion orchestration failures."""


class ConcurrentIngestionError(IngestionError):
    """Another run owns the source's ingestion lock."""


class IngestionRunError(IngestionError):
    """A fetch or normalization attempt failed after acquiring the lock."""

    def __init__(self, message: str, receipt_path: Path) -> None:
        super().__init__(message)
        self.receipt_path = receipt_path


class _ActiveArtifactLimitError(IngestionError):
    """A configured cap is smaller than an existing active artifact."""


class _ActiveMarkerChangedError(IngestionError):
    """The active marker changed after preflight and before commit."""


class _ActivatedIntegrityError(IngestionError):
    """The newly activated marker or its artifacts failed re-authentication."""


class _DuplicateJSONKeyError(ValueError):
    """An active marker JSON object contains an ambiguous duplicate key."""


class ReceiptError(TypedDict):
    type: str
    message: str


class IngestionReceipt(TypedDict):
    schema_version: str
    attempt_id: str
    source_id: str
    status: Literal["success", "failure"]
    started_at: str
    completed_at: str | None
    raw_sha256: str | None
    raw_snapshot: str | None
    normalized_sha256: str | None
    normalized_path: str | None
    previous_normalized_sha256: str | None
    activated: bool
    error: ReceiptError | None


@dataclass(frozen=True)
class IngestionResult:
    """Paths and hashes produced by a successful ingestion attempt."""

    source_id: str
    raw_snapshot: Path
    normalized_path: Path
    current_path: Path
    receipt_path: Path
    raw_sha256: str
    normalized_sha256: str


@dataclass(frozen=True)
class _ActiveMarker:
    marker_bytes: bytes
    receipt: IngestionReceipt
    normalized: bytes


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def _timestamp(value: dt.datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise IngestionError("ingestion clock must return a timezone-aware datetime")
    return value.astimezone(dt.UTC).isoformat().replace("+00:00", "Z")


def _digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _ensure_directory(path: Path) -> None:
    """Create/tighten one owned private directory and reject unsafe occupants."""
    created = False
    try:
        path.mkdir(mode=0o700)
        created = True
    except FileExistsError:
        pass
    try:
        metadata = path.stat(follow_symlinks=False)
    except FileNotFoundError:
        raise IngestionError(f"ingestion directory disappeared: {path}") from None
    if not stat.S_ISDIR(metadata.st_mode):
        raise IngestionError(f"ingestion path is not a real directory: {path}")
    if metadata.st_uid != os.geteuid():
        raise IngestionError(f"ingestion directory is not owned by the effective user: {path}")
    try:
        path.chmod(0o700, follow_symlinks=False)
    except (NotImplementedError, OSError):
        raise IngestionError(f"ingestion directory permissions are unsafe: {path}") from None
    if created:
        _fsync_directory(path.parent)


def _ensure_source_directory(root: Path, source_id: str) -> Path:
    with suppress(FileExistsError):
        root.mkdir(parents=True, mode=0o700)
    try:
        root_metadata = root.stat(follow_symlinks=False)
    except FileNotFoundError:
        raise IngestionError(f"ingestion root disappeared: {root}") from None
    if not stat.S_ISDIR(root_metadata.st_mode):
        raise IngestionError("ingestion root must be a real directory, not a symlink")
    if root_metadata.st_uid != os.geteuid():
        raise IngestionError("ingestion root is not owned by the effective user")
    try:
        root.chmod(0o700, follow_symlinks=False)
    except (NotImplementedError, OSError):
        raise IngestionError("ingestion root permissions are unsafe") from None
    source_root = root / source_id
    _ensure_directory(source_root)
    return source_root


def _ensure_subdirectory(source_root: Path, relative: Path) -> Path:
    if relative.is_absolute() or ".." in relative.parts:
        raise IngestionError("ingestion subdirectory must remain beneath its source root")
    current = source_root
    for part in relative.parts:
        current = current / part
        _ensure_directory(current)
    return current


def _write_temp(parent: Path, payload: bytes) -> Path:
    descriptor, name = tempfile.mkstemp(prefix=".ingestion-", dir=parent)
    path = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fchmod(handle.fileno(), 0o400)
            os.fsync(handle.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return path


def _validate_regular_metadata(
    path: Path, metadata: os.stat_result, maximum_bytes: int | None
) -> None:
    if not stat.S_ISREG(metadata.st_mode):
        raise IngestionError(f"ingestion artifact is not a regular file: {path}")
    if metadata.st_uid != os.geteuid():
        raise IngestionError(f"ingestion artifact is not owned by the effective user: {path}")
    if metadata.st_nlink != 1:
        raise IngestionError(f"ingestion artifact has an unsafe link count: {path}")
    if stat.S_IMODE(metadata.st_mode) != 0o400:
        raise IngestionError(f"ingestion artifact permissions are unsafe: {path}")
    if metadata.st_size <= 0:
        raise IngestionError(f"ingestion artifact is empty: {path}")
    if maximum_bytes is not None and metadata.st_size > maximum_bytes:
        raise _ActiveArtifactLimitError(
            f"ingestion artifact exceeds its configured byte limit: {path}"
        )


def _validate_directory_metadata(path: Path, metadata: os.stat_result) -> None:
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != os.geteuid()
        or stat.S_IMODE(metadata.st_mode) != 0o700
    ):
        raise IngestionError(f"ingestion directory is unsafe: {path}")


def _relative_parts(source_root: Path, path: Path) -> tuple[str, ...]:
    try:
        relative = path.relative_to(source_root)
    except ValueError:
        raise IngestionError("ingestion artifact escapes its source root") from None
    if relative.is_absolute() or not relative.parts or ".." in relative.parts:
        raise IngestionError("ingestion artifact escapes its source root")
    return relative.parts


def _required_open_flag(name: str) -> int:
    value = getattr(os, name, None)
    if not isinstance(value, int) or value == 0:
        raise IngestionError("platform does not support secure ingestion artifact reads")
    return value


def _open_regular_beneath(source_root: Path, path: Path, *, optional: bool) -> int | None:
    """Open a file through owned private directories without following symlinks."""
    parts = _relative_parts(source_root, path)
    if os.open not in os.supports_dir_fd:
        raise IngestionError("platform does not support secure ingestion artifact reads")
    directory_flags = (
        os.O_RDONLY | _required_open_flag("O_DIRECTORY") | _required_open_flag("O_NOFOLLOW")
    )
    file_flags = os.O_RDONLY | _required_open_flag("O_NOFOLLOW") | _required_open_flag("O_NONBLOCK")
    try:
        directory_descriptor = os.open(source_root, directory_flags)
    except OSError:
        raise IngestionError("ingestion source directory is not safely readable") from None
    try:
        _validate_directory_metadata(source_root, os.fstat(directory_descriptor))
        current = source_root
        for part in parts[:-1]:
            current /= part
            try:
                child_descriptor = os.open(part, directory_flags, dir_fd=directory_descriptor)
            except FileNotFoundError:
                if optional:
                    return None
                raise IngestionError(f"ingestion artifact is not safely readable: {path}") from None
            except OSError:
                raise IngestionError(f"ingestion directory is unsafe: {current}") from None
            os.close(directory_descriptor)
            directory_descriptor = child_descriptor
            _validate_directory_metadata(current, os.fstat(directory_descriptor))
        try:
            return os.open(parts[-1], file_flags, dir_fd=directory_descriptor)
        except FileNotFoundError:
            if optional:
                return None
            raise IngestionError(f"ingestion artifact is not safely readable: {path}") from None
        except OSError:
            raise IngestionError(f"ingestion artifact is not safely readable: {path}") from None
    finally:
        os.close(directory_descriptor)


def _stable_file_metadata(metadata: os.stat_result) -> tuple[int, ...]:
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


def _read_open_regular(descriptor: int, path: Path, maximum_bytes: int | None) -> bytes:
    try:
        metadata = os.fstat(descriptor)
        _validate_regular_metadata(path, metadata, maximum_bytes)
        with os.fdopen(descriptor, "rb") as handle:
            descriptor = -1
            payload = handle.read() if maximum_bytes is None else handle.read(maximum_bytes + 1)
            final_metadata = os.fstat(handle.fileno())
        if not payload:
            raise IngestionError(f"ingestion artifact is empty: {path}")
        if maximum_bytes is not None and len(payload) > maximum_bytes:
            raise _ActiveArtifactLimitError(
                f"ingestion artifact exceeds its configured byte limit: {path}"
            )
        if len(payload) != metadata.st_size or _stable_file_metadata(
            final_metadata
        ) != _stable_file_metadata(metadata):
            raise IngestionError(f"ingestion artifact changed while it was read: {path}")
        return payload
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _read_regular(source_root: Path, path: Path, *, maximum_bytes: int | None = None) -> bytes:
    descriptor = _open_regular_beneath(source_root, path, optional=False)
    if descriptor is None:  # pragma: no cover - non-optional opens never return None
        raise IngestionError(f"ingestion artifact is not safely readable: {path}") from None
    return _read_open_regular(descriptor, path, maximum_bytes)


def _read_optional_regular(
    source_root: Path, path: Path, *, maximum_bytes: int | None = None
) -> bytes | None:
    descriptor = _open_regular_beneath(source_root, path, optional=True)
    if descriptor is None:
        return None
    return _read_open_regular(descriptor, path, maximum_bytes)


def _install_immutable(source_root: Path, destination: Path, payload: bytes) -> None:
    """Atomically install bytes without ever replacing an existing artifact."""
    _ensure_subdirectory(source_root, destination.parent.relative_to(source_root))
    temporary = _write_temp(destination.parent, payload)
    try:
        try:
            os.link(temporary, destination)
        except FileExistsError:
            if _read_regular(source_root, destination, maximum_bytes=len(payload)) != payload:
                raise IngestionError(f"immutable artifact collision at {destination}") from None
        else:
            _fsync_directory(destination.parent)
    finally:
        temporary.unlink(missing_ok=True)


def _atomic_replace(source_root: Path, destination: Path, payload: bytes) -> None:
    """Replace the active normalized artifact atomically on the same filesystem."""
    _ensure_subdirectory(source_root, destination.parent.relative_to(source_root))
    temporary = _write_temp(destination.parent, payload)
    try:
        temporary.replace(destination)
        _fsync_directory(destination.parent)
    finally:
        temporary.unlink(missing_ok=True)


def _validate_receipt(receipt: IngestionReceipt) -> None:
    """Reject any receipt that does not satisfy the public audit contract."""
    try:
        _RECEIPT_VALIDATOR.validate(receipt)
    except Exception:
        raise IngestionError("internally constructed ingestion receipt is invalid") from None
    raw_snapshot = receipt["raw_snapshot"]
    raw_sha256 = receipt["raw_sha256"]
    if raw_snapshot is not None and raw_snapshot != f"raw/sha256/{raw_sha256}.bin":
        raise IngestionError("ingestion receipt snapshot path does not match its digest")
    normalized_path = receipt["normalized_path"]
    normalized_sha256 = receipt["normalized_sha256"]
    if (
        normalized_path is not None
        and normalized_path != f"normalized/sha256/{normalized_sha256}.bin"
    ):
        raise IngestionError("ingestion receipt normalized path does not match its digest")


def _receipt_bytes(receipt: IngestionReceipt) -> bytes:
    _validate_receipt(receipt)
    return (json.dumps(receipt, indent=2, sort_keys=True) + "\n").encode()


def _unique_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise _DuplicateJSONKeyError
        value[key] = item
    return value


def _parse_receipt(payload: bytes) -> IngestionReceipt:
    try:
        value = json.loads(payload, object_pairs_hook=_unique_json_object)
    except (UnicodeDecodeError, json.JSONDecodeError, _DuplicateJSONKeyError):
        raise IngestionError("active ingestion marker is not valid JSON") from None
    if not isinstance(value, dict):
        raise IngestionError("active ingestion marker is not a JSON object")
    receipt = cast(IngestionReceipt, value)
    _validate_receipt(receipt)
    if _receipt_bytes(receipt) != payload:
        raise IngestionError("active ingestion marker is not canonical JSON")
    return receipt


def _artifact_from_relative(source_root: Path, relative: str) -> Path:
    path = Path(relative)
    if path.is_absolute() or ".." in path.parts:
        raise IngestionError("ingestion receipt artifact path escapes its source root")
    return source_root / path


def _load_active_marker(
    source_root: Path,
    current_path: Path,
    source_id: str,
    *,
    max_raw_bytes: int | None = None,
    max_normalized_bytes: int | None = None,
) -> _ActiveMarker | None:
    marker_bytes = _read_optional_regular(
        source_root, current_path, maximum_bytes=_MAX_ACTIVE_RECEIPT_BYTES
    )
    if marker_bytes is None:
        return None
    receipt = _parse_receipt(marker_bytes)
    if (
        receipt["status"] != "success"
        or receipt["activated"] is not True
        or receipt["error"] is not None
        or receipt["source_id"] != source_id
    ):
        raise IngestionError("active ingestion marker is not a successful source receipt")
    raw_path_value = receipt["raw_snapshot"]
    normalized_path_value = receipt["normalized_path"]
    if raw_path_value is None or normalized_path_value is None:
        raise IngestionError("active ingestion marker does not reference immutable artifacts")
    raw = _read_regular(
        source_root,
        _artifact_from_relative(source_root, raw_path_value),
        maximum_bytes=(max_raw_bytes if max_raw_bytes is not None else _MAX_ACTIVE_ARTIFACT_BYTES),
    )
    normalized = _read_regular(
        source_root,
        _artifact_from_relative(source_root, normalized_path_value),
        maximum_bytes=(
            max_normalized_bytes if max_normalized_bytes is not None else _MAX_ACTIVE_ARTIFACT_BYTES
        ),
    )
    if _digest(raw) != receipt["raw_sha256"]:
        raise IngestionError("active ingestion marker raw snapshot hash mismatch")
    if _digest(normalized) != receipt["normalized_sha256"]:
        raise IngestionError("active ingestion marker normalized artifact hash mismatch")
    return _ActiveMarker(marker_bytes, receipt, normalized)


def _new_attempt_id(started: dt.datetime) -> str:
    stamp = started.astimezone(dt.UTC).strftime("%Y%m%dT%H%M%S.%fZ")
    return f"{stamp}-{uuid.uuid4().hex}"


def _validate_attempt_id(value: str) -> str:
    if not _SAFE_SOURCE_ID.fullmatch(value):
        raise IngestionError("attempt_id must contain only letters, digits, '.', '_' or '-'")
    return value


def _relative(path: Path, source_root: Path) -> str:
    return path.relative_to(source_root).as_posix()


def _require_payload(value: object, stage: str, maximum_bytes: int | None) -> bytes:
    if not isinstance(value, bytes):
        raise TypeError(f"{stage} must return bytes")
    if not value:
        raise ValueError(f"{stage} returned an empty payload")
    if maximum_bytes is not None and len(value) > maximum_bytes:
        raise ValueError(f"{stage} exceeded its configured byte limit")
    return value


def _acquire_lock(lock_path: Path, source_id: str) -> LockIdentity:
    try:
        lock_path.mkdir(mode=0o700)
    except FileExistsError:
        raise ConcurrentIngestionError(
            f"ingestion already locked for source {source_id!r}"
        ) from None
    try:
        metadata = lock_path.stat(follow_symlinks=False)
        if not stat.S_ISDIR(metadata.st_mode) or metadata.st_uid != os.geteuid():
            raise IngestionError("ingestion lock is not an owned directory")
        lock_path.chmod(0o700, follow_symlinks=False)
        _fsync_directory(lock_path.parent)
        return metadata.st_dev, metadata.st_ino
    except BaseException:
        try:
            lock_path.rmdir()
            _fsync_directory(lock_path.parent)
        except OSError:
            pass
        raise


def _release_lock(lock_path: Path, identity: LockIdentity) -> None:
    """Remove only the empty lock directory this process actually acquired."""
    try:
        metadata = lock_path.stat(follow_symlinks=False)
        if (metadata.st_dev, metadata.st_ino) != identity:
            return
        lock_path.rmdir()
        _fsync_directory(lock_path.parent)
    except OSError:
        # Leave a stale lock fail-closed. Cleanup must never mask ingestion or
        # rollback errors, and recursive deletion could remove attacker data.
        return


def _finalize_lock(lock_path: Path, identity: LockIdentity, retain: bool) -> None:
    if not retain:
        _release_lock(lock_path, identity)


def _rollback_activation(source_root: Path, current_path: Path, previous: bytes | None) -> None:
    if previous is None:
        current_path.unlink(missing_ok=True)
        _fsync_directory(current_path.parent)
    else:
        _atomic_replace(source_root, current_path, previous)


def _marker_state(
    source_root: Path,
    current_path: Path,
    previous: bytes | None,
    candidate: bytes | None,
) -> Literal["previous", "candidate", "ambiguous"]:
    try:
        active = _read_optional_regular(
            source_root, current_path, maximum_bytes=_MAX_ACTIVE_RECEIPT_BYTES
        )
    except Exception:
        return "ambiguous"
    if candidate is not None and active == candidate:
        return "candidate"
    if active == previous:
        return "previous"
    return "ambiguous"


def _require_active_marker_unchanged(
    source_root: Path, current_path: Path, expected: bytes | None
) -> None:
    try:
        observed = _read_optional_regular(
            source_root, current_path, maximum_bytes=_MAX_ACTIVE_RECEIPT_BYTES
        )
    except Exception:
        raise _ActiveMarkerChangedError(
            "active ingestion marker changed during ingestion"
        ) from None
    if observed != expected:
        raise _ActiveMarkerChangedError("active ingestion marker changed during ingestion")


def _require_precommit_integrity(
    *,
    source_root: Path,
    source_id: str,
    current_path: Path,
    previous: _ActiveMarker | None,
    raw_snapshot: Path,
    raw: bytes,
    raw_digest: str,
    normalized_path: Path,
    normalized: bytes,
    normalized_digest: str,
    max_raw_bytes: int | None,
    max_normalized_bytes: int | None,
) -> None:
    """Re-authenticate preserved and prior active state immediately before commit."""

    try:
        observed_raw = _read_regular(source_root, raw_snapshot, maximum_bytes=len(raw))
        observed_normalized = _read_regular(
            source_root, normalized_path, maximum_bytes=len(normalized)
        )
        if (
            observed_raw != raw
            or _digest(observed_raw) != raw_digest
            or observed_normalized != normalized
            or _digest(observed_normalized) != normalized_digest
        ):
            raise _ActiveMarkerChangedError("preserved ingestion artifacts changed before commit")
        observed_previous = _load_active_marker(
            source_root,
            current_path,
            source_id,
            max_raw_bytes=max_raw_bytes,
            max_normalized_bytes=max_normalized_bytes,
        )
    except _ActiveMarkerChangedError:
        raise
    except IngestionError:
        raise _ActiveMarkerChangedError("active ingestion state changed before commit") from None

    expected_marker = previous.marker_bytes if previous is not None else None
    observed_marker = observed_previous.marker_bytes if observed_previous is not None else None
    if observed_marker != expected_marker:
        raise _ActiveMarkerChangedError("active ingestion state changed before commit")
    _require_active_marker_unchanged(source_root, current_path, expected_marker)


def _candidate_artifacts_authenticated(
    *,
    source_root: Path,
    raw_snapshot: Path,
    raw: bytes,
    raw_digest: str,
    normalized_path: Path,
    normalized: bytes,
    normalized_digest: str,
) -> bool:
    try:
        observed_raw = _read_regular(source_root, raw_snapshot, maximum_bytes=len(raw))
        observed_normalized = _read_regular(
            source_root, normalized_path, maximum_bytes=len(normalized)
        )
    except IngestionError:
        return False
    return (
        observed_raw == raw
        and _digest(observed_raw) == raw_digest
        and observed_normalized == normalized
        and _digest(observed_normalized) == normalized_digest
    )


def _require_activated_integrity(
    *,
    source_root: Path,
    source_id: str,
    current_path: Path,
    success_marker: bytes,
    raw_snapshot: Path,
    raw: bytes,
    raw_digest: str,
    normalized_path: Path,
    normalized: bytes,
    normalized_digest: str,
    max_raw_bytes: int | None,
    max_normalized_bytes: int | None,
) -> None:
    """Re-authenticate the activated marker and exact candidate artifacts."""

    if not _candidate_artifacts_authenticated(
        source_root=source_root,
        raw_snapshot=raw_snapshot,
        raw=raw,
        raw_digest=raw_digest,
        normalized_path=normalized_path,
        normalized=normalized,
        normalized_digest=normalized_digest,
    ):
        raise _ActivatedIntegrityError("activated ingestion artifacts changed during validation")
    try:
        active = _load_active_marker(
            source_root,
            current_path,
            source_id,
            max_raw_bytes=max_raw_bytes,
            max_normalized_bytes=max_normalized_bytes,
        )
        if active is None or active.marker_bytes != success_marker:
            raise _ActivatedIntegrityError("activated ingestion marker changed during validation")
        _require_active_marker_unchanged(source_root, current_path, success_marker)
    except _ActivatedIntegrityError:
        raise
    except IngestionError:
        raise _ActivatedIntegrityError(
            "activated ingestion state changed during validation"
        ) from None


def _failure_timestamp(clock: Clock) -> str | None:
    try:
        return _timestamp(clock())
    except Exception:
        return None


def _error_type(exc: BaseException, rollback_failed: bool) -> str:
    if rollback_failed:
        return "RollbackError"
    if isinstance(exc, IngestionError):
        return "IngestionError"
    if isinstance(exc, TimeoutError):
        return "TimeoutError"
    if isinstance(exc, OSError):
        return "OSError"
    if isinstance(exc, ValueError):
        return "ValueError"
    if isinstance(exc, TypeError):
        return "TypeError"
    return "Exception"


def _validate_maximum(value: int | None, name: str) -> None:
    if value is not None and value <= 0:
        raise IngestionError(f"{name} must be positive when provided")


def _preflight_attempt(
    receipt_path: Path,
    source_root: Path,
    current_path: Path,
    source_id: str,
    *,
    max_raw_bytes: int | None,
    max_normalized_bytes: int | None,
) -> _ActiveMarker | None:
    active = _load_active_marker(
        source_root,
        current_path,
        source_id,
        max_raw_bytes=max_raw_bytes,
        max_normalized_bytes=max_normalized_bytes,
    )
    if active is not None:
        active_receipt_path = source_root / "receipts" / f"{active.receipt['attempt_id']}.json"
        _install_immutable(source_root, active_receipt_path, active.marker_bytes)
    try:
        receipt_path.stat(follow_symlinks=False)
    except FileNotFoundError:
        pass
    else:
        raise IngestionError(f"attempt receipt already exists: {receipt_path}")
    return active


def _write_preflight_limit_failure(
    *,
    source_root: Path,
    receipt_path: Path,
    source_id: str,
    attempt_id: str,
    started_at: str,
    clock: Clock,
) -> None:
    failure: IngestionReceipt = {
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "attempt_id": attempt_id,
        "source_id": source_id,
        "status": "failure",
        "started_at": started_at,
        "completed_at": _failure_timestamp(clock),
        "raw_sha256": None,
        "raw_snapshot": None,
        "normalized_sha256": None,
        "normalized_path": None,
        "previous_normalized_sha256": None,
        "activated": False,
        "error": {
            "type": "IngestionError",
            "message": "active artifact preflight failed",
        },
    }
    _install_immutable(source_root, receipt_path, _receipt_bytes(failure))


def run_ingestion(  # noqa: C901 - keep crash-state transitions together and auditable
    *,
    root: Path,
    source_id: str,
    fetch: Fetch,
    normalize: Normalize,
    validate_normalized: ValidateNormalized | None = None,
    validate_history: ValidateHistory | None = None,
    validate_activated: ValidateActivated | None = None,
    clock: Clock = _utc_now,
    attempt_id: str | None = None,
    max_raw_bytes: int | None = None,
    max_normalized_bytes: int | None = None,
) -> IngestionResult:
    """Fetch, snapshot, normalize, and atomically activate one source.

    ``fetch`` and ``normalize`` must return non-empty bytes. The optional
    candidate validator receives the candidate and previous normalized bytes.
    The optional history validator receives the owned source root, preserved
    candidate bytes, and exact canonical attempt start timestamp immediately
    before activation. The optional activated validator receives the owned source
    root, exact normalized candidate, and exact canonical success marker after
    activation but before success receipt finalization. Any exception
    after successful preflight produces a failure receipt and raises
    :class:`IngestionRunError`; the prior normalized artifact remains active.
    """
    if not _SAFE_SOURCE_ID.fullmatch(source_id):
        raise IngestionError("source_id must contain only letters, digits, '.', '_' or '-'")
    _validate_maximum(max_raw_bytes, "max_raw_bytes")
    _validate_maximum(max_normalized_bytes, "max_normalized_bytes")

    started = clock()
    started_at = _timestamp(started)
    run_id = _validate_attempt_id(attempt_id) if attempt_id else _new_attempt_id(started)
    source_root = _ensure_source_directory(root, source_id)
    lock_path = source_root / ".ingestion.lock"
    receipts_dir = source_root / "receipts"
    receipt_path = receipts_dir / f"{run_id}.json"
    current_path = source_root / "normalized" / "current.json"
    raw_digest: str | None = None
    raw_snapshot: Path | None = None
    normalized_digest: str | None = None
    normalized_path: Path | None = None
    success_marker: bytes | None = None
    activated = False
    retain_lock = False

    lock_identity = _acquire_lock(lock_path, source_id)

    try:
        previous = _preflight_attempt(
            receipt_path,
            source_root,
            current_path,
            source_id,
            max_raw_bytes=max_raw_bytes,
            max_normalized_bytes=max_normalized_bytes,
        )
    except _ActiveArtifactLimitError:
        try:
            _write_preflight_limit_failure(
                source_root=source_root,
                receipt_path=receipt_path,
                source_id=source_id,
                attempt_id=run_id,
                started_at=started_at,
                clock=clock,
            )
        except BaseException as receipt_exc:
            _release_lock(lock_path, lock_identity)
            if not isinstance(receipt_exc, Exception):
                raise
            raise IngestionError(
                "ingestion failed and its failure receipt could not be written"
            ) from None
        _release_lock(lock_path, lock_identity)
        raise IngestionRunError(
            f"ingestion failed for source {source_id!r}", receipt_path
        ) from None
    except BaseException:
        _release_lock(lock_path, lock_identity)
        raise

    previous_marker = previous.marker_bytes if previous is not None else None
    previous_normalized = previous.normalized if previous is not None else None
    previous_digest = previous.receipt["normalized_sha256"] if previous is not None else None
    failure_stage = "fetch"
    try:
        raw = _require_payload(fetch(), "fetch", max_raw_bytes)
        raw_candidate_digest = _digest(raw)
        raw_snapshot_candidate = source_root / "raw" / "sha256" / f"{raw_candidate_digest}.bin"
        failure_stage = "raw snapshot preservation"
        _install_immutable(source_root, raw_snapshot_candidate, raw)
        raw_digest = raw_candidate_digest
        raw_snapshot = raw_snapshot_candidate

        failure_stage = "normalization"
        normalized = _require_payload(normalize(raw), "normalize", max_normalized_bytes)
        normalized_candidate_digest = _digest(normalized)
        if validate_normalized is not None:
            failure_stage = "normalized artifact validation"
            validate_normalized(normalized, previous_normalized)
        normalized_candidate_path = (
            source_root / "normalized" / "sha256" / f"{normalized_candidate_digest}.bin"
        )
        failure_stage = "normalized artifact preservation"
        _install_immutable(source_root, normalized_candidate_path, normalized)
        normalized_digest = normalized_candidate_digest
        normalized_path = normalized_candidate_path

        if validate_history is not None:
            failure_stage = "normalized artifact validation"
            validate_history(source_root, normalized, started_at)
            failure_stage = "normalized artifact preservation"
        completed_at = _timestamp(clock())
        receipt: IngestionReceipt = {
            "schema_version": RECEIPT_SCHEMA_VERSION,
            "attempt_id": run_id,
            "source_id": source_id,
            "status": "success",
            "started_at": started_at,
            "completed_at": completed_at,
            "raw_sha256": raw_digest,
            "raw_snapshot": _relative(raw_snapshot, source_root),
            "normalized_sha256": normalized_digest,
            "normalized_path": _relative(normalized_path, source_root),
            "previous_normalized_sha256": previous_digest,
            "activated": True,
            "error": None,
        }
        success_marker = _receipt_bytes(receipt)
        failure_stage = "active marker commit"
        _require_precommit_integrity(
            source_root=source_root,
            source_id=source_id,
            current_path=current_path,
            previous=previous,
            raw_snapshot=raw_snapshot,
            raw=raw,
            raw_digest=raw_digest,
            normalized_path=normalized_path,
            normalized=normalized,
            normalized_digest=normalized_digest,
            max_raw_bytes=max_raw_bytes,
            max_normalized_bytes=max_normalized_bytes,
        )
        _atomic_replace(source_root, current_path, success_marker)
        activated = True

        if validate_activated is not None:
            failure_stage = "activated artifact validation"
            validate_activated(source_root, normalized, success_marker)
            _require_activated_integrity(
                source_root=source_root,
                source_id=source_id,
                current_path=current_path,
                success_marker=success_marker,
                raw_snapshot=raw_snapshot,
                raw=raw,
                raw_digest=raw_digest,
                normalized_path=normalized_path,
                normalized=normalized,
                normalized_digest=normalized_digest,
                max_raw_bytes=max_raw_bytes,
                max_normalized_bytes=max_normalized_bytes,
            )

        failure_stage = "success receipt finalization"
        _install_immutable(source_root, receipt_path, success_marker)
        return IngestionResult(
            source_id=source_id,
            raw_snapshot=raw_snapshot,
            normalized_path=normalized_path,
            current_path=current_path,
            receipt_path=receipt_path,
            raw_sha256=raw_digest,
            normalized_sha256=normalized_digest,
        )
    except BaseException as exc:
        marker_changed = isinstance(exc, _ActiveMarkerChangedError)
        if failure_stage == "activated artifact validation" and (
            raw_snapshot is None
            or raw_digest is None
            or normalized_path is None
            or normalized_digest is None
            or not _candidate_artifacts_authenticated(
                source_root=source_root,
                raw_snapshot=raw_snapshot,
                raw=raw,
                raw_digest=raw_digest,
                normalized_path=normalized_path,
                normalized=normalized,
                normalized_digest=normalized_digest,
            )
        ):
            raw_digest = None
            raw_snapshot = None
            normalized_digest = None
            normalized_path = None
        if marker_changed:
            raw_digest = None
            raw_snapshot = None
            normalized_digest = None
            normalized_path = None
            state = "ambiguous"
            activated = False
        else:
            state = _marker_state(source_root, current_path, previous_marker, success_marker)
            if state == "candidate":
                activated = True
            elif state == "previous":
                activated = False
            else:
                retain_lock = True

        if not isinstance(exc, Exception):
            raise
        if state == "ambiguous" and not marker_changed:
            raise IngestionError(
                "ingestion failed and active marker state could not be determined; "
                "operator intervention is required"
            ) from None

        rollback_failed = False
        if activated:
            try:
                _rollback_activation(source_root, current_path, previous_marker)
            except BaseException as rollback_exc:
                rollback_state = _marker_state(
                    source_root, current_path, previous_marker, success_marker
                )
                if rollback_state == "previous":
                    activated = False
                elif rollback_state == "ambiguous":
                    retain_lock = True
                    raise IngestionError(
                        "ingestion rollback left active marker state undetermined; "
                        "operator intervention is required"
                    ) from None
                else:
                    rollback_failed = True
                    activated = True
                    retain_lock = True
                if not isinstance(rollback_exc, Exception):
                    raise
            else:
                activated = False
        failure_completed_at = _failure_timestamp(clock)
        failure: IngestionReceipt = {
            "schema_version": RECEIPT_SCHEMA_VERSION,
            "attempt_id": run_id,
            "source_id": source_id,
            "status": "failure",
            "started_at": started_at,
            "completed_at": failure_completed_at,
            "raw_sha256": raw_digest,
            "raw_snapshot": (
                _relative(raw_snapshot, source_root) if raw_snapshot is not None else None
            ),
            "normalized_sha256": normalized_digest,
            "normalized_path": (
                _relative(normalized_path, source_root) if normalized_path is not None else None
            ),
            "previous_normalized_sha256": previous_digest,
            "activated": activated,
            "error": {
                "type": _error_type(exc, rollback_failed),
                "message": (
                    f"{failure_stage} failed; rollback also failed"
                    if rollback_failed
                    else f"{failure_stage} failed"
                ),
            },
        }
        failure_receipt_path = (
            receipts_dir / f"{run_id}.failure.json" if rollback_failed else receipt_path
        )
        try:
            _install_immutable(source_root, failure_receipt_path, _receipt_bytes(failure))
        except BaseException as receipt_exc:
            if not isinstance(receipt_exc, Exception):
                raise
            raise IngestionError(
                "ingestion failed and its failure receipt could not be written"
            ) from None
        if rollback_failed:
            raise IngestionRunError(
                f"ingestion failed for source {source_id!r} and rollback failed; "
                "operator intervention is required",
                failure_receipt_path,
            ) from None
        raise IngestionRunError(
            f"ingestion failed for source {source_id!r}", failure_receipt_path
        ) from None
    finally:
        _finalize_lock(lock_path, lock_identity, retain_lock)
