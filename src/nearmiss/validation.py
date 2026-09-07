"""Schema validation at intake.

A report is validated against ``schema/report.schema.json`` (JSON Schema draft
2020-12) before it is allowed anywhere near the dataset. A malformed or
malicious report is rejected here, never silently corrupting downstream results
(dependability / data integrity / safety).
"""

from __future__ import annotations

import functools
import json
import os
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from .errors import ValidationError
from .util import parse_rfc3339_datetime

_ENV_OVERRIDE = "NEARMISS_REPORT_SCHEMA"


def find_report_schema() -> Path:
    """Locate report.schema.json via env override or by walking up the tree."""
    override = os.environ.get(_ENV_OVERRIDE)
    if override:
        return Path(override)
    here = Path(__file__).resolve()
    # Installed from a wheel, the schemas ship as package data beside this
    # module (pyproject force-include). In a source checkout that directory
    # does not exist and the walk below finds the authoritative repo copy.
    packaged = here.parent / "schema" / "report.schema.json"
    if packaged.is_file():
        return packaged
    for parent in [here.parent, *here.parents]:
        candidate = parent / "schema" / "report.schema.json"
        if candidate.is_file():
            return candidate
    raise ValidationError(
        f"could not locate schema/report.schema.json; set {_ENV_OVERRIDE} to its path"
    )


@functools.lru_cache(maxsize=8)
def _validator_for(path: str) -> Draft202012Validator:
    schema = json.loads(Path(path).read_text(encoding="utf-8"))
    # JSON Schema treats `format` as an annotation unless a checker is supplied,
    # so without this the schema's constraints on shape are documentation the
    # gate never reads. It is NOT sufficient on its own: see _occurred_at_problem.
    return Draft202012Validator(schema, format_checker=FormatChecker())


def _occurred_at_problem(report: dict[str, object]) -> str | None:
    """Enforce the ``occurred_at`` contract that ``"format": "date-time"`` cannot.

    ``schema/report.schema.json`` says ``occurred_at`` is "an ISO-8601 / RFC 3339
    date-time with an explicit timezone offset (UTC 'Z' or +/-HH:MM)". Nothing
    enforced it. ``format`` is annotation-only without a ``FormatChecker`` — and
    even with one, ``date-time`` is **not** among jsonschema's built-in checkers:
    it needs the optional ``rfc3339-validator`` package, and when that is absent a
    ``FormatChecker`` skips the constraint *silently*. So adding the checker above
    looks like a fix and enforces nothing on this field; the rule has to be in code.

    Two rejections matter and are different:

    * **unparseable** (``""``, ``"yesterday"``, ``"2026-13-45T99:99:99Z"``) — the
      pipeline's window filter compares ``occurred_at[:10]`` as a *string*, so an
      unparseable value is silently classified ``out_of_window`` and reported as a
      report that fell outside the stated analysis period. It did not; its time
      could not be read.
    * **no offset** (``"2026-06-15T08:42:00"``) — parseable, and worse for it. The
      temporal breakdown deliberately reports the *local wall-clock hour* the
      contributor experienced, so a naive timestamp contributes an hour in an
      unstated zone to a published peak-hour claim. The spreadsheet adapter already
      refuses these and counts them; the direct intake path did not.
    """
    raw = report.get("occurred_at")
    if not isinstance(raw, str):
        return None  # a missing or non-string value is already a schema error
    if parse_rfc3339_datetime(raw) is not None:
        return None
    return (
        f"occurred_at: {raw!r} is not an RFC 3339 date-time with an explicit timezone "
        "offset (e.g. '2026-06-15T08:42:00-07:00' or '2026-06-15T15:42:00Z'). An event "
        "time that cannot be read is not an event time outside the analysis window, and "
        "a timestamp with no offset is an hour in an unstated zone."
    )


def _validator() -> Draft202012Validator:
    # Re-resolve the schema path each call (cheap) and cache per path, so the
    # NEARMISS_REPORT_SCHEMA override is honored rather than frozen at first use.
    return _validator_for(str(find_report_schema()))


def validate_report(report: dict[str, object]) -> list[str]:
    """Return a list of human-readable problems; empty means valid."""
    problems: list[str] = []
    for err in sorted(_validator().iter_errors(report), key=lambda e: list(e.path)):
        location = "/".join(str(p) for p in err.path) or "(root)"
        problems.append(f"{location}: {err.message}")
    timestamp_problem = _occurred_at_problem(report)
    if timestamp_problem is not None:
        problems.append(timestamp_problem)
    return problems


def require_valid(report: dict[str, object]) -> None:
    """Raise :class:`ValidationError` if the report is invalid."""
    problems = validate_report(report)
    if problems:
        rid = report.get("id", "<no id>")
        raise ValidationError(f"report {rid!r} failed validation", problems)
