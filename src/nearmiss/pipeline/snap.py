"""Snap reports to the nearest street segment.

A report is assigned to the nearest segment within ``snap_max_m``; beyond that
it is left unsnapped (segment_id ``None``) for the quality stage to flag, rather
than forced onto a segment it does not belong to.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..config import Config
from ..geometry import point_to_polyline_m
from ..models import Report, Segment
from ..util import reference_point


@dataclass(frozen=True)
class Snapped:
    report: Report
    segment_id: str | None
    distance_m: float | None


def snap(reports: list[Report], segments: list[Segment], config: Config) -> list[Snapped]:
    lat0, lon0 = reference_point(segments, config.ref_lat, config.ref_lon)
    out: list[Snapped] = []
    for r in reports:
        best_id: str | None = None
        best_d = float("inf")
        for seg in segments:
            d = point_to_polyline_m(r.lat, r.lon, seg.coords, lat0, lon0)
            if d < best_d:
                best_d, best_id = d, seg.id
        if best_id is None:
            out.append(Snapped(r, None, None))
        elif best_d <= config.snap_max_m:
            out.append(Snapped(r, best_id, best_d))
        else:
            out.append(Snapped(r, None, best_d))
    return out
