"""A tiny read-only server for the accessible map and its data view.

The server only ever reads static files over GET, and it refuses to serve the
PRIVATE raw store (``data/raw/``) or any dotfile, even when the served directory
is the repo root. This is a defense-in-depth guard for hard rule #4: a precise
raw report must never be reachable over HTTP, regardless of how the server is
launched.
"""

from __future__ import annotations

import functools
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path, PurePosixPath

# Path prefixes (relative to the served root) that must never be served.
_BLOCKED_PREFIXES = ("data/raw",)


def is_blocked_path(path: str) -> bool:
    """True if a request path must be refused (private raw store or any dotfile)."""
    rel = PurePosixPath(path.split("?", 1)[0].split("#", 1)[0].lstrip("/"))
    parts = rel.parts
    if any(part.startswith(".") for part in parts):
        return True
    joined = "/".join(parts)
    return any(joined == p or joined.startswith(p + "/") for p in _BLOCKED_PREFIXES)


class _RestrictedHandler(SimpleHTTPRequestHandler):
    """Serves static files but blocks the private raw store and dotfiles."""

    def do_GET(self) -> None:
        if is_blocked_path(self.path):
            self.send_error(403, "Forbidden: not a public artifact")
            return
        super().do_GET()

    def do_HEAD(self) -> None:
        if is_blocked_path(self.path):
            self.send_error(403, "Forbidden: not a public artifact")
            return
        super().do_HEAD()


def serve(directory: Path, port: int = 8000, host: str = "127.0.0.1") -> None:
    """Serve ``directory`` read-only (raw store and dotfiles blocked).

    Visit ``/web/index.html``. Even with ``--dir .`` (the repo root), requests
    under ``data/raw/`` and any dotfile path are refused with HTTP 403.
    """
    handler = functools.partial(_RestrictedHandler, directory=str(directory))
    with ThreadingHTTPServer((host, port), handler) as httpd:
        url = f"http://{host}:{port}/web/index.html"
        print(f"nearmiss: serving {directory} (read-only; data/raw blocked) at {url}")
        print("Press Ctrl+C to stop.")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nnearmiss: stopped.")
