"""Small shared utilities: deterministic timestamp parsing and number formatting."""

from __future__ import annotations

import re
from collections.abc import Iterable
from datetime import UTC, date, datetime

#: RFC 3339 ``full-date``: exactly ``YYYY-MM-DD``. Deliberately stricter than
#: :meth:`datetime.date.fromisoformat`, which since 3.11 also accepts the basic
#: form (``20240102``) and ISO week dates (``2024-W01-1``) — neither of which
#: satisfies the ``"format": "date"`` constraint the published dataset contract
#: declares. Keeping the loader's rule identical to the contract's rule is the
#: point: a value that survives one gate must survive the other.
_ISO_DATE = re.compile(r"\A\d{4}-\d{2}-\d{2}\Z")


def parse_iso_date(value: str) -> date | None:
    """Parse an RFC 3339 ``full-date`` (``YYYY-MM-DD``); ``None`` if it is not one.

    ``None`` means *unmeasurable*, and callers must treat it as a third state —
    neither a valid date nor a silently-tolerated one. See
    :func:`nearmiss.exposure.is_stale`, whose caller cannot distinguish "the
    vintage matches the reports" from "the vintage could not be read" unless the
    unreadable case is refused before it gets there.
    """
    if not _ISO_DATE.match(value):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


#: RFC 3339 ``date-time`` with a mandatory offset: ``YYYY-MM-DDTHH:MM:SS`` plus an
#: optional fractional part, then ``Z`` or ``±HH:MM``. The offset is not optional
#: here because ``schema/report.schema.json`` says it is not
#: ("an ISO-8601 / RFC 3339 date-time with an explicit timezone offset"): a naive
#: timestamp is an hour in an unstated zone, and the temporal breakdown reports it
#: as a local wall-clock hour, so accepting one publishes a peak hour nobody stated.
_RFC3339 = re.compile(
    r"\A\d{4}-\d{2}-\d{2}[Tt ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:[Zz]|[+-]\d{2}:\d{2})\Z"
)


def parse_rfc3339_datetime(value: str) -> datetime | None:
    """Parse an RFC 3339 ``date-time`` **with an explicit offset**; else ``None``.

    ``None`` is the third state — absent, malformed, or offset-less — and a caller
    that folds it into either of the other two is publishing an absence as a
    measurement. Used by :func:`nearmiss.validation.validate_report`, because
    JSON Schema's ``"format": "date-time"`` is unenforceable here: it needs the
    optional ``rfc3339-validator`` package, and without it a ``FormatChecker``
    ignores the constraint *silently*.
    """
    if not _RFC3339.match(value):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00").replace("z", "+00:00"))
    except ValueError:
        return None


def parse_ts(iso: str) -> float | None:
    """Parse an ISO-8601 timestamp to a POSIX epoch; None if unparseable."""
    try:
        s = iso.replace("Z", "+00:00") if iso.endswith("Z") else iso
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt.timestamp()
    except ValueError:
        return None


def reference_point(
    points: Iterable[tuple[float, float]], ref_lat: float | None, ref_lon: float | None
) -> tuple[float, float]:
    """Reference (lat0, lon0) for a local projection: config value, else the mean of ``points``.

    ``points`` is any iterable of (lat, lon) pairs — segment vertices, report
    locations, or centroids — whatever the caller is about to project.
    """
    if ref_lat is not None and ref_lon is not None:
        return ref_lat, ref_lon
    pts = list(points)
    lats = [p[0] for p in pts]
    lons = [p[1] for p in pts]
    return (sum(lats) / len(lats), sum(lons) / len(lons))


def round_stable(value: float | None, places: int) -> float | None:
    """Round for stable, reproducible JSON output (avoids float jitter in diffs)."""
    if value is None:
        return None
    return round(value, places)
