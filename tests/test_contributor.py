"""Contributor data-rights tooling: export / delete-my-reports + retention.

The contract under test is the executable consent posture: a contributor holding
their pseudonymous ``reporter_token`` can export everything held for them and
delete it from every private store, and a deleted report can never be
resurrected by a re-import or a re-submission. Deletion changes the raw inputs,
so the published artifact legitimately changes with it.

Auth model under test is deliberately weak and honest: token possession is the
ONLY authorization. These tests assert the mechanics of that model, not a
stronger one.
"""

from __future__ import annotations

import copy
import dataclasses
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from nearmiss.config import Config
from nearmiss.contributor import (
    delete_reports,
    export_reports,
    is_tombstoned,
    load_tombstones,
    purge_expired,
    tombstone_key,
)
from nearmiss.errors import NearmissError
from nearmiss.intake import run_intake
from nearmiss.moderation import (
    _approved_path,
    _queue_path,
    approve,
    approved_reports,
    submit,
)
from nearmiss.publish import publish

TOKEN = "contrib-AAA-123"
OTHER = "someone-else-BBB-456"


def _cfg(config: Config, tmp_path: Path) -> Config:
    """A config whose every PRIVATE store is isolated under ``tmp_path``."""
    raw_dir = tmp_path / "raw"
    return dataclasses.replace(
        config,
        submissions_dir=tmp_path / "pending",
        raw_dir=raw_dir,
        out_dir=tmp_path / "published",
        # publish/analyze read reports_path; point it at the raw store so a
        # delete/purge that compacts the raw store is what a republish sees.
        reports_path=raw_dir / "reports.json",
    )


def _report(base: dict[str, object], idx: int, token: str | None) -> dict[str, object]:
    """A valid report cloned from the fixture with a distinct id, spaced event
    time (past the dedupe window), and an optional reporter_token."""
    r = copy.deepcopy(base)
    r["id"] = f"00000000-0000-4000-8000-0000000000{idx:02d}"
    # Space each report an hour apart so near-duplicate collapsing does not eat them.
    r["occurred_at"] = f"2026-06-10T{7 + idx:02d}:20:00-07:00"
    if token is not None:
        r["reporter_token"] = token
    return r


