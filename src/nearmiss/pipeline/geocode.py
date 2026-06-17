"""Geocoding stage: resolve address-only reports to coordinates.

A report may arrive with a precise ``location`` OR with a free-text ``address``
(the report schema requires one or the other). Reports that already carry
coordinates pass through unchanged. An address-only report is resolved here, via
the configured geocoder (an offline gazetteer by default), so the rest of the
pipeline only ever deals with coordinates. An address that cannot be resolved is
left unplaced and is caught downstream as unsnapped — never snapped to an invented
location.
"""

from __future__ import annotations

from dataclasses import replace

from ..config import Config
from ..geocoder import load_geocoder
from ..models import Report

# Sentinel for "no location was provided" (Report.from_dict sets 0.0/0.0).
_UNSET = 0.0


def _needs_geocoding(r: Report) -> bool:
    return r.address is not None and r.lat == _UNSET and r.lon == _UNSET


def geocode(reports: list[Report], config: Config) -> list[Report]:
    """Return reports with addresses resolved to coordinates where possible."""
    if not any(_needs_geocoding(r) for r in reports):
        return list(reports)
    geocoder = load_geocoder(config)
    out: list[Report] = []
    for r in reports:
        if _needs_geocoding(r) and geocoder is not None:
            coords = geocoder.geocode(r.address or "")
            out.append(replace(r, lat=coords[0], lon=coords[1]) if coords else r)
        else:
            out.append(r)
    return out
