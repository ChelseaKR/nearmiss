"""The recurring production sentinel is exact, bounded, and privacy-negative."""

from __future__ import annotations

import http.client
import json
import shutil
import socket
import ssl
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, ClassVar
from urllib.parse import urlsplit

import pytest
import tools.verify_live_site as live_cli
from tools.build_site import build_site

import nearmiss.live_site_verifier as live
from nearmiss.live_site_verifier import (
    FetchResult,
    LiveSiteVerificationError,
    ProductionHttpsFetcher,
    verify_live_site,
)

SHA = "d" * 40
CACHE_TOKEN = "a" * 32
ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def expected_site(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("live-site") / "site"
    build_site(root, SHA)
    return root


class MemoryFetcher:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.overrides: dict[str, FetchResult] = {}
        self.fail_prefix: str | None = None
        self.share_status: int | None = None
        self.baseline_status: int | None = None
        self.targets: list[tuple[str, int]] = []
        self.not_found = FetchResult(
            404,
            (root / "404.html").read_bytes(),
            "text/html; charset=utf-8",
        )

    @staticmethod
    def _content_type(path: Path) -> str:
        return {
            ".css": "text/css; charset=utf-8",
            ".geojson": "application/geo+json",
            ".html": "text/html; charset=utf-8",
            ".js": "application/javascript; charset=utf-8",
            ".json": "application/json; charset=utf-8",
            ".md": "text/markdown; charset=utf-8",
            ".png": "image/png",
            ".svg": "image/svg+xml",
            ".woff2": "font/woff2",
        }.get(path.suffix.lower(), "application/octet-stream")

    def fetch(self, target: str, *, maximum_bytes: int) -> FetchResult:
        self.targets.append((target, maximum_bytes))
        if self.fail_prefix is not None and target.startswith(self.fail_prefix):
            raise LiveSiteVerificationError("simulated network failure")
        parsed = urlsplit(target)
        path = parsed.path
        if self.baseline_status is not None and path.startswith(
            "/.well-known/nearmiss-guaranteed-missing-"
        ):
            return FetchResult(
                self.baseline_status,
                self.not_found.body,
                self.not_found.content_type,
            )
        if (
            self.share_status is not None
            and path == "/web/us-coverage.html"
            and "year=" in parsed.query
        ):
            return FetchResult(self.share_status, b"query failed", "text/plain")
        if path in self.overrides:
            result = self.overrides[path]
        elif path == "/":
            result = FetchResult(200, (self.root / "index.html").read_bytes(), "text/html")
        elif path == "/fars/national/":
            result = FetchResult(
                200,
                (self.root / "fars" / "national" / "index.html").read_bytes(),
                "text/html",
            )
        elif path in {"/.nojekyll", "/CNAME"}:
            result = self.not_found
        else:
            candidate = self.root / path.removeprefix("/")
            if candidate.is_file():
                result = FetchResult(
                    200,
                    candidate.read_bytes(),
                    self._content_type(candidate),
                )
            else:
                result = self.not_found
        if len(result.body) > maximum_bytes:
            raise LiveSiteVerificationError("simulated response exceeds its byte safety limit")
        return result


def _verify(expected_site: Path, fetcher: MemoryFetcher) -> live.LiveSiteSummary:
    return verify_live_site(
        expected_site,
        expected_sha=SHA,
        cache_token=CACHE_TOKEN,
        fetcher=fetcher,
    )


def test_exact_site_and_reviewed_404s_pass(expected_site: Path) -> None:
    fetcher = MemoryFetcher(expected_site)
    summary = _verify(expected_site, fetcher)

    assert summary.source_sha == SHA
    expected_manifest = json.loads(
        (expected_site / "site-manifest.json").read_text(encoding="utf-8")
    )
    assert summary.file_count == len(expected_manifest["files"])
    assert summary.default_year == 2024
    assert summary.default_source_revision.startswith("reviewed-")
    assert summary.private_probe_count == len(live.PRIVATE_PATH_PROBES)
    assert any(
        target.startswith("/.well-known/nearmiss-guaranteed-missing-")
        for target, _ in fetcher.targets
    )
    assert any(urlsplit(target).path == "/fars/national/" for target, _ in fetcher.targets)
    assert all(f"verify={CACHE_TOKEN}" in target for target, _ in fetcher.targets)


def test_unreviewed_uniform_404_body_fails(expected_site: Path) -> None:
    fetcher = MemoryFetcher(expected_site)
    fetcher.not_found = FetchResult(404, b"injected not found", "text/html; charset=utf-8")

    with pytest.raises(LiveSiteVerificationError, match="manifest-bound reviewed document"):
        _verify(expected_site, fetcher)


@pytest.mark.parametrize(
    ("path", "body", "message"),
    [
        ("/site-manifest.json", b"{}\n", "manifest"),
        ("/web/us-coverage.js", b"tampered", "us-coverage.js"),
        ("/fars/national/", b"tampered", "canonical national route"),
        ("/", b"soft 200 error", "apex"),
        ("/deployment.json", b"{}\n", "deployment"),
    ],
)
def test_live_positive_surface_drift_fails(
    expected_site: Path,
    path: str,
    body: bytes,
    message: str,
) -> None:
    fetcher = MemoryFetcher(expected_site)
    fetcher.overrides[path] = FetchResult(200, body, "text/plain")
    with pytest.raises(LiveSiteVerificationError, match=message):
        _verify(expected_site, fetcher)


@pytest.mark.parametrize("status", [301, 302, 404, 500])
def test_required_public_file_rejects_non_200(expected_site: Path, status: int) -> None:
    fetcher = MemoryFetcher(expected_site)
    fetcher.overrides["/web/us-coverage.css"] = FetchResult(status, b"", "text/plain")
    with pytest.raises(LiveSiteVerificationError, match=rf"HTTP {status}"):
        _verify(expected_site, fetcher)


@pytest.mark.parametrize(
    "path",
    [
        "/index.html",
        "/web/us-coverage.js",
        "/web/us-coverage.css",
        "/deployment.json",
        "/data/published/davis.geojson",
        "/data/published/davis-rates.svg",
        "/web/vendor/fonts/overpass-latin-wght-normal.woff2",
        "/web/vendor/leaflet/images/layers.png",
    ],
)
def test_correct_public_bytes_with_wrong_mime_fail(expected_site: Path, path: str) -> None:
    fetcher = MemoryFetcher(expected_site)
    fetcher.overrides[path] = FetchResult(
        200,
        (expected_site / path.removeprefix("/")).read_bytes(),
        "text/plain; charset=utf-8",
    )

    with pytest.raises(LiveSiteVerificationError, match="invalid Content-Type"):
        _verify(expected_site, fetcher)


def test_404_requires_html_content_type(expected_site: Path) -> None:
    fetcher = MemoryFetcher(expected_site)
    fetcher.not_found = FetchResult(404, fetcher.not_found.body, "text/plain")

    with pytest.raises(LiveSiteVerificationError, match=r"live 404 response.*Content-Type"):
        _verify(expected_site, fetcher)


def test_private_probe_must_match_404_body_not_only_status(expected_site: Path) -> None:
    fetcher = MemoryFetcher(expected_site)
    fetcher.overrides["/data/raw/private.json"] = FetchResult(
        404,
        b"private bytes under a misleading status",
        "application/json",
    )
    with pytest.raises(LiveSiteVerificationError, match="did not match the reviewed 404"):
        _verify(expected_site, fetcher)


@pytest.mark.parametrize("status", [200, 301, 302])
def test_private_probe_rejects_served_or_redirected_path(expected_site: Path, status: int) -> None:
    fetcher = MemoryFetcher(expected_site)
    fetcher.overrides["/src/nearmiss/private_paths.py"] = FetchResult(
        status,
        fetcher.not_found.body,
        fetcher.not_found.content_type,
    )
    with pytest.raises(LiveSiteVerificationError, match="did not match the reviewed 404"):
        _verify(expected_site, fetcher)


def test_guaranteed_missing_baseline_must_be_404(expected_site: Path) -> None:
    fetcher = MemoryFetcher(expected_site)
    fetcher.baseline_status = 200
    with pytest.raises(LiveSiteVerificationError, match="baseline returned HTTP 200"):
        _verify(expected_site, fetcher)


@pytest.mark.parametrize("path", ["/.nojekyll", "/CNAME"])
def test_host_control_must_remain_non_retrievable(expected_site: Path, path: str) -> None:
    fetcher = MemoryFetcher(expected_site)
    fetcher.overrides[path] = FetchResult(200, b"", "application/octet-stream")
    with pytest.raises(LiveSiteVerificationError, match="host-control"):
        _verify(expected_site, fetcher)


def test_share_query_and_network_failure_clear_success(expected_site: Path) -> None:
    fetcher = MemoryFetcher(expected_site)
    fetcher.share_status = 503
    with pytest.raises(LiveSiteVerificationError, match="localized share shell returned HTTP 503"):
        _verify(expected_site, fetcher)

    fetcher = MemoryFetcher(expected_site)
    fetcher.fail_prefix = "/web/i18n.js"
    with pytest.raises(LiveSiteVerificationError, match="simulated network failure"):
        _verify(expected_site, fetcher)


@pytest.mark.parametrize(
    "value",
    [
        "",
        "/absolute",
        "trailing/",
        "a//b",
        "a/./b",
        "a/../b",
        "../escape",
        "percent%2fescape",
        "percent%2e%2e",
        "back\\slash",
        "query?x=1",
        "fragment#x",
        "scheme:https://example.test",
        "control\nname",
        "café.json",
    ],
)
def test_manifest_path_rejects_traversal_and_url_ambiguity(value: str) -> None:
    with pytest.raises(LiveSiteVerificationError, match="manifest path"):
        live._manifest_path(value)


@pytest.mark.parametrize("value", [None, 1, True, [], {}])
def test_manifest_path_requires_string(value: object) -> None:
    with pytest.raises(LiveSiteVerificationError, match="must be a string"):
        live._manifest_path(value)


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (b"", "byte safety"),
        (b"[]", "object"),
        (b"{", "invalid JSON"),
        (b"\xff", "UTF-8"),
        (b'{"a":1,"a":2}', "duplicate"),
        (b'{"a":NaN}', "non-finite"),
    ],
)
def test_strict_json_rejects_ambiguous_payloads(payload: bytes, message: str) -> None:
    with pytest.raises(LiveSiteVerificationError, match=message):
        live._strict_json_object(payload, label="fixture", maximum_bytes=1024)


