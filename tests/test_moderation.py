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
    categorize_reason,
    list_submissions,
    moderation_stats,
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


# --------------------------------------------------------------------------- #
# transparency report (EXP-07): decided_at, reason taxonomy, latency, k-anon
# --------------------------------------------------------------------------- #
def _seed_queue(cfg: Config, rows: list[dict[str, object]]) -> None:
    """Write a raw queue.json so tests can inject frozen timestamps and legacy rows."""
    path = cfg.submissions_dir / "queue.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"submissions": rows}), encoding="utf-8")


def _floor(cfg: Config, n: int) -> Config:
    return dataclasses.replace(cfg, min_publish_n=n)


def test_decided_at_set_on_approve_and_reject(
    config: Config, tmp_path: Path, a_valid_report: dict[str, object]
) -> None:
    cfg = _mod_config(config, tmp_path)
    a = submit(cfg, _report(a_valid_report, id="11111111-1111-1111-1111-111111111111"))
    b = submit(cfg, _report(a_valid_report, id="22222222-2222-2222-2222-222222222222"))
    assert a.decided_at is None and b.decided_at is None

    approved = approve(cfg, a.submission_id)
    rejected = reject(cfg, b.submission_id, reason="obvious spam")
    assert approved.decided_at is not None
    assert rejected.decided_at is not None

    # The decision timestamp is persisted to the private store, not just in memory.
    reloaded = {s.submission_id: s for s in list_submissions(cfg)}
    assert reloaded[a.submission_id].decided_at is not None
    assert reloaded[b.submission_id].decided_at is not None


def test_legacy_rows_without_decided_at_load_and_are_excluded_from_latency(
    config: Config, tmp_path: Path
) -> None:
    cfg = _floor(_mod_config(config, tmp_path), 1)
    _seed_queue(
        cfg,
        [
            {
                "submission_id": "legacy-1",
                "status": "rejected",
                "received_at": "2026-01-01T00:00:00Z",
                "reason": "spam",
                "report": {},
            }
        ],
    )
    subs = list_submissions(cfg)
    assert subs[0].decided_at is None  # tolerated, no KeyError

    stats = moderation_stats(cfg)
    latency = stats["review_latency_hours"]
    assert isinstance(latency, dict)
    assert latency["n_decided"] == 0
    assert latency["median"] is None


def test_categorize_reason_buckets() -> None:
    assert categorize_reason("looks like a duplicate of an earlier report") == "duplicate"
    assert categorize_reason("obvious spam advertisement") == "spam"
    assert categorize_reason("the note contains an email address") == "identifier-leak"
    assert categorize_reason("coordinates are off the map / out of area") == "invalid-location"
    assert categorize_reason("totally unrelated, not a hazard") == "off-topic"
    assert categorize_reason("just did not seem right") == "other"
    assert categorize_reason("") == "other"


def test_reason_category_withheld_below_floor(config: Config, tmp_path: Path) -> None:
    cfg = _floor(_mod_config(config, tmp_path), 3)
    _seed_queue(
        cfg,
        [
            {
                "submission_id": f"r{i}",
                "status": "rejected",
                "received_at": "2026-01-01T00:00:00Z",
                "decided_at": "2026-01-01T01:00:00Z",
                "reason": "spam junk",
                "report": {},
            }
            for i in range(2)  # two spam rejections, below the floor of 3
        ],
    )
    stats = moderation_stats(cfg)
    reasons = stats["reason_categories"]
    assert isinstance(reasons, dict)
    # 0 < 2 < 3 -> withheld as null, and tallied under withheld_cells.
    assert reasons["spam"] is None
    assert isinstance(stats["withheld_cells"], int) and stats["withheld_cells"] >= 1


def test_median_latency_with_frozen_timestamps(config: Config, tmp_path: Path) -> None:
    cfg = _floor(_mod_config(config, tmp_path), 1)  # floor 1 so nothing is withheld
    _seed_queue(
        cfg,
        [
            {
                "submission_id": "a",
                "status": "approved",
                "received_at": "2026-01-01T00:00:00Z",
                "decided_at": "2026-01-01T01:00:00Z",  # 1 h
                "report": {},
            },
            {
                "submission_id": "b",
                "status": "rejected",
                "received_at": "2026-01-01T00:00:00Z",
                "decided_at": "2026-01-01T02:00:00Z",  # 2 h (median)
                "reason": "duplicate",
                "report": {},
            },
            {
                "submission_id": "c",
                "status": "rejected",
                "received_at": "2026-01-01T00:00:00Z",
                "decided_at": "2026-01-01T03:00:00Z",  # 3 h
                "reason": "invalid location",
                "report": {},
            },
        ],
    )
    stats = moderation_stats(cfg)
    latency = stats["review_latency_hours"]
    assert isinstance(latency, dict)
    assert latency["n_decided"] == 3
    assert latency["median"] == 2.0


def test_free_text_reason_never_appears_in_stats_output(config: Config, tmp_path: Path) -> None:
    cfg = _floor(_mod_config(config, tmp_path), 1)
    secret = "jane.doe@example.com plate ABC1234 lives at 5 Elm St"
    _seed_queue(
        cfg,
        [
            {
                "submission_id": f"r{i}",
                "status": "rejected",
                "received_at": "2026-01-01T00:00:00Z",
                "decided_at": "2026-01-01T01:00:00Z",
                "reason": f"{secret} — clearly spam",
                "report": {},
            }
            for i in range(3)
        ],
    )
    stats = moderation_stats(cfg)
    blob = json.dumps(stats)
    assert secret not in blob
    assert "jane.doe@example.com" not in blob
    # The rejection was still counted, only bucketed to a coarse category.
    reasons = stats["reason_categories"]
    assert isinstance(reasons, dict)
    assert reasons["spam"] == 3


def test_malformed_timestamp_and_null_reason_are_tolerated(config: Config, tmp_path: Path) -> None:
    cfg = _floor(_mod_config(config, tmp_path), 1)
    _seed_queue(
        cfg,
        [
            # Decided, but the received timestamp is junk -> excluded from latency.
            {
                "submission_id": "bad-ts",
                "status": "approved",
                "received_at": "not-a-timestamp",
                "decided_at": "2026-01-01T01:00:00Z",
                "report": {},
            },
            # Rejected with no reason at all -> buckets to "other", never crashes.
            {
                "submission_id": "no-reason",
                "status": "rejected",
                "received_at": "2026-01-01T00:00:00Z",
                "decided_at": "2026-01-01T05:00:00Z",
                "reason": None,
                "report": {},
            },
        ],
    )
    stats = moderation_stats(cfg)
    latency = stats["review_latency_hours"]
    reasons = stats["reason_categories"]
    assert isinstance(latency, dict) and isinstance(reasons, dict)
    # Only the well-formed decided row (5 h) is counted.
    assert latency["n_decided"] == 1
    assert latency["median"] == 5.0
    assert reasons["other"] == 1
