#!/usr/bin/env python3
"""Build the public 2024 US state boundary asset from a pinned Census KML.

The visualization uses geometry only for orientation. Fatal-crash values remain
exclusively sourced from the separately verified FARS projection. The input is
the Census Bureau's national 1:20,000,000 cartographic boundary archive; the
output deliberately retains only the 50 states and District of Columbia.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import urllib.request
import zipfile
from pathlib import Path
from typing import TypedDict, cast
from xml.etree import ElementTree

SOURCE_URL = "https://www2.census.gov/geo/tiger/GENZ2024/kml/cb_2024_us_state_20m.zip"
SOURCE_SHA256 = "37337db59415f010c594fba96a48aa6e950e633dc0e555cc7b1ce8edd794c673"
KML_MEMBER = "cb_2024_us_state_20m.kml"
KML = "{http://www.opengis.net/kml/2.2}"

EXPECTED_STATES = {
    "01": ("AL", "Alabama"),
    "02": ("AK", "Alaska"),
    "04": ("AZ", "Arizona"),
    "05": ("AR", "Arkansas"),
    "06": ("CA", "California"),
    "08": ("CO", "Colorado"),
    "09": ("CT", "Connecticut"),
    "10": ("DE", "Delaware"),
    "11": ("DC", "District of Columbia"),
    "12": ("FL", "Florida"),
    "13": ("GA", "Georgia"),
    "15": ("HI", "Hawaii"),
    "16": ("ID", "Idaho"),
    "17": ("IL", "Illinois"),
    "18": ("IN", "Indiana"),
    "19": ("IA", "Iowa"),
    "20": ("KS", "Kansas"),
    "21": ("KY", "Kentucky"),
    "22": ("LA", "Louisiana"),
    "23": ("ME", "Maine"),
    "24": ("MD", "Maryland"),
    "25": ("MA", "Massachusetts"),
    "26": ("MI", "Michigan"),
    "27": ("MN", "Minnesota"),
    "28": ("MS", "Mississippi"),
    "29": ("MO", "Missouri"),
    "30": ("MT", "Montana"),
    "31": ("NE", "Nebraska"),
    "32": ("NV", "Nevada"),
    "33": ("NH", "New Hampshire"),
    "34": ("NJ", "New Jersey"),
    "35": ("NM", "New Mexico"),
    "36": ("NY", "New York"),
    "37": ("NC", "North Carolina"),
    "38": ("ND", "North Dakota"),
    "39": ("OH", "Ohio"),
    "40": ("OK", "Oklahoma"),
    "41": ("OR", "Oregon"),
    "42": ("PA", "Pennsylvania"),
    "44": ("RI", "Rhode Island"),
    "45": ("SC", "South Carolina"),
    "46": ("SD", "South Dakota"),
    "47": ("TN", "Tennessee"),
    "48": ("TX", "Texas"),
    "49": ("UT", "Utah"),
    "50": ("VT", "Vermont"),
    "51": ("VA", "Virginia"),
    "53": ("WA", "Washington"),
    "54": ("WV", "West Virginia"),
    "55": ("WI", "Wisconsin"),
    "56": ("WY", "Wyoming"),
}


class BoundaryFeature(TypedDict):
    type: str
    id: str
    properties: dict[str, str]
    geometry: dict[str, object]


class BoundaryCollection(TypedDict):
    type: str
    name: str
    source: dict[str, object]
    features: list[BoundaryFeature]


def _coordinates(text: str | None) -> list[list[float]]:
    if not text:
        raise ValueError("Census polygon ring has no coordinates")
    ring = [
        [round(float(parts[0]), 6), round(float(parts[1]), 6)]
        for token in text.split()
        if len(parts := token.split(",")) >= 2
    ]
    if len(ring) < 4:
        raise ValueError("Census polygon ring has fewer than four positions")
    if ring[0] != ring[-1]:
        ring.append(ring[0])
    return ring


def _ring(boundary: ElementTree.Element | None) -> list[list[float]]:
    if boundary is None:
        raise ValueError("Census polygon is missing a boundary")
    coordinates = boundary.find(f"{KML}LinearRing/{KML}coordinates")
    return _coordinates(coordinates.text if coordinates is not None else None)


def _geometry(placemark: ElementTree.Element) -> dict[str, object]:
    polygons: list[list[list[list[float]]]] = []
    for polygon in placemark.findall(f".//{KML}Polygon"):
        rings = [_ring(polygon.find(f"{KML}outerBoundaryIs"))]
        rings.extend(_ring(inner) for inner in polygon.findall(f"{KML}innerBoundaryIs"))
        polygons.append(rings)
    if not polygons:
        raise ValueError("Census state placemark has no polygon")
    if len(polygons) == 1:
        return {"type": "Polygon", "coordinates": polygons[0]}
    return {"type": "MultiPolygon", "coordinates": polygons}


def convert(archive: bytes) -> BoundaryCollection:
    actual_sha = hashlib.sha256(archive).hexdigest()
    if actual_sha != SOURCE_SHA256:
        raise ValueError(
            f"Census archive SHA-256 mismatch: expected {SOURCE_SHA256}, got {actual_sha}"
        )
    with zipfile.ZipFile(io.BytesIO(archive)) as source_zip:
        root = ElementTree.fromstring(source_zip.read(KML_MEMBER))

    features: list[BoundaryFeature] = []
    seen: set[str] = set()
    for placemark in root.findall(f".//{KML}Placemark"):
        values = {
            item.attrib.get("name", ""): (item.text or "")
            for item in placemark.findall(f".//{KML}SimpleData")
        }
        state_fips = values.get("STATEFP")
        if state_fips not in EXPECTED_STATES:
            continue
        abbreviation, name = EXPECTED_STATES[state_fips]
        if values.get("STUSPS") != abbreviation or values.get("NAME") != name:
            raise ValueError(f"unexpected Census state crosswalk for FIPS {state_fips}")
        if state_fips in seen:
            raise ValueError(f"duplicate Census state placemark for FIPS {state_fips}")
        seen.add(state_fips)
        features.append(
            {
                "type": "Feature",
                "id": abbreviation,
                "properties": {
                    "state_fips": state_fips,
                    "state_abbreviation": abbreviation,
                    "state_name": name,
                },
                "geometry": _geometry(placemark),
            }
        )

    missing = set(EXPECTED_STATES) - seen
    if missing:
        raise ValueError(f"Census archive is missing expected states: {sorted(missing)}")
    features.sort(key=lambda feature: str(feature["properties"]["state_fips"]))
    return {
        "type": "FeatureCollection",
        "name": "2024 Census cartographic boundaries for the 50 states and DC",
        "source": {
            "name": "U.S. Census Bureau 2024 Cartographic Boundary Files",
            "vintage": 2024,
            "resolution": "1:20,000,000",
            "distribution_url": SOURCE_URL,
            "raw_zip_sha256": SOURCE_SHA256,
            "raw_zip_size_bytes": len(archive),
            "conversion": (
                "KML polygons to RFC 7946 GeoJSON; coordinates rounded to 6 decimals; "
                "50 states and DC retained"
            ),
        },
        "features": features,
    }


def _download() -> bytes:
    request = urllib.request.Request(
        SOURCE_URL,
        headers={"User-Agent": "nearmiss-boundary-builder/1"},
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return bytes(response.read())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, help="use an already-downloaded pinned Census ZIP")
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("data/published/us-state-boundaries-2024.json"),
    )
    args = parser.parse_args()
    archive_path = cast(Path | None, args.archive)
    out_path = cast(Path, args.out)
    archive = archive_path.read_bytes() if archive_path else _download()
    boundary_data = convert(archive)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(boundary_data, ensure_ascii=False, separators=(",", ":")) + "\n"
    out_path.write_text(payload, encoding="utf-8")
    print(f"boundaries: {out_path} ({len(boundary_data['features'])} jurisdictions)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
