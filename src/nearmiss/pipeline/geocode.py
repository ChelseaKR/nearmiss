"""Geocoding stage (adapter seam).

Reports submitted through the form and the documented JSON path already carry
coordinates, so this stage is an identity pass for them. It exists as the single
place a real geocoder adapter (for address-only imports) would attach
coordinates, keeping that concern isolated and swappable (interchangeability).
A report whose coordinates are absent is left for the quality stage to flag, not
silently invented.
"""

from __future__ import annotations

from ..config import Config
from ..models import Report


def geocode(reports: list[Report], config: Config) -> list[Report]:
    """Return reports with coordinates resolved. Currently a pass-through."""
    del config  # no external geocoder configured in the default path
    return list(reports)
