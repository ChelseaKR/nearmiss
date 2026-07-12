"""End-to-end CLI contract: command dispatch, side effects, and exit codes.

``main(argv)`` is the product's operator surface. These tests drive it the way an
operator (or CI's ``make reproduce``) does, but always against a throwaway config
whose raw/published/pending stores live under a temp dir — never the repo's real
data/raw or data/published. They assert the things an exit code is supposed to
mean: 0 on success, 2 on a typed nearmiss error (with the problems printed).
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from nearmiss import moderation
from nearmiss.__main__ import main
from nearmiss.config import load_config

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "davis"


def _config(tmp_path: Path) -> Path:
    """A complete city config that reuses the committed davis fixtures for inputs
    but redirects every WRITE (raw store, published dir, moderation queue) into a
    temp dir, so CLI side effects never touch the repository."""
    cfg = tmp_path / "city.toml"
    cfg.write_text(
        "\n".join(
            [
                'city = "Davis"',
                'dataset_note = "Synthetic demonstration data — not real reports."',
                'exposure_unit = "bike trips (synthetic)"',
                f'streets = "{FIXTURES / "streets.geojson"}"',
                f'reports = "{FIXTURES / "reports.json"}"',
                f'exposure = "{FIXTURES / "exposure.json"}"',
                f'raw_dir = "{tmp_path / "raw"}"',
                f'out_dir = "{tmp_path / "out"}"',
                f'submissions_dir = "{tmp_path / "pending"}"',
                "ref_lat = 38.5449",
                "ref_lon = -121.7405",
                "",
                "[thresholds]",
                "snap_max_m = 25",
                "dedupe_window_s = 600",
                "dedupe_distance_m = 15",
                "small_n = 5",
                "min_publish_n = 3",
                "rate_per = 1000",
                "confidence_z = 1.96",
                "fdr_alpha = 0.05",
                "gi_band_m = 300",
                "kde_bandwidth_m = 150",
                "kde_grid = 20",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return cfg


# --------------------------------------------------------------------------- #
# parser-level behavior
# --------------------------------------------------------------------------- #
def test_version_command_prints_version(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["version"]) == 0
    assert capsys.readouterr().out.strip()  # a non-empty version string


def test_version_flag_exits_zero() -> None:
    with pytest.raises(SystemExit) as excinfo:
        main(["--version"])
    assert excinfo.value.code == 0


def test_no_subcommand_is_a_usage_error() -> None:
    with pytest.raises(SystemExit) as excinfo:
        main([])
    assert excinfo.value.code != 0  # argparse: required subcommand missing


# --------------------------------------------------------------------------- #
# intake
# --------------------------------------------------------------------------- #
def test_intake_success_writes_raw_store(tmp_path: Path) -> None:
    cfg = _config(tmp_path)
    assert main(["intake", "--config", str(cfg)]) == 0
    assert (tmp_path / "raw" / "reports.json").is_file()


def test_intake_validation_failure_returns_2_and_lists_problems(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    reports = json.loads((FIXTURES / "reports.json").read_text(encoding="utf-8"))
    bad = copy.deepcopy(reports["reports"][0])
    bad["id"] = "22222222-2222-4222-8222-222222222222"
    bad["hazard_type"] = "asteroid"
    src = tmp_path / "bad.json"
    src.write_text(json.dumps({"reports": [bad]}), encoding="utf-8")

    code = main(["intake", str(src), "--config", str(_config(tmp_path))])
    assert code == 2  # NearmissError -> exit code 2
    err = capsys.readouterr().err
    assert "error" in err
    assert "- " in err  # each problem printed as a bullet


# --------------------------------------------------------------------------- #
# read-only analysis commands
# --------------------------------------------------------------------------- #
def test_pipeline_dump_runs(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["pipeline", "--config", str(_config(tmp_path)), "--dump"]) == 0
    out = capsys.readouterr().out
    summary, _, dumped = out.partition("\n")
    assert "pipeline [Davis]" in summary
    assert isinstance(json.loads(dumped), list)  # the --dump JSON is parseable


def test_analyze_runs(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["analyze", "--config", str(_config(tmp_path))]) == 0
    assert "analyze [Davis]" in capsys.readouterr().out


# --------------------------------------------------------------------------- #
# artifact-producing commands (all write under tmp_path, never the repo)
# --------------------------------------------------------------------------- #
def test_publish_writes_geojson(tmp_path: Path) -> None:
    assert main(["publish", "--config", str(_config(tmp_path))]) == 0
    assert list((tmp_path / "out").glob("*.geojson"))


def test_brief_to_file(tmp_path: Path) -> None:
    out = tmp_path / "brief.md"
    assert main(["brief", "--config", str(_config(tmp_path)), "--out", str(out)]) == 0
    assert out.read_text(encoding="utf-8").strip()


def test_brief_to_stdout(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["brief", "--config", str(_config(tmp_path))]) == 0
    assert capsys.readouterr().out.strip()


def test_figures_to_out_dir(tmp_path: Path) -> None:
    figdir = tmp_path / "figs"
    assert main(["figures", "--config", str(_config(tmp_path)), "--out", str(figdir)]) == 0
    assert list(figdir.iterdir())


# --------------------------------------------------------------------------- #
# null calibration (EXP-01: "we attacked our own dataset")
# --------------------------------------------------------------------------- #
def test_analyze_calibrate_writes_calibration_json(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    caldir = tmp_path / "cal"
    code = main(
        [
            "analyze",
            "--config",
            str(_config(tmp_path)),
            "--calibrate",
            "--n-shuffles",
            "20",
            "--seed",
            "3",
            "--out",
            str(caldir),
        ]
    )
    assert code == 0
    [written] = list(caldir.glob("*.calibration.json"))
    payload = json.loads(written.read_text(encoding="utf-8"))
    assert payload["n_shuffles"] == 20
    assert payload["seed"] == 3
    assert payload["city"] == "Davis"
    assert "false_positive_rate" in payload
    assert "interpretation" in payload
    out = capsys.readouterr().out
    assert "calibrate [Davis]" in out


def test_analyze_without_calibrate_does_not_write_calibration_json(tmp_path: Path) -> None:
    caldir = tmp_path / "out"
    assert main(["analyze", "--config", str(_config(tmp_path))]) == 0
    assert not list(caldir.glob("*.calibration.json"))


def test_analyze_calibrate_defaults_to_out_dir(tmp_path: Path) -> None:
    cfg = _config(tmp_path)
    assert main(["analyze", "--config", str(cfg), "--calibrate", "--n-shuffles", "5"]) == 0
    assert list((tmp_path / "out").glob("*.calibration.json"))


def test_run_end_to_end(tmp_path: Path) -> None:
    out = tmp_path / "run-brief.md"
    assert main(["run", "--config", str(_config(tmp_path)), "--out", str(out)]) == 0
    assert (tmp_path / "raw" / "reports.json").is_file()
    assert list((tmp_path / "out").glob("*.geojson"))
    assert out.read_text(encoding="utf-8").strip()


def test_serve_dispatches_without_binding(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    called: dict[str, object] = {}

    def _fake_serve(directory: Path, port: int = 8000, host: str = "127.0.0.1") -> None:
        called["dir"] = directory
        called["port"] = port

    monkeypatch.setattr("nearmiss.__main__.serve", _fake_serve)
    assert main(["serve", "--dir", str(tmp_path), "--port", "0"]) == 0
    assert called == {"dir": tmp_path, "port": 0}


# --------------------------------------------------------------------------- #
# public-submission moderation lifecycle (the human-in-the-loop invariant)
# --------------------------------------------------------------------------- #
def _submit_one(tmp_path: Path, report: dict[str, object], name: str) -> None:
    src = tmp_path / name
    src.write_text(json.dumps(report), encoding="utf-8")  # a lone report, as the web form emits
    assert main(["submit", str(src), "--config", str(_config(tmp_path))]) == 0


def test_submit_then_moderate_lifecycle(
    tmp_path: Path, a_valid_report: dict[str, object], capsys: pytest.CaptureFixture[str]
) -> None:
    cfg = _config(tmp_path)

    # Two distinct submissions (different ids + locations so neither is a dup).
    first = copy.deepcopy(a_valid_report)
    second = copy.deepcopy(a_valid_report)
    second["id"] = "33333333-3333-4333-8333-333333333333"
    loc = second["location"]
    assert isinstance(loc, dict)
    loc["lat"] = 38.55
    _submit_one(tmp_path, first, "a.json")
    _submit_one(tmp_path, second, "b.json")

    # The parent --config precedes the moderate action subcommand.
    assert main(["moderate", "--config", str(cfg), "list"]) == 0
    assert "2 submission(s)" in capsys.readouterr().out

    pending = moderation.list_submissions(load_config(cfg), moderation.PENDING)
    assert len(pending) == 2
    approve_id, reject_id = pending[0].submission_id, pending[1].submission_id

    assert main(["moderate", "--config", str(cfg), "approve", approve_id]) == 0
    assert main(["moderate", "--config", str(cfg), "reject", reject_id, "--reason", "spam"]) == 0

    # A status filter narrows the listing.
    capsys.readouterr()
    assert main(["moderate", "--config", str(cfg), "list", "--status", "rejected"]) == 0
    assert "1 submission(s)" in capsys.readouterr().out

    # Only the approved report is exported into the pipeline-ready feed.
    export = tmp_path / "approved.json"
    assert main(["moderate", "--config", str(cfg), "export", str(export)]) == 0
    exported = json.loads(export.read_text(encoding="utf-8"))["reports"]
    assert [r["id"] for r in exported] == [first["id"]]


def test_moderate_list_empty_queue(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["moderate", "--config", str(_config(tmp_path)), "list"]) == 0
    assert "no submissions" in capsys.readouterr().out


def test_moderate_stats_summary_and_artifacts(
    tmp_path: Path, a_valid_report: dict[str, object], capsys: pytest.CaptureFixture[str]
) -> None:
    cfg = _config(tmp_path)
    _submit_one(tmp_path, a_valid_report, "a.json")
    capsys.readouterr()  # drop submit chatter

    # Human-readable summary to stdout.
    assert main(["moderate", "--config", str(cfg), "stats"]) == 0
    out = capsys.readouterr().out
    assert "by status" in out
    assert "reason categories" in out
    assert "median review latency" in out
    assert "withheld cells" in out

    # A JSON artifact (dated-path style) exposes the machine-readable report.
    art = tmp_path / "docs" / "audits" / "2026-07-02-moderation.json"
    assert main(["moderate", "--config", str(cfg), "stats", "--out", str(art)]) == 0
    data = json.loads(art.read_text(encoding="utf-8"))
    assert {
        "status_counts",
        "reason_categories",
        "flag_counts",
        "review_latency_hours",
        "withheld_cells",
        "min_publish_n",
        "total_submissions",
    } <= set(data)

    # A Markdown artifact for the audit trail.
    md = tmp_path / "docs" / "audits" / "2026-07-02-moderation.md"
    assert main(["moderate", "--config", str(cfg), "stats", "--out", str(md)]) == 0
    assert "# Moderation transparency report" in md.read_text(encoding="utf-8")


def test_moderate_stats_never_prints_free_text_reason(
    tmp_path: Path, a_valid_report: dict[str, object], capsys: pytest.CaptureFixture[str]
) -> None:
    cfg = _config(tmp_path)
    _submit_one(tmp_path, a_valid_report, "a.json")
    pending = moderation.list_submissions(load_config(cfg), moderation.PENDING)
    secret = "REJECT-NOTE-jane@example.com-plate-XYZ7788"
    assert (
        main(
            [
                "moderate",
                "--config",
                str(cfg),
                "reject",
                pending[0].submission_id,
                "--reason",
                f"{secret} spam",
            ]
        )
        == 0
    )
    capsys.readouterr()
    assert main(["moderate", "--config", str(cfg), "stats"]) == 0
    assert secret not in capsys.readouterr().out
