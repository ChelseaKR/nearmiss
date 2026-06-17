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
import urllib.parse
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from .errors import NearmissError

if TYPE_CHECKING:
    from .config import Config

# A transport maps (url, headers) -> response body text. Injectable for testing.
Transport = Callable[[str, dict[str, str]], str]


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


def _urllib_transport(url: str, headers: dict[str, str]) -> str:
    if not url.lower().startswith("https://"):
        raise NearmissError("geocoder transport refuses non-HTTPS URLs")
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=10) as resp:
        body: str = resp.read().decode("utf-8")
    return body


class NominatimGeocoder:
    """Networked geocoder using a Nominatim-compatible search endpoint.

    Opt-in (``geocoder = "nominatim"`` in config), NOT the default, because the
    analysis is meant to run offline. Results are cached in-process so a repeated
    address is not re-requested, which keeps a run deterministic and polite to the
    service. The HTTP transport is injectable so this is testable without network.
    """

    def __init__(
        self,
        base_url: str = "https://nominatim.openstreetmap.org/search",
        user_agent: str = "nearmiss",
        transport: Transport | None = None,
    ) -> None:
        self._base = base_url
        self._ua = user_agent
        self._transport = transport or _urllib_transport
        self._cache: dict[str, tuple[float, float] | None] = {}

    def geocode(self, address: str) -> tuple[float, float] | None:
        key = " ".join(address.lower().split())
        if key in self._cache:
            return self._cache[key]
        query = urllib.parse.urlencode({"q": address, "format": "jsonv2", "limit": 1})
        url = f"{self._base}?{query}"
        result: tuple[float, float] | None = None
        try:
            data = json.loads(self._transport(url, {"User-Agent": self._ua}))
            if isinstance(data, list) and data:
                result = (float(data[0]["lat"]), float(data[0]["lon"]))
        except (OSError, ValueError, KeyError, NearmissError):
            result = None  # unreachable / malformed -> leave unplaced, never invent
        self._cache[key] = result
        return result


def load_geocoder(config: Config) -> Geocoder | None:
    """Build the configured geocoder: offline gazetteer, Nominatim, or none.

    The offline gazetteer wins if configured (deterministic, no network). The
    networked Nominatim adapter is opt-in via ``geocoder = "nominatim"``.
    """
    if config.gazetteer_path is not None:
        return GazetteerGeocoder.from_file(config.gazetteer_path)
    if config.geocoder == "nominatim":
        return NominatimGeocoder(user_agent=config.geocoder_user_agent)
    return None
