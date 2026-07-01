"""A tiny read-only server for the accessible map and its data view.

The server only ever reads static files over GET, and it refuses to serve the
PRIVATE raw store (``data/raw/``) or any dotfile, even when the served directory
is the repo root. This is a defense-in-depth guard for hard rule #4: a precise
raw report must never be reachable over HTTP, regardless of how the server is
launched.

Observability (Tier C per OBSERVABILITY-STANDARD): the server emits one
structured JSON line per request (method, redacted path, status, latency,
request_id) via :mod:`nearmiss.obs`, and exposes Kubernetes-style ``/livez``
(liveness) and ``/readyz`` (readiness — fail-closed 503 if the served data dir
is unavailable) probes. The stdlib access log is suppressed because it would
otherwise write the *raw* request path — including protected ``data/raw/`` and
dotfile paths — to stderr; the structured line logs a redacted path instead, so
a protected path never enters the log stream even on a refused request.
"""

from __future__ import annotations

import functools
import json
import time
import uuid
from collections.abc import Mapping
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path, PurePosixPath

from .obs import get_logger

# Path prefixes (relative to the served root) that must never be served.
_BLOCKED_PREFIXES = ("data/raw",)

# Unauthenticated health probes: routed directly, never file-served, and
# excluded from the access log (Kubernetes probe contract).
_HEALTH_PATHS = ("/livez", "/readyz")


def is_blocked_path(path: str) -> bool:
    """True if a request path must be refused (private raw store or any dotfile)."""
    rel = PurePosixPath(path.split("?", 1)[0].split("#", 1)[0].lstrip("/"))
    parts = rel.parts
    if any(part.startswith(".") for part in parts):
        return True
    joined = "/".join(parts)
    return any(joined == p or joined.startswith(p + "/") for p in _BLOCKED_PREFIXES)


def _clean_path(path: str) -> str:
    """The path portion of a request target, with any query string and fragment removed."""
    return path.split("?", 1)[0].split("#", 1)[0]


def _redact_path(path: str) -> str:
    """A log-safe rendering of a request path.

    Protected paths (the private raw store or any dotfile — hard rule #4) never
    reach the log stream: they collapse to the fixed token ``"<blocked>"``. This
    keeps a precise-report path (e.g. ``data/raw/...``) or a dotfile name out of
    the logs even on a refused request. Query strings and fragments are dropped
    for all paths so a value smuggled in a query is never logged either.
    """
    if is_blocked_path(path):
        return "<blocked>"
    return _clean_path(path)


def check_readiness(directory: str | Path) -> tuple[bool, dict[str, str]]:
    """Readiness of the served static store — the server's one hard dependency.

    Fail-closed: if the served directory is missing or is not a directory, the
    server is NOT ready and ``/readyz`` returns 503. It never optimistically
    reports 200 when the dependency is unavailable.
    """
    ok = Path(directory).is_dir()
    return ok, {"data_dir": "ok" if ok else "unavailable"}


class _RestrictedHandler(SimpleHTTPRequestHandler):
    """Serves static files but blocks the private raw store and dotfiles.

    Adds ``/livez`` + ``/readyz`` probes and one structured JSON access-log line
    per (non-health) request. The stdlib access log is suppressed (see
    :meth:`log_message`) so raw request paths never leak to stderr.
    """

    # Captured by the send_response override so the access-log line reports the
    # final status of a request that SimpleHTTPRequestHandler resolves internally.
    _status: int = 0

    def do_GET(self) -> None:
        self._dispatch("GET")

    def do_HEAD(self) -> None:
        self._dispatch("HEAD")

    def _dispatch(self, method: str) -> None:
        clean = _clean_path(self.path)
        if clean in _HEALTH_PATHS:
            # Health probes are unauthenticated and excluded from the access log.
            self._health(clean, write_body=method == "GET")
            return

        request_id = uuid.uuid4().hex
        start = time.perf_counter()
        self._status = 0
        if is_blocked_path(self.path):
            # Hard rule #4 guard, preserved exactly: 403, no body/metadata leak.
            self.send_error(403, "Forbidden: not a public artifact")
        elif method == "HEAD":
            super().do_HEAD()
        else:
            super().do_GET()

        latency_ms = round((time.perf_counter() - start) * 1000, 3)
        get_logger().info(
            "request",
            request_id=request_id,
            method=method,
            path=_redact_path(self.path),  # protected paths -> "<blocked>"
            status=self._status,
            latency_ms=latency_ms,
        )

    def _health(self, path: str, *, write_body: bool) -> None:
        """Serve ``/livez`` (cheap, always 200) or ``/readyz`` (dependency-checked)."""
        if path == "/livez":
            # Liveness: the process is up and dispatching. No dependency calls.
            self._send_json(200, {"status": "ok"}, write_body=write_body)
            return
        ready, checks = check_readiness(self.directory)
        status = 200 if ready else 503
        body = {"status": "ok" if ready else "unavailable", "checks": checks}
        self._send_json(status, body, write_body=write_body)

    def _send_json(self, status: int, body: Mapping[str, object], *, write_body: bool) -> None:
        payload = json.dumps(body, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        if write_body:  # a HEAD request gets the headers but no body
            self.wfile.write(payload)

    def send_response(self, code: int, message: str | None = None) -> None:
        # Single choke point for the final status of every response path (served
        # file, 403, 404, JSON health), captured for the structured access log.
        self._status = code
        super().send_response(code, message)

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002 (stdlib override name)
        """Silence the stdlib access log; it would write raw request paths to stderr."""


def serve(directory: Path, port: int = 8000, host: str = "127.0.0.1") -> None:
    """Serve ``directory`` read-only (raw store and dotfiles blocked).

    Visit ``/web/index.html``. Even with ``--dir .`` (the repo root), requests
    under ``data/raw/`` and any dotfile path are refused with HTTP 403. Liveness
    and readiness are at ``/livez`` and ``/readyz``.
    """
    logger = get_logger()
    handler = functools.partial(_RestrictedHandler, directory=str(directory))
    with ThreadingHTTPServer((host, port), handler) as httpd:
        url = f"http://{host}:{port}/web/index.html"
        logger.info(
            "serving",
            directory=str(directory),
            url=url,
            host=host,
            port=port,
            note="read-only; private raw store and dotfiles blocked (HTTP 403)",
        )
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            logger.info("stopped")
