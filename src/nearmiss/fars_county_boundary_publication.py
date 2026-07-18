# SPDX-License-Identifier: Apache-2.0
"""Fail-closed public county-boundary state shards.

County values and county geometry have different release boundaries.  A reviewed
private Census boundary shard is necessary to construct a county projection, but
its private envelope must never become a public artifact dependency.  This
module republishes only the reviewed public geometry and Census provenance under
a distinct canonical public contract.  It carries no FARS values, crosswalk
rows, source record identifiers, or private-artifact digests.
"""

from __future__ import annotations

import copy
import json
import math
import re
from collections.abc import Mapping, Sequence
from typing import Any, NoReturn, cast

from jsonschema import Draft202012Validator

from .fars_county_crosswalk import (
    FARS_COUNTY_BOUNDARY_CONVERSION_VERSION,
    FARS_COUNTY_BOUNDARY_MEMBER,
    FARS_COUNTY_BOUNDARY_PRESENTATION_VINTAGE,
    FARS_COUNTY_BOUNDARY_RESOLUTION,
    FARS_COUNTY_BOUNDARY_URL,
)
from .fars_public_context import FARS_PUBLIC_STATE_CROSSWALK

FARS_COUNTY_PUBLIC_BOUNDARY_SCHEMA_VERSION = "1.0.0"
FARS_COUNTY_PUBLIC_BOUNDARY_ARTIFACT_TYPE = "nearmiss.public.us_county_boundary_shard"
FARS_COUNTY_PUBLIC_BOUNDARY_MAX_BYTES = 1_024 * 1_024
FARS_COUNTY_PUBLIC_BOUNDARY_RAW_ZIP_SHA256 = (
    "590c1bfc1ae2746163a7417100670680a4a0ca79a577771e3c7c6821eea5149f"
)
FARS_COUNTY_PUBLIC_BOUNDARY_RAW_ZIP_SIZE_BYTES = 802_100
FARS_COUNTY_PUBLIC_BOUNDARY_MEMBER_SHA256 = (
    "920cacc5b601d99a7b697a63ab16e0d846d34df271a34a2b278e5fd9cb8b6c12"
)

_MAX_FEATURES_PER_STATE = 300
_MAX_COORDINATES_PER_STATE = 500_000
_STATE_FIPS_RE = re.compile(r"^[0-9]{2}$", re.ASCII)
_COUNTY_FIPS_RE = re.compile(r"^[0-9]{3}$", re.ASCII)
_GEOID_RE = re.compile(r"^[0-9]{5}$", re.ASCII)
_PRIVATE_ARTIFACT_TYPE = "nearmiss.private.us_county_boundary_shard"
_STATE_BY_FIPS = {
    f"{int(state_code):02d}": state for state_code, state in FARS_PUBLIC_STATE_CROSSWALK.items()
}


def _closed(properties: Mapping[str, object]) -> dict[str, object]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": list(properties),
        "properties": dict(properties),
    }


