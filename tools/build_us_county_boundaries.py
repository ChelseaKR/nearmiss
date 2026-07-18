#!/usr/bin/env python3
"""Build private, reviewable 2024 Census county-equivalent boundary shards.

The result is intentionally not a public site artifact.  It preserves only the
county-equivalent identities and simplified orientation geometry needed for a
future reviewed crosswalk, with every shard bound to exact Census source bytes.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import re
import stat
import urllib.request
import zipfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from types import MappingProxyType
from typing import cast
from xml.etree import ElementTree

from jsonschema import Draft202012Validator

from nearmiss.fars_public_context import FARS_PUBLIC_STATE_CROSSWALK

SCHEMA_VERSION = "1.0.0"
ARTIFACT_TYPE = "nearmiss.private.us_county_boundary_shard"
PRESENTATION_VINTAGE = 2024
RESOLUTION = "1:20,000,000"
CONVERSION_VERSION = "county-boundary-kml-to-rfc7946-v1"
SOURCE_URL = "https://www2.census.gov/geo/tiger/GENZ2024/kml/cb_2024_us_county_20m.zip"
SOURCE_SHA256 = "590c1bfc1ae2746163a7417100670680a4a0ca79a577771e3c7c6821eea5149f"
SOURCE_SIZE_BYTES = 802_100
KML_MEMBER = "cb_2024_us_county_20m.kml"
KML_MEMBER_SHA256 = "920cacc5b601d99a7b697a63ab16e0d846d34df271a34a2b278e5fd9cb8b6c12"
ALLOWED_MEMBERS = frozenset(
    {
        KML_MEMBER,
        "cb_2024_us_county_20m.kml.ea.iso.xml",
        "cb_2024_us_county_20m.kml.iso.xml",
    }
)
KML = "{http://www.opengis.net/kml/2.2}"
MAX_ARCHIVE_BYTES = 2 * 1024 * 1024
MAX_MEMBER_BYTES = 10 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 12 * 1024 * 1024
MAX_COMPRESSION_RATIO = 50
MAX_FEATURES_PER_STATE = 300
MAX_COORDINATES_PER_STATE = 500_000
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
PUBLISHED_DATA_ROOT = (REPOSITORY_ROOT / "data" / "published").resolve()

_STATE_FIPS_RE = re.compile(r"^[0-9]{2}$", re.ASCII)
_COUNTY_FIPS_RE = re.compile(r"^[0-9]{3}$", re.ASCII)
_GEOID_RE = re.compile(r"^[0-9]{5}$", re.ASCII)

# The state crosswalk is already reviewed for the existing state lens.  County
# output remains private, but it must use the same 50-state-and-DC scope.
EXPECTED_STATES = MappingProxyType(
    {
        f"{int(code):02d}": value
        for code, value in sorted(
            FARS_PUBLIC_STATE_CROSSWALK.items(), key=lambda item: int(item[0])
        )
    }
)


def _closed(properties: Mapping[str, object]) -> dict[str, object]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": list(properties),
        "properties": dict(properties),
    }


def _count(*, minimum: int = 0, maximum: int = MAX_COORDINATES_PER_STATE) -> dict[str, object]:
    return {"type": "integer", "minimum": minimum, "maximum": maximum}


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
_POLYGON_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["type", "coordinates"],
    "properties": {
        "type": {"const": "Polygon"},
        "coordinates": {"type": "array", "minItems": 1, "items": _RING_SCHEMA},
    },
}
_MULTIPOLYGON_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["type", "coordinates"],
    "properties": {
        "type": {"const": "MultiPolygon"},
        "coordinates": {
            "type": "array",
            "minItems": 1,
            "items": {"type": "array", "minItems": 1, "items": _RING_SCHEMA},
        },
    },
}
_SOURCE_SCHEMA = _closed(
    {
        "presentation_vintage": {"const": PRESENTATION_VINTAGE},
        "distribution_url": {"const": SOURCE_URL},
        "raw_zip_sha256": {"const": SOURCE_SHA256},
        "raw_zip_size_bytes": {"const": SOURCE_SIZE_BYTES},
        "member_name": {"const": KML_MEMBER},
        "member_sha256": {"const": KML_MEMBER_SHA256},
        "resolution": {"const": RESOLUTION},
        "conversion_version": {"const": CONVERSION_VERSION},
    }
)

BOUNDARY_SHARD_SCHEMA: dict[str, object] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "https://nearmiss.dev/schema/us-county-boundaries.schema.json",
    "title": "Private NearMiss state-sharded 2024 Census county-equivalent boundaries",
    "type": "object",
    "additionalProperties": False,
    "required": [
        "schema_version",
        "artifact_type",
        "visibility",
        "state_fips",
        "source",
        "accounting",
        "features",
    ],
    "properties": {
        "schema_version": {"const": SCHEMA_VERSION},
        "artifact_type": {"const": ARTIFACT_TYPE},
        "visibility": {"const": "private"},
        "state_fips": {"type": "string", "enum": list(EXPECTED_STATES)},
        "source": _SOURCE_SCHEMA,
        "accounting": _closed(
            {
                "feature_count": _count(minimum=1, maximum=MAX_FEATURES_PER_STATE),
                "polygon_feature_count": _count(maximum=MAX_FEATURES_PER_STATE),
                "multipolygon_feature_count": _count(maximum=MAX_FEATURES_PER_STATE),
                "coordinate_count": _count(minimum=4),
            }
        ),
        "features": {
            "type": "array",
            "minItems": 1,
            "maxItems": MAX_FEATURES_PER_STATE,
            "items": _closed(
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
            ),
        },
    },
}

_VALIDATOR = Draft202012Validator(BOUNDARY_SHARD_SCHEMA)


def _canonical_json_bytes(value: Mapping[str, object]) -> bytes:
    return (
        json.dumps(
            value, ensure_ascii=False, allow_nan=False, separators=(",", ":"), sort_keys=True
        )
        + "\n"
    ).encode("utf-8")


def _schema_error(shard: Mapping[str, object]) -> None:
    errors = sorted(_VALIDATOR.iter_errors(shard), key=lambda error: list(error.absolute_path))
    if errors:
        error = errors[0]
        path = "/".join(str(part) for part in error.absolute_path) or "(root)"
        raise ValueError(f"invalid private county boundary shard at {path}: {error.message}")


def _safe_text(value: object, *, label: str, maximum: int) -> str:
    if not isinstance(value, str) or not value or value != value.strip() or len(value) > maximum:
        raise ValueError(f"Census county {label} is invalid")
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise ValueError(f"Census county {label} contains control characters")
    return value


def _strict_fips(value: object, *, label: str, pattern: re.Pattern[str]) -> str:
    if not isinstance(value, str) or not pattern.fullmatch(value):
        raise ValueError(f"Census county {label} is invalid")
    return value


def _validate_archive_member(info: zipfile.ZipInfo) -> int:
    if info.is_dir() or stat.S_ISLNK(info.external_attr >> 16):
        raise ValueError("Census county archive contains an unsafe member")
    if info.file_size > MAX_MEMBER_BYTES:
        raise ValueError("Census county archive member exceeds its safety limit")
    if info.compress_size <= 0 or info.file_size > info.compress_size * MAX_COMPRESSION_RATIO:
        raise ValueError("Census county archive member exceeds its compression safety limit")
    return info.file_size


def _validate_zip(archive: bytes) -> bytes:
    if len(archive) != SOURCE_SIZE_BYTES:
        raise ValueError("Census county archive byte size does not match the reviewed release")
    actual_sha = hashlib.sha256(archive).hexdigest()
    if actual_sha != SOURCE_SHA256:
        raise ValueError(
            f"Census county archive SHA-256 mismatch: expected {SOURCE_SHA256}, got {actual_sha}"
        )
    if len(archive) > MAX_ARCHIVE_BYTES:
        raise ValueError("Census county archive exceeds its compressed safety limit")
    try:
        source_zip = zipfile.ZipFile(io.BytesIO(archive))
    except zipfile.BadZipFile as exc:
        raise ValueError("Census county archive is not a ZIP") from exc
    with source_zip:
        infos = source_zip.infolist()
        if {info.filename for info in infos} != ALLOWED_MEMBERS:
            raise ValueError("Census county archive has unexpected members")
        total_uncompressed = sum(_validate_archive_member(info) for info in infos)
        if total_uncompressed > MAX_UNCOMPRESSED_BYTES:
            raise ValueError("Census county archive exceeds its uncompressed safety limit")
        kml = source_zip.read(KML_MEMBER)
    if hashlib.sha256(kml).hexdigest() != KML_MEMBER_SHA256:
        raise ValueError("Census county KML member SHA-256 mismatch")
    if b"<!DOCTYPE" in kml.upper() or b"<!ENTITY" in kml.upper():
        raise ValueError("Census county KML declares an unsafe XML entity")
    return kml


def _coordinates(text: str | None) -> list[list[float]]:
    if not text:
        raise ValueError("Census county polygon ring has no coordinates")
    ring: list[list[float]] = []
    for token in text.split():
        parts = token.split(",")
        if not 2 <= len(parts) <= 3:
            raise ValueError("Census county coordinate has an invalid arity")
        try:
            longitude, latitude = float(parts[0]), float(parts[1])
        except ValueError as exc:
            raise ValueError("Census county coordinate is not numeric") from exc
        if not math.isfinite(longitude) or not math.isfinite(latitude):
            raise ValueError("Census county coordinate is not finite")
        if not -180 <= longitude <= 180 or not -90 <= latitude <= 90:
            raise ValueError("Census county coordinate is outside WGS84 bounds")
        ring.append([round(longitude, 6), round(latitude, 6)])
    if len(ring) < 4 or ring[0] != ring[-1]:
        raise ValueError("Census county polygon ring is not closed")
    area = sum(
        ring[index][0] * ring[index + 1][1] - ring[index + 1][0] * ring[index][1]
        for index in range(len(ring) - 1)
    )
    if not math.isfinite(area) or abs(area) < 1e-12:
        raise ValueError("Census county polygon ring has no measurable area")
    return ring


def _ring(boundary: ElementTree.Element | None) -> list[list[float]]:
    if boundary is None:
        raise ValueError("Census county polygon is missing a boundary")
    coordinates = boundary.find(f"{KML}LinearRing/{KML}coordinates")
    return _coordinates(coordinates.text if coordinates is not None else None)


def _geometry(placemark: ElementTree.Element) -> dict[str, object]:
    polygons: list[list[list[list[float]]]] = []
    for polygon in placemark.findall(f".//{KML}Polygon"):
        rings = [_ring(polygon.find(f"{KML}outerBoundaryIs"))]
        rings.extend(_ring(inner) for inner in polygon.findall(f"{KML}innerBoundaryIs"))
        polygons.append(rings)
    if not polygons:
        raise ValueError("Census county placemark has no polygon")
    if len(polygons) == 1:
        return {"type": "Polygon", "coordinates": polygons[0]}
    return {"type": "MultiPolygon", "coordinates": polygons}


def _placemark_values(placemark: ElementTree.Element) -> dict[str, str]:
    values: dict[str, str] = {}
    for item in placemark.findall(f".//{KML}SimpleData"):
        key = item.attrib.get("name")
        if not key or key in values:
            raise ValueError("Census county placemark has duplicate or missing field names")
        values[key] = item.text or ""
    required = {"STATEFP", "COUNTYFP", "GEOID", "NAME", "NAMELSAD", "STUSPS", "STATE_NAME"}
    missing = required - set(values)
    if missing:
        raise ValueError(f"Census county placemark is missing fields: {sorted(missing)}")
    return values


def _boundary_source() -> dict[str, object]:
    return {
        "presentation_vintage": PRESENTATION_VINTAGE,
        "distribution_url": SOURCE_URL,
        "raw_zip_sha256": SOURCE_SHA256,
        "raw_zip_size_bytes": SOURCE_SIZE_BYTES,
        "member_name": KML_MEMBER,
        "member_sha256": KML_MEMBER_SHA256,
        "resolution": RESOLUTION,
        "conversion_version": CONVERSION_VERSION,
    }


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
    geometry_type = geometry.get("type")
    if geometry_type not in {"Polygon", "MultiPolygon"}:
        raise ValueError("private county boundary geometry type is invalid")
    coordinate_count = 0
    for ring in _rings(geometry):
        if len(ring) < 4 or ring[0] != ring[-1]:
            raise ValueError("private county boundary ring is invalid")
        area = 0.0
        for index in range(len(ring) - 1):
            position, next_position = ring[index], ring[index + 1]
            if len(position) != 2 or len(next_position) != 2:
                raise ValueError("private county boundary position arity is invalid")
            longitude, latitude = position
            if not all(
                isinstance(value, (int, float)) and math.isfinite(value) for value in position
            ):
                raise ValueError("private county boundary position is invalid")
            if not -180 <= longitude <= 180 or not -90 <= latitude <= 90:
                raise ValueError("private county boundary position is outside WGS84 bounds")
            area += longitude * next_position[1] - next_position[0] * latitude
        if abs(area) < 1e-12:
            raise ValueError("private county boundary ring has no measurable area")
        coordinate_count += len(ring)
    return coordinate_count


def validate_boundary_shard(shard: Mapping[str, object]) -> None:
    """Reject a malformed, noncanonical, or cross-state private boundary shard."""

    _schema_error(shard)
    state_fips = cast(str, shard["state_fips"])
    features = cast(list[Mapping[str, object]], shard["features"])
    ids = [cast(str, feature["id"]) for feature in features]
    if ids != sorted(ids) or len(ids) != len(set(ids)):
        raise ValueError("private county boundary features are not uniquely canonically ordered")
    polygon_count = 0
    multipolygon_count = 0
    coordinate_count = 0
    for feature in features:
        properties = cast(Mapping[str, object], feature["properties"])
        feature_state_fips = cast(str, properties["state_fips"])
        county_fips = cast(str, properties["county_fips"])
        geoid = cast(str, properties["geoid"])
        if (
            feature_state_fips != state_fips
            or geoid != feature_state_fips + county_fips
            or feature["id"] != geoid
        ):
            raise ValueError("private county boundary feature identity is inconsistent")
        geometry = cast(Mapping[str, object], feature["geometry"])
        coordinate_count += _validate_geometry(geometry)
        if geometry["type"] == "Polygon":
            polygon_count += 1
        else:
            multipolygon_count += 1
    accounting = cast(Mapping[str, int], shard["accounting"])
    if accounting != {
        "feature_count": len(features),
        "polygon_feature_count": polygon_count,
        "multipolygon_feature_count": multipolygon_count,
        "coordinate_count": coordinate_count,
    }:
        raise ValueError("private county boundary shard accounting is inconsistent")


def _shard(state_fips: str, features: Sequence[Mapping[str, object]]) -> dict[str, object]:
    ordered_features = sorted(
        (dict(feature) for feature in features), key=lambda feature: str(feature["id"])
    )
    polygon_count = sum(
        cast(Mapping[str, object], feature["geometry"])["type"] == "Polygon"
        for feature in ordered_features
    )
    coordinate_count = sum(
        _validate_geometry(cast(Mapping[str, object], feature["geometry"]))
        for feature in ordered_features
    )
    shard: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": ARTIFACT_TYPE,
        "visibility": "private",
        "state_fips": state_fips,
        "source": _boundary_source(),
        "accounting": {
            "feature_count": len(ordered_features),
            "polygon_feature_count": polygon_count,
            "multipolygon_feature_count": len(ordered_features) - polygon_count,
            "coordinate_count": coordinate_count,
        },
        "features": ordered_features,
    }
    validate_boundary_shard(shard)
    return shard


def convert(archive: bytes) -> dict[str, dict[str, object]]:
    """Convert exact reviewed Census ZIP bytes into private canonical state shards."""

    kml = _validate_zip(archive)
    try:
        root = ElementTree.fromstring(kml)
    except ElementTree.ParseError as exc:
        raise ValueError("Census county KML is invalid XML") from exc
    by_state: dict[str, list[dict[str, object]]] = {
        state_fips: [] for state_fips in EXPECTED_STATES
    }
    seen_geoids: set[str] = set()
    for placemark in root.findall(f".//{KML}Placemark"):
        values = _placemark_values(placemark)
        state_fips = _strict_fips(values["STATEFP"], label="state FIPS", pattern=_STATE_FIPS_RE)
        if state_fips not in EXPECTED_STATES:
            continue
        abbreviation, state_name = EXPECTED_STATES[state_fips]
        if values["STUSPS"] != abbreviation or values["STATE_NAME"] != state_name:
            raise ValueError(f"unexpected Census county state crosswalk for FIPS {state_fips}")
        county_fips = _strict_fips(values["COUNTYFP"], label="county FIPS", pattern=_COUNTY_FIPS_RE)
        geoid = _strict_fips(values["GEOID"], label="GEOID", pattern=_GEOID_RE)
        if geoid != state_fips + county_fips:
            raise ValueError("Census county GEOID does not match its FIPS components")
        if geoid in seen_geoids:
            raise ValueError(f"duplicate Census county GEOID: {geoid}")
        seen_geoids.add(geoid)
        by_state[state_fips].append(
            {
                "type": "Feature",
                "id": geoid,
                "properties": {
                    "state_fips": state_fips,
                    "county_fips": county_fips,
                    "geoid": geoid,
                    "name": _safe_text(values["NAME"], label="name", maximum=128),
                    "namelsad": _safe_text(values["NAMELSAD"], label="NAMELSAD", maximum=160),
                },
                "geometry": _geometry(placemark),
            }
        )
    missing = [state_fips for state_fips, features in by_state.items() if not features]
    if missing:
        raise ValueError(f"Census county archive is missing expected states: {missing}")
    return {state_fips: _shard(state_fips, features) for state_fips, features in by_state.items()}


def canonical_boundary_shard_bytes(shard: Mapping[str, object]) -> bytes:
    """Return canonical bytes for one validated private state shard."""

    validate_boundary_shard(shard)
    return _canonical_json_bytes(shard)


def _is_public_output_path(out_dir: Path) -> bool:
    try:
        out_dir.resolve(strict=False).relative_to(PUBLISHED_DATA_ROOT)
    except ValueError:
        return False
    return True


def write_shards(shards: Mapping[str, Mapping[str, object]], out_dir: Path) -> list[Path]:
    """Write canonical private shards beneath an explicit non-public directory."""

    if _is_public_output_path(out_dir):
        raise ValueError("private county boundary shards must not be written to data/published")
    serialized: list[tuple[Path, bytes]] = []
    for state_fips, shard in sorted(shards.items()):
        if state_fips != shard.get("state_fips"):
            raise ValueError("private county boundary shard filename state is inconsistent")
        path = out_dir / f"{state_fips}.json"
        serialized.append((path, canonical_boundary_shard_bytes(shard)))
    out_dir.mkdir(parents=True, exist_ok=True)
    for path, payload in serialized:
        path.write_bytes(payload)
    return [path for path, _payload in serialized]


def _download() -> bytes:
    request = urllib.request.Request(
        SOURCE_URL, headers={"User-Agent": "nearmiss-county-boundary-builder/1"}
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return bytes(response.read(MAX_ARCHIVE_BYTES + 1))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--archive", type=Path, help="use an already-downloaded reviewed Census ZIP"
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("build/private-county-boundaries-2024"),
        help="private output directory; this command never writes data/published",
    )
    args = parser.parse_args()
    archive_path = cast(Path | None, args.archive)
    out_dir = cast(Path, args.out_dir)
    if _is_public_output_path(out_dir):
        parser.error("--out-dir must not be inside data/published")
    archive = archive_path.read_bytes() if archive_path else _download()
    paths = write_shards(convert(archive), out_dir)
    print(f"private county boundaries: {len(paths)} state shards -> {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
