#!/usr/bin/env python3
"""Export one public-safe annual state burden artifact from a verified private root."""

from __future__ import annotations

import argparse
import os
import tempfile
from pathlib import Path

from nearmiss.fars_public_context import (
    build_verified_fars_public_context,
    build_verified_fars_public_release,
    canonical_fars_public_context_bytes,
)
from nearmiss.fars_year_contracts import fars_year_contract_revision
from nearmiss.verified_fars_years import _load_verified_active_fars_year_snapshot
from nearmiss.verified_outcomes import _load_verified_active_fars_joined_activation_state


def build_public_context(joined_root: str | Path) -> bytes:
    """Verify exact private lineage and return canonical public projection bytes."""
    activation = _load_verified_active_fars_joined_activation_state(joined_root)
    return canonical_fars_public_context_bytes(
        build_verified_fars_public_context(activation.snapshot)
    )


def canonical_public_release_filename(year: int) -> str:
    """Return the only supported public filename for an annual release."""
    fars_year_contract_revision(year, 1)
    return f"fars-{year}-state-mode.json"


def require_public_release_output_path(path: str | Path, *, year: int) -> Path:
    """Prevent a valid annual payload from being published under the wrong year."""
    output = Path(path)
    expected = canonical_public_release_filename(year)
    if output.name != expected:
        raise ValueError(f"annual public FARS output filename must be {expected}")
    return output


def build_public_release(
    private_root: str | Path,
    *,
    year: int,
    contract_revision: int,
) -> bytes:
    """Replay exact annual lineage and return only canonical public bytes."""
    snapshot = _load_verified_active_fars_year_snapshot(
        private_root,
        year=year,
        contract_revision=contract_revision,
    )
    return canonical_fars_public_context_bytes(
        build_verified_fars_public_release(
            snapshot,
            year=year,
            contract_revision=contract_revision,
        )
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
    parser.add_argument(
        "--year",
        type=int,
        help="registered annual dataset year; requires --contract-revision",
    )
    parser.add_argument(
        "--contract-revision",
        type=int,
        help="exact annual contract revision; requires --year",
    )
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    has_year = args.year is not None
    has_revision = args.contract_revision is not None
    if has_year != has_revision:
        parser.error("--year and --contract-revision must be provided together")
    if not has_year:
        output = args.out
        payload = build_public_context(args.joined_root)
    else:
        output = require_public_release_output_path(args.out, year=args.year)
        payload = build_public_release(
            args.joined_root,
            year=args.year,
            contract_revision=args.contract_revision,
        )
    _atomic_write_public_context(output, payload)
    print(f"public FARS state context: {output} ({len(payload)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
