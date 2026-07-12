"""The deployed Pages artifact is minimal, traceable, and privacy-safe."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest
import tools.build_site as build_site_module
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

    artifact_files = {path.relative_to(out).as_posix() for path in out.rglob("*") if path.is_file()}
    assert set(manifest["files"]) == artifact_files - {"site-manifest.json"}
    assert "site-manifest.json" in artifact_files


def test_build_is_byte_stable_for_same_commit(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    build_site(first, SHA)
    build_site(second, SHA)
    assert (first / "site-manifest.json").read_bytes() == (
        second / "site-manifest.json"
    ).read_bytes()


def _minimal_site_source(root: Path) -> None:
    (root / "web" / "vendor").mkdir(parents=True)
    (root / "web" / "locales").mkdir()
    (root / "data" / "published").mkdir(parents=True)
    (root / "index.html").write_text("index", encoding="utf-8")
    (root / "CNAME").write_text("example.test\n", encoding="utf-8")
    (root / "web" / "index.html").write_text("web", encoding="utf-8")
    (root / "web" / "vendor" / "safe.js").write_text("safe", encoding="utf-8")
    (root / "web" / "locales" / "en.json").write_text("{}", encoding="utf-8")


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="symlinks unavailable")
def test_build_rejects_published_symlink_escape(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "repo"
    _minimal_site_source(root)
    private = root / "data" / "raw" / "precise.json"
    private.parent.mkdir(parents=True)
    private.write_text('{"precise": true}', encoding="utf-8")
    (root / "data" / "published" / "escape.json").symlink_to(private)
    monkeypatch.setattr(build_site_module, "ROOT", root)

    with pytest.raises(ValueError, match="refusing symlink"):
        build_site_module.build_site(tmp_path / "site", SHA)


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="symlinks unavailable")
def test_build_rejects_symlink_inside_copied_web_tree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "repo"
    _minimal_site_source(root)
    private = root / "private.js"
    private.write_text("private", encoding="utf-8")
    (root / "web" / "vendor" / "escape.js").symlink_to(private)
    monkeypatch.setattr(build_site_module, "ROOT", root)

    with pytest.raises(ValueError, match="refusing symlink"):
        build_site_module.build_site(tmp_path / "site", SHA)


def test_copy_rejects_lexical_path_that_resolves_outside_root(tmp_path: Path) -> None:
    allowed = tmp_path / "public"
    allowed.mkdir()
    private = tmp_path / "private.json"
    private.write_text('{"precise": true}', encoding="utf-8")

    with pytest.raises(ValueError, match="escapes"):
        build_site_module._copy_file(
            allowed / ".." / private.name,
            tmp_path / "site" / "leak.json",
            allowed_root=allowed,
        )
