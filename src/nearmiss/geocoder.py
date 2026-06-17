"""Geocoding adapters: resolve an address to coordinates.

The pipeline's geocode stage uses a :class:`Geocoder` to place address-only
reports on the map. The default, offline, deterministic adapter is a
:class:`GazetteerGeocoder` backed by a committed address->coordinate table, so
the demo and tests run with no network. A networked adapter (e.g. Nominatim)
would implement the same protocol; it is intentionally not the default, because
the analysis must run anywhere with no external service.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol

from .errors import NearmissError


class Geocoder(Protocol):
    def geocode(self, address: str) -> tuple[float, float] | None:
        """Return (lat, lon) for an address, or None if it cannot be resolved."""
        ...


class GazetteerGeocoder:
    """Offline geocoder backed by an address -> (lat, lon) table.

    Matching is case-insensitive and whitespace-normalized so minor formatting
    differences still resolve. Deterministic: the same address always maps to the
    same coordinate.
    """

    def __init__(self, table: dict[str, tuple[float, float]]) -> None:
        self._table = {self._norm(k): v for k, v in table.items()}

    @staticmethod
    def _norm(s: str) -> str:
        return " ".join(s.lower().split())

    def geocode(self, address: str) -> tuple[float, float] | None:
        return self._table.get(self._norm(address))

    @classmethod
    def from_file(cls, path: Path) -> GazetteerGeocoder:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise NearmissError(f"gazetteer not found: {path}") from exc
        except json.JSONDecodeError as exc:
            raise NearmissError(f"invalid gazetteer JSON in {path}: {exc}") from exc
        rows = data["addresses"] if isinstance(data, dict) else data
        table: dict[str, tuple[float, float]] = {}
        try:
            for row in rows:
                table[str(row["address"])] = (float(row["lat"]), float(row["lon"]))
        except (KeyError, TypeError, ValueError) as exc:
            raise NearmissError(f"{path}: malformed gazetteer row ({exc})") from exc
        return cls(table)


def load_geocoder(gazetteer_path: Path | None) -> Geocoder | None:
    """Build the configured geocoder, or None when no gazetteer is configured."""
    if gazetteer_path is None:
        return None
    return GazetteerGeocoder.from_file(gazetteer_path)
