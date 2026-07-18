#!/usr/bin/env python3
"""Assemble the minimal public GitHub Pages artifact.

The builder publishes a small evidence-to-action gateway plus the reviewed
national FARS reference application and its exact public data dependencies. It
stamps the source commit and emits hashes for every deployed file. Synthetic
methodology fixtures remain in the repository and cannot enter production.
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
PUBLIC_WEB_FILES = (
    "index.html",  # Public evidence-to-action gateway; not the former Davis application.
    "us-coverage.html",
    "us-coverage.js",
    "i18n.js",
    "brand.css",
    "landing.css",
    "style.css",
    "us-coverage.css",
    "us-coverage-studio.css",
    "vendor/brand/clearance-mark.svg",
    "vendor/fonts/LICENSE-atkinson-hyperlegible-next.txt",
    "vendor/fonts/LICENSE-fragment-mono.txt",
    "vendor/fonts/LICENSE-overpass.txt",
    "vendor/fonts/atkinson-hyperlegible-next-latin-ext-wght-normal.woff2",
    "vendor/fonts/atkinson-hyperlegible-next-latin-wght-normal.woff2",
    "vendor/fonts/fragment-mono-latin-400-normal.woff2",
    "vendor/fonts/fragment-mono-latin-ext-400-normal.woff2",
    "vendor/fonts/overpass-latin-ext-wght-normal.woff2",
    "vendor/fonts/overpass-latin-wght-normal.woff2",
)
PUBLIC_WEB_LOCALES = ("en.json", "es.json")
PUBLIC_WEB_MESSAGE_PREFIX = "web.coverage."

PUBLIC_FARS_FILES = (
    "fars-state-mode-index.json",
    "fars-state-mode-index-v2.json",
    "fars-release-corrections.json",
    "fars-2020-state-mode.json",
    "fars-2021-state-mode.json",
    "fars-2022-state-mode.json",
    "fars-2023-state-mode.json",
    "fars-2024-state-mode.json",
    "fars-2024-state-mode-r2.json",
    "us-state-boundaries-2024.json",
)


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


def _copy_allowlist(
    source_root: Path,
    destination_root: Path,
    relative_paths: tuple[str, ...],
) -> None:
    """Copy only the named files, failing closed on missing or linked entries."""
    for relative in relative_paths:
        _copy_file(
            source_root / relative,
            destination_root / relative,
            allowed_root=source_root,
        )


def _write_national_locales(source_root: Path, destination_root: Path) -> None:
    """Publish only national-studio messages from the shared source catalogs."""
    for name in PUBLIC_WEB_LOCALES:
        source = _resolved_beneath(source_root / name, source_root)
        if not source.is_file():
            raise ValueError(f"public locale source is not a file: {source}")
        try:
            catalog = json.loads(source.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"public locale source is invalid: {source}") from exc
        if not isinstance(catalog, dict) or not all(
            isinstance(key, str) and isinstance(value, str) for key, value in catalog.items()
        ):
            raise ValueError(f"public locale source must be a string catalog: {source}")
        national = {
            key: value
            for key, value in catalog.items()
            if key.startswith(PUBLIC_WEB_MESSAGE_PREFIX)
        }
        if not national:
            raise ValueError(f"public locale source has no national messages: {source}")
        destination = destination_root / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            json.dumps(national, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
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
    _copy_file(ROOT / "404.html", out / "404.html", allowed_root=ROOT)
    _copy_file(ROOT / "CNAME", out / "CNAME", allowed_root=ROOT)
    (out / ".nojekyll").write_text("", encoding="utf-8")

    _copy_allowlist(ROOT / "web", out / "web", PUBLIC_WEB_FILES)
    _write_national_locales(ROOT / "web" / "locales", out / "web" / "locales")

    # Keep the historical flat-file URL available while publishing the same
    # reviewed document at the stable, product-facing route. The document uses
    # root-absolute dependencies, so these byte-identical copies need no
    # redirect shell or path-rewriting <base> element.
    _copy_file(
        ROOT / "web" / "us-coverage.html",
        out / "fars" / "national" / "index.html",
        allowed_root=ROOT / "web",
    )
    published = ROOT / "data" / "published"
    _verify_fars_releases(published)
    _copy_allowlist(
        published,
        out / "data" / "published",
        PUBLIC_FARS_FILES,
    )

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
