#!/usr/bin/env python3
"""Assemble the minimal public GitHub Pages artifact.

Legacy Pages served the repository root. This builder instead allowlists the
web application and already-aggregated published datasets, stamps the source
commit, and emits hashes for every deployed file.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path
from typing import TypedDict

ROOT = Path(__file__).resolve().parents[1]
WEB_PATTERNS = ("*.html", "*.js", "*.css")
PUBLISHED_SUFFIXES = (".geojson", ".json", ".svg", ".md")


class SiteManifest(TypedDict):
    schema_version: int
    source_sha: str
    files: dict[str, str]


def _resolved_beneath(source: Path, allowed_root: Path) -> Path:
    """Resolve *source* and fail closed if it leaves its public source root."""
    if allowed_root.is_symlink():
        raise ValueError(f"refusing symlinked public source root: {allowed_root}")
    root = allowed_root.resolve(strict=True)
    try:
        relative = source.relative_to(allowed_root)
    except ValueError as exc:
        raise ValueError(f"public artifact source escapes {root}: {source}") from exc
    cursor = allowed_root
    for part in relative.parts:
        cursor /= part
        if cursor.is_symlink():
            raise ValueError(f"refusing symlink in public artifact: {cursor}")
    resolved = source.resolve(strict=True)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"public artifact source escapes {root}: {source}") from exc
    return resolved


def _copy_file(source: Path, destination: Path, *, allowed_root: Path) -> None:
    resolved = _resolved_beneath(source, allowed_root)
    if not resolved.is_file():
        raise ValueError(f"public artifact source is not a file: {source}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(resolved, destination)


def _copy_tree(source_root: Path, destination_root: Path) -> None:
    """Copy a public tree without following symlinks or resolution escapes."""
    if source_root.is_symlink():
        raise ValueError(f"refusing symlinked public source root: {source_root}")
    if not source_root.resolve(strict=True).is_dir():
        raise ValueError(f"public artifact source is not a directory: {source_root}")
    for source in sorted(source_root.rglob("*")):
        if source.is_symlink():
            raise ValueError(f"refusing symlink in public artifact: {source}")
        if source.is_file():
            relative = source.relative_to(source_root)
            _copy_file(
                source,
                destination_root / relative,
                allowed_root=source_root,
            )


def _copy_published(source_root: Path, destination_root: Path) -> None:
    """Copy only supported published outputs, excluding private run manifests."""
    if source_root.is_symlink():
        raise ValueError(f"refusing symlinked public source root: {source_root}")
    if not source_root.resolve(strict=True).is_dir():
        raise ValueError(f"public artifact source is not a directory: {source_root}")
    for source in sorted(source_root.rglob("*")):
        if source.is_symlink():
            raise ValueError(f"refusing symlink in public artifact: {source}")
        if not source.is_file():
            continue
        if source.name.endswith(".run.json") or source.suffix not in PUBLISHED_SUFFIXES:
            continue
        _copy_file(
            source,
            destination_root / source.relative_to(source_root),
            allowed_root=source_root,
        )


def _verify_fars_releases(source_root: Path) -> None:
    """Load the dependency-free annual release contract from the source tree."""
    source_package = str(ROOT / "src")
    if source_package not in sys.path:
        sys.path.insert(0, source_package)
    from nearmiss.fars_public_index import verify_fars_public_release_directory

    verify_fars_public_release_directory(source_root)


def build_site(out: Path, source_sha: str) -> SiteManifest:
    """Build an allowlisted static artifact and return its manifest."""
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    _copy_file(ROOT / "index.html", out / "index.html", allowed_root=ROOT)
    _copy_file(ROOT / "CNAME", out / "CNAME", allowed_root=ROOT)
    (out / ".nojekyll").write_text("", encoding="utf-8")

    for pattern in WEB_PATTERNS:
        for source in sorted((ROOT / "web").glob(pattern)):
            _copy_file(
                source,
                out / "web" / source.name,
                allowed_root=ROOT / "web",
            )
    for directory in ("vendor", "locales"):
        _copy_tree(ROOT / "web" / directory, out / "web" / directory)
    published = ROOT / "data" / "published"
    _verify_fars_releases(published)
    _copy_published(published, out / "data" / "published")

    deployment = {
        "schema_version": 1,
        "source_sha": source_sha,
        "source_url": f"https://github.com/ChelseaKR/nearmiss/commit/{source_sha}",
    }
    (out / "deployment.json").write_text(
        json.dumps(deployment, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    # site-manifest.json is the envelope for these hashes and is therefore the
    # sole public file not included in its own payload inventory.
    hashes = {}
    for path in sorted(p for p in out.rglob("*") if p.is_file()):
        relative = path.relative_to(out).as_posix()
        hashes[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    manifest: SiteManifest = {
        "schema_version": 1,
        "source_sha": source_sha,
        "files": hashes,
    }
    (out / "site-manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("_site"))
    parser.add_argument("--sha", required=True, help="exact source commit SHA")
    args = parser.parse_args()
    manifest = build_site(args.out, args.sha)
    print(f"site: {args.out} ({len(manifest['files'])} hashed public files)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
