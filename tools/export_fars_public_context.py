#!/usr/bin/env python3
"""Export the public-safe 2024 state burden artifact from a verified joined root."""

from __future__ import annotations

import argparse
import os
import tempfile
from pathlib import Path

from nearmiss.fars_public_context import (
    build_verified_fars_public_context,
    canonical_fars_public_context_bytes,
)
from nearmiss.verified_outcomes import _load_verified_active_fars_joined_activation_state


def build_public_context(joined_root: str | Path) -> bytes:
    """Verify exact private lineage and return canonical public projection bytes."""
    activation = _load_verified_active_fars_joined_activation_state(joined_root)
    return canonical_fars_public_context_bytes(
        build_verified_fars_public_context(activation.snapshot)
    )


def _atomic_write_public_context(path: Path, payload: bytes) -> None:
    """Replace one public artifact atomically without exposing partial bytes."""
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
        directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        directory_descriptor = os.open(path.parent, directory_flags)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    finally:
        temporary.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--joined-root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    payload = build_public_context(args.joined_root)
    _atomic_write_public_context(args.out, payload)
    print(f"public FARS state context: {args.out} ({len(payload)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
