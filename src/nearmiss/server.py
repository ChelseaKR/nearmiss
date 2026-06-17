"""A tiny read-only server for the accessible map and its data view.

The server only ever reads published artifacts and serves static files over GET;
there is no write path, no upload, and no always-on dependency. It is meant for
local preview and cheap static-friendly hosting.
"""

from __future__ import annotations

import functools
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


def serve(directory: Path, port: int = 8000, host: str = "127.0.0.1") -> None:
    """Serve ``directory`` (the repo root) read-only. Visit /web/index.html."""
    handler = functools.partial(SimpleHTTPRequestHandler, directory=str(directory))
    with ThreadingHTTPServer((host, port), handler) as httpd:
        url = f"http://{host}:{port}/web/index.html"
        print(f"nearmiss: serving {directory} (read-only) at {url}")
        print("Press Ctrl+C to stop.")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nnearmiss: stopped.")