def test_strict_json_requires_exact_bytes() -> None:
    with pytest.raises(TypeError, match="payload must be bytes"):
        live._strict_json_object("{}", label="fixture", maximum_bytes=1024)  # type: ignore[arg-type]


def test_manifest_rejects_shape_types_digest_and_source() -> None:
    base: dict[str, Any] = {
        "schema_version": 1,
        "source_sha": SHA,
        "files": {"index.html": "0" * 64},
    }
    mutations: tuple[Callable[[dict[str, Any]], object], ...] = (
        lambda value: value.update(extra=True),
        lambda value: value.__setitem__("schema_version", 2),
        lambda value: value.__setitem__("source_sha", "0" * 40),
        lambda value: value.__setitem__("files", []),
        lambda value: value.__setitem__("files", {}),
        lambda value: value.__setitem__("files", {"index.html": "bad"}),
        lambda value: value.__setitem__("files", {"site-manifest.json": "0" * 64}),
    )
    for mutation in mutations:
        value = json.loads(json.dumps(base))
        mutation(value)
        payload = (json.dumps(value, sort_keys=True) + "\n").encode()
        with pytest.raises(LiveSiteVerificationError):
            live._manifest(payload, expected_sha=SHA, label="fixture manifest")


def test_expected_site_rejects_extra_missing_digest_and_symlink(
    expected_site: Path,
    tmp_path: Path,
) -> None:
    extra = tmp_path / "extra"
    shutil.copytree(expected_site, extra)
    (extra / "surprise.txt").write_text("not inventoried", encoding="utf-8")
    with pytest.raises(LiveSiteVerificationError, match="do not match its manifest"):
        live._expected_inventory(extra, expected_sha=SHA)

    missing = tmp_path / "missing"
    shutil.copytree(expected_site, missing)
    (missing / "web" / "us-coverage.js").unlink()
    with pytest.raises(LiveSiteVerificationError, match="do not match its manifest"):
        live._expected_inventory(missing, expected_sha=SHA)

    drift = tmp_path / "drift"
    shutil.copytree(expected_site, drift)
    (drift / "web" / "us-coverage.js").write_bytes(b"changed")
    with pytest.raises(LiveSiteVerificationError, match="does not match its manifest"):
        live._expected_inventory(drift, expected_sha=SHA)

    symlinked_file = tmp_path / "symlinked-file"
    shutil.copytree(expected_site, symlinked_file)
    target = symlinked_file / "target"
    target.write_text("target", encoding="utf-8")
    (symlinked_file / "web" / "us-coverage.js").unlink()
    (symlinked_file / "web" / "us-coverage.js").symlink_to(target)
    with pytest.raises(LiveSiteVerificationError, match="symlink"):
        live._expected_inventory(symlinked_file, expected_sha=SHA)


