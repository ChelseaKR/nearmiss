"""Public-submission moderation queue.

This is the server-side counterpart to the public submission form
(``web/submit.html``): the path a crowdsourced near-miss takes from "someone on
the curb pressed submit" to "part of the dataset". The design is in
``docs/INTAKE-AND-ABUSE.md``; this module implements the core of it — a
**moderation queue** with an explicit pending → approved/rejected lifecycle.

The hard invariant: **a submission never reaches the dataset until a human
approves it.** Submissions land *pending* in a PRIVATE store
(``data/pending/``, gitignored like ``data/raw/`` — hard rule #4), are validated
against the same ``report.schema.json`` contract as every other report, and only
``approve`` moves a report into the approved store that the pipeline consumes.
Everything else (rates, k-anonymity, the publish boundary) is unchanged: an
approved report still flows raw → pipeline → ``publish.py`` (aggregate, withhold
low-count) before anything is public.

Abuse defenses here are a small, **testable** subset of the full B-series in the
design doc: schema validation, near-duplicate detection, and light
identifier-leak heuristics that *flag for review* (never auto-publish, never
silently drop). The expensive controls (rate limiting, proof-of-work) belong at
the network edge and are out of scope for this library module.
"""

from __future__ import annotations

import json
import re
import statistics
import uuid
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from .config import Config
from .errors import NearmissError, ValidationError
from .validation import validate_report

# Submission lifecycle states. A submission is born ``pending``; a human moves it.
Status = str  # one of: "pending", "approved", "rejected"
PENDING = "pending"
APPROVED = "approved"
REJECTED = "rejected"

_QUEUE_FILE = "queue.json"
_APPROVED_FILE = "approved-reports.json"

# Light identifier-leak heuristics. These do NOT block — they raise a flag so a
# moderator looks before approving (the note field is asked to omit identifiers).
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_PHONE_RE = re.compile(r"\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b")
# A loose US/Canada plate-ish token: 5–8 chars mixing letters and digits.
_PLATE_RE = re.compile(r"\b(?=[A-Z0-9]{5,8}\b)(?=[A-Z0-9]*[A-Z])(?=[A-Z0-9]*\d)[A-Z0-9]{5,8}\b")


@dataclass
class Submission:
    """One public submission plus its moderation state. ``report`` stays private."""

    submission_id: str
    status: Status
    received_at: str  # ISO-8601 UTC, submission time (NOT the event time)
    report: dict[str, object]
    flags: list[str] = field(default_factory=list)
    reason: str | None = None  # set on reject (or an approver note)
    decided_at: str | None = None  # ISO-8601 UTC, set when a human approves/rejects

    def to_dict(self) -> dict[str, object]:
        return {
            "submission_id": self.submission_id,
            "status": self.status,
            "received_at": self.received_at,
            "decided_at": self.decided_at,
            "flags": list(self.flags),
            "reason": self.reason,
            "report": self.report,
        }

    @staticmethod
    def from_dict(d: dict[str, object]) -> Submission:
        report = d.get("report")
        raw_flags = d.get("flags")
        flags = [str(f) for f in raw_flags] if isinstance(raw_flags, list) else []
        # ``decided_at`` is a later addition; legacy queue.json rows omit it.
        return Submission(
            submission_id=str(d["submission_id"]),
            status=str(d.get("status", PENDING)),
            received_at=str(d.get("received_at", "")),
            report=dict(report) if isinstance(report, dict) else {},
            flags=flags,
            reason=(str(d["reason"]) if d.get("reason") is not None else None),
            decided_at=(str(d["decided_at"]) if d.get("decided_at") is not None else None),
        )


def _queue_path(config: Config) -> Path:
    return config.submissions_dir / _QUEUE_FILE


def _approved_path(config: Config) -> Path:
    return config.submissions_dir / _APPROVED_FILE


def _load_queue(config: Config) -> list[Submission]:
    path = _queue_path(config)
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise NearmissError(f"could not read moderation queue {path}: {exc}") from exc
    rows = data.get("submissions", []) if isinstance(data, dict) else data
    if not isinstance(rows, list):
        raise NearmissError(f"{path}: expected a list of submissions")
    return [Submission.from_dict(dict(r)) for r in rows]


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _save_queue(config: Config, submissions: Iterable[Submission]) -> None:
    _write_json(_queue_path(config), {"submissions": [s.to_dict() for s in submissions]})


def _coarse_key(report: dict[str, object]) -> tuple[object, ...]:
    """A near-duplicate key: coarse location + hazard type + event hour."""
    loc = report.get("location")
    lat = lon = None
    if isinstance(loc, dict):
        try:
            lat = round(float(loc.get("lat", 0.0)), 4)  # ~11 m
            lon = round(float(loc.get("lon", 0.0)), 4)
        except (TypeError, ValueError):
            lat = lon = None
    occurred = str(report.get("occurred_at", ""))[:13]  # to the hour
    return (lat, lon, report.get("address"), report.get("hazard_type"), occurred)


