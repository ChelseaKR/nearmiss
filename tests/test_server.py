"""The read-only server actually refuses the private raw store and dotfiles.

These are behavioral tests over a real HTTP server: they bind an ephemeral port,
serve a temp tree, and assert that public artifacts are reachable while the
private raw store and any dotfile path are answered with 403 — the defense in
depth behind hard rule #4 (a precise raw report must never be reachable over
HTTP, regardless of how the server is launched).
"""

from __future__ import annotations

import contextlib
import functools
import threading
import urllib.error
import urllib.request
from collections.abc import Iterator
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from nearmiss.server import _RestrictedHandler, is_blocked_path, serve


@contextlib.contextmanager
def _running_server(root: Path) -> Iterator[str]:
    """Serve ``root`` on an ephemeral port for the duration of the block."""
    handler = functools.partial(_RestrictedHandler, directory=str(root))
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    port = httpd.server_address[1]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)


def _make_root(tmp_path: Path) -> Path:
    """A served tree with one public artifact, one private raw report, one dotfile."""
    (tmp_path / "web").mkdir()
    (tmp_path / "web" / "index.html").write_text("<h1>public map</h1>", encoding="utf-8")
    (tmp_path / "data" / "raw" / "davis").mkdir(parents=True)
    (tmp_path / "data" / "raw" / "davis" / "reports.json").write_text("SECRET", encoding="utf-8")
    (tmp_path / ".env").write_text("TOKEN=should-never-be-served", encoding="utf-8")
    return tmp_path


def _fetch(url: str, method: str = "GET") -> tuple[int, bytes]:
    req = urllib.request.Request(url, method=method)
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return int(resp.status), resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


def test_public_served_but_private_store_and_dotfiles_forbidden(tmp_path: Path) -> None:
    root = _make_root(tmp_path)
    with _running_server(root) as base:
        public_status, public_body = _fetch(f"{base}/web/index.html")
        assert public_status == 200
        assert b"public map" in public_body

        # The private precise-report store is never reachable over HTTP.
        raw_status, raw_body = _fetch(f"{base}/data/raw/davis/reports.json")
        assert raw_status == 403
        assert b"SECRET" not in raw_body

        # Dotfiles (.env, .git, ...) are refused too.
        assert _fetch(f"{base}/.env")[0] == 403

        # HEAD enforces the same authorization as GET (no metadata leak either).
        assert _fetch(f"{base}/web/index.html", method="HEAD")[0] == 200
        assert _fetch(f"{base}/data/raw/davis/reports.json", method="HEAD")[0] == 403


def test_is_blocked_path_normalizes_and_bounds_prefixes() -> None:
    cases = [
        ("/data/raw/davis/reports.json", True),
        ("/data/raw", True),
        ("data/raw", True),  # leading slash optional
        ("/data/raw/davis/reports.json?cachebust=1", True),  # query string stripped
        ("/data/raw/davis/reports.json#frag", True),  # fragment stripped
        ("/.git/config", True),  # dotdir
        ("/web/nested/.hidden", True),  # dotfile anywhere in the path
        ("/data/rawish/ok.json", False),  # prefix must be a path boundary, not a substring
        ("/web/index.html", False),
        ("/data/published/davis.geojson", False),
    ]
    for path, blocked in cases:
        assert is_blocked_path(path) is blocked, path


def test_serve_wires_host_port_and_handles_keyboard_interrupt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """serve() must bind the requested host/port and shut down cleanly on Ctrl+C."""
    captured: dict[str, object] = {}

    class _FakeServer:
        def __init__(self, address: tuple[str, int], handler: object) -> None:
            captured["address"] = address
            captured["handler"] = handler

        def __enter__(self) -> _FakeServer:
            return self

        def __exit__(self, *exc: object) -> None:
            return None

        def serve_forever(self) -> None:
            raise KeyboardInterrupt

    monkeypatch.setattr("nearmiss.server.ThreadingHTTPServer", _FakeServer)
    # Returns cleanly (no exception) because serve() catches KeyboardInterrupt.
    serve(tmp_path, port=54321, host="127.0.0.1")

    assert captured["address"] == ("127.0.0.1", 54321)
    out = capsys.readouterr().out
    assert "serving" in out
    assert "stopped" in out
