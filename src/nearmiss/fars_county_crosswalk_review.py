# SPDX-License-Identifier: Apache-2.0
"""Private review packets for FARS-to-Census county crosswalks.

This module turns a verified county-feasibility artifact into a deliberately
non-public review packet.  The packet contains every reported source county
code, but no crash counts, case identifiers, or locations.  A reviewer must
explicitly map each source code (or mark it unresolved) before the packet can
be converted to the existing private crosswalk contract.
"""

from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Mapping
from typing import cast

from jsonschema import Draft202012Validator

from . import fars_county_crosswalk as crosswalk
from . import fars_county_feasibility as feasibility
from .fars_year_contracts import fars_year_contract_revision, fars_year_contract_sha256

FARS_COUNTY_CROSSWALK_REVIEW_SCHEMA_VERSION = "1.0.0"
FARS_COUNTY_CROSSWALK_REVIEW_ARTIFACT_TYPE = "nearmiss.private.fars_county_crosswalk_review"
FARS_COUNTY_CROSSWALK_REVIEW_TEMPLATE_REFERENCE = "pending-review"

_MAX_ROWS = 4_000
_SHA256 = {"type": "string", "pattern": "^[0-9a-f]{64}$"}


def _closed(properties: Mapping[str, object]) -> dict[str, object]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": list(properties),
        "properties": dict(properties),
    }


_CROSSWALK_ROWS_SCHEMA = cast(
    dict[str, object],
    cast(
        Mapping[str, object],
        cast(Mapping[str, object], crosswalk.FARS_COUNTY_CROSSWALK_ARTIFACT_SCHEMA["properties"])[
            "rows"
        ],
    ),
)
_REVIEW_ROWS_SCHEMA = copy.deepcopy(_CROSSWALK_ROWS_SCHEMA)

FARS_COUNTY_CROSSWALK_REVIEW_ARTIFACT_SCHEMA: dict[str, object] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "https://nearmiss.dev/schema/private-fars-county-crosswalk-review.schema.json",
    "title": "Private NearMiss FARS county crosswalk review packet",
    "type": "object",
    "additionalProperties": False,
    "required": [
        "schema_version",
        "artifact_type",
        "visibility",
        "dataset_year",
        "source_lineage",
        "review_reference",
        "accounting",
        "rows",
    ],
    "properties": {
        "schema_version": {"const": FARS_COUNTY_CROSSWALK_REVIEW_SCHEMA_VERSION},
        "artifact_type": {"const": FARS_COUNTY_CROSSWALK_REVIEW_ARTIFACT_TYPE},
        "visibility": {"const": "private"},
        "dataset_year": {"type": "integer", "minimum": 2020, "maximum": 2024},
        "source_lineage": _closed(
            {
                "source_id": {"type": "string", "minLength": 1},
                "contract_revision": {"type": "integer", "minimum": 1},
                "source_revision_id": {"type": "string", "minLength": 1},
                "contract_sha256": _SHA256,
                "normalized_sha256": _SHA256,
                "county_code_system": {"type": "string", "minLength": 1},
                "feasibility_sha256": _SHA256,
            }
        ),
        "review_reference": {
            "type": "string",
            "pattern": "^[a-z0-9][a-z0-9._-]{2,127}$",
        },
        "accounting": _closed(
            {
                "source_row_count": {"type": "integer", "minimum": 1, "maximum": _MAX_ROWS},
            }
        ),
        "rows": _REVIEW_ROWS_SCHEMA,
    },
}

_VALIDATOR = Draft202012Validator(FARS_COUNTY_CROSSWALK_REVIEW_ARTIFACT_SCHEMA)

_PLACEHOLDER_BOUNDARY: dict[str, object] = {
    "presentation_vintage": crosswalk.FARS_COUNTY_BOUNDARY_PRESENTATION_VINTAGE,
    "distribution_url": crosswalk.FARS_COUNTY_BOUNDARY_URL,
    "raw_zip_sha256": "0" * 64,
    "raw_zip_size_bytes": 1,
    "member_name": crosswalk.FARS_COUNTY_BOUNDARY_MEMBER,
    "member_sha256": "0" * 64,
    "resolution": crosswalk.FARS_COUNTY_BOUNDARY_RESOLUTION,
    "conversion_version": crosswalk.FARS_COUNTY_BOUNDARY_CONVERSION_VERSION,
}


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
        raise ValueError(f"invalid private FARS county crosswalk review at {path}: {error.message}")


def _validated_review_rows(artifact: Mapping[str, object]) -> list[dict[str, object]]:
    year = cast(int, artifact["dataset_year"])
    source = cast(Mapping[str, object], artifact["source_lineage"])
    try:
        contract = fars_year_contract_revision(year, cast(int, source["contract_revision"]))
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "private FARS county crosswalk review uses an unregistered contract"
        ) from exc
    expected = {
        "source_id": contract.source_id,
        "source_revision_id": contract.source_revision_id,
        "contract_sha256": fars_year_contract_sha256(contract),
        "county_code_system": contract.county_code_system,
    }
    if any(source[key] != value for key, value in expected.items()):
        raise ValueError("private FARS county crosswalk review source lineage is inconsistent")

    rows = cast(list[Mapping[str, object]], artifact["rows"])
    review_reference = cast(str, artifact["review_reference"])
    candidate = crosswalk.build_fars_county_crosswalk(
        rows,
        year=year,
        contract_revision=contract.revision,
        review_reference=review_reference,
        boundary=_PLACEHOLDER_BOUNDARY,
    )
    canonical_rows = cast(list[dict[str, object]], candidate["rows"])
    if rows != canonical_rows:
        raise ValueError(
            "private FARS county crosswalk review rows are not uniquely canonically ordered"
        )
    accounting = cast(Mapping[str, int], artifact["accounting"])
    if accounting != {"source_row_count": len(canonical_rows)}:
        raise ValueError("private FARS county crosswalk review accounting is inconsistent")
    return canonical_rows


