#!/usr/bin/env python3
"""Build the canonical public FARS provenance-correction ledger."""

from __future__ import annotations

import argparse
import os
import stat
import tempfile
from pathlib import Path

from nearmiss.fars_public_index import build_fars_public_correction_ledger_bytes

_MAX_BYTES = 256 * 1024


def _read_bounded(path: Path, *, label: str) -> bytes:
    if path.is_symlink():
        raise ValueError(f"{label} must not be a symlink")
    try:
        metadata = path.stat()
    except OSError as exc:
        raise ValueError(f"{label} is unavailable") from exc
    if not stat.S_ISREG(metadata.st_mode) or not 1 <= metadata.st_size <= _MAX_BYTES:
        raise ValueError(f"{label} is not a bounded regular file")
    payload = path.read_bytes()
    if len(payload) != metadata.st_size:
        raise ValueError(f"{label} changed while it was read")
    return payload


def build_ledger(
    *,
    prior_artifact: Path,
    replacement_artifact: Path,
    prior_index: Path,
    replacement_index: Path,
) -> bytes:
    """Read exact inputs and return the closed canonical correction ledger."""
    return build_fars_public_correction_ledger_bytes(
        prior_artifact=_read_bounded(prior_artifact, label="prior artifact"),
        replacement_artifact=_read_bounded(
            replacement_artifact,
            label="replacement artifact",
        ),
        prior_index=_read_bounded(prior_index, label="prior index"),
        replacement_index=_read_bounded(replacement_index, label="replacement index"),
    )


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            os.fchmod(stream.fileno(), 0o644)
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
        directory_descriptor = os.open(
            path.parent,
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
        )
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    finally:
        temporary.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prior-artifact", type=Path, required=True)
    parser.add_argument("--replacement-artifact", type=Path, required=True)
    parser.add_argument("--prior-index", type=Path, required=True)
    parser.add_argument("--replacement-index", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    payload = build_ledger(
        prior_artifact=args.prior_artifact,
        replacement_artifact=args.replacement_artifact,
        prior_index=args.prior_index,
        replacement_index=args.replacement_index,
    )
    _atomic_write(args.out, payload)
    print(f"public FARS correction ledger: {args.out} ({len(payload)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
