from __future__ import annotations

import json
from pathlib import Path

import pytest

from nearmiss.config import load_config, load_config_bytes
from nearmiss.errors import ConfigError, NearmissError
from nearmiss.loaders import load_streets, load_streets_bytes


def _config_payload() -> bytes:
    return (
        b'city = "Byte City"\n'
        b'streets = "streets.geojson"\n'
        b'reports = "r.json"\n'
        b'exposure = "e.json"\n'
    )


def _street_payload(segment_id: str) -> bytes:
    return json.dumps(
        {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {"segment_id": segment_id},
                    "geometry": {
                        "type": "LineString",
                        "coordinates": [[-121.75, 38.53], [-121.74, 38.54]],
                    },
                }
            ],
        }
    ).encode()


def test_load_config_bytes_parses_the_supplied_snapshot_without_reopening(tmp_path: Path) -> None:
    path = tmp_path / "city.toml"
    original = _config_payload()
    path.write_bytes(original)
    expected = load_config(path)
    path.write_text("invalid = [", encoding="utf-8")

    actual = load_config_bytes(path, original)

    assert actual == expected
    assert actual.streets_path == (tmp_path / "streets.geojson").resolve()


def test_load_streets_bytes_parses_the_supplied_snapshot_without_reopening(
    tmp_path: Path,
) -> None:
    path = tmp_path / "streets.geojson"
    original = _street_payload("original")
    path.write_bytes(original)
    expected = load_streets(path)
    path.write_bytes(_street_payload("replacement"))

    actual = load_streets_bytes(path, original)

    assert actual == expected
    assert actual[0].id == "original"


def test_load_streets_bytes_preserves_strict_utf8_input_contract(tmp_path: Path) -> None:
    path = tmp_path / "streets.geojson"

    with pytest.raises(NearmissError, match="invalid JSON"):
        load_streets_bytes(path, _street_payload("utf16").decode().encode("utf-16"))


def test_load_config_bytes_rejects_non_object_json_root(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="top-level object"):
        load_config_bytes(tmp_path / "city.json", b"[]")


@pytest.mark.parametrize(
    "replacement",
    [
        {"type": "FeatureCollection", "features": {}},
        {"type": "FeatureCollection", "features": [None]},
        {
            "type": "FeatureCollection",
            "features": [{"type": "Feature", "properties": [], "geometry": {"type": "LineString"}}],
        },
        {
            "type": "FeatureCollection",
            "features": [{"type": "Feature", "properties": {}, "geometry": []}],
        },
        {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {},
                    "geometry": {"type": "LineString", "coordinates": {}},
                }
            ],
        },
        {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {},
                    "geometry": {"type": "LineString", "coordinates": [[1], [2, 3]]},
                }
            ],
        },
        {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {},
                    "geometry": {
                        "type": "LineString",
                        "coordinates": [["west", 1], [2, 3]],
                    },
                }
            ],
        },
        {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {},
                    "geometry": {
                        "type": "LineString",
                        "coordinates": [[10**1000, 1], [2, 3]],
                    },
                }
            ],
        },
    ],
)
def test_load_streets_bytes_rejects_malformed_nested_shapes(
    tmp_path: Path, replacement: object
) -> None:
    with pytest.raises(NearmissError):
        load_streets_bytes(tmp_path / "streets.geojson", json.dumps(replacement).encode())


@pytest.mark.parametrize("field", ["segment_id", "name"])
def test_load_streets_bytes_rejects_escaped_lone_surrogate(tmp_path: Path, field: str) -> None:
    payload = _street_payload("valid")
    decoded = json.loads(payload)
    decoded["features"][0]["properties"][field] = "\ud800"
    escaped = json.dumps(decoded).encode("ascii")

    with pytest.raises(NearmissError, match="invalid Unicode scalar"):
        load_streets_bytes(tmp_path / "streets.geojson", escaped)


def test_load_config_bytes_rejects_escaped_lone_surrogate(tmp_path: Path) -> None:
    payload = b'{"city":"\\ud800","streets":"s.geojson","reports":"r.json","exposure":"e.json"}'
    with pytest.raises(ConfigError, match="invalid Unicode scalar"):
        load_config_bytes(tmp_path / "city.json", payload)


def test_load_config_bytes_translates_deep_object_recursion(tmp_path: Path) -> None:
    payload = b'{"nested":' * 2_000 + b"null" + b"}" * 2_000
    with pytest.raises(ConfigError, match="invalid config"):
        load_config_bytes(tmp_path / "city.json", payload)


def test_load_streets_bytes_translates_deep_list_recursion(tmp_path: Path) -> None:
    payload = b"[" * 2_000 + b"null" + b"]" * 2_000
    with pytest.raises(NearmissError, match="invalid JSON"):
        load_streets_bytes(tmp_path / "streets.geojson", payload)
