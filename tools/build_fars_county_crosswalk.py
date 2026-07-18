#!/usr/bin/env python3
"""Create and consume private review packets for a FARS county crosswalk.

The template mode extracts every reported FARS county code from one verified
feasibility artifact without carrying any counts.  Build mode accepts only that
fully reviewed packet, validates every selected Census identity against the
pinned private boundary shards, and writes a canonical *private* crosswalk.
Neither mode can write into the public artifact tree.
"""

from __future__ import annotations

import argparse
import json
import os
import stat
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import cast

from build_us_county_boundaries import (  # type: ignore[import-not-found]
    EXPECTED_STATES,
    canonical_boundary_shard_bytes,
    validate_boundary_shard,
)

from nearmiss import fars_county_crosswalk_review as review
from nearmiss import fars_county_feasibility as feasibility
from nearmiss.fars_county_crosswalk import canonical_fars_county_crosswalk_bytes

_MAX_ARTIFACT_BYTES = 16 * 1024 * 1024
_MAX_BOUNDARY_SHARD_BYTES = 16 * 1024 * 1024
_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
_PUBLISHED_DATA_ROOT = (_REPOSITORY_ROOT / "data" / "published").resolve()


def _reject_json_constant(value: str) -> object:
    raise ValueError(f"JSON constant {value!r} is not permitted")


def _read_bounded_json(
    path: Path, *, label: str, maximum: int
) -> tuple[bytes, Mapping[str, object]]:
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
    try:
        decoded = json.loads(payload.decode("utf-8"), parse_constant=_reject_json_constant)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise ValueError(f"{label} is not strict JSON") from exc
    if not isinstance(decoded, Mapping):
        raise ValueError(f"{label} root must be an object")
    return payload, cast(Mapping[str, object], decoded)


def _require_canonical(payload: bytes, canonical: bytes, *, label: str) -> None:
    if payload != canonical:
        raise ValueError(f"{label} must use the canonical private JSON encoding")


def _is_public_output_path(path: Path) -> bool:
    try:
        path.resolve().relative_to(_PUBLISHED_DATA_ROOT)
    except ValueError:
        return False
    return True


def _atomic_write(path: Path, payload: bytes) -> None:
    if _is_public_output_path(path):
        raise ValueError("private county crosswalk output must not be written to data/published")
    if path.is_symlink():
        raise ValueError("private county crosswalk output must not be a symlink")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            os.fchmod(stream.fileno(), 0o600)
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


def _read_boundary_shards(
    boundary_dir: Path,
) -> tuple[dict[str, Mapping[str, object]], Mapping[str, object]]:
    if boundary_dir.is_symlink() or not boundary_dir.is_dir():
        raise ValueError("private county boundary directory must be a real directory")
    expected_filenames = {f"{state_fips}.json" for state_fips in EXPECTED_STATES}
    actual_filenames = {path.name for path in boundary_dir.iterdir()}
    if actual_filenames != expected_filenames:
        raise ValueError(
            "private county boundary directory does not contain exactly 51 state shards"
        )

    shards: dict[str, Mapping[str, object]] = {}
    source: Mapping[str, object] | None = None
    for state_fips in sorted(EXPECTED_STATES):
        payload, shard = _read_bounded_json(
            boundary_dir / f"{state_fips}.json",
            label=f"private county boundary shard {state_fips}",
            maximum=_MAX_BOUNDARY_SHARD_BYTES,
        )
        validate_boundary_shard(shard)
        _require_canonical(
            payload,
            canonical_boundary_shard_bytes(shard),
            label=f"private county boundary shard {state_fips}",
        )
        if shard["state_fips"] != state_fips:
            raise ValueError("private county boundary shard filename state is inconsistent")
        shard_source = cast(Mapping[str, object], shard["source"])
        if source is None:
            source = shard_source
        elif dict(shard_source) != dict(source):
            raise ValueError("private county boundary shards do not share exact provenance")
        shards[state_fips] = shard
    if source is None:
        raise ValueError("private county boundary directory is empty")
    return shards, source