def test_expected_root_rejects_missing_file_and_symlink(tmp_path: Path) -> None:
    with pytest.raises(LiveSiteVerificationError, match="unavailable"):
        live._expected_inventory(tmp_path / "missing", expected_sha=SHA)
    root_file = tmp_path / "file"
    root_file.write_text("file", encoding="utf-8")
    with pytest.raises(LiveSiteVerificationError, match="directory"):
        live._expected_inventory(root_file, expected_sha=SHA)
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    link.symlink_to(real, target_is_directory=True)
    with pytest.raises(LiveSiteVerificationError, match="symlink"):
        live._expected_inventory(link, expected_sha=SHA)


def test_bounded_file_detects_change_during_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "file"
    path.write_bytes(b"reviewed")
    original = Path.read_bytes

    def shortened(value: Path) -> bytes:
        payload = original(value)
        return payload[:-1] if value == path else payload

    monkeypatch.setattr(Path, "read_bytes", shortened)
    with pytest.raises(LiveSiteVerificationError, match="changed while it was read"):
        live._bounded_file(path, maximum_bytes=1024, label="fixture")


def test_bounded_file_rejects_missing_directory_symlink_and_read_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(LiveSiteVerificationError, match="unavailable"):
        live._bounded_file(tmp_path / "missing", maximum_bytes=1024, label="fixture")
    with pytest.raises(LiveSiteVerificationError, match="regular file"):
        live._bounded_file(tmp_path, maximum_bytes=1024, label="fixture")
    target = tmp_path / "target"
    target.write_bytes(b"target")
    link = tmp_path / "link"
    link.symlink_to(target)
    with pytest.raises(LiveSiteVerificationError, match="symlink"):
        live._bounded_file(link, maximum_bytes=1024, label="fixture")

    def unreadable(_path: Path) -> bytes:
        raise OSError("simulated")

    monkeypatch.setattr(Path, "read_bytes", unreadable)
    with pytest.raises(LiveSiteVerificationError, match="could not be read"):
        live._bounded_file(target, maximum_bytes=1024, label="fixture")


