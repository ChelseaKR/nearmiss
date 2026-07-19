"""Contributor data-rights tooling: export / delete "my reports" + retention.

This is the executable counterpart to the consent posture that is otherwise only
prose (``docs/DATA-CARD.md`` §consent, ``RR-15``). A contributor who kept the
pseudonymous ``reporter_token`` they submitted with can:

* **export** every report of theirs still held anywhere in the private stores
  (the raw store ``data/raw/``, the pending moderation queue, and the approved
  store), as one JSON-serializable bundle; and
* **delete** those reports — removed from all three stores *and* recorded as
  **tombstones** so a later re-import of the same upstream source cannot quietly
  resurrect a deleted report.

A third entry point, :func:`purge_expired`, enforces a **retention window**
(``Config.retention_days``): raw records whose event time is older than the
window are tombstone-deleted automatically, so the private store does not
accumulate precise reports forever.

Authentication model — be honest about it: **token possession is the only
auth.** There is no account, password, or identity check. Anyone holding a
contributor's ``reporter_token`` can export or delete that contributor's
reports. This is an intentional, documented trade-off for a self-service,
account-less tool (see ``docs/SUBMISSIONS.md``); a hosted deployment that needs
stronger assurance must add its own authentication in front of this library.

Tombstones are keyed by the **SHA-256 of the report id** (never the token, never
the raw id): the tombstone file records *that* an id was deleted without
retaining the report or any linkage back to a person. Because deletion changes
the raw inputs, the published artifacts legitimately change too — ``make
reproduce`` rebuilds from the surviving raw records and its committed outputs are
expected to move after a deletion. That is correct behaviour, not drift.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from .config import Config
from .errors import NearmissError
from .moderation import (
    APPROVED,
    PENDING,
    _approved_path,
    _load_queue,
    _save_queue,
    _write_json,
)
from .util import parse_ts

_TOMBSTONE_FILE = "tombstones.json"


def _tombstone_path(config: Config) -> Path:
    return config.raw_dir / _TOMBSTONE_FILE


def tombstone_key(report_id: object) -> str:
    """Stable tombstone key for a report id: its SHA-256 hex digest.

    Hashing keeps the tombstone file free of raw report ids (and therefore of any
    residual linkage) while remaining a deterministic, collision-resistant key a
    re-import can check against.
    """
    return hashlib.sha256(str(report_id).encode("utf-8")).hexdigest()


def load_tombstones(config: Config) -> set[str]:
    """Return the set of tombstoned id hashes (empty if the store is absent)."""
    path = _tombstone_path(config)
    if not path.is_file():
        return set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise NearmissError(f"could not read tombstone store {path}: {exc}") from exc
    rows = data.get("tombstones", []) if isinstance(data, dict) else data
    if not isinstance(rows, list):
        raise NearmissError(f"{path}: expected a list of tombstones")
    keys: set[str] = set()
    for row in rows:
        if isinstance(row, dict) and "id_sha256" in row:
            keys.add(str(row["id_sha256"]))
    return keys


def is_tombstoned(config: Config, report_id: object) -> bool:
    """True if ``report_id`` has been tombstone-deleted and must not be resurrected."""
    return tombstone_key(report_id) in load_tombstones(config)


def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _record_tombstones(config: Config, report_ids: Iterable[object], *, reason: str) -> int:
    """Merge new tombstones into the store. Returns the count newly added.

    Idempotent: re-tombstoning an already-deleted id does not duplicate it.
    """
    path = _tombstone_path(config)
    existing: list[dict[str, object]] = []
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise NearmissError(f"could not read tombstone store {path}: {exc}") from exc
        rows = data.get("tombstones", []) if isinstance(data, dict) else data
        if isinstance(rows, list):
            existing = [dict(r) for r in rows if isinstance(r, dict)]
    have = {str(r.get("id_sha256")) for r in existing}
    added = 0
    when = _now_iso()
    for rid in report_ids:
        key = tombstone_key(rid)
        if key in have:
            continue
        existing.append({"id_sha256": key, "deleted_at": when, "reason": reason})
        have.add(key)
        added += 1
    if added:
        # Deterministic on-disk order so the private store diffs cleanly.
        existing.sort(key=lambda r: str(r.get("id_sha256")))
        _write_json(path, {"tombstones": existing})
    return added


# --------------------------------------------------------------------------- #
# Raw store scanning
# --------------------------------------------------------------------------- #


def _raw_report_files(config: Config) -> list[Path]:
    """Every JSON report file in the raw store (the tombstone store excluded)."""
    raw_dir = config.raw_dir
    if not raw_dir.is_dir():
        return []
    return sorted(p for p in raw_dir.glob("*.json") if p.is_file() and p.name != _TOMBSTONE_FILE)


def _read_raw_reports(path: Path) -> list[dict[str, object]]:
    """Load report dicts from one raw file ({'reports': [...]} or a bare list)."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise NearmissError(f"could not read raw store {path}: {exc}") from exc
    rows = data.get("reports", []) if isinstance(data, dict) else data
    if not isinstance(rows, list):
        raise NearmissError(f"{path}: expected reports or a {{'reports': [...]}} object")
    return [dict(r) for r in rows if isinstance(r, dict)]


