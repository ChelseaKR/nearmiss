# SPDX-License-Identifier: Apache-2.0
"""Closed, private FARS-to-Census county-equivalent crosswalk contracts.

FARS COUNTY is a source-native GSA code, while Census county GEOIDs are
presentation identities.  This module keeps that distinction explicit: it
validates reviewed mappings and their boundary provenance, but never derives a
GEOID by concatenating an unreviewed FARS state and county code.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from collections.abc import Mapping, Sequence
from types import MappingProxyType
from typing import cast

from jsonschema import Draft202012Validator

from .fars_public_context import FARS_PUBLIC_STATE_CROSSWALK
from .fars_year_contracts import (
    FarsYearContract,
    fars_year_contract_revision,
    fars_year_contract_sha256,
)

FARS_COUNTY_CROSSWALK_SCHEMA_VERSION = "1.0.0"
FARS_COUNTY_CROSSWALK_ARTIFACT_TYPE = "nearmiss.private.fars_county_crosswalk"
FARS_COUNTY_CROSSWALK_VERSION = "fars-county-2024-v1"
FARS_COUNTY_CROSSWALK_BUILDER_VERSION = "fars-county-crosswalk-v1"
FARS_COUNTY_BOUNDARY_PRESENTATION_VINTAGE = 2024
FARS_COUNTY_BOUNDARY_RESOLUTION = "1:20,000,000"
FARS_COUNTY_BOUNDARY_CONVERSION_VERSION = "county-boundary-kml-to-rfc7946-v1"
FARS_COUNTY_BOUNDARY_URL = (
    "https://www2.census.gov/geo/tiger/GENZ2024/kml/cb_2024_us_county_20m.zip"
)
FARS_COUNTY_BOUNDARY_MEMBER = "cb_2024_us_county_20m.kml"

_MAX_ROWS = 4_000
_MAX_STATES = len(FARS_PUBLIC_STATE_CROSSWALK)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$", re.ASCII)
_STATE_CODE_RE = re.compile(r"^[1-9][0-9]?$", re.ASCII)
_COUNTY_CODE_RE = re.compile(r"^[0-9]{3}$", re.ASCII)
_FIPS_RE = re.compile(r"^[0-9]{2}$", re.ASCII)
_GEOID_RE = re.compile(r"^[0-9]{5}$", re.ASCII)
_REVIEW_REFERENCE_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{2,127}$", re.ASCII)
_SENTINEL_CODES = frozenset({"000", "997", "998", "999"})
_MAPPING_STATUSES = (
    "exact",
    "historical_equivalent",
    "retired_to_current",
    "unresolved",
)
_ENTITY_CLASSES = (
    "borough",
    "census_area",
    "county",
    "county_equivalent",
    "district",
    "independent_city",
    "parish",
)
_SUPPORTED_STATE_CODES = tuple(sorted(FARS_PUBLIC_STATE_CROSSWALK, key=int))
_STATE_CODE_TO_FIPS = MappingProxyType(
    {state_code: f"{int(state_code):02d}" for state_code in _SUPPORTED_STATE_CODES}
)


def _closed(properties: Mapping[str, object]) -> dict[str, object]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": list(properties),
        "properties": dict(properties),
    }


def _count(*, minimum: int = 0, maximum: int = _MAX_ROWS) -> dict[str, object]:
    return {"type": "integer", "minimum": minimum, "maximum": maximum}


_SHA256 = {"type": "string", "pattern": "^[0-9a-f]{64}$"}
_BOUNDARY_PROVENANCE_SCHEMA = _closed(
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
_PRESENTATION_SCHEMA = _closed(
    {
        "state_fips": {"type": "string", "pattern": "^[0-9]{2}$"},
        "county_fips": {"type": "string", "pattern": "^[0-9]{3}$"},
        "geoid": {"type": "string", "pattern": "^[0-9]{5}$"},
        "name": {"type": "string", "minLength": 1, "maxLength": 128},
        "namelsad": {"type": "string", "minLength": 1, "maxLength": 160},
        "entity_class": {"type": "string", "enum": list(_ENTITY_CLASSES)},
    }
)
_ROW_SCHEMA: dict[str, object] = _closed(
    {
        "state_code": {"type": "string", "enum": list(_SUPPORTED_STATE_CODES)},
        "county_code": {"type": "string", "pattern": "^[0-9]{3}$"},
        "mapping_status": {"type": "string", "enum": list(_MAPPING_STATUSES)},
        "review_note": {"type": "string", "minLength": 1, "maxLength": 512},
        "presentation": {"oneOf": [_PRESENTATION_SCHEMA, {"type": "null"}]},
    }
)
_ROW_SCHEMA["allOf"] = [
    {
        "if": {"properties": {"mapping_status": {"const": "unresolved"}}},
        "then": {"properties": {"presentation": {"type": "null"}}},
        "else": {"properties": {"presentation": _PRESENTATION_SCHEMA}},
    }
]

FARS_COUNTY_CROSSWALK_ARTIFACT_SCHEMA: dict[str, object] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "https://nearmiss.dev/schema/fars-county-crosswalk.schema.json",
    "title": "Private NearMiss FARS-to-Census county-equivalent crosswalk",
    "type": "object",
    "additionalProperties": False,
    "required": [
        "schema_version",
        "artifact_type",
        "visibility",
        "dataset_year",
        "crosswalk_version",
        "source_lineage",
        "accounting",
        "rows",
    ],
    "properties": {
        "schema_version": {"const": FARS_COUNTY_CROSSWALK_SCHEMA_VERSION},
        "artifact_type": {"const": FARS_COUNTY_CROSSWALK_ARTIFACT_TYPE},
        "visibility": {"const": "private"},
        "dataset_year": {"type": "integer", "minimum": 2020, "maximum": 2024},
        "crosswalk_version": {"const": FARS_COUNTY_CROSSWALK_VERSION},
        "source_lineage": _closed(
            {
                "source_id": {"type": "string", "minLength": 1},
                "contract_revision": {"type": "integer", "minimum": 1},
                "source_revision_id": {"type": "string", "minLength": 1},
                "contract_sha256": _SHA256,
                "county_code_system": {"type": "string", "minLength": 1},
                "review_reference": {
                    "type": "string",
                    "pattern": "^[a-z0-9][a-z0-9._-]{2,127}$",
                },
                "boundary": _BOUNDARY_PROVENANCE_SCHEMA,
                "builder_version": {"const": FARS_COUNTY_CROSSWALK_BUILDER_VERSION},
            }
        ),
        "accounting": _closed(
            {
                "source_row_count": _count(minimum=1),
                "resolved_row_count": _count(),
                "unresolved_row_count": _count(),
                "state_count": _count(minimum=1, maximum=_MAX_STATES),
                "presentation_geoid_count": _count(),
            }
        ),
        "rows": {
            "type": "array",
            "minItems": 1,
            "maxItems": _MAX_ROWS,
            "items": _ROW_SCHEMA,
        },
    },
}

_VALIDATOR = Draft202012Validator(FARS_COUNTY_CROSSWALK_ARTIFACT_SCHEMA)


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


def _schema_error(artifact: Mapping[str, object]) -> None:
    errors = sorted(_VALIDATOR.iter_errors(artifact), key=lambda error: list(error.absolute_path))
    if errors:
        error = errors[0]
        path = "/".join(str(part) for part in error.absolute_path) or "(root)"
        raise ValueError(f"invalid private FARS county crosswalk at {path}: {error.message}")


def _contract_from_source_lineage(artifact: Mapping[str, object]) -> FarsYearContract:
    year = cast(int, artifact["dataset_year"])
    source = cast(Mapping[str, object], artifact["source_lineage"])
    revision = cast(int, source["contract_revision"])
    try:
        contract = fars_year_contract_revision(year, revision)
    except (TypeError, ValueError) as exc:
        raise ValueError("private FARS county crosswalk uses an unregistered contract") from exc
    expected = {
        "source_id": contract.source_id,
        "source_revision_id": contract.source_revision_id,
        "contract_sha256": fars_year_contract_sha256(contract),
        "county_code_system": contract.county_code_system,
    }
    if any(source[key] != value for key, value in expected.items()):
        raise ValueError("private FARS county crosswalk source lineage is inconsistent")
    review_reference = source["review_reference"]
    if (
        not isinstance(review_reference, str)
        or _REVIEW_REFERENCE_RE.fullmatch(review_reference) is None
    ):
        raise ValueError("private FARS county crosswalk review reference is invalid")
    return contract


def _canonical_source_key(row: Mapping[str, object]) -> tuple[str, str]:
    state_code = row["state_code"]
    county_code = row["county_code"]
    if not isinstance(state_code, str) or _STATE_CODE_RE.fullmatch(state_code) is None:
        raise ValueError("private FARS county crosswalk state code is invalid")
    if state_code not in _STATE_CODE_TO_FIPS:
        raise ValueError("private FARS county crosswalk state is outside reviewed coverage")
    if not isinstance(county_code, str) or _COUNTY_CODE_RE.fullmatch(county_code) is None:
        raise ValueError("private FARS county crosswalk county code is invalid")
    if county_code in _SENTINEL_CODES:
        raise ValueError("private FARS county crosswalk cannot map a sentinel county code")
    return state_code, county_code


def _validate_presentation(  # noqa: C901 - preserve one fail-closed target check
    row: Mapping[str, object],
    *,
    state_code: str,
) -> str | None:
    status = cast(str, row["mapping_status"])
    presentation = row["presentation"]
    if status == "unresolved":
        if presentation is not None:
            raise ValueError(
                "private FARS county crosswalk unresolved row has a presentation target"
            )
        return None
    if not isinstance(presentation, Mapping):
        raise ValueError("private FARS county crosswalk resolved row has no presentation target")
    state_fips = presentation["state_fips"]
    county_fips = presentation["county_fips"]
    geoid = presentation["geoid"]
    if not isinstance(state_fips, str) or _FIPS_RE.fullmatch(state_fips) is None:
        raise ValueError("private FARS county crosswalk presentation state FIPS is invalid")
    if state_fips != _STATE_CODE_TO_FIPS[state_code]:
        raise ValueError("private FARS county crosswalk presentation crosses a state boundary")
    if not isinstance(county_fips, str) or _COUNTY_CODE_RE.fullmatch(county_fips) is None:
        raise ValueError("private FARS county crosswalk presentation county FIPS is invalid")
    if not isinstance(geoid, str) or _GEOID_RE.fullmatch(geoid) is None:
        raise ValueError("private FARS county crosswalk presentation GEOID is invalid")
    if geoid != state_fips + county_fips:
        raise ValueError("private FARS county crosswalk GEOID does not match its FIPS components")
    for key in ("name", "namelsad"):
        value = presentation[key]
        if not isinstance(value, str) or not value.strip() or value != value.strip():
            raise ValueError(f"private FARS county crosswalk presentation {key} is invalid")
    return geoid


def _validate_canonical_rows(rows: Sequence[Mapping[str, object]]) -> tuple[int, int, int]:
    keys = [_canonical_source_key(row) for row in rows]
    expected_keys = sorted(keys, key=lambda key: (int(key[0]), int(key[1])))
    if keys != expected_keys or len(keys) != len(set(keys)):
        raise ValueError("private FARS county crosswalk rows are not uniquely canonically ordered")

    target_rows: dict[str, list[Mapping[str, object]]] = defaultdict(list)
    unresolved = 0
    for row, (state_code, _county_code) in zip(rows, keys, strict=True):
        geoid = _validate_presentation(row, state_code=state_code)
        if geoid is None:
            unresolved += 1
        else:
            target_rows[geoid].append(row)

    for geoid, matching_rows in target_rows.items():
        if len(matching_rows) == 1:
            continue
        statuses = {cast(str, row["mapping_status"]) for row in matching_rows}
        if (
            "retired_to_current" not in statuses
            or not statuses <= {"exact", "retired_to_current"}
            or sum(cast(str, row["mapping_status"]) == "exact" for row in matching_rows) > 1
        ):
            raise ValueError(
                "private FARS county crosswalk duplicate presentation GEOID "
                f"{geoid} lacks an explicit retired-to-current review"
            )
    return len(keys), len(keys) - unresolved, len(target_rows)


def validate_fars_county_crosswalk_artifact(artifact: Mapping[str, object]) -> None:
    """Reject malformed, unreviewable, or noncanonical private crosswalks."""

    _schema_error(artifact)
    _contract_from_source_lineage(artifact)
    rows = cast(list[Mapping[str, object]], artifact["rows"])
    source_count, resolved_count, geoid_count = _validate_canonical_rows(rows)
    accounting = cast(Mapping[str, int], artifact["accounting"])
    unresolved_count = source_count - resolved_count
    state_count = len({cast(str, row["state_code"]) for row in rows})
    if accounting != {
        "source_row_count": source_count,
        "resolved_row_count": resolved_count,
        "unresolved_row_count": unresolved_count,
        "state_count": state_count,
        "presentation_geoid_count": geoid_count,
    }:
        raise ValueError("private FARS county crosswalk accounting is inconsistent")


def _canonical_row(row: Mapping[str, object]) -> dict[str, object]:
    source_key = _canonical_source_key(row)
    status = row.get("mapping_status")
    note = row.get("review_note")
    if not isinstance(status, str) or status not in _MAPPING_STATUSES:
        raise ValueError("private FARS county crosswalk mapping status is invalid")
    if not isinstance(note, str):
        raise ValueError("private FARS county crosswalk review note is invalid")
    return {
        "state_code": source_key[0],
        "county_code": source_key[1],
        "mapping_status": status,
        "review_note": note,
        "presentation": row.get("presentation"),
    }


def build_fars_county_crosswalk(
    rows: Sequence[Mapping[str, object]],
    *,
    year: int,
    contract_revision: int,
    review_reference: str,
    boundary: Mapping[str, object],
) -> dict[str, object]:
    """Build a private, canonical crosswalk from explicitly reviewed row mappings."""

    if not rows or len(rows) > _MAX_ROWS:
        raise ValueError("private FARS county crosswalk row count is outside safety bounds")
    contract = fars_year_contract_revision(year, contract_revision)
    canonical_rows = sorted(
        (_canonical_row(row) for row in rows),
        key=lambda row: (int(cast(str, row["state_code"])), int(cast(str, row["county_code"]))),
    )
    unresolved_count = sum(row["mapping_status"] == "unresolved" for row in canonical_rows)
    geoid_count = len(
        {
            cast(Mapping[str, str], row["presentation"])["geoid"]
            for row in canonical_rows
            if row["presentation"] is not None
        }
    )
    artifact: dict[str, object] = {
        "schema_version": FARS_COUNTY_CROSSWALK_SCHEMA_VERSION,
        "artifact_type": FARS_COUNTY_CROSSWALK_ARTIFACT_TYPE,
        "visibility": "private",
        "dataset_year": contract.year,
        "crosswalk_version": FARS_COUNTY_CROSSWALK_VERSION,
        "source_lineage": {
            "source_id": contract.source_id,
            "contract_revision": contract.revision,
            "source_revision_id": contract.source_revision_id,
            "contract_sha256": fars_year_contract_sha256(contract),
            "county_code_system": contract.county_code_system,
            "review_reference": review_reference,
            "boundary": dict(boundary),
            "builder_version": FARS_COUNTY_CROSSWALK_BUILDER_VERSION,
        },
        "accounting": {
            "source_row_count": len(canonical_rows),
            "resolved_row_count": len(canonical_rows) - unresolved_count,
            "unresolved_row_count": unresolved_count,
            "state_count": len({cast(str, row["state_code"]) for row in canonical_rows}),
            "presentation_geoid_count": geoid_count,
        },
        "rows": canonical_rows,
    }
    validate_fars_county_crosswalk_artifact(artifact)
    return artifact


def canonical_fars_county_crosswalk_bytes(artifact: Mapping[str, object]) -> bytes:
    """Return canonical bytes only for a fully validated private crosswalk."""

    validate_fars_county_crosswalk_artifact(artifact)
    return _canonical_json_bytes(artifact)


def fars_county_crosswalk_sha256(artifact: Mapping[str, object]) -> str:
    """Return the exact digest referenced by later private/public projections."""

    return hashlib.sha256(canonical_fars_county_crosswalk_bytes(artifact)).hexdigest()


def require_fars_county_crosswalk_resolved(artifact: Mapping[str, object]) -> None:
    """Fail public-projection callers closed until every source row has a target."""

    validate_fars_county_crosswalk_artifact(artifact)
    accounting = cast(Mapping[str, int], artifact["accounting"])
    if accounting["unresolved_row_count"]:
        raise ValueError("private FARS county crosswalk contains unresolved source county codes")