def test_cache_target_and_deployment_contract_reject_drift() -> None:
    with pytest.raises(LiveSiteVerificationError, match="request path"):
        live._cache_target("relative", cache_token=CACHE_TOKEN)
    with pytest.raises(LiveSiteVerificationError, match="request path"):
        live._cache_target("/path?query", cache_token=CACHE_TOKEN)
    with pytest.raises(LiveSiteVerificationError, match="deployment record"):
        live._deployment(b"{}\n", expected_sha=SHA)


def test_valid_but_different_live_manifest_fails_exact_match(expected_site: Path) -> None:
    fetcher = MemoryFetcher(expected_site)
    value = json.loads((expected_site / "site-manifest.json").read_text(encoding="utf-8"))
    value["files"]["index.html"] = "0" * 64
    payload = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()
    fetcher.overrides["/site-manifest.json"] = FetchResult(200, payload, "application/json")
    with pytest.raises(LiveSiteVerificationError, match="exact reviewed build"):
        _verify(expected_site, fetcher)


def test_share_shell_200_body_must_match(expected_site: Path) -> None:
    fetcher = MemoryFetcher(expected_site)
    original_fetch = fetcher.fetch

    def changed_share(target: str, *, maximum_bytes: int) -> FetchResult:
        parsed = urlsplit(target)
        if parsed.path == "/web/us-coverage.html" and "year=" in parsed.query:
            return FetchResult(200, b"wrong shell", "text/html")
        return original_fetch(target, maximum_bytes=maximum_bytes)

    fetcher.fetch = changed_share  # type: ignore[method-assign]
    with pytest.raises(LiveSiteVerificationError, match="changed the reviewed HTML"):
        _verify(expected_site, fetcher)


