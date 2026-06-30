"""Public-submission moderation-queue tests.

The contract under test is the one that matters for trust: a submission is
validated at the boundary, lands PENDING in the private store, and **never**
reaches the dataset feed until a human approves it. Rejected and pending
submissions are never exported; abuse/identifier heuristics flag for review
without blocking or auto-approving.
"""

from __future__ import annotations

import copy
import dataclasses
import json
from pathlib import Path

import pytest

from nearmiss.config import Config
from nearmiss.engine import build_analysis
from nearmiss.errors import NearmissError, ValidationError
from nearmiss.moderation import (
    APPROVED,
    PENDING,
    approve,
    approved_reports,
    list_submissions,
    reject,
    submit,
)


def _mod_config(config: Config, tmp_path: Path) -> Config:
    """A config whose moderation store points at an isolated temp dir."""
    return dataclasses.replace(config, submissions_dir=tmp_path / "pending")


def _report(a_valid_report: dict[str, object], **over: object) -> dict[str, object]:
    r = copy.deepcopy(a_valid_report)
    r.update(over)
    return r


def test_submit_lands_pending_not_in_dataset(
    config: Config, tmp_path: Path, a_valid_report: dict[str, object]
) -> None:
    cfg = _mod_config(config, tmp_path)
    sub = submit(cfg, _report(a_valid_report))
    assert sub.status == PENDING
    # A pending submission is NOT in the moderated feed into the pipeline.
    assert approved_reports(cfg) == []
    assert len(list_submissions(cfg, PENDING)) == 1


def test_invalid_submission_is_rejected_at_the_boundary(config: Config, tmp_path: Path) -> None:
    cfg = _mod_config(config, tmp_path)
    with pytest.raises(ValidationError):
        submit(cfg, {"hazard_type": "not_a_real_type"})
    # Nothing was queued.
    assert list_submissions(cfg) == []


def test_only_approved_reports_are_exported(
    config: Config, tmp_path: Path, a_valid_report: dict[str, object]
) -> None:
    cfg = _mod_config(config, tmp_path)
    keep = submit(cfg, _report(a_valid_report, id="11111111-1111-1111-1111-111111111111"))
    drop = submit(cfg, _report(a_valid_report, id="22222222-2222-2222-2222-222222222222"))
    submit(cfg, _report(a_valid_report, id="33333333-3333-3333-3333-333333333333"))  # stays pending

    approve(cfg, keep.submission_id)
    reject(cfg, drop.submission_id, reason="spam")

    exported = approved_reports(cfg)
    ids = {r["id"] for r in exported}
    assert ids == {"11111111-1111-1111-1111-111111111111"}  # only the approved one


def test_reject_then_approve_is_refused(
    config: Config, tmp_path: Path, a_valid_report: dict[str, object]
) -> None:
    cfg = _mod_config(config, tmp_path)
    sub = submit(cfg, _report(a_valid_report))
    reject(cfg, sub.submission_id, reason="duplicate")
    with pytest.raises(NearmissError):
        approve(cfg, sub.submission_id)
    assert approved_reports(cfg) == []


def test_approve_is_idempotent(
    config: Config, tmp_path: Path, a_valid_report: dict[str, object]
) -> None:
    cfg = _mod_config(config, tmp_path)
    sub = submit(cfg, _report(a_valid_report))
    approve(cfg, sub.submission_id)
    approve(cfg, sub.submission_id)  # second approve must not double-count
    assert len(approved_reports(cfg)) == 1
    assert list_submissions(cfg, APPROVED)[0].submission_id == sub.submission_id


def test_identifier_heuristics_flag_for_review_without_blocking(
    config: Config, tmp_path: Path, a_valid_report: dict[str, object]
) -> None:
    cfg = _mod_config(config, tmp_path)
    sub = submit(
        cfg,
        _report(a_valid_report, note="driver was rude, plate ABC1234, email a@b.com"),
    )
    # Flagged, but still accepted as pending (review, not auto-drop).
    assert sub.status == PENDING
    assert "possible_email_in_note" in sub.flags
    assert "possible_plate_in_note" in sub.flags


def test_near_duplicate_is_flagged(
    config: Config, tmp_path: Path, a_valid_report: dict[str, object]
) -> None:
    cfg = _mod_config(config, tmp_path)
    submit(cfg, _report(a_valid_report, id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"))
    dup = _report(a_valid_report, id="bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")  # same loc/time/type
    sub = submit(cfg, dup)
    assert "possible_duplicate" in sub.flags


def test_queue_persists_to_the_private_store(
    config: Config, tmp_path: Path, a_valid_report: dict[str, object]
) -> None:
    cfg = _mod_config(config, tmp_path)
    submit(cfg, _report(a_valid_report))
    queue_file = cfg.submissions_dir / "queue.json"
    assert queue_file.is_file()
    # The store lives under the (gitignored) submissions dir, never under published.
    assert "pending" in str(cfg.submissions_dir)
    data = json.loads(queue_file.read_text(encoding="utf-8"))
    assert data["submissions"][0]["status"] == PENDING


def test_approved_feed_flows_through_publish_aggregation(
    config: Config, tmp_path: Path, a_valid_report: dict[str, object]
) -> None:
    # End-to-end: an approved submission, exported as a reports source, still
    # passes through the normal pipeline/publish boundary (no special path).
    cfg = _mod_config(config, tmp_path)
    sub = submit(cfg, _report(a_valid_report))
    approve(cfg, sub.submission_id)
    reports_src = tmp_path / "approved-source.json"
    reports_src.write_text(json.dumps({"reports": approved_reports(cfg)}), encoding="utf-8")
    run_cfg = dataclasses.replace(cfg, reports_path=reports_src)
    bundle = build_analysis(run_cfg)
    # The single approved report is below min_publish_n, so k-anonymity withholds
    # it from the public artifact. Every PUBLISHABLE segment has 0 or >= floor
    # reports; the lone approved report is not publishable on its own.
    published = [s for s in bundle.result.segments if s.publishable]
    assert all(s.report_count == 0 or s.report_count >= run_cfg.min_publish_n for s in published)
    assert any(
        0 < s.report_count < run_cfg.min_publish_n and not s.publishable
        for s in bundle.result.segments
    )
