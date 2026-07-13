"""The deployed Pages artifact is minimal, traceable, and privacy-safe."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from html.parser import HTMLParser
from pathlib import Path

import pytest
import tools.build_site as build_site_module
from tools.build_site import build_site

SHA = "a" * 40
PROJECT_ROOT = Path(__file__).resolve().parents[1]
NATIONAL_ROUTE = "/fars/national/"
NATIONAL_MANIFEST_PATH = "fars/national/index.html"
NATIONAL_CANONICAL = "https://nearmiss.report/fars/national/"


class _ApexDocument(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.refreshes: list[str] = []
        self.canonicals: list[str] = []
        self.links: list[str] = []
        self.main_landmarks = 0
        self.redirect_scripts: list[str] = []
        self._script_parts: list[str] | None = None

    def handle_starttag(self, tag: str, attrs_list: list[tuple[str, str | None]]) -> None:
        attrs = {key.casefold(): value or "" for key, value in attrs_list}
        normalized_tag = tag.casefold()
        if normalized_tag == "meta" and attrs.get("http-equiv", "").casefold() == "refresh":
            self.refreshes.append(attrs.get("content", ""))
        elif normalized_tag == "link" and "canonical" in attrs.get("rel", "").casefold().split():
            self.canonicals.append(attrs.get("href", ""))
        elif normalized_tag == "a":
            self.links.append(attrs.get("href", ""))
        elif normalized_tag == "main":
            self.main_landmarks += 1
        elif normalized_tag == "script" and "data-apex-redirect" in attrs:
            self._script_parts = []

    def handle_data(self, data: str) -> None:
        if self._script_parts is not None:
            self._script_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() == "script" and self._script_parts is not None:
            self.redirect_scripts.append("".join(self._script_parts))
            self._script_parts = None


def _assert_national_apex(html: str) -> None:
    document = _ApexDocument()
    document.feed(html)
    document.close()

    assert document.refreshes == [f"0; url={NATIONAL_ROUTE}"]
    assert document.canonicals == [NATIONAL_CANONICAL]
    assert document.main_landmarks == 1
    assert len(document.redirect_scripts) == 1
    redirect = document.redirect_scripts[0]
    assert 'const values = new URLSearchParams(window.location.search).getAll("lang")' in redirect
    assert 'values.length === 1 ? values[0] : ""' in redirect
    assert 'language === "es" ? "?lang=es"' in redirect
    assert 'language === "en" ? "?lang=en"' in redirect
    assert "window.location.replace(`/fars/national/${query}`)" in redirect
    assert NATIONAL_ROUTE in document.links
    assert f"{NATIONAL_ROUTE}?lang=es" in document.links
    assert "/web/index.html" in document.links
    assert "/data/published/fars-state-mode-index-v2.json" in document.links
    assert "/data/published/fars-2024-state-mode-r2.json" in document.links
    assert "/data/published/fars-release-corrections.json" in document.links
    assert "/data/published/" not in document.links
    assert document.links.index(NATIONAL_ROUTE) < document.links.index("/web/index.html")


def test_site_artifact_contains_only_public_surfaces(tmp_path: Path) -> None:
    out = tmp_path / "site"
    manifest = build_site(out, SHA)
    files = set(manifest["files"])

    assert "index.html" in files
    assert "web/index.html" in files
    assert "web/app.js" in files
    assert "web/us-coverage.html" in files
    assert NATIONAL_MANIFEST_PATH in files
    assert "web/us-coverage.js" in files
    assert "web/us-coverage.css" in files
    assert "web/vendor/leaflet/leaflet.js" in files
    assert "data/published/davis.geojson" in files
    assert "data/published/fars-state-mode-index.json" in files
    assert "data/published/fars-state-mode-index-v2.json" in files
    assert "data/published/fars-release-corrections.json" in files
    for year in range(2020, 2025):
        assert f"data/published/fars-{year}-state-mode.json" in files
    assert "data/published/fars-2024-state-mode-r2.json" in files
    assert "deployment.json" in files
    assert not any(path.startswith("data/raw/") for path in files)
    assert not any(path.startswith("config/") for path in files)
    assert not any(path.startswith("src/") for path in files)
    assert not any("node_modules" in path for path in files)
    assert not any(path.endswith(".run.json") for path in files)


def test_source_and_built_apex_promote_national_surface(tmp_path: Path) -> None:
    out = tmp_path / "site"
    build_site(out, SHA)
    source = (build_site_module.ROOT / "index.html").read_text(encoding="utf-8")
    built = (out / "index.html").read_text(encoding="utf-8")

    assert built == source
    _assert_national_apex(source)
    _assert_national_apex(built)


def test_canonical_national_route_is_a_byte_identical_real_page(tmp_path: Path) -> None:
    out = tmp_path / "site"
    manifest = build_site(out, SHA)
    legacy = out / "web" / "us-coverage.html"
    canonical = out / NATIONAL_MANIFEST_PATH

    assert canonical.read_bytes() == legacy.read_bytes()
    html = canonical.read_text(encoding="utf-8")
    document = _ApexDocument()
    document.feed(html)
    document.close()
    assert document.canonicals == [NATIONAL_CANONICAL]
    assert "<base" not in html.casefold()
    assert 'class="skip-link" href="#main"' in html

    dependencies = {
        "web/style.css",
        "web/us-coverage.css",
        "web/i18n.js",
        "web/us-coverage.js",
        "data/published/fars-2024-state-mode-r2.json",
        "data/published/fars-state-mode-index-v2.json",
        "data/published/fars-release-corrections.json",
        "deployment.json",
    }
    assert dependencies <= set(manifest["files"])
    for path in dependencies:
        assert f'="/{path}"' in html


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


def test_deploy_verifier_hash_binds_every_national_runtime_dependency() -> None:
    workflow = (PROJECT_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    required_specs = {
        "index.html|",
        "deployment.json|deployment.json",
        "web/index.html|web/index.html",
        "web/us-coverage.html|web/us-coverage.html",
        "fars/national/index.html|fars/national/",
        "web/us-coverage.js|web/us-coverage.js",
        "web/i18n.js|web/i18n.js",
        "web/locales/en.json|web/locales/en.json",
        "web/locales/es.json|web/locales/es.json",
        "web/us-coverage.css|web/us-coverage.css",
        "web/style.css|web/style.css",
        "data/published/davis.geojson|data/published/davis.geojson",
        "data/published/fars-state-mode-index.json|data/published/fars-state-mode-index.json",
        "data/published/fars-2024-state-mode.json|data/published/fars-2024-state-mode.json",
        "data/published/fars-state-mode-index-v2.json|data/published/fars-state-mode-index-v2.json",
        "data/published/fars-release-corrections.json|data/published/fars-release-corrections.json",
    }
    for spec in required_specs:
        assert f"'{spec}'" in workflow
    assert '[ "$live_sha" != "$expected_sha" ]' in workflow
    assert '[ "$live_sha" != "$manifest_artifact_sha" ]' in workflow


def test_build_is_byte_stable_for_same_commit(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    build_site(first, SHA)
    build_site(second, SHA)
    assert (first / "site-manifest.json").read_bytes() == (
        second / "site-manifest.json"
    ).read_bytes()


def test_pages_builder_runs_without_site_packages(tmp_path: Path) -> None:
    """The clean Pages job must not depend on packages preinstalled on its runner."""
    out = tmp_path / "isolated-site"
    result = subprocess.run(
        [
            sys.executable,
            "-S",
            str(PROJECT_ROOT / "tools" / "build_site.py"),
            "--out",
            str(out),
            "--sha",
            SHA,
        ],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    manifest = json.loads((out / "site-manifest.json").read_text(encoding="utf-8"))
    assert manifest["source_sha"] == SHA


def _minimal_site_source(root: Path) -> None:
    (root / "web" / "vendor").mkdir(parents=True)
    (root / "web" / "locales").mkdir()
    (root / "data" / "published").mkdir(parents=True)
    (root / "index.html").write_text("index", encoding="utf-8")
    (root / "CNAME").write_text("example.test\n", encoding="utf-8")
    (root / "web" / "index.html").write_text("web", encoding="utf-8")
    (root / "web" / "us-coverage.html").write_text("national", encoding="utf-8")
    (root / "web" / "vendor" / "safe.js").write_text("safe", encoding="utf-8")
    (root / "web" / "locales" / "en.json").write_text("{}", encoding="utf-8")


def _copy_current_fars_release_set(destination: Path) -> None:
    source = PROJECT_ROOT / "data" / "published"
    names = {
        "fars-state-mode-index.json",
        "fars-state-mode-index-v2.json",
        "fars-release-corrections.json",
    }
    for index_name in ("fars-state-mode-index.json", "fars-state-mode-index-v2.json"):
        index = json.loads((source / index_name).read_text(encoding="utf-8"))
        names.update(release["artifact_path"] for release in index["releases"])
    for name in names:
        (destination / name).write_bytes((source / name).read_bytes())


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
    _copy_current_fars_release_set(root / "data" / "published")
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


def test_build_rejects_unindexed_fars_json_before_published_copy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "repo"
    _minimal_site_source(root)
    published = root / "data" / "published"
    _copy_current_fars_release_set(published)
    (published / "fars-2023-debug.json").write_text(
        '{"raw_case_ids":["private-case-id"]}\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(build_site_module, "ROOT", root)

    out = tmp_path / "site"
    with pytest.raises(ValueError, match="FARS namespace"):
        build_site_module.build_site(out, SHA)
    assert not (out / "data" / "published").exists()