_POSITION_SCHEMA = {
    "type": "array",
    "prefixItems": [
        {"type": "number", "minimum": -180, "maximum": 180},
        {"type": "number", "minimum": -90, "maximum": 90},
    ],
    "items": False,
    "minItems": 2,
    "maxItems": 2,
}
_RING_SCHEMA = {"type": "array", "minItems": 4, "items": _POSITION_SCHEMA}
_POLYGON_SCHEMA = _closed(
    {
        "type": {"const": "Polygon"},
        "coordinates": {"type": "array", "minItems": 1, "items": _RING_SCHEMA},
    }
)
_MULTIPOLYGON_SCHEMA = _closed(
    {
        "type": {"const": "MultiPolygon"},
        "coordinates": {
            "type": "array",
            "minItems": 1,
            "items": {"type": "array", "minItems": 1, "items": _RING_SCHEMA},
        },
    }
)
_SOURCE_SCHEMA = _closed(
    {
        "presentation_vintage": {"const": FARS_COUNTY_BOUNDARY_PRESENTATION_VINTAGE},
        "distribution_url": {"const": FARS_COUNTY_BOUNDARY_URL},
        "raw_zip_sha256": {"const": FARS_COUNTY_PUBLIC_BOUNDARY_RAW_ZIP_SHA256},
        "raw_zip_size_bytes": {"const": FARS_COUNTY_PUBLIC_BOUNDARY_RAW_ZIP_SIZE_BYTES},
        "member_name": {"const": FARS_COUNTY_BOUNDARY_MEMBER},
        "member_sha256": {"const": FARS_COUNTY_PUBLIC_BOUNDARY_MEMBER_SHA256},
        "resolution": {"const": FARS_COUNTY_BOUNDARY_RESOLUTION},
        "conversion_version": {"const": FARS_COUNTY_BOUNDARY_CONVERSION_VERSION},
    }
)
_FEATURE_SCHEMA = _closed(
    {
        "type": {"const": "Feature"},
        "id": {"type": "string", "pattern": "^[0-9]{5}$"},
        "properties": _closed(
            {
                "state_fips": {"type": "string", "pattern": "^[0-9]{2}$"},
                "county_fips": {"type": "string", "pattern": "^[0-9]{3}$"},
                "geoid": {"type": "string", "pattern": "^[0-9]{5}$"},
                "name": {"type": "string", "minLength": 1, "maxLength": 128},
                "namelsad": {"type": "string", "minLength": 1, "maxLength": 160},
            }
        ),
        "geometry": {"oneOf": [_POLYGON_SCHEMA, _MULTIPOLYGON_SCHEMA]},
    }
)
_ACCOUNTING_SCHEMA = _closed(
    {
        "feature_count": {"type": "integer", "minimum": 1, "maximum": _MAX_FEATURES_PER_STATE},
        "polygon_feature_count": {
            "type": "integer",
            "minimum": 0,
            "maximum": _MAX_FEATURES_PER_STATE,
        },
        "multipolygon_feature_count": {
            "type": "integer",
            "minimum": 0,
            "maximum": _MAX_FEATURES_PER_STATE,
        },
        "coordinate_count": {
            "type": "integer",
            "minimum": 4,
            "maximum": _MAX_COORDINATES_PER_STATE,
        },
    }
)

FARS_COUNTY_PUBLIC_BOUNDARY_SCHEMA: dict[str, object] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "https://nearmiss.dev/schema/public-us-county-boundaries.schema.json",
    "title": "Public NearMiss state-sharded 2024 Census county-equivalent boundaries",
    "type": "object",
    "additionalProperties": False,
    "required": [
        "schema_version",
        "artifact_type",
        "visibility",
        "state",
        "source",
        "accounting",
        "features",
    ],
    "properties": {
        "schema_version": {"const": FARS_COUNTY_PUBLIC_BOUNDARY_SCHEMA_VERSION},
        "artifact_type": {"const": FARS_COUNTY_PUBLIC_BOUNDARY_ARTIFACT_TYPE},
        "visibility": {"const": "public"},
        "state": _closed(
            {
                "state_fips": {"type": "string", "pattern": "^[0-9]{2}$"},
                "state_abbreviation": {"type": "string", "pattern": "^[A-Z]{2}$"},
                "state_name": {"type": "string", "minLength": 1, "maxLength": 64},
            }
        ),
        "source": _SOURCE_SCHEMA,
        "accounting": _ACCOUNTING_SCHEMA,
        "features": {
            "type": "array",
            "minItems": 1,
            "maxItems": _MAX_FEATURES_PER_STATE,
            "items": _FEATURE_SCHEMA,
        },
    },
}

_PUBLIC_VALIDATOR = Draft202012Validator(FARS_COUNTY_PUBLIC_BOUNDARY_SCHEMA)


def _canonical_json_bytes(value: Mapping[str, object]) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def _reject_constant(_value: str) -> NoReturn:
    raise ValueError("public county boundary JSON contains a non-finite number")


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("public county boundary JSON contains a duplicate key")
        result[key] = value
    return result


def _mapping(value: object, *, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"public county boundary has an invalid {label}")
    return value


def _sequence(value: object, *, label: str) -> Sequence[Mapping[str, object]]:
    if not isinstance(value, list) or any(not isinstance(item, Mapping) for item in value):
        raise ValueError(f"public county boundary has an invalid {label}")
    return cast(Sequence[Mapping[str, object]], value)


def _schema_error(artifact: Mapping[str, object]) -> None:
    errors = sorted(
        _PUBLIC_VALIDATOR.iter_errors(artifact), key=lambda error: list(error.absolute_path)
    )
    if errors:
        error = errors[0]
        path = "/".join(str(part) for part in error.absolute_path) or "(root)"
        raise ValueError(f"invalid public county boundary at {path}: {error.message}")