@pytest.mark.parametrize("sha", ["", "A" * 40, "0" * 39, "0" * 41])
def test_verifier_rejects_invalid_sha(expected_site: Path, sha: str) -> None:
    with pytest.raises(LiveSiteVerificationError, match="source SHA"):
        verify_live_site(
            expected_site,
            expected_sha=sha,
            cache_token=CACHE_TOKEN,
            fetcher=MemoryFetcher(expected_site),
        )


@pytest.mark.parametrize("token", ["", "A" * 32, "0" * 31, "0" * 33])
def test_verifier_rejects_invalid_cache_token(expected_site: Path, token: str) -> None:
    with pytest.raises(LiveSiteVerificationError, match="cache token"):
        verify_live_site(
            expected_site,
            expected_sha=SHA,
            cache_token=token,
            fetcher=MemoryFetcher(expected_site),
        )


def test_production_fetcher_rejects_invalid_policy_and_target() -> None:
    with pytest.raises(ValueError, match="timeout"):
        ProductionHttpsFetcher(timeout_seconds=0)
    with pytest.raises(ValueError, match="deadline"):
        ProductionHttpsFetcher(deadline_seconds=10)
    fetcher = ProductionHttpsFetcher()
    for target in ("", "relative", "//other.test/path", "/path#fragment", "/bad\npath"):
        with pytest.raises(LiveSiteVerificationError, match="target"):
            fetcher.fetch(target, maximum_bytes=1024)
    with pytest.raises(LiveSiteVerificationError, match="byte limit"):
        fetcher.fetch("/path", maximum_bytes=-1)


def test_production_fetcher_rejects_nonpublic_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443))],
    )
    with pytest.raises(LiveSiteVerificationError, match="non-public"):
        ProductionHttpsFetcher().fetch("/path", maximum_bytes=1024)


