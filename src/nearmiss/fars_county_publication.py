# SPDX-License-Identifier: Apache-2.0
"""Fail-closed public county FARS shard contracts.

The private county projection is deliberately richer than a public map payload.
This module makes the boundary explicit: it can emit a single public state
shard only from exact, reconciled private inputs, and its suppressed branch has
no numeric field at all.  It intentionally emits no aggregate crash totals, so
subtraction cannot recover a withheld county value.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from typing import cast

from jsonschema import Draft202012Validator

from .adapters.fars_joined import MODE_ORDER
from .fars_county_boundary_publication import (
    canonical_public_fars_county_boundary_state_bytes,
    validate_public_fars_county_boundary_state_artifact,
)
from .fars_county_crosswalk import (
    FARS_COUNTY_CROSSWALK_VERSION,
    canonical_fars_county_crosswalk_bytes,
    require_fars_county_crosswalk_resolved,
)
from .fars_county_feasibility import (
    canonical_fars_county_feasibility_bytes,
    validate_fars_county_feasibility_artifact,
)
from .fars_county_projection import (
    validate_fars_county_projection_artifact,
)
from .fars_public_context import FARS_PUBLIC_STATE_CROSSWALK
from .fars_year_contracts import (
    FarsYearContract,
    fars_year_contract_revision,
    fars_year_contract_sha256,
)

FARS_COUNTY_PUBLIC_ARTIFACT_SCHEMA_VERSION = "1.0.0"
FARS_COUNTY_PUBLIC_ARTIFACT_TYPE = "nearmiss.public.fars_county_context"
FARS_COUNTY_PUBLIC_ALGORITHM_VERSION = "county-involved-mode-publication-v1"
FARS_COUNTY_PUBLIC_MIN_EFFECTIVE_K = 10
FARS_COUNTY_PUBLIC_MAX_EFFECTIVE_K = 10_000

_MAX_COUNTIES_PER_STATE = 300
_MAX_CELLS_PER_STATE = _MAX_COUNTIES_PER_STATE * len(MODE_ORDER)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$", re.ASCII)
_FIPS_RE = re.compile(r"^[0-9]{2}$", re.ASCII)
_COUNTY_FIPS_RE = re.compile(r"^[0-9]{3}$", re.ASCII)
_GEOID_RE = re.compile(r"^[0-9]{5}$", re.ASCII)


def _closed(properties: Mapping[str, object]) -> dict[str, object]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": list(properties),
        "properties": dict(properties),
    }


_SHA256 = {"type": "string", "pattern": "^[0-9a-f]{64}$"}
_PUBLISHED_CELL_SCHEMA = _closed(
    {
        "involved_mode": {"type": "string", "enum": list(MODE_ORDER)},
        "status": {"const": "published"},
        "crash_count": {"type": "integer", "minimum": FARS_COUNTY_PUBLIC_MIN_EFFECTIVE_K},
    }
)
_SUPPRESSED_OR_ZERO_CELL_SCHEMA = _closed(
    {
        "involved_mode": {"type": "string", "enum": list(MODE_ORDER)},
        "status": {"const": "suppressed_or_zero"},
    }
)
_COUNTY_SCHEMA = _closed(
    {
        "geoid": {"type": "string", "pattern": "^[0-9]{5}$"},
        "county_fips": {"type": "string", "pattern": "^[0-9]{3}$"},
        "county_name": {"type": "string", "minLength": 1, "maxLength": 128},
        "county_label": {"type": "string", "minLength": 1, "maxLength": 160},
        "cells": {
            "type": "array",
            "prefixItems": [
                {
                    "oneOf": [
                        {
                            **_PUBLISHED_CELL_SCHEMA,
                            "properties": {
                                **cast(dict[str, object], _PUBLISHED_CELL_SCHEMA["properties"]),
                                "involved_mode": {"const": mode},
                            },
                        },
                        {
                            **_SUPPRESSED_OR_ZERO_CELL_SCHEMA,
                            "properties": {
                                **cast(
                                    dict[str, object],
                                    _SUPPRESSED_OR_ZERO_CELL_SCHEMA["properties"],
                                ),
                                "involved_mode": {"const": mode},
                            },
                        },
                    ]
                }
                for mode in MODE_ORDER
            ],
            "items": False,
            "minItems": len(MODE_ORDER),
            "maxItems": len(MODE_ORDER),
        },
    }
)

FARS_COUNTY_PUBLIC_ARTIFACT_SCHEMA: dict[str, object] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "https://nearmiss.dev/schema/public-fars-county-context.schema.json",
    "title": "Public NearMiss FARS county-equivalent context state shard",
    "type": "object",
    "additionalProperties": False,
    "required": [
        "schema_version",
        "artifact_type",
        "visibility",
        "dataset_year",
        "state",
        "source",
        "geography",
        "metric",
        "accounting",
        "caveat",
        "counties",
    ],
    "properties": {
        "schema_version": {"const": FARS_COUNTY_PUBLIC_ARTIFACT_SCHEMA_VERSION},
        "artifact_type": {"const": FARS_COUNTY_PUBLIC_ARTIFACT_TYPE},
        "visibility": {"const": "public"},
        "dataset_year": {"type": "integer", "minimum": 2020, "maximum": 2024},
        "state": _closed(
            {
                "state_fips": {"type": "string", "pattern": "^[0-9]{2}$"},
                "state_abbreviation": {"type": "string", "pattern": "^[A-Z]{2}$"},
                "state_name": {"type": "string", "minLength": 1, "maxLength": 64},
            }
        ),
        "source": _closed(
            {
                "source_id": {"type": "string", "minLength": 1},
                "contract_revision": {"type": "integer", "minimum": 1},
                "name": {"const": "NHTSA Fatality Analysis Reporting System (FARS)"},
                "release_stage": {"type": "string", "minLength": 1},
                "distribution_url": {"type": "string", "format": "uri"},
                "source_revision_id": {"type": "string", "minLength": 1},
                "raw_size_bytes": {"type": "integer", "minimum": 1},
                "raw_sha256": _SHA256,
                "contract_sha256": _SHA256,
            }
        ),
        "geography": _closed(
            {
                "type": {"const": "census_county_equivalent_geoid"},
                "presentation_vintage": {"const": 2024},
                "crosswalk_version": {"const": FARS_COUNTY_CROSSWALK_VERSION},
                "crosswalk_sha256": _SHA256,
                "boundary_sha256": _SHA256,
            }
        ),
        "metric": _closed(
            {
                "algorithm_version": {"const": FARS_COUNTY_PUBLIC_ALGORITHM_VERSION},
                "dimension": {"const": "involved_mode"},
                "contribution_unit": {"const": "distinct_crash_once_per_involved_mode"},
                "effective_k": {
                    "type": "integer",
                    "minimum": FARS_COUNTY_PUBLIC_MIN_EFFECTIVE_K,
                    "maximum": FARS_COUNTY_PUBLIC_MAX_EFFECTIVE_K,
                },
                "modes_non_additive": {"const": True},
                "modes": {
                    "type": "array",
                    "prefixItems": [{"const": mode} for mode in MODE_ORDER],
                    "items": False,
                    "minItems": len(MODE_ORDER),
                    "maxItems": len(MODE_ORDER),
                },
            }
        ),
        "accounting": _closed(
            {
                "county_count": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": _MAX_COUNTIES_PER_STATE,
                },
                "county_mode_cell_count": {
                    "type": "integer",
                    "minimum": len(MODE_ORDER),
                    "maximum": _MAX_CELLS_PER_STATE,
                },
                "published_cell_count": {
                    "type": "integer",
                    "minimum": 0,
                    "maximum": _MAX_CELLS_PER_STATE,
                },
                "suppressed_or_zero_cell_count": {
                    "type": "integer",
                    "minimum": 0,
                    "maximum": _MAX_CELLS_PER_STATE,
                },
            }
        ),
        "caveat": {"type": "string", "minLength": 1, "maxLength": 1_500},
        "counties": {
            "type": "array",
            "minItems": 1,
            "maxItems": _MAX_COUNTIES_PER_STATE,
            "items": _COUNTY_SCHEMA,
        },
    },
}

_VALIDATOR = Draft202012Validator(FARS_COUNTY_PUBLIC_ARTIFACT_SCHEMA)


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


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _mapping(value: object, *, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"public FARS county shard has invalid {label}")
    return value


def _sequence(value: object, *, label: str) -> Sequence[Mapping[str, object]]:
    if not isinstance(value, list) or any(not isinstance(item, Mapping) for item in value):
        raise ValueError(f"public FARS county shard has invalid {label}")
    return cast(Sequence[Mapping[str, object]], value)


def _schema_error(artifact: Mapping[str, object]) -> None:
    errors = sorted(_VALIDATOR.iter_errors(artifact), key=lambda error: list(error.absolute_path))
    if errors:
        error = errors[0]
        path = "/".join(str(part) for part in error.absolute_path) or "(root)"
        raise ValueError(f"invalid public FARS county shard at {path}: {error.message}")


def _state_code_from_fips(state_fips: str) -> str:
    if _FIPS_RE.fullmatch(state_fips) is None:
        raise ValueError("public FARS county shard state FIPS is invalid")
    state_code = str(int(state_fips))
    if state_code not in FARS_PUBLIC_STATE_CROSSWALK:
        raise ValueError("public FARS county shard state is outside reviewed coverage")
    return state_code


def fars_county_public_caveat(
    year: int,
    *,
    contract_revision: int = 1,
    effective_k: int = FARS_COUNTY_PUBLIC_MIN_EFFECTIVE_K,
) -> str:
    """Return the exact burden-not-risk and suppression caveat for one annual shard."""

    contract = fars_year_contract_revision(year, contract_revision)
    if not isinstance(effective_k, int) or not (
        FARS_COUNTY_PUBLIC_MIN_EFFECTIVE_K <= effective_k <= FARS_COUNTY_PUBLIC_MAX_EFFECTIVE_K
    ):
        raise ValueError("county publication effective k is outside its reviewed safety bounds")
    return (
        f"This county-equivalent view shows reviewed {year} FARS fatal-crash burden by "
        "involved road-user mode. It is not an exposure-normalized risk, safety ranking, "
        "hotspot, causal finding, or count of near misses. Mode cells overlap and are "
        "non-additive. A suppressed_or_zero cell is either zero or a positive value below "
        f"the publication floor k={effective_k}; it must never be "
        "read as zero. No state or county contribution totals are published, preventing "
        "subtraction from recovering withheld values. The source is the reviewed "
        f"{contract.release_stage.replace('_', ' ')} release for the 50 states and DC; "
        "Puerto Rico requires a separately verified source."
    )


def _source_from_contract(contract: FarsYearContract) -> dict[str, object]:
    return {
        "source_id": contract.source_id,
        "contract_revision": contract.revision,
        "name": "NHTSA Fatality Analysis Reporting System (FARS)",
        "release_stage": contract.release_stage,
        "distribution_url": contract.distribution_url,
        "source_revision_id": contract.source_revision_id,
        "raw_size_bytes": contract.raw_size_bytes,
        "raw_sha256": contract.raw_sha256,
        "contract_sha256": fars_year_contract_sha256(contract),
    }


def _validate_public_source(source: Mapping[str, object], *, year: int) -> None:
    revision = source["contract_revision"]
    if not isinstance(revision, int):
        raise ValueError("public FARS county shard contract revision is invalid")
    try:
        contract = fars_year_contract_revision(year, revision)
    except (TypeError, ValueError) as exc:
        raise ValueError("public FARS county shard uses an unregistered annual contract") from exc
    if dict(source) != _source_from_contract(contract):
        raise ValueError("public FARS county shard source lineage is inconsistent")


def validate_public_fars_county_state_artifact(  # noqa: C901 - preserve adjacent leakage checks
    artifact: Mapping[str, object],
) -> None:
    """Reject malformed public shards and any possible suppressed-count leakage."""

    _schema_error(artifact)
    year = cast(int, artifact["dataset_year"])
    source = _mapping(artifact["source"], label="source")
    _validate_public_source(source, year=year)
    contract_revision = cast(int, source["contract_revision"])
    state = _mapping(artifact["state"], label="state")
    state_fips = cast(str, state["state_fips"])
    state_code = _state_code_from_fips(state_fips)
    abbreviation, name = FARS_PUBLIC_STATE_CROSSWALK[state_code]
    if state != {
        "state_fips": state_fips,
        "state_abbreviation": abbreviation,
        "state_name": name,
    }:
        raise ValueError("public FARS county shard state identity is inconsistent")
    metric = _mapping(artifact["metric"], label="metric")
    effective_k = cast(int, metric["effective_k"])
    if metric != {
        "algorithm_version": FARS_COUNTY_PUBLIC_ALGORITHM_VERSION,
        "dimension": "involved_mode",
        "contribution_unit": "distinct_crash_once_per_involved_mode",
        "effective_k": effective_k,
        "modes_non_additive": True,
        "modes": list(MODE_ORDER),
    }:
        raise ValueError("public FARS county shard metric is inconsistent")
    if artifact["caveat"] != fars_county_public_caveat(
        year, contract_revision=contract_revision, effective_k=effective_k
    ):
        raise ValueError("public FARS county shard caveat is inconsistent")

    counties = _sequence(artifact["counties"], label="counties")
    geoids = [cast(str, county["geoid"]) for county in counties]
    if geoids != sorted(geoids, key=int) or len(geoids) != len(set(geoids)):
        raise ValueError("public FARS county shard counties are not uniquely canonically ordered")
    published = 0
    suppressed_or_zero = 0
    for county in counties:
        geoid = cast(str, county["geoid"])
        county_fips = cast(str, county["county_fips"])
        if (
            _GEOID_RE.fullmatch(geoid) is None
            or _COUNTY_FIPS_RE.fullmatch(county_fips) is None
            or geoid != state_fips + county_fips
        ):
            raise ValueError("public FARS county shard county identity is inconsistent")
        cells = _sequence(county["cells"], label="county cells")
        modes = [cast(str, cell["involved_mode"]) for cell in cells]
        if modes != list(MODE_ORDER):
            raise ValueError("public FARS county shard county cells are not canonically ordered")
        for cell in cells:
            status = cell["status"]
            if status == "published":
                count = cell.get("crash_count")
                if not isinstance(count, int) or count < effective_k:
                    raise ValueError("public FARS county shard published cell is below its floor")
                published += 1
            elif status == "suppressed_or_zero":
                if set(cell) != {"involved_mode", "status"}:
                    raise ValueError("public FARS county shard suppressed cell leaks a value")
                suppressed_or_zero += 1
            else:
                raise ValueError("public FARS county shard cell status is invalid")
    accounting = _mapping(artifact["accounting"], label="accounting")
    expected_accounting = {
        "county_count": len(counties),
        "county_mode_cell_count": len(counties) * len(MODE_ORDER),
        "published_cell_count": published,
        "suppressed_or_zero_cell_count": suppressed_or_zero,
    }
    if accounting != expected_accounting:
        raise ValueError("public FARS county shard accounting is inconsistent")
    if published + suppressed_or_zero != len(counties) * len(MODE_ORDER):
        raise ValueError("public FARS county shard cell accounting does not reconcile")


def _validated_private_inputs(
    feasibility_artifact: Mapping[str, object],
    crosswalk_artifact: Mapping[str, object],
    projection_artifact: Mapping[str, object],
) -> tuple[int, Mapping[str, object]]:
    validate_fars_county_feasibility_artifact(feasibility_artifact)
    require_fars_county_crosswalk_resolved(crosswalk_artifact)
    validate_fars_county_projection_artifact(projection_artifact)
    year = cast(int, feasibility_artifact["dataset_year"])
    if (
        crosswalk_artifact.get("dataset_year") != year
        or projection_artifact.get("dataset_year") != year
    ):
        raise ValueError("county publication inputs use different dataset years")
    projection_source = _mapping(projection_artifact["source_lineage"], label="projection lineage")
    expected_feasibility = _sha256(canonical_fars_county_feasibility_bytes(feasibility_artifact))
    expected_crosswalk = _sha256(canonical_fars_county_crosswalk_bytes(crosswalk_artifact))
    if (
        projection_source.get("feasibility_sha256") != expected_feasibility
        or projection_source.get("crosswalk_sha256") != expected_crosswalk
    ):
        raise ValueError("county publication projection is detached from reviewed inputs")
    crosswalk_source = _mapping(crosswalk_artifact["source_lineage"], label="crosswalk lineage")
    feasibility_source = _mapping(
        feasibility_artifact["source_lineage"], label="feasibility lineage"
    )
    if any(
        feasibility_source.get(key) != crosswalk_source.get(key)
        for key in (
            "source_id",
            "contract_revision",
            "source_revision_id",
            "contract_sha256",
            "county_code_system",
        )
    ):
        raise ValueError("county publication reviewed source lineage is inconsistent")
    boundary = _mapping(crosswalk_source["boundary"], label="crosswalk boundary")
    if projection_source.get("boundary") != boundary:
        raise ValueError("county publication projection boundary lineage is inconsistent")
    return year, boundary


def _boundary_counties(
    public_boundary_artifact: Mapping[str, object],
    *,
    state_fips: str,
    expected_source: Mapping[str, object],
) -> list[dict[str, str]]:
    validate_public_fars_county_boundary_state_artifact(public_boundary_artifact)
    state = _mapping(public_boundary_artifact.get("state"), label="boundary state")
    if (
        state.get("state_fips") != state_fips
        or _mapping(public_boundary_artifact.get("source"), label="boundary source")
        != expected_source
    ):
        raise ValueError("county publication boundary shard identity is inconsistent")
    counties: list[dict[str, str]] = []
    for feature in _sequence(public_boundary_artifact.get("features"), label="boundary features"):
        properties = _mapping(feature.get("properties"), label="boundary feature properties")
        geoid = properties.get("geoid")
        county_fips = properties.get("county_fips")
        name = properties.get("name")
        label = properties.get("namelsad")
        if (
            feature.get("id") != geoid
            or properties.get("state_fips") != state_fips
            or not isinstance(geoid, str)
            or _GEOID_RE.fullmatch(geoid) is None
            or not isinstance(county_fips, str)
            or _COUNTY_FIPS_RE.fullmatch(county_fips) is None
            or geoid != state_fips + county_fips
            or not isinstance(name, str)
            or not name
            or not isinstance(label, str)
            or not label
        ):
            raise ValueError("county publication boundary county identity is inconsistent")
        counties.append(
            {
                "geoid": geoid,
                "county_fips": county_fips,
                "county_name": name,
                "county_label": label,
            }
        )
    counties.sort(key=lambda county: int(county["geoid"]))
    if not counties or len(counties) > _MAX_COUNTIES_PER_STATE:
        raise ValueError("county publication boundary county count is outside safety bounds")
    if len({county["geoid"] for county in counties}) != len(counties):
        raise ValueError("county publication boundary shard duplicates a county GEOID")
    return counties


def _validate_crosswalk_targets_for_state(
    crosswalk_artifact: Mapping[str, object],
    *,
    state_code: str,
    counties: Sequence[Mapping[str, str]],
) -> None:
    by_geoid = {county["geoid"]: county for county in counties}
    for row in _sequence(crosswalk_artifact["rows"], label="crosswalk rows"):
        if row["state_code"] != state_code:
            continue
        presentation = _mapping(row["presentation"], label="crosswalk presentation")
        geoid = presentation["geoid"]
        if not isinstance(geoid, str):
            raise ValueError("county publication crosswalk GEOID is invalid")
        county = by_geoid.get(geoid)
        expected = {
            "geoid": presentation["geoid"],
            "county_fips": presentation["county_fips"],
            "county_name": presentation["name"],
            "county_label": presentation["namelsad"],
        }
        if county is None or dict(county) != expected:
            raise ValueError("county publication crosswalk target lacks matching boundary county")


def build_public_fars_county_state_artifact(
    feasibility_artifact: Mapping[str, object],
    crosswalk_artifact: Mapping[str, object],
    projection_artifact: Mapping[str, object],
    public_boundary_artifact: Mapping[str, object],
    *,
    state_fips: str,
    effective_k: int = FARS_COUNTY_PUBLIC_MIN_EFFECTIVE_K,
) -> dict[str, object]:
    """Build one public state shard without retaining suppressed numeric values."""

    if not isinstance(effective_k, int) or not (
        FARS_COUNTY_PUBLIC_MIN_EFFECTIVE_K <= effective_k <= FARS_COUNTY_PUBLIC_MAX_EFFECTIVE_K
    ):
        raise ValueError("county publication effective k is outside its reviewed safety bounds")
    year, boundary_source = _validated_private_inputs(
        feasibility_artifact, crosswalk_artifact, projection_artifact
    )
    state_code = _state_code_from_fips(state_fips)
    counties = _boundary_counties(
        public_boundary_artifact, state_fips=state_fips, expected_source=boundary_source
    )
    _validate_crosswalk_targets_for_state(
        crosswalk_artifact, state_code=state_code, counties=counties
    )
    projection_states = _sequence(projection_artifact["states"], label="projection states")
    projection_state = next(
        (state for state in projection_states if state["state_code"] == state_code), None
    )
    if projection_state is None or projection_state.get("state_fips") != state_fips:
        raise ValueError("county publication projection has no matching state")
    counts = {
        (cast(str, cell["geoid"]), cast(str, cell["involved_mode"])): cast(int, cell["crash_count"])
        for cell in _sequence(projection_state["cells"], label="projection cells")
    }
    county_geoids = {county["geoid"] for county in counties}
    if not {geoid for geoid, _mode in counts} <= county_geoids:
        raise ValueError("county publication projection cell has no boundary county")
    public_counties: list[dict[str, object]] = []
    published = 0
    for county in counties:
        cells: list[dict[str, object]] = []
        for mode in MODE_ORDER:
            count = counts.get((county["geoid"], mode), 0)
            if count >= effective_k:
                cells.append({"involved_mode": mode, "status": "published", "crash_count": count})
                published += 1
            else:
                cells.append({"involved_mode": mode, "status": "suppressed_or_zero"})
        public_counties.append({**county, "cells": cells})
    contract_revision = cast(
        int, cast(Mapping[str, object], feasibility_artifact["source_lineage"])["contract_revision"]
    )
    contract = fars_year_contract_revision(year, contract_revision)
    total_cells = len(public_counties) * len(MODE_ORDER)
    abbreviation, state_name = FARS_PUBLIC_STATE_CROSSWALK[state_code]
    artifact: dict[str, object] = {
        "schema_version": FARS_COUNTY_PUBLIC_ARTIFACT_SCHEMA_VERSION,
        "artifact_type": FARS_COUNTY_PUBLIC_ARTIFACT_TYPE,
        "visibility": "public",
        "dataset_year": year,
        "state": {
            "state_fips": state_fips,
            "state_abbreviation": abbreviation,
            "state_name": state_name,
        },
        "source": _source_from_contract(contract),
        "geography": {
            "type": "census_county_equivalent_geoid",
            "presentation_vintage": boundary_source["presentation_vintage"],
            "crosswalk_version": crosswalk_artifact["crosswalk_version"],
            "crosswalk_sha256": _sha256(canonical_fars_county_crosswalk_bytes(crosswalk_artifact)),
            "boundary_sha256": _sha256(
                canonical_public_fars_county_boundary_state_bytes(public_boundary_artifact)
            ),
        },
        "metric": {
            "algorithm_version": FARS_COUNTY_PUBLIC_ALGORITHM_VERSION,
            "dimension": "involved_mode",
            "contribution_unit": "distinct_crash_once_per_involved_mode",
            "effective_k": effective_k,
            "modes_non_additive": True,
            "modes": list(MODE_ORDER),
        },
        "accounting": {
            "county_count": len(public_counties),
            "county_mode_cell_count": total_cells,
            "published_cell_count": published,
            "suppressed_or_zero_cell_count": total_cells - published,
        },
        "caveat": fars_county_public_caveat(
            year, contract_revision=contract_revision, effective_k=effective_k
        ),
        "counties": public_counties,
    }
    validate_public_fars_county_state_artifact(artifact)
    return artifact


def canonical_public_fars_county_state_bytes(artifact: Mapping[str, object]) -> bytes:
    """Return canonical bytes only for a validated public county state shard."""

    validate_public_fars_county_state_artifact(artifact)
    return _canonical_json_bytes(artifact)
