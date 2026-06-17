"""Small shared utilities: deterministic timestamp parsing and number formatting."""

from __future__ import annotations

from datetime import UTC, datetime

from .models import Segment


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
    segments: list[Segment], ref_lat: float | None, ref_lon: float | None
) -> tuple[float, float]:
    """Reference (lat0, lon0) for the local projection: config value or bbox centre."""
    if ref_lat is not None and ref_lon is not None:
        return ref_lat, ref_lon
    lats = [c[0] for s in segments for c in s.coords]
    lons = [c[1] for s in segments for c in s.coords]
    return (sum(lats) / len(lats), sum(lons) / len(lons))


def round_stable(value: float | None, places: int) -> float | None:
    """Round for stable, reproducible JSON output (avoids float jitter in diffs)."""
    if value is None:
        return None
    return round(value, places)
