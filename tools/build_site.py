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
from pathlib import Path
from typing import TypedDict

ROOT = Path(__file__).resolve().parents[1]
WEB_PATTERNS = ("*.html", "*.js", "*.css")
PUBLISHED_SUFFIXES = (".geojson", ".json", ".svg", ".md")


class SiteManifest(TypedDict):
    schema_version: int
    source_sha: str
    files: dict[str, str]


def _copy_file(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def build_site(out: Path, source_sha: str) -> SiteManifest:
    """Build an allowlisted static artifact and return its manifest."""
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    _copy_file(ROOT / "index.html", out / "index.html")
    _copy_file(ROOT / "CNAME", out / "CNAME")
    (out / ".nojekyll").write_text("", encoding="utf-8")

    for pattern in WEB_PATTERNS:
        for source in sorted((ROOT / "web").glob(pattern)):
            _copy_file(source, out / "web" / source.name)
    for directory in ("vendor", "locales"):
        shutil.copytree(ROOT / "web" / directory, out / "web" / directory)
    published = ROOT / "data" / "published"
    for source in sorted(path for path in published.rglob("*") if path.is_file()):
        if source.name.endswith(".run.json") or source.suffix not in PUBLISHED_SUFFIXES:
            continue
        _copy_file(source, out / "data" / "published" / source.relative_to(published))

    deployment = {
        "schema_version": 1,
        "source_sha": source_sha,
        "source_url": f"https://github.com/ChelseaKR/nearmiss/commit/{source_sha}",
    }
    (out / "deployment.json").write_text(
        json.dumps(deployment, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

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