def _boundary_source(source: Mapping[str, object]) -> dict[str, object]:
    expected = {
        "presentation_vintage": FARS_COUNTY_BOUNDARY_PRESENTATION_VINTAGE,
        "distribution_url": FARS_COUNTY_BOUNDARY_URL,
        "raw_zip_sha256": FARS_COUNTY_PUBLIC_BOUNDARY_RAW_ZIP_SHA256,
        "raw_zip_size_bytes": FARS_COUNTY_PUBLIC_BOUNDARY_RAW_ZIP_SIZE_BYTES,
        "member_name": FARS_COUNTY_BOUNDARY_MEMBER,
        "member_sha256": FARS_COUNTY_PUBLIC_BOUNDARY_MEMBER_SHA256,
        "resolution": FARS_COUNTY_BOUNDARY_RESOLUTION,
        "conversion_version": FARS_COUNTY_BOUNDARY_CONVERSION_VERSION,
    }
    if dict(source) != expected:
        raise ValueError("public county boundary source provenance is inconsistent")
    return expected


def _rings(geometry: Mapping[str, object]) -> Sequence[Sequence[Sequence[float]]]:
    coordinates = cast(Sequence[object], geometry["coordinates"])
    if geometry["type"] == "Polygon":
        return cast(Sequence[Sequence[Sequence[float]]], coordinates)
    return [
        ring
        for polygon in cast(Sequence[Sequence[Sequence[Sequence[float]]]], coordinates)
        for ring in polygon
    ]


def _validate_geometry(geometry: Mapping[str, object]) -> int:
    if geometry.get("type") not in {"Polygon", "MultiPolygon"}:
        raise ValueError("public county boundary geometry type is invalid")
    coordinate_count = 0
    for ring in _rings(geometry):
        if len(ring) < 4 or ring[0] != ring[-1]:
            raise ValueError("public county boundary ring is invalid")
        area = 0.0
        for index in range(len(ring) - 1):
            position, next_position = ring[index], ring[index + 1]
            if len(position) != 2 or len(next_position) != 2:
                raise ValueError("public county boundary position arity is invalid")
            longitude, latitude = position
            if (
                not isinstance(longitude, (int, float))
                or not isinstance(latitude, (int, float))
                or not math.isfinite(longitude)
                or not math.isfinite(latitude)
                or not -180 <= longitude <= 180
                or not -90 <= latitude <= 90
            ):
                raise ValueError("public county boundary position is invalid")
            area += longitude * next_position[1] - next_position[0] * latitude
        if not math.isfinite(area) or abs(area) < 1e-12:
            raise ValueError("public county boundary ring has no measurable area")
        coordinate_count += len(ring)
    return coordinate_count


def _validate_features(
    features: Sequence[Mapping[str, object]], *, state_fips: str
) -> dict[str, int]:
    geoids: list[str] = []
    polygon_count = 0
    coordinate_count = 0
    for feature in features:
        properties = _mapping(feature["properties"], label="feature properties")
        geoid = cast(str, properties["geoid"])
        county_fips = cast(str, properties["county_fips"])
        if (
            feature["type"] != "Feature"
            or feature["id"] != geoid
            or _GEOID_RE.fullmatch(geoid) is None
            or _COUNTY_FIPS_RE.fullmatch(county_fips) is None
            or properties["state_fips"] != state_fips
            or geoid != state_fips + county_fips
        ):
            raise ValueError("public county boundary feature identity is inconsistent")
        geometry = _mapping(feature["geometry"], label="feature geometry")
        coordinate_count += _validate_geometry(geometry)
        polygon_count += geometry["type"] == "Polygon"
        geoids.append(geoid)
    if geoids != sorted(geoids) or len(geoids) != len(set(geoids)):
        raise ValueError("public county boundary features are not uniquely canonically ordered")
    return {
        "feature_count": len(features),
        "polygon_feature_count": polygon_count,
        "multipolygon_feature_count": len(features) - polygon_count,
        "coordinate_count": coordinate_count,
    }


def _state_identity(state: Mapping[str, object]) -> str:
    state_fips = state.get("state_fips")
    if not isinstance(state_fips, str) or _STATE_FIPS_RE.fullmatch(state_fips) is None:
        raise ValueError("public county boundary state FIPS is invalid")
    expected = _STATE_BY_FIPS.get(state_fips)
    if expected is None:
        raise ValueError("public county boundary state is outside reviewed coverage")
    if dict(state) != {
        "state_fips": state_fips,
        "state_abbreviation": expected[0],
        "state_name": expected[1],
    }:
        raise ValueError("public county boundary state identity is inconsistent")
    return state_fips