def _validate_reviewed_targets(
    crosswalk_artifact: Mapping[str, object],
    boundary_shards: Mapping[str, Mapping[str, object]],
) -> None:
    features: dict[str, Mapping[str, object]] = {}
    for shard in boundary_shards.values():
        for feature in cast(list[Mapping[str, object]], shard["features"]):
            geoid = cast(str, feature["id"])
            if geoid in features:
                raise ValueError("private county boundary shards duplicate a GEOID")
            features[geoid] = feature
    for row in cast(list[Mapping[str, object]], crosswalk_artifact["rows"]):
        presentation = row["presentation"]
        if presentation is None:
            continue
        target = cast(Mapping[str, object], presentation)
        geoid = cast(str, target["geoid"])
        feature = features.get(geoid)
        if feature is None:
            raise ValueError("reviewed FARS county target has no private boundary feature")
        properties = cast(Mapping[str, object], feature["properties"])
        expected = {
            "state_fips": target["state_fips"],
            "county_fips": target["county_fips"],
            "geoid": target["geoid"],
            "name": target["name"],
            "namelsad": target["namelsad"],
        }
        if any(properties[key] != value for key, value in expected.items()):
            raise ValueError("reviewed FARS county target does not match its boundary identity")


def _load_feasibility(path: Path) -> Mapping[str, object]:
    payload, artifact = _read_bounded_json(
        path,
        label="private FARS county feasibility artifact",
        maximum=_MAX_ARTIFACT_BYTES,
    )
    feasibility.validate_fars_county_feasibility_artifact(artifact)
    _require_canonical(
        payload,
        feasibility.canonical_fars_county_feasibility_bytes(artifact),
        label="private FARS county feasibility artifact",
    )
    return artifact


def _load_review(path: Path) -> Mapping[str, object]:
    payload, artifact = _read_bounded_json(
        path,
        label="private FARS county crosswalk review",
        maximum=_MAX_ARTIFACT_BYTES,
    )
    review.validate_fars_county_crosswalk_review_artifact(artifact)
    _require_canonical(
        payload,
        review.canonical_fars_county_crosswalk_review_bytes(artifact),
        label="private FARS county crosswalk review",
    )
    return artifact


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--feasibility", type=Path, required=True)
    operation = parser.add_mutually_exclusive_group(required=True)
    operation.add_argument("--template-out", type=Path)
    operation.add_argument("--review", type=Path)
    parser.add_argument("--boundary-dir", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    feasibility_artifact = _load_feasibility(cast(Path, args.feasibility))
    template_out = cast(Path | None, args.template_out)
    if template_out is not None:
        if args.boundary_dir is not None or args.out is not None:
            parser.error("--template-out cannot be combined with --boundary-dir or --out")
        template = review.build_fars_county_crosswalk_review_template(feasibility_artifact)
        _atomic_write(template_out, review.canonical_fars_county_crosswalk_review_bytes(template))
        source_count = cast(Mapping[str, int], template["accounting"])["source_row_count"]
        print(f"private FARS county review template: {template_out} ({source_count} source codes)")
        return 0

    review_path = cast(Path | None, args.review)
    boundary_dir = cast(Path | None, args.boundary_dir)
    out = cast(Path | None, args.out)
    if review_path is None or boundary_dir is None or out is None:
        parser.error("--review requires --boundary-dir and --out")
    review_artifact = _load_review(review_path)
    boundary_shards, boundary_source = _read_boundary_shards(boundary_dir)
    crosswalk_artifact = review.build_fars_county_crosswalk_from_review(
        review_artifact,
        feasibility_artifact=feasibility_artifact,
        boundary=boundary_source,
    )
    _validate_reviewed_targets(crosswalk_artifact, boundary_shards)
    _atomic_write(out, canonical_fars_county_crosswalk_bytes(crosswalk_artifact))
    source_count = cast(Mapping[str, int], crosswalk_artifact["accounting"])["source_row_count"]
    print(f"private FARS county crosswalk: {out} ({source_count} reviewed source codes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