def _matches_token(report: dict[str, object], token: str) -> bool:
    return report.get("reporter_token") == token


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #


@dataclass
class ExportBundle:
    """Everything held for one contributor token, ready to serialize as JSON."""

    reporter_token: str
    exported_at: str
    raw: list[dict[str, object]]
    pending: list[dict[str, object]]
    approved: list[dict[str, object]]

    @property
    def count(self) -> int:
        return len(self.raw) + len(self.pending) + len(self.approved)

    def to_dict(self) -> dict[str, object]:
        return {
            "reporter_token": self.reporter_token,
            "exported_at": self.exported_at,
            "count": self.count,
            "auth": "token-possession-only",
            "raw": self.raw,
            "pending": self.pending,
            "approved": self.approved,
        }


def export_reports(config: Config, token: str) -> ExportBundle:
    """Collect every stored report whose ``reporter_token`` matches ``token``.

    Scans the raw store (all report files under ``data/raw/``), the pending
    moderation queue, and the approved store, and returns a JSON-serializable
    :class:`ExportBundle`. Read-only: nothing is modified. Token possession is
    the only authorization (see the module docstring).
    """
    if not token:
        raise NearmissError("a reporter_token is required to export reports")

    raw_hits: list[dict[str, object]] = []
    for path in _raw_report_files(config):
        raw_hits.extend(r for r in _read_raw_reports(path) if _matches_token(r, token))

    queue = _load_queue(config)
    pending = [
        dict(s.report) for s in queue if s.status == PENDING and _matches_token(s.report, token)
    ]

    approved_hits: list[dict[str, object]] = [
        dict(s.report) for s in queue if s.status == APPROVED and _matches_token(s.report, token)
    ]
    approved_hits.extend(r for r in _read_approved_store(config) if _matches_token(r, token))
    # De-duplicate the approved view by report id (a report can appear both in the
    # queue-as-approved and in the standalone approved store).
    approved = _dedupe_by_id(approved_hits)

    return ExportBundle(
        reporter_token=token,
        exported_at=_now_iso(),
        raw=raw_hits,
        pending=pending,
        approved=approved,
    )


def _dedupe_by_id(reports: list[dict[str, object]]) -> list[dict[str, object]]:
    seen: set[object] = set()
    out: list[dict[str, object]] = []
    for r in reports:
        rid = r.get("id")
        if rid in seen:
            continue
        seen.add(rid)
        out.append(r)
    return out


def _read_approved_store(config: Config) -> list[dict[str, object]]:
    path = _approved_path(config)
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise NearmissError(f"could not read approved store {path}: {exc}") from exc
    rows = data.get("reports", []) if isinstance(data, dict) else data
    return [dict(r) for r in rows] if isinstance(rows, list) else []


@dataclass
class DeletionResult:
    """What a delete removed, per store, plus the tombstones written."""

    reporter_token: str
    raw_removed: int
    pending_removed: int
    approved_removed: int
    tombstones_added: int

    @property
    def total_removed(self) -> int:
        return self.raw_removed + self.pending_removed + self.approved_removed