class FakeHttpResponse:
    def __init__(
        self,
        body: bytes = b"reviewed",
        *,
        status: int = 200,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.body = body
        self.status = status
        self.headers = headers or {}

    def getheader(self, name: str) -> str | None:
        return self.headers.get(name)

    def read(self, _limit: int) -> bytes:
        return self.body


class FakeHttpsConnection:
    response: ClassVar[FakeHttpResponse] = FakeHttpResponse()
    request_error: ClassVar[BaseException | None] = None
    response_error: ClassVar[BaseException | None] = None
    instances: ClassVar[list[FakeHttpsConnection]] = []

    def __init__(self, host: str, *, timeout: float, context: object) -> None:
        self.host = host
        self.timeout = timeout
        self.context = context
        self.request_args: tuple[str, str, dict[str, str]] | None = None
        self.closed = False
        self.instances.append(self)

    def request(self, method: str, target: str, *, headers: dict[str, str]) -> None:
        if self.request_error is not None:
            raise self.request_error
        self.request_args = (method, target, headers)

    def getresponse(self) -> FakeHttpResponse:
        if self.response_error is not None:
            raise self.response_error
        return self.response

    def close(self) -> None:
        self.closed = True


def _install_fake_https(
    monkeypatch: pytest.MonkeyPatch,
    response: FakeHttpResponse,
) -> None:
    FakeHttpsConnection.response = response
    FakeHttpsConnection.request_error = None
    FakeHttpsConnection.response_error = None
    FakeHttpsConnection.instances = []
    monkeypatch.setattr(http.client, "HTTPSConnection", FakeHttpsConnection)
    monkeypatch.setattr(ssl, "create_default_context", lambda: object())
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("185.199.108.153", 443))
        ],
    )


