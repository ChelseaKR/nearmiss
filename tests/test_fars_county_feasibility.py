# SPDX-License-Identifier: Apache-2.0
"""Known-answer and adversarial tests for private county feasibility accounting."""

from __future__ import annotations

import copy
import hashlib
from collections.abc import Iterable
from typing import Any, cast

import pytest
from jsonschema import Draft202012Validator

from nearmiss import fars_county_feasibility as feasibility
from nearmiss.fars_national_context import FARS_2024_STATE_CODES
from nearmiss.fars_year_contracts import fars_year_contract_revision


def _record(
    *,
    case: int,
    state: str,
    county: str,
    modes: Iterable[str],
    county_status: str | None = None,
) -> dict[str, object]:
    status = {
        "000": "not_applicable",
        "997": "other",
        "998": "not_reported",
        "999": "unknown",
    }.get(county, "reported")
    if county_status is not None:
        status = county_status
    source_id = f"2024:{case}"
    return {
        "outcome": {"source_record_id": source_id, "state_code": state},
        "mode_summary": {"source_record_id": source_id, "involved_modes": list(modes)},
        "jurisdiction": {
            "source_record_id": source_id,
            "state_code": state,
            "state_code_system": "nhtsa_fars_state_2024",
            "county_code": county,
            "county_status": status,
            "county_code_system": "nhtsa_fars_gsa_2024",
        },
    }


def _artifact(records: list[dict[str, object]]) -> dict[str, object]:
    return feasibility._build_county_feasibility(
        records,
        contract=fars_year_contract_revision(2024, 1),
        normalized_sha256=hashlib.sha256(b"county-feasibility-fixture").hexdigest(),
        require_national_coverage=False,
    )


def _national_records() -> list[dict[str, object]]:
    return [
        _record(case=index, state=state, county="001", modes=["pedestrian"])
        for index, state in enumerate(
            (code for code in FARS_2024_STATE_CODES if code != "43"), start=1
        )
    ]


def test_known_answer_separates_reported_counties_from_every_sentinel_bucket() -> None:
    artifact = _artifact(
        [
            _record(case=1, state="6", county="001", modes=["pedestrian", "pedalcyclist"]),
            _record(case=2, state="6", county="001", modes=["pedestrian"]),
            _record(case=3, state="6", county="003", modes=["motorcyclist"]),
            _record(case=4, state="6", county="000", modes=["other_road_user"]),
            _record(case=5, state="6", county="997", modes=["pedestrian"]),
            _record(case=6, state="6", county="998", modes=["pedestrian"]),
            _record(case=7, state="6", county="999", modes=["pedestrian"]),
            _record(case=8, state="48", county="201", modes=["motor_vehicle_occupant"]),
        ]
    )

    assert artifact["states"] == [
        {
            "state_code": "6",
            "county_cells": [
                {"county_code": "001", "involved_mode": "pedalcyclist", "crash_count": 1},
                {"county_code": "001", "involved_mode": "pedestrian", "crash_count": 2},
                {"county_code": "003", "involved_mode": "motorcyclist", "crash_count": 1},
            ],
            "sentinel_cells": [
                {
                    "county_status": "not_applicable",
                    "involved_mode": "other_road_user",
                    "crash_count": 1,
                },
                {"county_status": "other", "involved_mode": "pedestrian", "crash_count": 1},
                {"county_status": "not_reported", "involved_mode": "pedestrian", "crash_count": 1},
                {"county_status": "unknown", "involved_mode": "pedestrian", "crash_count": 1},
            ],
            "state_mode_totals": [
                {"involved_mode": "motorcyclist", "crash_count": 1},
                {"involved_mode": "pedalcyclist", "crash_count": 1},
                {"involved_mode": "pedestrian", "crash_count": 5},
                {"involved_mode": "other_road_user", "crash_count": 1},
            ],
        },
        {
            "state_code": "48",
            "county_cells": [
                {"county_code": "201", "involved_mode": "motor_vehicle_occupant", "crash_count": 1}
            ],
            "sentinel_cells": [],
            "state_mode_totals": [{"involved_mode": "motor_vehicle_occupant", "crash_count": 1}],
        },
    ]
    assert artifact["accounting"] == {
        "case_count": 8,
        "state_count": 2,
        "reported_county_cell_count": 4,
        "sentinel_cell_count": 4,
        "state_mode_total_count": 5,
        "reported_county_contribution_total": 5,
        "sentinel_contribution_total": 4,
        "crash_contribution_total": 9,
    }


def test_national_artifact_validates_and_serializes_canonically_without_source_record_ids() -> None:
    artifact = feasibility._build_county_feasibility(
        _national_records(),
        contract=fars_year_contract_revision(2024, 1),
        normalized_sha256=hashlib.sha256(b"national-county-fixture").hexdigest(),
        require_national_coverage=True,
    )
    feasibility.validate_fars_county_feasibility_artifact(artifact)
    first = feasibility.canonical_fars_county_feasibility_bytes(artifact)
    second = feasibility.canonical_fars_county_feasibility_bytes(copy.deepcopy(artifact))
    assert first == second
    assert first.endswith(b"\n") and b"\n" not in first[:-1]
    assert b'"source_record_id"' not in first
    assert b'"occurred_on"' not in first
    assert b'"latitude"' not in first
    assert b'"longitude"' not in first


def test_duplicate_crash_identity_fails_before_aggregation() -> None:
    records = [_record(case=1, state="6", county="001", modes=["pedestrian"])] * 2
    with pytest.raises(ValueError, match="duplicate crash identities"):
        _artifact(records)


def test_verified_builder_requires_a_proof_bound_annual_snapshot() -> None:
    with pytest.raises(TypeError, match="proof-bound annual snapshot"):
        feasibility.build_verified_fars_year_county_feasibility(
            object(),
            year=2024,
            contract_revision=1,
        )


@pytest.mark.parametrize(
    ("county", "status", "message"),
    [
        ("001", "unknown", "status is inconsistent"),
        ("997", "reported", "status is inconsistent"),
        ("01", "reported", "noncanonical county code"),
    ],
)
def test_source_county_identity_and_status_must_remain_exact(
    county: str, status: str, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        _artifact(
            [_record(case=1, state="6", county=county, modes=["pedestrian"], county_status=status)]
        )


def test_source_code_system_mismatch_fails_closed() -> None:
    record = _record(case=1, state="6", county="001", modes=["pedestrian"])
    cast(dict[str, object], record["jurisdiction"])["county_code_system"] = "census_geoid"
    with pytest.raises(ValueError, match="county code system"):
        _artifact([record])


def test_artifact_validator_rejects_sentinel_as_a_public_like_county_cell() -> None:
    artifact = feasibility._build_county_feasibility(
        _national_records(),
        contract=fars_year_contract_revision(2024, 1),
        normalized_sha256=hashlib.sha256(b"national-county-fixture").hexdigest(),
        require_national_coverage=True,
    )
    states = cast(list[dict[str, Any]], artifact["states"])
    states[0]["county_cells"] = [
        {"county_code": "997", "involved_mode": "pedestrian", "crash_count": 1}
    ]
    with pytest.raises(ValueError, match="sentinel as a county"):
        feasibility.validate_fars_county_feasibility_artifact(artifact)


def test_embedded_schema_is_valid_json_schema() -> None:
    Draft202012Validator.check_schema(feasibility.FARS_COUNTY_FEASIBILITY_ARTIFACT_SCHEMA)
