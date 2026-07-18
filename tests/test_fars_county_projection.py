# SPDX-License-Identifier: Apache-2.0
"""Private county projection contracts require every upstream review gate."""

from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any, cast

import pytest
from jsonschema import Draft202012Validator
from tools import build_us_county_boundaries as boundaries

from nearmiss import fars_county_crosswalk as crosswalk
from nearmiss import fars_county_feasibility as feasibility
from nearmiss import fars_county_projection as projection
from nearmiss.fars_national_context import FARS_2024_STATE_CODES
from nearmiss.fars_year_contracts import fars_year_contract_revision

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schema" / "private-fars-county-projection.schema.json"


def _record(*, case: int, state: str, county: str, modes: Iterable[str]) -> dict[str, object]:
    source_id = f"2024:{case}"
    return {
        "outcome": {"source_record_id": source_id, "state_code": state},
        "mode_summary": {"source_record_id": source_id, "involved_modes": list(modes)},
        "jurisdiction": {
            "source_record_id": source_id,
            "state_code": state,
            "state_code_system": "nhtsa_fars_state_2024",
            "county_code": county,
            "county_status": "reported" if county == "001" else "unknown",
            "county_code_system": "nhtsa_fars_gsa_2024",
        },
    }


def _national_feasibility() -> dict[str, object]:
    records = [
        _record(case=index, state=state, county="001", modes=["pedestrian"])
        for index, state in enumerate(
            (state for state in FARS_2024_STATE_CODES if state != "43"), start=1
        )
    ]
    records.append(_record(case=len(records) + 1, state="6", county="999", modes=["pedestrian"]))
    return feasibility._build_county_feasibility(
        records,
        contract=fars_year_contract_revision(2024, 1),
        normalized_sha256=hashlib.sha256(b"national-projection-fixture").hexdigest(),
        require_national_coverage=True,
    )


def _presentation(state_code: str) -> dict[str, str]:
    state_fips = f"{int(state_code):02d}"
    return {
        "state_fips": state_fips,
        "county_fips": "001",
        "geoid": state_fips + "001",
        "name": f"Fixture {state_fips}",
        "namelsad": f"Fixture {state_fips} County",
        "entity_class": "district" if state_code == "11" else "county",
    }


def _crosswalk_rows() -> list[dict[str, object]]:
    return [
        {
            "state_code": state_code,
            "county_code": "001",
            "mapping_status": "exact",
            "review_note": "Synthetic national mapping fixture for projection-contract validation",
            "presentation": _presentation(state_code),
        }
        for state_code in FARS_2024_STATE_CODES
        if state_code != "43"
    ]


def _crosswalk(rows: list[dict[str, object]] | None = None) -> dict[str, object]:
    return crosswalk.build_fars_county_crosswalk(
        _crosswalk_rows() if rows is None else rows,
        year=2024,
        contract_revision=1,
        review_reference="county-projection-fixture-20260718",
        boundary=boundaries._boundary_source(),
    )


def _feature(state_code: str, *, name: str | None = None) -> dict[str, object]:
    presentation = _presentation(state_code)
    if name is not None:
        presentation["name"] = name
    return {
        "type": "Feature",
        "id": presentation["geoid"],
        "properties": {
            key: presentation[key]
            for key in ("state_fips", "county_fips", "geoid", "name", "namelsad")
        },
        "geometry": {
            "type": "Polygon",
            "coordinates": [[[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 0.0]]],
        },
    }


def _boundaries(*, altered_state: str | None = None) -> dict[str, dict[str, object]]:
    return {
        f"{int(state_code):02d}": boundaries._shard(
            f"{int(state_code):02d}",
            [
                _feature(
                    state_code,
                    name="Unexpected county" if state_code == altered_state else None,
                )
            ],
        )
        for state_code in FARS_2024_STATE_CODES
        if state_code != "43"
    }


def _projection() -> dict[str, object]:
    return projection.build_private_fars_county_projection(
        _national_feasibility(), _crosswalk(), _boundaries()
    )


def test_builds_a_private_reconciled_national_projection() -> None:
    artifact = _projection()
    projection.validate_fars_county_projection_artifact(artifact)

    states = cast(list[dict[str, Any]], artifact["states"])
    california = next(state for state in states if state["state_code"] == "6")
    assert california == {
        "state_code": "6",
        "state_fips": "06",
        "accounting": {
            "source_county_cell_count": 1,
            "projected_county_cell_count": 1,
            "projected_contribution_total": 1,
            "sentinel_contribution_total": 1,
            "source_contribution_total": 2,
        },
        "cells": [{"geoid": "06001", "involved_mode": "pedestrian", "crash_count": 1}],
    }
    assert artifact["accounting"] == {
        "state_count": 51,
        "source_county_cell_count": 51,
        "projected_county_cell_count": 51,
        "projected_contribution_total": 51,
        "sentinel_contribution_total": 1,
        "source_contribution_total": 52,
    }