def _detect_flags(report: dict[str, object], existing: list[Submission]) -> list[str]:
    """Compute review flags. These surface a submission for a closer look; they
    never block submission or auto-approve it."""
    flags: list[str] = []
    note = report.get("note")
    if isinstance(note, str) and note:
        if _EMAIL_RE.search(note):
            flags.append("possible_email_in_note")
        if _PHONE_RE.search(note):
            flags.append("possible_phone_in_note")
        if _PLATE_RE.search(note.upper()):
            flags.append("possible_plate_in_note")
    key = _coarse_key(report)
    if any(s.status != REJECTED and _coarse_key(s.report) == key for s in existing):
        flags.append("possible_duplicate")
    return flags


def submit(config: Config, report: dict[str, object]) -> Submission:
    """Validate and enqueue a public submission as PENDING. Never auto-approves.

    Raises :class:`ValidationError` (listing every problem) if the report does
    not satisfy ``report.schema.json`` — a malformed or malicious submission is
    rejected at this boundary, exactly as CLI/file intake is.
    """
    problems = validate_report(report)
    if problems:
        raise ValidationError(
            f"submission failed validation ({len(problems)} problem(s))", problems
        )
    queue = _load_queue(config)
    flags = _detect_flags(report, queue)
    submission = Submission(
        submission_id=str(uuid.uuid4()),
        status=PENDING,
        received_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        report=dict(report),
        flags=flags,
    )
    queue.append(submission)
    _save_queue(config, queue)
    return submission


def list_submissions(config: Config, status: Status | None = None) -> list[Submission]:
    """List queued submissions, optionally filtered by status."""
    queue = _load_queue(config)
    return [s for s in queue if status is None or s.status == status]


def _find(queue: list[Submission], submission_id: str) -> Submission:
    for s in queue:
        if s.submission_id == submission_id:
            return s
    raise NearmissError(f"no submission with id {submission_id!r} in the moderation queue")


def approve(config: Config, submission_id: str, note: str | None = None) -> Submission:
    """Approve a pending submission: mark approved and append it to the approved
    reports store the pipeline can consume. Idempotent for already-approved ids."""
    queue = _load_queue(config)
    sub = _find(queue, submission_id)
    if sub.status == APPROVED:
        return sub
    if sub.status == REJECTED:
        raise NearmissError(
            f"submission {submission_id!r} was rejected; it cannot be approved without resubmission"
        )
    sub.status = APPROVED
    sub.reason = note
    sub.decided_at = datetime.now(UTC).isoformat()
    _save_queue(config, queue)
    _append_approved(config, sub.report)
    return sub


def reject(config: Config, submission_id: str, reason: str) -> Submission:
    """Reject a submission with a recorded reason. The report never enters the
    approved store."""
    queue = _load_queue(config)
    sub = _find(queue, submission_id)
    sub.status = REJECTED
    sub.reason = reason
    sub.decided_at = datetime.now(UTC).isoformat()
    _save_queue(config, queue)
    return sub


def _append_approved(config: Config, report: dict[str, object]) -> None:
    path = _approved_path(config)
    reports: list[dict[str, object]] = []
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise NearmissError(f"could not read approved store {path}: {exc}") from exc
        existing = data.get("reports", []) if isinstance(data, dict) else data
        if isinstance(existing, list):
            reports = [dict(r) for r in existing]
    # De-duplicate by report id so re-approving never double-counts.
    rid = report.get("id")
    if not any(r.get("id") == rid for r in reports):
        reports.append(dict(report))
    _write_json(path, {"reports": reports})


def approved_reports(config: Config) -> list[dict[str, object]]:
    """Return the approved reports (the moderated feed into the pipeline).

    This is the ONLY path by which a public submission reaches the dataset:
    pending and rejected submissions are never returned here.
    """
    path = _approved_path(config)
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise NearmissError(f"could not read approved store {path}: {exc}") from exc
    rows = data.get("reports", []) if isinstance(data, dict) else data
    return [dict(r) for r in rows] if isinstance(rows, list) else []


# --------------------------------------------------------------------------- #
# Transparency reporting (EXP-07)
#
# A moderator's rejection ``reason`` is free text and MAY contain identifying or
# sensitive detail, so it is NEVER emitted verbatim in the public transparency
# report. Instead we bucket it into a tiny fixed taxonomy and only ever publish
# the coarse category and a count — and even the count is withheld when the cell
# is smaller than the k-anonymity floor (``config.min_publish_n``), matching the
# low-count withholding that ``publish.py`` applies to the map data.
# --------------------------------------------------------------------------- #

