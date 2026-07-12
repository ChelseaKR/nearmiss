"""Observability: structured JSON logs, /livez + /readyz, and log-stream safety.

These tests pin the Tier-C observability surface (OBSERVABILITY-STANDARD): the
server emits one JSON line per request with the expected fields, liveness is a
cheap 200, readiness is fail-closed (503 when the served data dir is gone), and
— the non-negotiable, non-tiered gate — no secret and no protected path (hard
rule #4: ``data/raw/`` + dotfiles) ever reaches the log stream, even on a
refused request. They reinforce, and never weaken, the 403-no-leak guard.
"""

from __future__ import annotations

import contextlib
import functools
import io
import json
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from nearmiss import obs
from nearmiss.server import _RestrictedHandler, check_readiness


@pytest.fixture(autouse=True)
def _reset_default_logger() -> Iterator[None]:
    """Keep the process-wide logger as JSON-to-stdout for every other test/module."""
    obs.configure_logging()
    yield
    obs.configure_logging()


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


def _wait_for_lines(buf: io.StringIO, count: int, timeout: float = 3.0) -> list[str]:
    """Poll ``buf`` until it holds ``count`` non-empty lines (log emit is async)."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        lines = [ln for ln in buf.getvalue().splitlines() if ln.strip()]
        if len(lines) >= count:
            return lines
        time.sleep(0.01)
    return [ln for ln in buf.getvalue().splitlines() if ln.strip()]


# --------------------------------------------------------------------------- #
# The structured logger itself
# --------------------------------------------------------------------------- #


def test_structured_logger_emits_one_json_object_per_line_with_levels() -> None:
    buf = io.StringIO()
    log = obs.StructuredLogger(buf)
    log.info("hello", a=1, b="two")
    log.warning("careful")
    log.error("boom", code=500)

    records = [json.loads(ln) for ln in buf.getvalue().splitlines()]
    assert [r["level"] for r in records] == ["info", "warning", "error"]
    assert all({"ts", "level", "msg", "service"} <= r.keys() for r in records)
    assert all(r["service"] == "nearmiss" for r in records)
    assert records[0]["msg"] == "hello"
    assert records[0]["a"] == 1
    assert records[0]["b"] == "two"
    assert records[2]["code"] == 500


def test_default_logger_writes_json_to_live_stdout(capsys: pytest.CaptureFixture[str]) -> None:
    obs.configure_logging()  # None stream -> resolve sys.stdout at write time
    obs.get_logger().info("startup", detail="ok")
    line = capsys.readouterr().out.strip().splitlines()[-1]
    record = json.loads(line)
    assert record["msg"] == "startup"
    assert record["detail"] == "ok"
    assert record["level"] == "info"


def test_get_logger_initializes_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(obs, "_logger", None)
    logger = obs.get_logger()
    assert isinstance(logger, obs.StructuredLogger)


# --------------------------------------------------------------------------- #
# Pipeline-stage telemetry: `nearmiss run` emits one JSON line per stage
# --------------------------------------------------------------------------- #

_FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "davis"


def _run_config(tmp_path: Path) -> Path:
    """A throwaway config reusing the davis fixtures but writing under tmp_path."""
    cfg = tmp_path / "city.toml"
    cfg.write_text(
        "\n".join(
            [
                'city = "Davis"',
                'dataset_note = "Synthetic demonstration data — not real reports."',
                f'streets = "{_FIXTURES / "streets.geojson"}"',
                f'reports = "{_FIXTURES / "reports.json"}"',
                f'exposure = "{_FIXTURES / "exposure.json"}"',
                f'raw_dir = "{tmp_path / "raw"}"',
                f'out_dir = "{tmp_path / "out"}"',
                f'submissions_dir = "{tmp_path / "pending"}"',
                "ref_lat = 38.5449",
                "ref_lon = -121.7405",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return cfg


def test_run_command_emits_one_structured_stage_log_per_pipeline_stage(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from nearmiss.__main__ import main

    obs.configure_logging()  # None stream -> live sys.stdout, which capsys captures
    assert main(["run", "--config", str(_run_config(tmp_path))]) == 0

    stage_records = []
    for line in capsys.readouterr().out.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue  # a human-readable print(), not a JSON log line
        record = json.loads(line)
        if record.get("msg") == "stage":
            stage_records.append(record)

    stages = [r["stage"] for r in stage_records]
    # Every timed pipeline stage produced exactly one structured line.
    assert stages == ["load", "pipeline", "analyze"]
    for record in stage_records:
        assert {"ts", "level", "msg", "service", "stage", "counts", "ms"} <= record.keys()
        assert record["level"] == "info"
        assert record["service"] == "nearmiss"
        assert isinstance(record["counts"], dict)
        assert isinstance(record["ms"], (int, float))
    # Counts are structured provenance, not raw report content.
    pipeline_counts = next(r["counts"] for r in stage_records if r["stage"] == "pipeline")
    assert "reports_in" in pipeline_counts


# --------------------------------------------------------------------------- #
# Readiness (pure function)
# --------------------------------------------------------------------------- #


def test_check_readiness_ok_and_fail_closed(tmp_path: Path) -> None:
    ok, checks = check_readiness(tmp_path)
    assert ok is True
    assert checks == {"data_dir": "ok"}

    not_ok, checks_bad = check_readiness(tmp_path / "does-not-exist")
    assert not_ok is False
    assert checks_bad == {"data_dir": "unavailable"}


# --------------------------------------------------------------------------- #
# Health endpoints over real HTTP
# --------------------------------------------------------------------------- #


def test_livez_is_a_cheap_200(tmp_path: Path) -> None:
    root = _make_root(tmp_path)
    with _running_server(root) as base:
        status, body = _fetch(f"{base}/livez")
        assert status == 200
        assert json.loads(body) == {"status": "ok"}
        # HEAD returns headers but no body, and stays 200.
        assert _fetch(f"{base}/livez", method="HEAD") == (200, b"")


def test_readyz_200_when_ready(tmp_path: Path) -> None:
    root = _make_root(tmp_path)
    with _running_server(root) as base:
        status, body = _fetch(f"{base}/readyz")
    assert status == 200
    data = json.loads(body)
    assert data["status"] == "ok"
    assert data["checks"]["data_dir"] == "ok"


def test_readyz_fails_closed_503_when_data_dir_missing(tmp_path: Path) -> None:
    served = tmp_path / "store"
    served.mkdir()
    with _running_server(served) as base:
        # Remove the served dir out from under the running server: the critical
        # dependency is now unavailable, so readiness must fail CLOSED (503).
        served.rmdir()
        status, body = _fetch(f"{base}/readyz")
    assert status == 503
    data = json.loads(body)
    assert data["status"] == "unavailable"
    assert data["checks"]["data_dir"] == "unavailable"


# --------------------------------------------------------------------------- #
# Request access log: JSON shape + hard-rule-#4 no-leak guard
# --------------------------------------------------------------------------- #


def test_request_log_is_json_with_expected_fields_and_no_protected_leak(tmp_path: Path) -> None:
    root = _make_root(tmp_path)
    buf = io.StringIO()
    obs.configure_logging(stream=buf)

    with _running_server(root) as base:
        assert _fetch(f"{base}/web/index.html")[0] == 200
        # The 403-no-leak guard still holds on the wire (reinforced, not weakened).
        raw_status, raw_body = _fetch(f"{base}/data/raw/davis/reports.json")
        assert raw_status == 403
        assert b"SECRET" not in raw_body
        assert _fetch(f"{base}/.env")[0] == 403
        # A missing public file is a normal 404 (still logged, not blocked).
        assert _fetch(f"{base}/web/missing.html")[0] == 404
        lines = _wait_for_lines(buf, count=4)

    records = [json.loads(ln) for ln in lines]
    for record in records:
        for field in (
            "ts",
            "level",
            "msg",
            "service",
            "request_id",
            "method",
            "path",
            "status",
            "latency_ms",
        ):
            assert field in record, f"missing {field} in {record}"
        assert record["msg"] == "request"
        assert isinstance(record["latency_ms"], float)

    by_path: dict[str, list[dict[str, object]]] = {}
    for record in records:
        by_path.setdefault(str(record["path"]), []).append(record)

    # The public artifact is logged with its real, non-sensitive path.
    assert by_path["/web/index.html"][0]["status"] == 200
    assert by_path["/web/missing.html"][0]["status"] == 404
    # Both refused requests collapse to the redaction token — never their path.
    assert len(by_path["<blocked>"]) == 2
    assert all(r["status"] == 403 for r in by_path["<blocked>"])

    # The load-bearing gate: NOTHING protected reaches the log stream.
    blob = buf.getvalue()
    assert "data/raw" not in blob
    assert "reports.json" not in blob
    assert "SECRET" not in blob
    assert "TOKEN" not in blob
    assert ".env" not in blob