def test_projection_canonical_bytes_exclude_source_county_codes_and_crash_ids() -> None:
    artifact = _projection()
    first = projection.canonical_fars_county_projection_bytes(artifact)
    second = projection.canonical_fars_county_projection_bytes(copy.deepcopy(artifact))
    assert first == second
    assert first.endswith(b"\n") and b"\n" not in first[:-1]
    assert b'"county_code"' not in first
    assert b'"source_record_id"' not in first
    assert b'"latitude"' not in first
    assert b'"longitude"' not in first


def test_unresolved_crosswalk_and_missing_mapping_fail_closed() -> None:
    rows = _crosswalk_rows()
    unresolved = rows[0]
    unresolved["mapping_status"] = "unresolved"
    unresolved["presentation"] = None
    with pytest.raises(ValueError, match="unresolved source county codes"):
        projection.build_private_fars_county_projection(
            _national_feasibility(), _crosswalk(rows), _boundaries()
        )

    missing = _crosswalk_rows()[1:]
    with pytest.raises(ValueError, match="unresolved FARS county code"):
        projection.build_private_fars_county_projection(
            _national_feasibility(), _crosswalk(missing), _boundaries()
        )


def test_crosswalk_must_match_a_private_boundary_feature_and_provenance() -> None:
    with pytest.raises(ValueError, match="lacks matching boundary"):
        projection.build_private_fars_county_projection(
            _national_feasibility(), _crosswalk(), _boundaries(altered_state="6")
        )

    shards = _boundaries()
    source = cast(dict[str, object], shards["06"]["source"])
    source["member_sha256"] = hashlib.sha256(b"wrong-boundary-member").hexdigest()
    with pytest.raises(ValueError, match="does not match crosswalk"):
        projection.build_private_fars_county_projection(
            _national_feasibility(), _crosswalk(), shards
        )


def test_output_validator_rejects_cross_state_cells_and_nonreconciling_totals() -> None:
    artifact = _projection()
    states = cast(list[dict[str, Any]], artifact["states"])
    california = next(state for state in states if state["state_code"] == "6")
    california["cells"][0]["geoid"] = "51001"
    with pytest.raises(ValueError, match="crosses a state boundary"):
        projection.validate_fars_county_projection_artifact(artifact)

    artifact = _projection()
    accounting = cast(dict[str, int], artifact["accounting"])
    accounting["sentinel_contribution_total"] = 0
    with pytest.raises(ValueError, match="accounting is inconsistent"):
        projection.validate_fars_county_projection_artifact(artifact)


def test_validator_rejects_malformed_and_noncanonical_state_order() -> None:
    with pytest.raises(ValueError, match="invalid private FARS county projection"):
        projection.validate_fars_county_projection_artifact({})

    artifact = _projection()
    states = cast(list[dict[str, Any]], artifact["states"])
    states.reverse()
    with pytest.raises(ValueError, match="states are not uniquely canonically ordered"):
        projection.validate_fars_county_projection_artifact(artifact)


def test_projection_requires_complete_private_boundary_shards() -> None:
    shards = _boundaries()
    del shards["06"]
    with pytest.raises(ValueError, match="do not cover the reviewed states"):
        projection.build_private_fars_county_projection(
            _national_feasibility(), _crosswalk(), shards
        )

    shards = _boundaries()
    shards["06"]["visibility"] = "public"
    with pytest.raises(ValueError, match="boundary shard identity is inconsistent"):
        projection.build_private_fars_county_projection(
            _national_feasibility(), _crosswalk(), shards
        )


def test_validator_rejects_a_state_code_to_fips_mismatch() -> None:
    artifact = _projection()
    states = cast(list[dict[str, Any]], artifact["states"])
    california = next(state for state in states if state["state_code"] == "6")
    california["state_fips"] = "51"
    with pytest.raises(ValueError, match="state identity is inconsistent"):
        projection.validate_fars_county_projection_artifact(artifact)


def test_repository_schema_matches_embedded_private_contract() -> None:
    assert json.loads(SCHEMA_PATH.read_text(encoding="utf-8")) == (
        projection.FARS_COUNTY_PROJECTION_ARTIFACT_SCHEMA
    )
    Draft202012Validator.check_schema(projection.FARS_COUNTY_PROJECTION_ARTIFACT_SCHEMA)
