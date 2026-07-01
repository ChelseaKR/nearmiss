"""Intake validates every report and lands accepted rows in the PRIVATE raw store.

The contract under test: intake validates each report against the schema, rejects
the whole batch with a listed reason for every bad report (never silently dropping
or accepting bad data), and only on a fully-valid batch writes the raw store
(hard rule #4 — that store is private and gitignored).
"""

from __future__ import annotations

import copy
import dataclasses
import json
from pathlib import Path

import pytest

from nearmiss.config import Config
from nearmiss.errors import ValidationError
from nearmiss.intake import run_intake


def _config_with_raw(config: Config, tmp_path: Path) -> Config:
    """The session config, but writing its raw store under a throwaway temp dir."""
    return dataclasses.replace(config, raw_dir=tmp_path / "raw")


def _write_reports(path: Path, reports: list[dict[str, object]]) -> Path:
    path.write_text(json.dumps({"reports": reports}), encoding="utf-8")
    return path


def test_valid_batch_is_written_to_the_raw_store(config: Config, tmp_path: Path) -> None:
    cfg = _config_with_raw(config, tmp_path)
    accepted = run_intake(cfg)  # source defaults to config.reports_path (59 valid reports)

    assert len(accepted) == 59
    raw_file = cfg.raw_dir / "reports.json"
    assert raw_file.is_file()  # raw_dir created on demand
    written = json.loads(raw_file.read_text(encoding="utf-8"))
    assert written["reports"] == accepted  # exactly the accepted rows, nothing added


def test_source_argument_overrides_configured_path(
    config: Config, tmp_path: Path, a_valid_report: dict[str, object]
) -> None:
    cfg = _config_with_raw(config, tmp_path)
    src = _write_reports(tmp_path / "alt.json", [a_valid_report])
    accepted = run_intake(cfg, source=src)
    assert len(accepted) == 1  # the override file, not the 59-report configured default


def test_one_bad_report_rejects_the_whole_batch(
    config: Config, tmp_path: Path, a_valid_report: dict[str, object]
) -> None:
    bad_id = "11111111-1111-4111-8111-111111111111"
    good = copy.deepcopy(a_valid_report)
    bad = copy.deepcopy(a_valid_report)
    bad["id"] = bad_id
    bad["hazard_type"] = "asteroid"  # not in the closed vocabulary
    src = _write_reports(tmp_path / "mixed.json", [good, bad])
    cfg = _config_with_raw(config, tmp_path)

    with pytest.raises(ValidationError) as excinfo:
        run_intake(cfg, source=src)

    err = excinfo.value
    assert "1 of 2 reports failed validation" in str(err)
    # The rejection is attributed to the offending report's id, not the good one.
    assert err.problems
    assert err.problems[0].startswith(bad_id)
    # Nothing is written when the batch is rejected (no partial/poisoned raw store).
    assert not (cfg.raw_dir / "reports.json").exists()


def test_report_without_id_is_labelled_no_id(config: Config, tmp_path: Path) -> None:
    # A report missing both 'id' and required fields is rejected and labelled
    # "<no id>" rather than crashing on the absent key.
    src = _write_reports(tmp_path / "noid.json", [{"mode": "cyclist"}])
    cfg = _config_with_raw(config, tmp_path)
    with pytest.raises(ValidationError) as excinfo:
        run_intake(cfg, source=src)
    assert excinfo.value.problems[0].startswith("<no id>:")