# Ordered so the FIRST matching bucket wins; keywords are matched case-folded.
_REASON_TAXONOMY: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("duplicate", ("duplicate", "dupe", "already reported", "already submitted", "repost")),
    ("spam", ("spam", "advert", "advertis", "junk", "bot", "gibberish", "test submission")),
    (
        "identifier-leak",
        ("identif", "personal", "pii", "email", "phone", "plate", "license", "name of", "doxx"),
    ),
    (
        "invalid-location",
        ("location", "geocode", "coordinate", "off the map", "out of area", "outside", "address"),
    ),
    (
        "off-topic",
        ("off-topic", "off topic", "unrelated", "not a hazard", "not relevant", "irrelevant"),
    ),
)

# The public set of reason buckets (the taxonomy plus the catch-all).
REASON_CATEGORIES: tuple[str, ...] = (*(name for name, _ in _REASON_TAXONOMY), "other")

# Sentinel for a count cell suppressed by the k-anonymity floor.
WITHHELD: None = None


def categorize_reason(reason: str) -> str:
    """Bucket a free-text rejection reason into a small fixed taxonomy.

    Returns one of :data:`REASON_CATEGORIES`. The raw text is only inspected to
    pick a bucket; it is never returned, so a stats report built on this can
    never leak a moderator's free-text note. Empty/unknown text is ``"other"``.
    """
    text = (reason or "").casefold()
    if not text.strip():
        return "other"
    for name, keywords in _REASON_TAXONOMY:
        if any(kw in text for kw in keywords):
            return name
    return "other"


def _apply_floor(counts: dict[str, int], min_publish_n: int) -> tuple[dict[str, int | None], int]:
    """Withhold small cells: any count ``0 < n < min_publish_n`` becomes ``None``.

    Returns the floored mapping plus how many cells were withheld, so a report
    can state exactly how many breakdowns were suppressed for privacy.
    """
    floored: dict[str, int | None] = {}
    withheld = 0
    for key, n in counts.items():
        if 0 < n < min_publish_n:
            floored[key] = WITHHELD
            withheld += 1
        else:
            floored[key] = n
    return floored, withheld


def _parse_iso(value: str) -> datetime | None:
    """Parse an ISO-8601 timestamp, tolerating a trailing ``Z``. ``None`` on junk."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _latency_hours(sub: Submission) -> float | None:
    """Review latency (received -> decided) in hours, or ``None`` if not decided
    or either timestamp is missing/unparseable (legacy rows have no ``decided_at``)."""
    if sub.decided_at is None:
        return None
    received = _parse_iso(sub.received_at)
    decided = _parse_iso(sub.decided_at)
    if received is None or decided is None:
        return None
    return (decided - received).total_seconds() / 3600.0


def moderation_stats(config: Config) -> dict[str, object]:
    """Build the moderation transparency report for the current queue.

    Reports totals by status, review-flag frequencies, rejection-reason
    *category* counts (never the free text), and the median review latency in
    hours. Every per-cell count is passed through the k-anonymity floor
    (``config.min_publish_n``): a non-zero count below the floor is reported as
    ``null`` and tallied under ``withheld_cells`` so "how many did not make it"
    stays explicit without exposing a group too small to be anonymous.
    """
    min_n = config.min_publish_n
    queue = _load_queue(config)

    status_counts = {PENDING: 0, APPROVED: 0, REJECTED: 0}
    flag_counts: dict[str, int] = {}
    reason_counts: dict[str, int] = dict.fromkeys(REASON_CATEGORIES, 0)
    latencies: list[float] = []

    for sub in queue:
        status_counts[sub.status] = status_counts.get(sub.status, 0) + 1
        for flag in sub.flags:
            flag_counts[flag] = flag_counts.get(flag, 0) + 1
        if sub.status == REJECTED:
            reason_counts[categorize_reason(sub.reason or "")] += 1
        latency = _latency_hours(sub)
        if latency is not None:
            latencies.append(latency)

    total = len(queue)
    decided = len(latencies)
    floored_status, w_status = _apply_floor(status_counts, min_n)
    floored_flags, w_flags = _apply_floor(flag_counts, min_n)
    floored_reasons, w_reasons = _apply_floor(reason_counts, min_n)

    # The median only reveals a data point when the decided cohort itself clears
    # the floor; a median over 1-2 reviews would leak an individual latency.
    if 0 < decided < min_n:
        median_latency: float | None = WITHHELD
        latency_withheld = True
    elif decided == 0:
        median_latency = None
        latency_withheld = False
    else:
        median_latency = round(statistics.median(latencies), 2)
        latency_withheld = False

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "min_publish_n": min_n,
        "total_submissions": total,
        "status_counts": floored_status,
        "flag_counts": floored_flags,
        "reason_categories": floored_reasons,
        "review_latency_hours": {
            "median": median_latency,
            "n_decided": decided,
            "withheld": latency_withheld,
        },
        "withheld_cells": w_status + w_flags + w_reasons + (1 if latency_withheld else 0),
    }