def test_production_fetcher_enforces_host_headers_status_and_close(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_https(
        monkeypatch,
        FakeHttpResponse(
            b"reviewed",
            status=404,
            headers={"Content-Length": "8", "Content-Type": "text/plain"},
        ),
    )
    result = ProductionHttpsFetcher(timeout_seconds=5, deadline_seconds=30).fetch(
        "/private?verify=abc",
        maximum_bytes=32,
    )
    assert result == FetchResult(404, b"reviewed", "text/plain")
    connection = FakeHttpsConnection.instances[-1]
    assert connection.host == "nearmiss.chelseakr.com"
    assert connection.timeout <= 5
    assert connection.request_args is not None
    method, target, headers = connection.request_args
    assert (method, target) == ("GET", "/private?verify=abc")
    assert headers["Accept-Encoding"] == "identity"
    assert headers["Cache-Control"] == "no-cache, no-store, max-age=0"
    assert connection.closed is True


@pytest.mark.parametrize("encoding", ["gzip", "deflate", "br"])
def test_production_fetcher_rejects_compression(
    monkeypatch: pytest.MonkeyPatch,
    encoding: str,
) -> None:
    _install_fake_https(
        monkeypatch,
        FakeHttpResponse(headers={"Content-Encoding": encoding}),
    )
    with pytest.raises(LiveSiteVerificationError, match="unexpected encoding"):
        ProductionHttpsFetcher(deadline_seconds=30).fetch("/path", maximum_bytes=1024)
    assert FakeHttpsConnection.instances[-1].closed is True


@pytest.mark.parametrize("length", ["invalid", "-1", "1025"])
def test_production_fetcher_rejects_invalid_or_oversize_length(
    monkeypatch: pytest.MonkeyPatch,
    length: str,
) -> None:
    _install_fake_https(
        monkeypatch,
        FakeHttpResponse(headers={"Content-Length": length}),
    )
    message = "invalid length" if length == "invalid" else "byte safety"
    with pytest.raises(LiveSiteVerificationError, match=message):
        ProductionHttpsFetcher(deadline_seconds=30).fetch("/path", maximum_bytes=1024)


def test_production_fetcher_rejects_unannounced_oversize_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_https(monkeypatch, FakeHttpResponse(b"x" * 1025))
    with pytest.raises(LiveSiteVerificationError, match="byte safety"):
        ProductionHttpsFetcher(deadline_seconds=30).fetch("/path", maximum_bytes=1024)


@pytest.mark.parametrize("stage", ["request", "response"])
def test_production_fetcher_translates_http_and_socket_errors(
    monkeypatch: pytest.MonkeyPatch,
    stage: str,
) -> None:
    _install_fake_https(monkeypatch, FakeHttpResponse())
    if stage == "request":
        FakeHttpsConnection.request_error = OSError("socket failed")
    else:
        FakeHttpsConnection.response_error = http.client.HTTPException("HTTP failed")
    with pytest.raises(LiveSiteVerificationError, match="HTTPS request failed"):
        ProductionHttpsFetcher(deadline_seconds=30).fetch("/path", maximum_bytes=1024)
    assert FakeHttpsConnection.instances[-1].closed is True


def test_production_fetcher_rejects_dns_failure_empty_and_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fetcher = ProductionHttpsFetcher(deadline_seconds=30)
    monkeypatch.setattr(socket, "getaddrinfo", lambda *_args, **_kwargs: [])
    with pytest.raises(LiveSiteVerificationError, match="no addresses"):
        fetcher.fetch("/path", maximum_bytes=1024)

    def dns_error(*_args: object, **_kwargs: object) -> list[object]:
        raise OSError("DNS failed")

    monkeypatch.setattr(socket, "getaddrinfo", dns_error)
    with pytest.raises(LiveSiteVerificationError, match="DNS lookup failed"):
        fetcher.fetch("/path", maximum_bytes=1024)

    monkeypatch.setattr(time, "monotonic", lambda: fetcher._deadline + 1)
    with pytest.raises(LiveSiteVerificationError, match="total deadline"):
        fetcher.fetch("/path", maximum_bytes=1024)


def test_production_origin_configuration_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(live, "PRODUCTION_SITE_URL", "http://127.0.0.1")
    with pytest.raises(RuntimeError, match="canonical HTTPS origin"):
        ProductionHttpsFetcher()


def test_python_s_site_cli_imports_without_third_party_packages() -> None:
    result = subprocess.run(
        [sys.executable, "-S", str(ROOT / "tools" / "verify_live_site.py"), "--help"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "--expected-sha" in result.stdout


def test_workflow_is_read_only_pinned_bounded_and_main_scoped() -> None:
    workflow = (ROOT / ".github" / "workflows" / "live-integrity.yml").read_text(encoding="utf-8")
    assert "schedule:" in workflow and "workflow_dispatch:" in workflow
    assert "permissions:\n  contents: read" in workflow
    assert "pages: write" not in workflow
    assert "id-token: write" not in workflow
    assert "secrets." not in workflow
    assert "timeout-minutes: 10" in workflow
    assert "ref: main" in workflow
    assert "persist-credentials: false" in workflow
    assert "cancel-in-progress: false" in workflow
    assert "set +e" in workflow and 'remote_sha="$(git ls-remote' in workflow
    for line in workflow.splitlines():
        if "uses:" in line:
            reference = line.split("@", 1)[1].split()[0]
            assert len(reference) == 40 and all(
                character in "0123456789abcdef" for character in reference
            )


def test_retry_loop_uses_fresh_tokens_and_stops_after_success(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    tokens = iter(("1" * 32, "2" * 32))
    observed: list[str] = []
    monkeypatch.setattr(live_cli, "_checkout_sha", lambda: SHA)
    monkeypatch.setattr(live_cli, "build_site", lambda root, sha: root.mkdir(parents=True))
    monkeypatch.setattr(live_cli, "ProductionHttpsFetcher", lambda **_kwargs: object())
    monkeypatch.setattr("tools.verify_live_site.secrets.token_hex", lambda _size: next(tokens))
    monkeypatch.setattr("tools.verify_live_site.time.sleep", lambda _seconds: None)

    def verify(*_args: object, **kwargs: object) -> live.LiveSiteSummary:
        observed.append(str(kwargs["cache_token"]))
        if len(observed) == 1:
            raise LiveSiteVerificationError("not converged")
        return live.LiveSiteSummary(SHA, 46, 1, 2024, "reviewed", 9)

    monkeypatch.setattr(live_cli, "verify_live_site", verify)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "verify_live_site.py",
            "--expected-sha",
            SHA,
            "--attempts",
            "2",
            "--retry-seconds",
            "0",
            "--deadline-seconds",
            "30",
        ],
    )
    assert live_cli.main() == 0
    assert observed == ["1" * 32, "2" * 32]
    assert json.loads(capsys.readouterr().out)["source_sha"] == SHA
