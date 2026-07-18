"""Private county boundary shards are pinned, canonical, and non-publishable."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import cast
from xml.etree import ElementTree

import pytest
from jsonschema import Draft202012Validator
from tools import build_us_county_boundaries as boundaries

from nearmiss import fars_county_crosswalk as crosswalk

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schema" / "us-county-boundaries.schema.json"


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


def _shard() -> dict[str, object]:
    return boundaries._shard(
        "06",
        [
            _feature(county_fips="075", name="San Francisco", namelsad="San Francisco County"),
            _feature(),
        ],
    )


def test_private_boundary_shard_is_canonical_and_has_exact_pinned_provenance() -> None:
    shard = _shard()
    boundaries.validate_boundary_shard(shard)

    assert [feature["id"] for feature in cast(list[dict[str, object]], shard["features"])] == [
        "06013",
        "06075",
    ]
    assert shard["source"] == {
        "presentation_vintage": 2024,
        "distribution_url": boundaries.SOURCE_URL,
        "raw_zip_sha256": boundaries.SOURCE_SHA256,
        "raw_zip_size_bytes": 802_100,
        "member_name": boundaries.KML_MEMBER,
        "member_sha256": boundaries.KML_MEMBER_SHA256,
        "resolution": "1:20,000,000",
        "conversion_version": "county-boundary-kml-to-rfc7946-v1",
    }
    assert shard["accounting"] == {
        "feature_count": 2,
        "polygon_feature_count": 2,
        "multipolygon_feature_count": 0,
        "coordinate_count": 8,
    }

    first = boundaries.canonical_boundary_shard_bytes(shard)
    second = boundaries.canonical_boundary_shard_bytes(copy.deepcopy(shard))
    assert first == second
    assert first.endswith(b"\n") and b"\n" not in first[:-1]


def test_private_boundary_shard_rejects_cross_state_identity_and_bad_accounting() -> None:
    shard = _shard()
    feature = cast(dict[str, object], cast(list[object], shard["features"])[0])
    properties = cast(dict[str, object], feature["properties"])
    properties["state_fips"] = "51"
    with pytest.raises(ValueError, match="identity is inconsistent"):
        boundaries.validate_boundary_shard(shard)

    shard = _shard()
    accounting = cast(dict[str, int], shard["accounting"])
    accounting["coordinate_count"] = 7
    with pytest.raises(ValueError, match="accounting is inconsistent"):
        boundaries.validate_boundary_shard(shard)


def test_converter_fails_closed_on_unpinned_archive_bytes() -> None:
    with pytest.raises(ValueError, match="byte size does not match"):
        boundaries.convert(b"not the reviewed Census archive")


def test_kml_parser_preserves_county_identity_and_rejects_open_rings() -> None:
    placemark = ElementTree.fromstring(
        """
        <Placemark xmlns="http://www.opengis.net/kml/2.2">
          <ExtendedData><SchemaData>
            <SimpleData name="STATEFP">06</SimpleData>
            <SimpleData name="COUNTYFP">013</SimpleData>
            <SimpleData name="GEOID">06013</SimpleData>
            <SimpleData name="NAME">Contra Costa</SimpleData>
            <SimpleData name="NAMELSAD">Contra Costa County</SimpleData>
            <SimpleData name="STUSPS">CA</SimpleData>
            <SimpleData name="STATE_NAME">California</SimpleData>
          </SchemaData></ExtendedData>
          <Polygon><outerBoundaryIs><LinearRing>
            <coordinates>-122,37 -121,37 -121,38 -122,37</coordinates>
          </LinearRing></outerBoundaryIs></Polygon>
        </Placemark>
        """
    )

    assert boundaries._placemark_values(placemark)["GEOID"] == "06013"
    assert boundaries._geometry(placemark) == {
        "type": "Polygon",
        "coordinates": [[[-122.0, 37.0], [-121.0, 37.0], [-121.0, 38.0], [-122.0, 37.0]]],
    }
    with pytest.raises(ValueError, match="not closed"):
        boundaries._coordinates("-122,37 -121,37 -121,38 -122,38")


def test_private_writer_refuses_the_public_data_root(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="must not be written to data/published"):
        boundaries.write_shards({"06": _shard()}, boundaries.PUBLISHED_DATA_ROOT)

    paths = boundaries.write_shards({"06": _shard()}, tmp_path / "county-review")
    assert paths == [tmp_path / "county-review" / "06.json"]
    assert paths[0].read_bytes() == boundaries.canonical_boundary_shard_bytes(_shard())


def test_boundary_provenance_interoperates_with_the_private_crosswalk_contract() -> None:
    artifact = crosswalk.build_fars_county_crosswalk(
        [
            {
                "state_code": "6",
                "county_code": "013",
                "mapping_status": "exact",
                "review_note": "Synthetic integration fixture for boundary provenance",
                "presentation": {
                    "state_fips": "06",
                    "county_fips": "013",
                    "geoid": "06013",
                    "name": "Contra Costa",
                    "namelsad": "Contra Costa County",
                    "entity_class": "county",
                },
            }
        ],
        year=2024,
        contract_revision=1,
        review_reference="county-boundary-integration-20260718",
        boundary=cast(dict[str, object], _shard()["source"]),
    )
    crosswalk.require_fars_county_crosswalk_resolved(artifact)


def test_repository_schema_matches_embedded_private_contract() -> None:
    assert json.loads(SCHEMA_PATH.read_text(encoding="utf-8")) == boundaries.BOUNDARY_SHARD_SCHEMA
    Draft202012Validator.check_schema(boundaries.BOUNDARY_SHARD_SCHEMA)
