"""Address-only reports are geocoded so they can enter the pipeline (Fatima)."""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

from nearmiss.config import Config
from nearmiss.geocoder import GazetteerGeocoder, NominatimGeocoder
from nearmiss.models import Report
from nearmiss.pipeline.geocode import geocode

_TS = "2026-06-10T07:00:00-07:00"


def test_gazetteer_resolves_normalized() -> None:
    g = GazetteerGeocoder({"B St & 3rd St": (38.5, -121.7)})
    assert g.geocode("b st &  3rd st") == (38.5, -121.7)  # case + whitespace insensitive
    assert g.geocode("nowhere") is None


def test_geocode_stage_fills_address_only_report(config: Config, tmp_path: Path) -> None:
    gaz = tmp_path / "gaz.json"
    gaz.write_text(
        json.dumps({"addresses": [{"address": "B St & 3rd St", "lat": 38.5, "lon": -121.7}]}),
        encoding="utf-8",
    )
    cfg = dataclasses.replace(config, gazetteer_path=gaz)
    r = Report(
        id="x",
        occurred_at=_TS,
        lat=0.0,
        lon=0.0,
        mode="cyclist",
        hazard_type="close_pass",
        severity="near_miss",
        address="B St & 3rd St",
    )
    out = geocode([r], cfg)
    assert (out[0].lat, out[0].lon) == (38.5, -121.7)


def test_nominatim_geocoder_with_injected_transport() -> None:
    calls: list[str] = []

    def fake(url: str, headers: dict[str, str]) -> str:
        calls.append(url)
        assert "User-Agent" in headers
        return json.dumps([{"lat": "38.5", "lon": "-121.7"}])

    g = NominatimGeocoder(transport=fake)
    assert g.geocode("5th St & C St, Davis") == (38.5, -121.7)
    g.geocode("5th St & C St, Davis")  # cached — no second request
    assert len(calls) == 1


def test_nominatim_returns_none_when_unresolved() -> None:
    g = NominatimGeocoder(transport=lambda url, headers: "[]")
    assert g.geocode("nowhere at all") is None


def test_geocode_leaves_coordinate_reports_untouched(config: Config) -> None:
    r = Report(
        id="x",
        occurred_at=_TS,
        lat=38.54,
        lon=-121.74,
        mode="cyclist",
        hazard_type="close_pass",
        severity="near_miss",
    )
    out = geocode([r], config)
    assert (out[0].lat, out[0].lon) == (38.54, -121.74)