def validate_fars_county_crosswalk_review_artifact(artifact: Mapping[str, object]) -> None:
    """Reject a noncanonical review packet or one detached from an annual contract."""

    _schema_error(artifact)
    _validated_review_rows(artifact)


def canonical_fars_county_crosswalk_review_bytes(artifact: Mapping[str, object]) -> bytes:
    """Return deterministic bytes only for a validated private review packet."""

    validate_fars_county_crosswalk_review_artifact(artifact)
    return _canonical_json_bytes(artifact)


def fars_county_crosswalk_review_sha256(artifact: Mapping[str, object]) -> str:
    """Return the exact review-packet digest used for audit records."""

    return hashlib.sha256(canonical_fars_county_crosswalk_review_bytes(artifact)).hexdigest()


def _feasibility_source_keys(artifact: Mapping[str, object]) -> list[tuple[str, str]]:
    states = cast(list[Mapping[str, object]], artifact["states"])
    keys = [
        (cast(str, state["state_code"]), cast(str, cell["county_code"]))
        for state in states
        for cell in cast(list[Mapping[str, object]], state["county_cells"])
    ]
    return sorted(set(keys), key=lambda key: (int(key[0]), int(key[1])))


def build_fars_county_crosswalk_review_template(
    feasibility_artifact: Mapping[str, object],
) -> dict[str, object]:
    """Create a private no-count template with one explicit row per source county code."""

    feasibility.validate_fars_county_feasibility_artifact(feasibility_artifact)
    source = cast(Mapping[str, object], feasibility_artifact["source_lineage"])
    rows = [
        {
            "state_code": state_code,
            "county_code": county_code,
            "mapping_status": "unresolved",
            "review_note": "Pending independent county-equivalent review",
            "presentation": None,
        }
        for state_code, county_code in _feasibility_source_keys(feasibility_artifact)
    ]
    artifact: dict[str, object] = {
        "schema_version": FARS_COUNTY_CROSSWALK_REVIEW_SCHEMA_VERSION,
        "artifact_type": FARS_COUNTY_CROSSWALK_REVIEW_ARTIFACT_TYPE,
        "visibility": "private",
        "dataset_year": feasibility_artifact["dataset_year"],
        "source_lineage": {
            "source_id": source["source_id"],
            "contract_revision": source["contract_revision"],
            "source_revision_id": source["source_revision_id"],
            "contract_sha256": source["contract_sha256"],
            "normalized_sha256": source["normalized_sha256"],
            "county_code_system": source["county_code_system"],
            "feasibility_sha256": hashlib.sha256(
                feasibility.canonical_fars_county_feasibility_bytes(feasibility_artifact)
            ).hexdigest(),
        },
        "review_reference": FARS_COUNTY_CROSSWALK_REVIEW_TEMPLATE_REFERENCE,
        "accounting": {"source_row_count": len(rows)},
        "rows": rows,
    }
    validate_fars_county_crosswalk_review_artifact(artifact)
    return artifact


def build_fars_county_crosswalk_from_review(
    review_artifact: Mapping[str, object],
    *,
    feasibility_artifact: Mapping[str, object],
    boundary: Mapping[str, object],
) -> dict[str, object]:
    """Build the private crosswalk only when review coverage exactly matches feasibility."""

    feasibility.validate_fars_county_feasibility_artifact(feasibility_artifact)
    validate_fars_county_crosswalk_review_artifact(review_artifact)
    if review_artifact["review_reference"] == FARS_COUNTY_CROSSWALK_REVIEW_TEMPLATE_REFERENCE:
        raise ValueError("private FARS county crosswalk review still has the pending reference")
    if review_artifact["dataset_year"] != feasibility_artifact["dataset_year"]:
        raise ValueError("private FARS county crosswalk review year does not match feasibility")
    source = cast(Mapping[str, object], feasibility_artifact["source_lineage"])
    review_source = cast(Mapping[str, object], review_artifact["source_lineage"])
    expected_lineage = {
        "source_id": source["source_id"],
        "contract_revision": source["contract_revision"],
        "source_revision_id": source["source_revision_id"],
        "contract_sha256": source["contract_sha256"],
        "normalized_sha256": source["normalized_sha256"],
        "county_code_system": source["county_code_system"],
        "feasibility_sha256": hashlib.sha256(
            feasibility.canonical_fars_county_feasibility_bytes(feasibility_artifact)
        ).hexdigest(),
    }
    if dict(review_source) != expected_lineage:
        raise ValueError("private FARS county crosswalk review is detached from feasibility")
    rows = _validated_review_rows(review_artifact)
    review_keys = [(cast(str, row["state_code"]), cast(str, row["county_code"])) for row in rows]
    if review_keys != _feasibility_source_keys(feasibility_artifact):
        raise ValueError(
            "private FARS county crosswalk review does not cover feasibility source codes"
        )
    return crosswalk.build_fars_county_crosswalk(
        rows,
        year=cast(int, review_artifact["dataset_year"]),
        contract_revision=cast(int, review_source["contract_revision"]),
        review_reference=cast(str, review_artifact["review_reference"]),
        boundary=boundary,
    )