def _split_matches[T](
    items: Iterable[T],
    token: str,
    report_of: Callable[[T], dict[str, object]],
    deleted_ids: list[object],
) -> tuple[list[T], int]:
    """Partition ``items`` into (kept, removed_count), recording matched ids.

    ``report_of`` extracts the report dict a given item wraps (identity for raw/
    approved records, ``.report`` for queue :class:`Submission` entries) so the
    same matching logic serves all three stores in :func:`delete_reports`.
    """
    kept: list[T] = []
    removed = 0
    for item in items:
        report = report_of(item)
        if _matches_token(report, token):
            deleted_ids.append(report.get("id"))
            removed += 1
        else:
            kept.append(item)
    return kept, removed


def delete_reports(config: Config, token: str) -> DeletionResult:
    """Delete every stored report matching ``token`` and tombstone their ids.

    Removes matching records from the raw store, the pending moderation queue, and
    the approved store, then writes tombstones (keyed by SHA-256 of each report id)
    so a re-import of the same upstream source will not resurrect them.

    The approved store is otherwise append-only; deletion **compacts** it by
    rewriting the JSON via :func:`nearmiss.moderation._write_json`.

    Authorization is token possession only. Because this changes the raw inputs,
    the published artifacts legitimately change on the next ``make reproduce``.
    """
    if not token:
        raise NearmissError("a reporter_token is required to delete reports")

    deleted_ids: list[object] = []

    # 1. Raw store: rewrite each file without the matching reports.
    raw_removed = 0
    for path in _raw_report_files(config):
        reports = _read_raw_reports(path)
        kept, removed = _split_matches(reports, token, lambda r: r, deleted_ids)
        if removed:
            _write_json(path, {"reports": kept})
        raw_removed += removed

    # 2. Pending queue: drop matching submissions (any status), compacting the store.
    queue = _load_queue(config)
    kept_subs, pending_removed = _split_matches(queue, token, lambda s: s.report, deleted_ids)
    if pending_removed:
        _save_queue(config, kept_subs)

    # 3. Approved store: compact by rewriting the append-only JSON without matches.
    approved = _read_approved_store(config)
    kept_approved, approved_removed = _split_matches(approved, token, lambda r: r, deleted_ids)
    if approved_removed:
        _write_json(_approved_path(config), {"reports": kept_approved})

    added = _record_tombstones(config, deleted_ids, reason="contributor_delete")

    return DeletionResult(
        reporter_token=token,
        raw_removed=raw_removed,
        pending_removed=pending_removed,
        approved_removed=approved_removed,
        tombstones_added=added,
    )


@dataclass
class PurgeResult:
    """Outcome of a retention sweep over the raw store."""

    retention_days: int
    cutoff: str
    raw_removed: int
    tombstones_added: int


def purge_expired(config: Config, now: datetime | None = None) -> PurgeResult:
    """Tombstone-delete raw records older than the ``retention_days`` window.

    A record is expired when its ``occurred_at`` event time is strictly older than
    ``now - retention_days``. Expired records are removed from every raw report
    file and tombstoned (so they cannot be re-imported). Records without a
    parseable ``occurred_at`` are kept (fail-safe: never silently drop data whose
    age is unknown).

    ``retention_days <= 0`` disables retention and is a no-op.
    """
    days = config.retention_days
    reference = now or datetime.now(UTC)
    cutoff_epoch = reference.timestamp() - days * 86400
    cutoff_iso = datetime.fromtimestamp(cutoff_epoch, tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    if days <= 0:
        return PurgeResult(
            retention_days=days, cutoff=cutoff_iso, raw_removed=0, tombstones_added=0
        )

    expired_ids: list[object] = []
    raw_removed = 0
    for path in _raw_report_files(config):
        reports = _read_raw_reports(path)
        kept = []
        for r in reports:
            ts = parse_ts(str(r.get("occurred_at", "")))
            if ts is not None and ts < cutoff_epoch:
                expired_ids.append(r.get("id"))
                raw_removed += 1
            else:
                kept.append(r)
        if len(kept) != len(reports):
            _write_json(path, {"reports": kept})

    added = _record_tombstones(config, expired_ids, reason="retention_expired")
    return PurgeResult(
        retention_days=days,
        cutoff=cutoff_iso,
        raw_removed=raw_removed,
        tombstones_added=added,
    )