def _write_raw(cfg: Config, reports: list[dict[str, object]]) -> None:
    cfg.raw_dir.mkdir(parents=True, exist_ok=True)
    (cfg.raw_dir / "reports.json").write_text(
        json.dumps({"reports": reports}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _published_reports_in(cfg: Config) -> int:
    result = publish(cfg)
    meta = json.loads(result.metadata_path.read_text(encoding="utf-8"))
    return int(meta["summary"]["reports_in"])


# --------------------------------------------------------------------------- #
# Excellence-bar round trip: submit -> approve -> publish -> delete -> republish
# --------------------------------------------------------------------------- #


def test_roundtrip_delete_decrements_published_and_leaves_no_residue(
    config: Config, tmp_path: Path, a_valid_report: dict[str, object]
) -> None:
    cfg = _cfg(config, tmp_path)

    # submit: 3 reports carry the contributor's token, 2 belong to someone else.
    mine = [_report(a_valid_report, i, TOKEN) for i in range(1, 4)]
    theirs = [_report(a_valid_report, i, OTHER) for i in range(4, 6)]
    subs = [submit(cfg, r) for r in mine + theirs]

    # approve: every submission flows into the approved store.
    for s in subs:
        approve(cfg, s.submission_id)
    assert len(approved_reports(cfg)) == 5

    # publish: export the approved store as the raw/reports source, then publish.
    _write_raw(cfg, approved_reports(cfg))
    before = _published_reports_in(cfg)
    assert before == 5  # all five reports, spaced past the dedupe window

    # export ("my reports"): finds exactly the contributor's three, across stores.
    bundle = export_reports(cfg, TOKEN)
    assert bundle.count == 3 + 3  # 3 in the raw source + 3 in the approved store/queue
    assert {r["id"] for r in bundle.raw} == {r["id"] for r in mine}

    # delete: remove them from raw + queue + approved and tombstone their ids.
    result = delete_reports(cfg, TOKEN)
    assert result.raw_removed == 3
    assert result.pending_removed == 3  # the three approved-in-queue submissions
    assert result.approved_removed == 3
    assert result.tombstones_added == 3

    # republish: the published count legitimately decrements by the deleted three.
    after = _published_reports_in(cfg)
    assert after == before - 3 == 2

    # grep-style residue check: the token and every deleted id are gone from the
    # queue, the approved store, and the raw store.
    queue_text = _queue_path(cfg).read_text(encoding="utf-8")
    approved_text = _approved_path(cfg).read_text(encoding="utf-8")
    raw_text = (cfg.raw_dir / "reports.json").read_text(encoding="utf-8")
    for blob in (queue_text, approved_text, raw_text):
        assert TOKEN not in blob
        for r in mine:
            assert str(r["id"]) not in blob
    # The other contributor's data is untouched.
    assert OTHER in approved_text
    assert len(approved_reports(cfg)) == 2


# --------------------------------------------------------------------------- #
# export
# --------------------------------------------------------------------------- #


def test_export_gathers_from_raw_pending_and_approved(
    config: Config, tmp_path: Path, a_valid_report: dict[str, object]
) -> None:
    cfg = _cfg(config, tmp_path)
    # One report only in the raw store.
    _write_raw(cfg, [_report(a_valid_report, 1, TOKEN)])
    # One pending in the queue, one approved.
    pend = submit(cfg, _report(a_valid_report, 2, TOKEN))
    appr = submit(cfg, _report(a_valid_report, 3, TOKEN))
    approve(cfg, appr.submission_id)
    # An unrelated token must not appear.
    submit(cfg, _report(a_valid_report, 4, OTHER))

    bundle = export_reports(cfg, TOKEN)
    assert [r["id"] for r in bundle.raw] == ["00000000-0000-4000-8000-000000000001"]
    # id 2 is still pending; id 3 was approved so it moves to the approved bucket.
    assert [r["id"] for r in bundle.pending] == ["00000000-0000-4000-8000-000000000002"]
    assert [r["id"] for r in bundle.approved] == ["00000000-0000-4000-8000-000000000003"]
    # JSON-serializable and honest about its auth model.
    payload = json.loads(json.dumps(bundle.to_dict()))
    assert payload["auth"] == "token-possession-only"
    assert payload["count"] == bundle.count
    _ = pend  # (submitted; asserted via bundle.pending)


def test_export_empty_when_no_match(
    config: Config, tmp_path: Path, a_valid_report: dict[str, object]
) -> None:
    cfg = _cfg(config, tmp_path)
    _write_raw(cfg, [_report(a_valid_report, 1, OTHER)])
    bundle = export_reports(cfg, TOKEN)
    assert bundle.count == 0
    assert bundle.raw == [] and bundle.pending == [] and bundle.approved == []


def test_export_requires_a_token(config: Config, tmp_path: Path) -> None:
    cfg = _cfg(config, tmp_path)
    with pytest.raises(NearmissError):
        export_reports(cfg, "")


# --------------------------------------------------------------------------- #
# delete + tombstones
# --------------------------------------------------------------------------- #


def test_delete_writes_hashed_tombstones_and_is_idempotent(
    config: Config, tmp_path: Path, a_valid_report: dict[str, object]
) -> None:
    cfg = _cfg(config, tmp_path)
    r = _report(a_valid_report, 1, TOKEN)
    _write_raw(cfg, [r])

    result = delete_reports(cfg, TOKEN)
    assert result.raw_removed == 1
    assert result.tombstones_added == 1

    # Tombstone key is the SHA-256 of the id, and the raw id never appears in the store.
    tomb_file = cfg.raw_dir / "tombstones.json"
    tomb_text = tomb_file.read_text(encoding="utf-8")
    assert tombstone_key(r["id"]) in tomb_text
    assert str(r["id"]) not in tomb_text
    assert is_tombstoned(cfg, r["id"])
    assert load_tombstones(cfg) == {tombstone_key(r["id"])}

    # Deleting again is a no-op that adds no new tombstones.
    again = delete_reports(cfg, TOKEN)
    assert again.total_removed == 0
    assert again.tombstones_added == 0
    assert load_tombstones(cfg) == {tombstone_key(r["id"])}


def test_delete_requires_a_token(config: Config, tmp_path: Path) -> None:
    cfg = _cfg(config, tmp_path)
    with pytest.raises(NearmissError):
        delete_reports(cfg, "")


# --------------------------------------------------------------------------- #
# tombstone blocks re-import and re-submission
# --------------------------------------------------------------------------- #


def test_tombstone_blocks_reimport(
    config: Config, tmp_path: Path, a_valid_report: dict[str, object]
) -> None:
    cfg = _cfg(config, tmp_path)
    keep = _report(a_valid_report, 1, OTHER)
    gone = _report(a_valid_report, 2, TOKEN)

    # The upstream source that a re-import would read still contains both reports.
    upstream = tmp_path / "upstream.json"
    upstream.write_text(json.dumps({"reports": [keep, gone]}), encoding="utf-8")

    # First import lands both in the raw store; then the contributor deletes theirs.
    run_intake(cfg, upstream)
    delete_reports(cfg, TOKEN)

    # Re-importing the unchanged upstream source must NOT resurrect the deleted one.
    accepted = run_intake(cfg, upstream)
    ids = {r["id"] for r in accepted}
    assert gone["id"] not in ids
    assert keep["id"] in ids
    raw_text = (cfg.raw_dir / "reports.json").read_text(encoding="utf-8")
    assert str(gone["id"]) not in raw_text


def test_tombstone_blocks_resubmission(
    config: Config, tmp_path: Path, a_valid_report: dict[str, object]
) -> None:
    cfg = _cfg(config, tmp_path)
    r = _report(a_valid_report, 1, TOKEN)
    _write_raw(cfg, [r])
    delete_reports(cfg, TOKEN)
    # A moderation re-submission of the same id is refused, not resurrected.
    with pytest.raises(NearmissError):
        submit(cfg, r)


# --------------------------------------------------------------------------- #
# retention window
# --------------------------------------------------------------------------- #


def test_purge_expired_tombstone_deletes_old_raw_records(
    config: Config, tmp_path: Path, a_valid_report: dict[str, object]
) -> None:
    cfg = dataclasses.replace(_cfg(config, tmp_path), retention_days=30)
    old = copy.deepcopy(a_valid_report)
    old["id"] = "00000000-0000-4000-8000-0000000000aa"
    old["occurred_at"] = "2020-01-01T00:00:00Z"  # far outside a 30-day window
    recent = copy.deepcopy(a_valid_report)
    recent["id"] = "00000000-0000-4000-8000-0000000000bb"
    recent["occurred_at"] = "2026-07-01T00:00:00Z"  # one day before "now"
    _write_raw(cfg, [old, recent])

    now = datetime(2026, 7, 2, tzinfo=UTC)
    result = purge_expired(cfg, now=now)
    assert result.raw_removed == 1
    assert result.tombstones_added == 1
    assert is_tombstoned(cfg, old["id"])
    assert not is_tombstoned(cfg, recent["id"])

    raw_text = (cfg.raw_dir / "reports.json").read_text(encoding="utf-8")
    assert str(old["id"]) not in raw_text
    assert str(recent["id"]) in raw_text


def test_purge_disabled_when_retention_zero(
    config: Config, tmp_path: Path, a_valid_report: dict[str, object]
) -> None:
    cfg = _cfg(config, tmp_path)  # retention_days defaults to 0
    old = copy.deepcopy(a_valid_report)
    old["occurred_at"] = "2000-01-01T00:00:00Z"
    _write_raw(cfg, [old])
    result = purge_expired(cfg)
    assert result.raw_removed == 0
    assert result.tombstones_added == 0
    assert load_tombstones(cfg) == set()


def test_purge_keeps_records_with_unparseable_time(
    config: Config, tmp_path: Path, a_valid_report: dict[str, object]
) -> None:
    cfg = dataclasses.replace(_cfg(config, tmp_path), retention_days=1)
    bad = copy.deepcopy(a_valid_report)
    bad["id"] = "00000000-0000-4000-8000-0000000000cc"
    bad["occurred_at"] = "not-a-timestamp"
    _write_raw(cfg, [bad])
    result = purge_expired(cfg, now=datetime(2026, 7, 2, tzinfo=UTC))
    # Fail-safe: a record whose age is unknown is kept, never silently dropped.
    assert result.raw_removed == 0
    raw_text = (cfg.raw_dir / "reports.json").read_text(encoding="utf-8")
    assert str(bad["id"]) in raw_text
