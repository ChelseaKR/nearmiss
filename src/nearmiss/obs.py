"""Structured JSON logging for the nearmiss read-only server.

The server emits one JSON object per line to a stream (stdout by default):

    {"ts":"2026-06-30T18:00:00+00:00","level":"info","msg":"request",
     "service":"nearmiss","request_id":"...","method":"GET",
     "path":"/web/index.html","status":200,"latency_ms":1.2}

This is the small, opt-in JSON logger the Observability Standard asks of a
Tier-C library/CLI. It is deliberately dependency-free (standard library only),
matching this project's minimal-runtime-dependency posture (see ``pyproject``:
the only runtime dependency is ``jsonschema``); OTel tracing/metrics are
out-of-scope for a local-only CLI with no long-lived network surface.

The one non-negotiable, non-tiered gate applies here: **no secret and no
protected path ever enters the log stream.** Redaction of protected request
paths (hard rule #4: the private ``data/raw/`` store and any dotfile) is the
server's responsibility (see ``server._redact_path``); this module never reads,
formats, or logs a file body.
"""

from __future__ import annotations

import json
import sys
import threading
from datetime import UTC, datetime
from typing import IO

SERVICE_NAME = "nearmiss"


class StructuredLogger:
    """Emit one compact JSON object per line to a text stream (thread-safe).

    A ``None`` stream means "the live ``sys.stdout``", resolved at write time so
    the logger cooperates with output capture (e.g. pytest's ``capsys``) that
    swaps ``sys.stdout`` after the logger is constructed.
    """

    def __init__(self, stream: IO[str] | None = None, *, service: str = SERVICE_NAME) -> None:
        self._stream = stream
        self._service = service
        self._lock = threading.Lock()

    def emit(self, level: str, msg: str, **fields: object) -> None:
        """Write one JSON record: ``ts``, ``level``, ``msg``, ``service``, then ``fields``.

        Callers must pass only non-sensitive, structured values as ``fields`` —
        never a secret, a file body, or an unredacted protected path.
        """
        record: dict[str, object] = {
            "ts": datetime.now(tz=UTC).isoformat(),
            "level": level,
            "msg": msg,
            "service": self._service,
        }
        record.update(fields)
        line = json.dumps(record, ensure_ascii=False, separators=(",", ":"))
        stream = self._stream if self._stream is not None else sys.stdout
        with self._lock:
            stream.write(line + "\n")
            stream.flush()

    def info(self, msg: str, **fields: object) -> None:
        """Emit an ``info``-level record."""
        self.emit("info", msg, **fields)

    def warning(self, msg: str, **fields: object) -> None:
        """Emit a ``warning``-level record."""
        self.emit("warning", msg, **fields)

    def error(self, msg: str, **fields: object) -> None:
        """Emit an ``error``-level record."""
        self.emit("error", msg, **fields)


_logger: StructuredLogger | None = None


def configure_logging(stream: IO[str] | None = None) -> StructuredLogger:
    """Install (or replace) the process-wide structured logger and return it.

    Idempotent: call with no argument for JSON to stdout, or pass a stream to
    capture output (used by the tests).
    """
    global _logger
    _logger = StructuredLogger(stream)
    return _logger


def get_logger() -> StructuredLogger:
    """Return the process-wide structured logger, creating a stdout one if unset."""
    if _logger is None:
        return configure_logging()
    return _logger
