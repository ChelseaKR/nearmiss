#!/usr/bin/env python3
"""Build one canonical county-context release index from explicit public files.

This tool has no discovery mode. Operators name every candidate state value and
boundary path relative to a reviewed release root, so an unreviewed file cannot
be silently added to the browser allowlist.
"""

from __future__ import annotations

import argparse
import os
import stat
import tempfile
from collections.abc import Sequence
from pathlib import Path

from nearmiss.fars_county_boundary_publication import FARS_COUNTY_PUBLIC_BOUNDARY_MAX_BYTES
from nearmiss.fars_county_public_index import (
    FARS_COUNTY_PUBLIC_CORRECTIONS_FILENAME,
    FARS_COUNTY_PUBLIC_INDEX_MAX_BYTES,
    build_fars_county_public_release_index,
    canonical_fars_county_public_release_index_bytes,
)
from nearmiss.fars_county_publication import FARS_COUNTY_PUBLIC_ARTIFACT_MAX_BYTES


def _bounded_relative_file(root: Path, relative: str, *, maximum: int, label: str) -> bytes:
    candidate = Path(relative)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ValueError(f"{label} path must be relative to the release root")
    path = root / candidate
    if path.is_symlink():
        raise ValueError(f"{label} must not be a symlink")
    try:
        metadata = path.stat()
    except OSError as exc:
        raise ValueError(f"{label} is unavailable") from exc
    if not stat.S_ISREG(metadata.st_mode) or not 1 <= metadata.st_size <= maximum:
        raise ValueError(f"{label} is not a bounded regular file")
    payload = path.read_bytes()
    if len(payload) != metadata.st_size:
        raise ValueError(f"{label} changed while it was read")
    return payload


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            os.fchmod(stream.fileno(), 0o644)
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
        directory_descriptor = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    finally:
        temporary.unlink(missing_ok=True)


def build_index(
    *,
    root: Path,
    values: Sequence[str],
    boundaries: Sequence[str],
    correction_ledger: str = FARS_COUNTY_PUBLIC_CORRECTIONS_FILENAME,
    release_id: str,
) -> bytes:
    """Read explicit public inputs and return one canonical index payload."""

    if root.is_symlink() or not root.is_dir():
        raise ValueError("county release root must be a real directory")
    if len(values) != len(set(values)) or len(boundaries) != len(set(boundaries)):
        raise ValueError("county release input paths must be unique")
    value_payloads = {
        path: _bounded_relative_file(
            root,
            path,
            maximum=FARS_COUNTY_PUBLIC_ARTIFACT_MAX_BYTES,
            label="county value artifact",
        )
        for path in values
    }
    boundary_payloads = {
        path: _bounded_relative_file(
            root,
            path,
            maximum=FARS_COUNTY_PUBLIC_BOUNDARY_MAX_BYTES,
            label="county boundary artifact",
        )
        for path in boundaries
    }
    ledger_payload = _bounded_relative_file(
        root,
        correction_ledger,
        maximum=FARS_COUNTY_PUBLIC_INDEX_MAX_BYTES,
        label="county correction ledger",
    )
    return canonical_fars_county_public_release_index_bytes(
        build_fars_county_public_release_index(
            value_payloads,
            boundary_payloads,
            ledger_payload,
            release_id=release_id,
        )
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True, help="reviewed release root")
    parser.add_argument(
        "--value",
        action="append",
        required=True,
        help="canonical value path relative to --root (repeat for each state/year)",
    )
    parser.add_argument(
        "--boundary",
        action="append",
        required=True,
        help="canonical public boundary path relative to --root (repeat for each state)",
    )
    parser.add_argument(
        "--correction-ledger",
        default=FARS_COUNTY_PUBLIC_CORRECTIONS_FILENAME,
        help="canonical correction-ledger path relative to --root",
    )
    parser.add_argument("--release-id", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    payload = build_index(
        root=args.root,
        values=args.value,
        boundaries=args.boundary,
        correction_ledger=args.correction_ledger,
        release_id=args.release_id,
    )
    _atomic_write(args.out, payload)
    print(f"county public release index: {args.out} ({len(payload)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