def validate_public_fars_county_boundary_state_artifact(artifact: Mapping[str, object]) -> None:
    """Reject malformed, noncanonical, or provenance-detached public geometry."""

    _schema_error(artifact)
    state_fips = _state_identity(_mapping(artifact["state"], label="state"))
    _boundary_source(_mapping(artifact["source"], label="source"))
    features = _sequence(artifact["features"], label="features")
    expected_accounting = _validate_features(features, state_fips=state_fips)
    if artifact["accounting"] != expected_accounting:
        raise ValueError("public county boundary accounting is inconsistent")


def _private_boundary_parts(
    private_boundary_shard: Mapping[str, object],
) -> tuple[str, Mapping[str, object], Mapping[str, object], Sequence[Mapping[str, object]]]:
    if (
        private_boundary_shard.get("schema_version") != FARS_COUNTY_PUBLIC_BOUNDARY_SCHEMA_VERSION
        or private_boundary_shard.get("artifact_type") != _PRIVATE_ARTIFACT_TYPE
        or private_boundary_shard.get("visibility") != "private"
    ):
        raise ValueError("county boundary input is not the reviewed private boundary contract")
    state_fips = private_boundary_shard.get("state_fips")
    if not isinstance(state_fips, str) or _STATE_FIPS_RE.fullmatch(state_fips) is None:
        raise ValueError("county boundary private state FIPS is invalid")
    if state_fips not in _STATE_BY_FIPS:
        raise ValueError("county boundary private state is outside reviewed coverage")
    source = _mapping(private_boundary_shard.get("source"), label="private source")
    accounting = _mapping(private_boundary_shard.get("accounting"), label="private accounting")
    features = _sequence(private_boundary_shard.get("features"), label="private features")
    if accounting != _validate_features(features, state_fips=state_fips):
        raise ValueError("county boundary private accounting is inconsistent")
    return state_fips, source, accounting, features


def build_public_fars_county_boundary_state_artifact(
    private_boundary_shard: Mapping[str, object],
) -> dict[str, object]:
    """Derive a public geometry shard without retaining the private envelope."""

    state_fips, source, accounting, features = _private_boundary_parts(private_boundary_shard)
    public_source = _boundary_source(source)
    abbreviation, state_name = _STATE_BY_FIPS[state_fips]
    artifact: dict[str, object] = {
        "schema_version": FARS_COUNTY_PUBLIC_BOUNDARY_SCHEMA_VERSION,
        "artifact_type": FARS_COUNTY_PUBLIC_BOUNDARY_ARTIFACT_TYPE,
        "visibility": "public",
        "state": {
            "state_fips": state_fips,
            "state_abbreviation": abbreviation,
            "state_name": state_name,
        },
        "source": public_source,
        "accounting": copy.deepcopy(dict(accounting)),
        "features": copy.deepcopy(list(features)),
    }
    validate_public_fars_county_boundary_state_artifact(artifact)
    return artifact


def canonical_public_fars_county_boundary_state_bytes(artifact: Mapping[str, object]) -> bytes:
    """Return canonical UTF-8 bytes only for a validated public boundary shard."""

    validate_public_fars_county_boundary_state_artifact(artifact)
    return _canonical_json_bytes(artifact)


def load_public_fars_county_boundary_state_bytes(payload: bytes) -> dict[str, object]:
    """Load exact bounded canonical public county-boundary bytes."""

    if type(payload) is not bytes:
        raise TypeError("public county boundary payload must be bytes")
    if not payload or len(payload) > FARS_COUNTY_PUBLIC_BOUNDARY_MAX_BYTES:
        raise ValueError("public county boundary exceeds its byte safety limit")
    try:
        value = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_strict_object,
            parse_constant=_reject_constant,
        )
    except UnicodeDecodeError as exc:
        raise ValueError("public county boundary is not UTF-8") from exc
    except (json.JSONDecodeError, RecursionError) as exc:
        raise ValueError("public county boundary is invalid JSON") from exc
    if not isinstance(value, dict):
        raise ValueError("public county boundary must be an object")
    artifact = cast(dict[str, object], value)
    validate_public_fars_county_boundary_state_artifact(artifact)
    if canonical_public_fars_county_boundary_state_bytes(artifact) != payload:
        raise ValueError("public county boundary is not canonical")
    return copy.deepcopy(artifact)
