# SPDX-License-Identifier: Apache-2.0
"""Private, fully reconciled county-level FARS projection contracts.

This is deliberately not a public-map builder.  It can project the already
proof-bound county feasibility cells only when an explicitly reviewed FARS GSA
to Census county-equivalent crosswalk and corresponding private Census boundary
shards are complete.  Sentinel geography stays out of county cells while
remaining in reconciliation accounting.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from typing import cast

from jsonschema import Draft202012Validator

from .adapters.fars_joined import MODE_ORDER
from .fars_county_crosswalk import (
    FARS_COUNTY_BOUNDARY_CONVERSION_VERSION,
    FARS_COUNTY_BOUNDARY_MEMBER,
    FARS_COUNTY_BOUNDARY_PRESENTATION_VINTAGE,
    FARS_COUNTY_BOUNDARY_RESOLUTION,
    FARS_COUNTY_BOUNDARY_URL,
    canonical_fars_county_crosswalk_bytes,
    require_fars_county_crosswalk_resolved,
)
from .fars_county_feasibility import (
    canonical_fars_county_feasibility_bytes,
    validate_fars_county_feasibility_artifact,
)
from .fars_public_context import FARS_PUBLIC_STATE_CROSSWALK

FARS_COUNTY_PROJECTION_SCHEMA_VERSION = "1.0.0"
FARS_COUNTY_PROJECTION_ARTIFACT_TYPE = "nearmiss.private.fars_county_projection"
FARS_COUNTY_PROJECTION_BUILDER_VERSION = "fars-county-projection-v1"

_MAX_STATES = len(FARS_PUBLIC_STATE_CROSSWALK)
_MAX_COUNTY_CELLS = 20_000
_MAX_CONTRIBUTIONS = 200_000
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$", re.ASCII)
_STATE_CODE_RE = re.compile(r"^[1-9][0-9]?$", re.ASCII)
_FIPS_RE = re.compile(r"^[0-9]{2}$", re.ASCII)
_GEOID_RE = re.compile(r"^[0-9]{5}$", re.ASCII)
_COUNTY_FIPS_RE = re.compile(r"^[0-9]{3}$", re.ASCII)
_STATE_FIPS_BY_CODE = {
    state_code: f"{int(state_code):02d}" for state_code in FARS_PUBLIC_STATE_CROSSWALK
}
_EXPECTED_STATE_FIPS = frozenset(_STATE_FIPS_BY_CODE.values())


def _closed(properties: Mapping[str, object]) -> dict[str, object]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": list(properties),
        "properties": dict(properties),
    }


def _count(*, minimum: int = 0, maximum: int = _MAX_CONTRIBUTIONS) -> dict[str, object]:
    return {"type": "integer", "minimum": minimum, "maximum": maximum}


_SHA256 = {"type": "string", "pattern": "^[0-9a-f]{64}$"}
_BOUNDARY_SOURCE_SCHEMA = _closed(
    {
        "presentation_vintage": {"const": FARS_COUNTY_BOUNDARY_PRESENTATION_VINTAGE},
        "distribution_url": {"const": FARS_COUNTY_BOUNDARY_URL},
        "raw_zip_sha256": _SHA256,
        "raw_zip_size_bytes": _count(minimum=1, maximum=64 * 1024 * 1024),
        "member_name": {"const": FARS_COUNTY_BOUNDARY_MEMBER},
        "member_sha256": _SHA256,
        "resolution": {"const": FARS_COUNTY_BOUNDARY_RESOLUTION},
        "conversion_version": {"const": FARS_COUNTY_BOUNDARY_CONVERSION_VERSION},
    }
)
_CELL_SCHEMA = _closed(
    {
        "geoid": {"type": "string", "pattern": "^[0-9]{5}$"},
        "involved_mode": {"type": "string", "enum": list(MODE_ORDER)},
        "crash_count": _count(minimum=1),
    }
)
_STATE_SCHEMA = _closed(
    {
        "state_code": {"type": "string", "enum": sorted(FARS_PUBLIC_STATE_CROSSWALK, key=int)},
        "state_fips": {"type": "string", "pattern": "^[0-9]{2}$"},
        "accounting": _closed(
            {
                "source_county_cell_count": _count(maximum=_MAX_COUNTY_CELLS),
                "projected_county_cell_count": _count(maximum=_MAX_COUNTY_CELLS),
                "projected_contribution_total": _count(),
                "sentinel_contribution_total": _count(),
                "source_contribution_total": _count(minimum=1),
            }
        ),
        "cells": {"type": "array", "maxItems": _MAX_COUNTY_CELLS, "items": _CELL_SCHEMA},
    }
)

FARS_COUNTY_PROJECTION_ARTIFACT_SCHEMA: dict[str, object] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "https://nearmiss.dev/schema/private-fars-county-projection.schema.json",
    "title": "Private NearMiss reconciled FARS county-equivalent projection",
    "type": "object",
    "additionalProperties": False,
    "required": [
        "schema_version",
        "artifact_type",
        "visibility",
        "dataset_year",
        "source_lineage",
        "method",
        "accounting",
        "states",
    ],
    "properties": {
        "schema_version": {"const": FARS_COUNTY_PROJECTION_SCHEMA_VERSION},
        "artifact_type": {"const": FARS_COUNTY_PROJECTION_ARTIFACT_TYPE},
        "visibility": {"const": "private"},
        "dataset_year": {"type": "integer", "minimum": 2020, "maximum": 2024},
        "source_lineage": _closed(
            {
                "feasibility_sha256": _SHA256,
                "crosswalk_sha256": _SHA256,
                "boundary": _BOUNDARY_SOURCE_SCHEMA,
                "builder_version": {"const": FARS_COUNTY_PROJECTION_BUILDER_VERSION},
            }
        ),
        "method": _closed(
            {
                "dimension": {"const": "involved_mode"},
                "contribution_unit": {"const": "distinct_crash_once_per_involved_mode"},
                "modes_non_additive": {"const": True},
                "sentinel_handling": {"const": "excluded_from_county_cells_accounted_separately"},
            }
        ),
        "accounting": _closed(
            {
                "state_count": _count(minimum=1, maximum=_MAX_STATES),
                "source_county_cell_count": _count(maximum=_MAX_COUNTY_CELLS),
                "projected_county_cell_count": _count(maximum=_MAX_COUNTY_CELLS),
                "projected_contribution_total": _count(),
                "sentinel_contribution_total": _count(),
                "source_contribution_total": _count(minimum=1),
            }
        ),
        "states": {"type": "array", "minItems": 1, "maxItems": _MAX_STATES, "items": _STATE_SCHEMA},
    },
}

_VALIDATOR = Draft202012Validator(FARS_COUNTY_PROJECTION_ARTIFACT_SCHEMA)


def _canonical_json_bytes(value: Mapping[str, object]) -> bytes:
    return (
        json.dumps(
            value, ensure_ascii=False, allow_nan=False, separators=(",", ":"), sort_keys=True
        )
        + "\n"
    ).encode("utf-8")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _schema_error(artifact: Mapping[str, object]) -> None:
    errors = sorted(_VALIDATOR.iter_errors(artifact), key=lambda error: list(error.absolute_path))
    if errors:
        error = errors[0]
        path = "/".join(str(part) for part in error.absolute_path) or "(root)"
        raise ValueError(f"invalid private FARS county projection at {path}: {error.message}")


def _mapping(value: object, *, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"private county projection has an invalid {label}")
    return value


def _sequence(value: object, *, label: str) -> Sequence[Mapping[str, object]]:
    if not isinstance(value, list) or any(not isinstance(item, Mapping) for item in value):
        raise ValueError(f"private county projection has an invalid {label}")
    return cast(Sequence[Mapping[str, object]], value)


def _boundary_feature_index(
    boundary_shards: Mapping[str, Mapping[str, object]],
    *,
    expected_source: Mapping[str, object],
) -> dict[str, Mapping[str, Mapping[str, object]]]:
    if set(boundary_shards) != _EXPECTED_STATE_FIPS:
        raise ValueError(
            "private county projection boundary shards do not cover the reviewed states"
        )
    indexed: dict[str, Mapping[str, Mapping[str, object]]] = {}
    for state_fips, shard in boundary_shards.items():
        if not _FIPS_RE.fullmatch(state_fips):
            raise ValueError("private county projection boundary shard key is invalid")
        if shard.get("visibility") != "private" or shard.get("state_fips") != state_fips:
            raise ValueError("private county projection boundary shard identity is inconsistent")
        source = _mapping(shard.get("source"), label="boundary source")
        if dict(source) != dict(expected_source):
            raise ValueError("private county projection boundary source does not match crosswalk")
        features = _sequence(shard.get("features"), label="boundary features")
        by_geoid: dict[str, Mapping[str, object]] = {}
        for feature in features:
            if feature.get("type") != "Feature" or not isinstance(feature.get("id"), str):
                raise ValueError("private county projection boundary feature is invalid")
            properties = _mapping(feature.get("properties"), label="boundary feature properties")
            feature_state = properties.get("state_fips")
            county_fips = properties.get("county_fips")
            geoid = properties.get("geoid")
            name = properties.get("name")
            namelsad = properties.get("namelsad")
            if (
                feature_state != state_fips
                or not isinstance(county_fips, str)
                or _COUNTY_FIPS_RE.fullmatch(county_fips) is None
                or not isinstance(geoid, str)
                or _GEOID_RE.fullmatch(geoid) is None
                or geoid != state_fips + county_fips
                or feature["id"] != geoid
                or not isinstance(name, str)
                or not name
                or not isinstance(namelsad, str)
                or not namelsad
                or geoid in by_geoid
            ):
                raise ValueError(
                    "private county projection boundary feature identity is inconsistent"
                )
            by_geoid[geoid] = properties
        if not by_geoid:
            raise ValueError("private county projection boundary shard is empty")
        indexed[state_fips] = by_geoid
    return indexed


def _crosswalk_index(
    artifact: Mapping[str, object],
    *,
    boundary_features: Mapping[str, Mapping[str, Mapping[str, object]]],
) -> dict[tuple[str, str], Mapping[str, object]]:
    require_fars_county_crosswalk_resolved(artifact)
    rows = _sequence(artifact.get("rows"), label="crosswalk rows")
    index: dict[tuple[str, str], Mapping[str, object]] = {}
    for row in rows:
        state_code = row.get("state_code")
        county_code = row.get("county_code")
        presentation = _mapping(row.get("presentation"), label="crosswalk presentation")
        if not isinstance(state_code, str) or _STATE_CODE_RE.fullmatch(state_code) is None:
            raise ValueError("private county projection crosswalk state code is invalid")
        if not isinstance(county_code, str) or re.fullmatch(r"[0-9]{3}", county_code) is None:
            raise ValueError("private county projection crosswalk county code is invalid")
        state_fips = _STATE_FIPS_BY_CODE.get(state_code)
        geoid = presentation.get("geoid")
        if state_fips is None or not isinstance(geoid, str):
            raise ValueError("private county projection crosswalk identity is invalid")
        boundary = boundary_features[state_fips].get(geoid)
        if boundary is None or any(
            presentation.get(key) != boundary.get(key)
            for key in ("state_fips", "county_fips", "geoid", "name", "namelsad")
        ):
            raise ValueError("private county projection crosswalk target lacks matching boundary")
        key = (state_code, county_code)
        if key in index:
            raise ValueError("private county projection crosswalk source key is duplicated")
        index[key] = presentation
    return index


def _canonical_state_cells(cells: Sequence[Mapping[str, object]]) -> None:
    actual = [(cast(str, cell["geoid"]), cast(str, cell["involved_mode"])) for cell in cells]
    expected = sorted(actual, key=lambda key: (int(key[0]), MODE_ORDER.index(key[1])))
    if actual != expected or len(actual) != len(set(actual)):
        raise ValueError("private county projection cells are not uniquely canonically ordered")


def validate_fars_county_projection_artifact(artifact: Mapping[str, object]) -> None:
    """Reject malformed, unreconciled, noncanonical, or public-like projections."""

    _schema_error(artifact)
    states = _sequence(artifact["states"], label="states")
    state_codes = [cast(str, state["state_code"]) for state in states]
    if state_codes != sorted(state_codes, key=int) or len(state_codes) != len(set(state_codes)):
        raise ValueError("private county projection states are not uniquely canonically ordered")
    if set(state_codes) != set(FARS_PUBLIC_STATE_CROSSWALK):
        raise ValueError("private county projection does not cover the reviewed national states")

    source_cells = 0
    projected_cells = 0
    projected_total = 0
    sentinel_total = 0
    source_total = 0
    for state in states:
        state_code = cast(str, state["state_code"])
        state_fips = cast(str, state["state_fips"])
        if _STATE_FIPS_BY_CODE[state_code] != state_fips:
            raise ValueError("private county projection state identity is inconsistent")
        cells = _sequence(state["cells"], label="state cells")
        _canonical_state_cells(cells)
        for cell in cells:
            geoid = cast(str, cell["geoid"])
            if not geoid.startswith(state_fips):
                raise ValueError("private county projection cell crosses a state boundary")
        cell_total = sum(cast(int, cell["crash_count"]) for cell in cells)
        accounting = _mapping(state["accounting"], label="state accounting")
        source_cell_count = cast(int, accounting["source_county_cell_count"])
        state_projected_total = cast(int, accounting["projected_contribution_total"])
        state_sentinel_total = cast(int, accounting["sentinel_contribution_total"])
        state_source_total = cast(int, accounting["source_contribution_total"])
        if not (
            accounting["projected_county_cell_count"] == len(cells)
            and state_projected_total == cell_total
            and source_cell_count >= len(cells)
            and state_source_total == cell_total + state_sentinel_total
        ):
            raise ValueError("private county projection state accounting is inconsistent")
        source_cells += source_cell_count
        projected_cells += len(cells)
        projected_total += cell_total
        sentinel_total += state_sentinel_total
        source_total += state_source_total

    accounting = _mapping(artifact["accounting"], label="accounting")
    if accounting != {
        "state_count": len(states),
        "source_county_cell_count": source_cells,
        "projected_county_cell_count": projected_cells,
        "projected_contribution_total": projected_total,
        "sentinel_contribution_total": sentinel_total,
        "source_contribution_total": source_total,
    }:
        raise ValueError("private county projection accounting is inconsistent")
    if source_total != projected_total + sentinel_total:
        raise ValueError("private county projection does not reconcile sentinel contributions")


def build_private_fars_county_projection(
    feasibility_artifact: Mapping[str, object],
    crosswalk_artifact: Mapping[str, object],
    boundary_shards: Mapping[str, Mapping[str, object]],
) -> dict[str, object]:
    """Build private county cells only after all three review gates reconcile."""

    validate_fars_county_feasibility_artifact(feasibility_artifact)
    require_fars_county_crosswalk_resolved(crosswalk_artifact)
    feasibility_year = cast(int, feasibility_artifact["dataset_year"])
    if crosswalk_artifact.get("dataset_year") != feasibility_year:
        raise ValueError("private county projection artifacts use different dataset years")
    feasibility_source = _mapping(
        feasibility_artifact["source_lineage"], label="feasibility lineage"
    )
    crosswalk_source = _mapping(crosswalk_artifact["source_lineage"], label="crosswalk lineage")
    for key in (
        "source_id",
        "contract_revision",
        "source_revision_id",
        "contract_sha256",
        "county_code_system",
    ):
        if feasibility_source.get(key) != crosswalk_source.get(key):
            raise ValueError("private county projection source lineage is inconsistent")
    boundary_source = _mapping(crosswalk_source["boundary"], label="crosswalk boundary")
    boundary_features = _boundary_feature_index(boundary_shards, expected_source=boundary_source)
    crosswalk = _crosswalk_index(crosswalk_artifact, boundary_features=boundary_features)

    states: list[dict[str, object]] = []
    all_source_cells = 0
    all_projected_cells = 0
    all_projected_total = 0
    all_sentinel_total = 0
    all_source_total = 0
    for source_state in _sequence(feasibility_artifact["states"], label="feasibility states"):
        state_code = cast(str, source_state["state_code"])
        state_fips = _STATE_FIPS_BY_CODE[state_code]
        projected: Counter[tuple[str, str]] = Counter()
        county_cells = _sequence(source_state["county_cells"], label="feasibility county cells")
        sentinel_cells = _sequence(
            source_state["sentinel_cells"], label="feasibility sentinel cells"
        )
        for cell in county_cells:
            county_code = cast(str, cell["county_code"])
            presentation = crosswalk.get((state_code, county_code))
            if presentation is None:
                raise ValueError("private county projection has an unresolved FARS county code")
            geoid = cast(str, presentation["geoid"])
            mode = cast(str, cell["involved_mode"])
            projected[(geoid, mode)] += cast(int, cell["crash_count"])
        cells = [
            {"geoid": geoid, "involved_mode": mode, "crash_count": count}
            for (geoid, mode), count in sorted(
                projected.items(), key=lambda item: (int(item[0][0]), MODE_ORDER.index(item[0][1]))
            )
        ]
        projected_total = sum(projected.values())
        sentinel_total = sum(cast(int, cell["crash_count"]) for cell in sentinel_cells)
        source_total = projected_total + sentinel_total
        states.append(
            {
                "state_code": state_code,
                "state_fips": state_fips,
                "accounting": {
                    "source_county_cell_count": len(county_cells),
                    "projected_county_cell_count": len(cells),
                    "projected_contribution_total": projected_total,
                    "sentinel_contribution_total": sentinel_total,
                    "source_contribution_total": source_total,
                },
                "cells": cells,
            }
        )
        all_source_cells += len(county_cells)
        all_projected_cells += len(cells)
        all_projected_total += projected_total
        all_sentinel_total += sentinel_total
        all_source_total += source_total

    artifact: dict[str, object] = {
        "schema_version": FARS_COUNTY_PROJECTION_SCHEMA_VERSION,
        "artifact_type": FARS_COUNTY_PROJECTION_ARTIFACT_TYPE,
        "visibility": "private",
        "dataset_year": feasibility_year,
        "source_lineage": {
            "feasibility_sha256": _sha256(
                canonical_fars_county_feasibility_bytes(feasibility_artifact)
            ),
            "crosswalk_sha256": _sha256(canonical_fars_county_crosswalk_bytes(crosswalk_artifact)),
            "boundary": dict(boundary_source),
            "builder_version": FARS_COUNTY_PROJECTION_BUILDER_VERSION,
        },
        "method": {
            "dimension": "involved_mode",
            "contribution_unit": "distinct_crash_once_per_involved_mode",
            "modes_non_additive": True,
            "sentinel_handling": "excluded_from_county_cells_accounted_separately",
        },
        "accounting": {
            "state_count": len(states),
            "source_county_cell_count": all_source_cells,
            "projected_county_cell_count": all_projected_cells,
            "projected_contribution_total": all_projected_total,
            "sentinel_contribution_total": all_sentinel_total,
            "source_contribution_total": all_source_total,
        },
        "states": states,
    }
    validate_fars_county_projection_artifact(artifact)
    return artifact


def canonical_fars_county_projection_bytes(artifact: Mapping[str, object]) -> bytes:
    """Return canonical bytes for a validated private county projection."""

    validate_fars_county_projection_artifact(artifact)
    return _canonical_json_bytes(artifact)
