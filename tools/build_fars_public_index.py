#!/usr/bin/env python3
"""Build the canonical public FARS release index from explicit annual files."""

from __future__ import annotations

import argparse
import os
import re
import tempfile
from collections.abc import Sequence
from pathlib import Path

from nearmiss.fars_public_index import (
    build_fars_public_release_index,
    canonical_fars_public_release_index_bytes,
)

_ARTIFACT_NAME = re.compile(r"^fars-([0-9]{4})-state-mode\.json$", re.ASCII)
_MAX_ARTIFACT_BYTES = 256 * 1024


def build_index(artifacts: Sequence[Path]) -> bytes:
    """Return a canonical index for explicitly named annual public artifacts."""
    if not artifacts:
        raise ValueError("at least one annual public FARS artifact is required")
    releases: dict[int, bytes] = {}
    for path in artifacts:
        match = _ARTIFACT_NAME.fullmatch(path.name)
        if match is None:
            raise ValueError("public FARS artifact filename is not canonical")
        year = int(match.group(1))
        if year in releases:
            raise ValueError("public FARS artifact year was supplied more than once")
        if path.is_symlink():
            raise ValueError("public FARS artifact must not be a symlink")
        try:
            size = path.stat().st_size
        except OSError as exc:
            raise ValueError("public FARS artifact is unavailable") from exc
        if not 1 <= size <= _MAX_ARTIFACT_BYTES:
            raise ValueError("public FARS artifact exceeds its byte safety limit")
        payload = path.read_bytes()
        if len(payload) != size:
            raise ValueError("public FARS artifact changed while it was read")
        releases[year] = payload
    return canonical_fars_public_release_index_bytes(build_fars_public_release_index(releases))


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
    parser.add_argument(
        "--artifact",
        action="append",
        required=True,
        type=Path,
        help="canonical fars-YYYY-state-mode.json file (repeat for each released year)",
    )
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    payload = build_index(args.artifact)
    _atomic_write(args.out, payload)
    print(f"public FARS release index: {args.out} ({len(payload)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
