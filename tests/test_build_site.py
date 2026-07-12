"""The deployed Pages artifact is minimal, traceable, and privacy-safe."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from tools.build_site import build_site

SHA = "a" * 40


def test_site_artifact_contains_only_public_surfaces(tmp_path: Path) -> None:
    out = tmp_path / "site"
    manifest = build_site(out, SHA)
    files = set(manifest["files"])

    assert "index.html" in files
    assert "web/index.html" in files
    assert "web/app.js" in files
    assert "web/vendor/leaflet/leaflet.js" in files
    assert "data/published/davis.geojson" in files
    assert "deployment.json" in files
    assert not any(path.startswith("data/raw/") for path in files)
    assert not any(path.startswith("config/") for path in files)
    assert not any(path.startswith("src/") for path in files)
    assert not any("node_modules" in path for path in files)
    assert not any(path.endswith(".run.json") for path in files)


def test_deployment_stamp_and_manifest_hashes_are_exact(tmp_path: Path) -> None:
    out = tmp_path / "site"
    manifest = build_site(out, SHA)
    deployment = json.loads((out / "deployment.json").read_text(encoding="utf-8"))
    assert deployment["source_sha"] == SHA
    assert deployment["source_url"].endswith(SHA)

    for relative, expected in manifest["files"].items():
        assert hashlib.sha256((out / relative).read_bytes()).hexdigest() == expected


def test_build_is_byte_stable_for_same_commit(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    build_site(first, SHA)
    build_site(second, SHA)
    assert (first / "site-manifest.json").read_bytes() == (
        second / "site-manifest.json"
    ).read_bytes()
