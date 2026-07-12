# SPDX-License-Identifier: Apache-2.0
"""Exact, bounded reads for operator-selected derivation inputs."""

from __future__ import annotations

import os
import stat
from contextlib import suppress
from pathlib import Path


class SecureInputError(Exception):
    """An operator input could not be read without weakening integrity gates."""


def _require_secure_capabilities() -> None:
    """Fail before traversal unless every required POSIX primitive is available."""
    security_flag_names = ("O_NOFOLLOW", "O_DIRECTORY", "O_CLOEXEC", "O_NONBLOCK")
    function_names = ("open", "close", "fdopen", "fstat", "geteuid")
    stat_fields = ("st_uid", "st_nlink", "st_mtime_ns", "st_ctime_ns")
    supports_dir_fd = getattr(os, "supports_dir_fd", ())
    if (
        not isinstance(getattr(os, "O_RDONLY", None), int)
        or any(
            not isinstance(getattr(os, name, None), int) or getattr(os, name) == 0
            for name in security_flag_names
        )
        or any(not callable(getattr(os, name, None)) for name in function_names)
        or os.open not in supports_dir_fd
        or any(not hasattr(os.stat_result, name) for name in stat_fields)
    ):
        raise SecureInputError("secure input verification is unavailable")


def _read_flags() -> int:
    return os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK


def _directory_flags() -> int:
    return os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC


def _validate_directory(descriptor: int) -> None:
    metadata = os.fstat(descriptor)
    if not stat.S_ISDIR(metadata.st_mode):
        raise SecureInputError("input ancestor is not a real directory")
    if metadata.st_uid not in {0, os.geteuid()}:
        raise SecureInputError("input ancestor ownership is unsafe")
    writable = bool(metadata.st_mode & 0o022)
    if writable and not metadata.st_mode & stat.S_ISVTX:
        raise SecureInputError("input ancestor permissions are unsafe")


def _open_parent(path: str | Path) -> tuple[int, str]:
    # ``Path.resolve`` would follow the intermediate symlinks this traversal is
    # specifically designed to reject.
    absolute = Path(os.path.abspath(os.fspath(path)))  # noqa: PTH100
    name = absolute.name
    if not name:
        raise SecureInputError("input path must name a file")
    descriptor = os.open(os.sep, _directory_flags())
    try:
        _validate_directory(descriptor)
        for part in absolute.parts[1:-1]:
            child = os.open(part, _directory_flags(), dir_fd=descriptor)
            try:
                _validate_directory(child)
            except BaseException:
                os.close(child)
                raise
            os.close(descriptor)
            descriptor = child
        return descriptor, name
    except BaseException:
        with suppress(OSError):
            os.close(descriptor)
        raise


def _read_descriptor(descriptor: int, maximum_bytes: int) -> bytes:
    before = os.fstat(descriptor)
    if not stat.S_ISREG(before.st_mode):
        raise SecureInputError("input is not a regular file")
    if before.st_uid != os.geteuid() or before.st_nlink != 1:
        raise SecureInputError("input ownership or link count is unsafe")
    if before.st_mode & 0o022:
        raise SecureInputError("input permissions are unsafe")
    if before.st_size <= 0 or before.st_size > maximum_bytes:
        raise SecureInputError("input size is outside its safety limit")
    with os.fdopen(descriptor, "rb", closefd=False) as handle:
        payload = handle.read(maximum_bytes + 1)
    after = os.fstat(descriptor)
    identity_before = (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
        before.st_ctime_ns,
    )
    identity_after = (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
        after.st_ctime_ns,
    )
    if identity_after != identity_before or len(payload) != before.st_size:
        raise SecureInputError("input changed while it was read")
    return payload


def read_owned_regular(path: str | Path, *, maximum_bytes: int) -> bytes:
    """Read one owned, non-writable regular file exactly once through its fd.

    The returned bytes are suitable for both hashing and parsing.  Rename races
    cannot substitute content after the open, and in-place mutations are
    rejected by comparing descriptor metadata before and after the bounded
    read.  Paths and payload details are deliberately absent from errors so a
    caller can safely redact failures at a CLI boundary.
    """
    if isinstance(maximum_bytes, bool) or not isinstance(maximum_bytes, int):
        raise TypeError("maximum_bytes must be an integer")
    if maximum_bytes <= 0:
        raise ValueError("maximum_bytes must be positive")
    _require_secure_capabilities()
    parent_descriptor = -1
    descriptor = -1
    try:
        parent_descriptor, name = _open_parent(path)
        descriptor = os.open(name, _read_flags(), dir_fd=parent_descriptor)
        return _read_descriptor(descriptor, maximum_bytes)
    except SecureInputError:
        raise
    except OSError:
        raise SecureInputError("input is not safely readable") from None
    finally:
        for open_descriptor in (descriptor, parent_descriptor):
            if open_descriptor >= 0:
                with suppress(OSError):
                    os.close(open_descriptor)


__all__ = ["SecureInputError", "read_owned_regular"]
