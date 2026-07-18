# SPDX-License-Identifier: Apache-2.0
"""Public county geometry must be canonical without exposing its private envelope."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, cast

import pytest
from jsonschema import Draft202012Validator
from tools import build_us_county_boundaries as private_boundaries

from nearmiss import fars_county_boundary_publication as publication

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schema" / "public-us-county-boundaries.schema.json"


def _feature(
    *,
    county_fips: str = "013",
    name: str = "Contra Costa",
    namelsad: str = "Contra Costa County",
) -> dict[str, object]:
    geoid = "06" + county_fips
    return {
        "type": "Feature",
        "id": geoid,
        "properties": {
            "state_fips": "06",
            "county_fips": county_fips,
            "geoid": geoid,
            "name": name,
            "namelsad": namelsad,
        },
        "geometry": {
            "type": "Polygon",
            "coordinates": [[[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 0.0]]],
        },
    }


def _private_shard() -> dict[str, object]:
    return private_boundaries._shard(
        "06",
        [
            _feature(county_fips="075", name="San Francisco", namelsad="San Francisco County"),
            _feature(),
        ],
    )


def _public_shard() -> dict[str, object]:
    return publication.build_public_fars_county_boundary_state_artifact(_private_shard())


def test_public_boundary_is_canonical_and_detached_from_private_envelope() -> None:
    artifact = _public_shard()
    publication.validate_public_fars_county_boundary_state_artifact(artifact)
    payload = publication.canonical_public_fars_county_boundary_state_bytes(artifact)

    assert artifact["state"] == {
        "state_fips": "06",
        "state_abbreviation": "CA",
        "state_name": "California",
    }
    assert cast(dict[str, int], artifact["accounting"]) == {
        "feature_count": 2,
        "polygon_feature_count": 2,
        "multipolygon_feature_count": 0,
        "coordinate_count": 8,
    }
    assert b'"visibility":"private"' not in payload
    assert b"nearmiss.private.us_county_boundary_shard" not in payload
    assert b'"state_fips":"06"' in payload
    assert payload.endswith(b"\n") and b"\n" not in payload[:-1]
    assert publication.load_public_fars_county_boundary_state_bytes(payload) == artifact


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (b"", "byte safety limit"),
        (b" " * (publication.FARS_COUNTY_PUBLIC_BOUNDARY_MAX_BYTES + 1), "byte safety limit"),
        (b"\xff", "not UTF-8"),
        (b"{", "invalid JSON"),
        (b"[]", "must be an object"),
        (b'{"value":NaN}', "non-finite"),
        (b'{"state":1,"state":2}', "duplicate key"),
    ],
)
def test_public_boundary_loader_rejects_unsafe_or_noncanonical_payloads(
    payload: bytes, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        publication.load_public_fars_county_boundary_state_bytes(payload)


def test_public_boundary_rejects_private_input_and_identity_accounting_drift() -> None:
    private = _private_shard()
    private["visibility"] = "public"
    with pytest.raises(ValueError, match="reviewed private boundary contract"):
        publication.build_public_fars_county_boundary_state_artifact(private)

    artifact = _public_shard()
    state = cast(dict[str, str], artifact["state"])
    state["state_abbreviation"] = "ZZ"
    with pytest.raises(ValueError, match="state identity"):
        publication.validate_public_fars_county_boundary_state_artifact(artifact)

    artifact = _public_shard()
    accounting = cast(dict[str, int], artifact["accounting"])
    accounting["coordinate_count"] = 7
    with pytest.raises(ValueError, match="accounting"):
        publication.validate_public_fars_county_boundary_state_artifact(artifact)


def test_public_boundary_rejects_geometry_and_ordering_drift() -> None:
    artifact = _public_shard()
    features = cast(list[dict[str, Any]], artifact["features"])
    artifact["features"] = list(reversed(features))
    with pytest.raises(ValueError, match="not uniquely canonically ordered"):
        publication.validate_public_fars_county_boundary_state_artifact(artifact)

    artifact = _public_shard()
    feature = cast(list[dict[str, Any]], artifact["features"])[0]
    coordinates = cast(list[list[list[float]]], feature["geometry"]["coordinates"])
    coordinates[0][-1] = [1.0, 1.0]
    with pytest.raises(ValueError, match="ring is invalid"):
        publication.validate_public_fars_county_boundary_state_artifact(artifact)


def test_public_boundary_canonicalization_is_stable_and_source_is_not_mutable() -> None:
    artifact = _public_shard()
    first = publication.canonical_public_fars_county_boundary_state_bytes(artifact)
    second = publication.canonical_public_fars_county_boundary_state_bytes(copy.deepcopy(artifact))
    assert first == second

    artifact = _public_shard()
    source = cast(dict[str, object], artifact["source"])
    source["resolution"] = "unreviewed"
    with pytest.raises(ValueError, match="was expected"):
        publication.validate_public_fars_county_boundary_state_artifact(artifact)


def test_public_boundary_internal_guards_reject_untrusted_shapes_and_values() -> None:
    with pytest.raises(ValueError, match="invalid fixture"):
        publication._mapping([], label="fixture")
    with pytest.raises(ValueError, match="invalid fixture"):
        publication._sequence({}, label="fixture")

    source = copy.deepcopy(cast(dict[str, object], _public_shard()["source"]))
    source["unexpected"] = "field"
    with pytest.raises(ValueError, match="source provenance"):
        publication._boundary_source(source)
    source = copy.deepcopy(cast(dict[str, object], _public_shard()["source"]))
    source["raw_zip_sha256"] = "g" * 64
    with pytest.raises(ValueError, match="source provenance"):
        publication._boundary_source(source)
    source = copy.deepcopy(cast(dict[str, object], _public_shard()["source"]))
    source["raw_zip_size_bytes"] = True
    with pytest.raises(ValueError, match="source provenance"):
        publication._boundary_source(source)

    with pytest.raises(ValueError, match="geometry type"):
        publication._validate_geometry({"type": "LineString", "coordinates": []})
    with pytest.raises(ValueError, match="position arity"):
        publication._validate_geometry(
            {
                "type": "Polygon",
                "coordinates": [[[0.0, 0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 0.0, 0.0]]],
            }
        )
    with pytest.raises(ValueError, match="position is invalid"):
        publication._validate_geometry(
            {
                "type": "Polygon",
                "coordinates": [[[0.0, 0.0], [181.0, 0.0], [1.0, 1.0], [0.0, 0.0]]],
            }
        )
    with pytest.raises(ValueError, match="no measurable area"):
        publication._validate_geometry(
            {
                "type": "Polygon",
                "coordinates": [[[0.0, 0.0], [1.0, 1.0], [2.0, 2.0], [0.0, 0.0]]],
            }
        )

    with pytest.raises(ValueError, match="state FIPS"):
        publication._state_identity({"state_fips": "CA"})
    with pytest.raises(ValueError, match="outside reviewed coverage"):
        publication._state_identity(
            {"state_fips": "00", "state_abbreviation": "ZZ", "state_name": "Unknown"}
        )

    private = _private_shard()
    private["state_fips"] = "CA"
    with pytest.raises(ValueError, match="private state FIPS"):
        publication._private_boundary_parts(private)
    private = _private_shard()
    private["state_fips"] = "00"
    with pytest.raises(ValueError, match="outside reviewed coverage"):
        publication._private_boundary_parts(private)
    private = _private_shard()
    private_accounting = cast(dict[str, int], private["accounting"])
    private_accounting["coordinate_count"] = 7
    with pytest.raises(ValueError, match="private accounting"):
        publication._private_boundary_parts(private)


def test_public_boundary_handles_multipolygons_and_rejects_noncanonical_bytes() -> None:
    feature = _feature()
    geometry = cast(dict[str, object], feature["geometry"])
    geometry["type"] = "MultiPolygon"
    geometry["coordinates"] = [geometry["coordinates"]]
    private = private_boundaries._shard("06", [feature])
    artifact = publication.build_public_fars_county_boundary_state_artifact(private)
    assert cast(list[dict[str, Any]], artifact["features"])[0]["geometry"]["type"] == "MultiPolygon"

    with pytest.raises(TypeError, match="payload must be bytes"):
        publication.load_public_fars_county_boundary_state_bytes(bytearray(b"{}"))  # type: ignore[arg-type]
    pretty = json.dumps(_public_shard(), sort_keys=True, indent=2).encode("utf-8")
    with pytest.raises(ValueError, match="not canonical"):
        publication.load_public_fars_county_boundary_state_bytes(pretty)


def test_repository_schema_matches_embedded_public_contract() -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    assert schema == publication.FARS_COUNTY_PUBLIC_BOUNDARY_SCHEMA
    Draft202012Validator.check_schema(schema)
