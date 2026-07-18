# SPDX-License-Identifier: Apache-2.0
"""Known-answer and leakage tests for public county FARS state shards."""

from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Iterable
from typing import Any, cast

import pytest
from tools import build_us_county_boundaries as boundaries

from nearmiss import fars_county_boundary_publication as boundary_publication
from nearmiss import fars_county_crosswalk as crosswalk
from nearmiss import fars_county_feasibility as feasibility
from nearmiss import fars_county_projection as projection
from nearmiss import fars_county_publication as publication
from nearmiss.adapters.fars_joined import MODE_ORDER
from nearmiss.fars_national_context import FARS_2024_STATE_CODES
from nearmiss.fars_year_contracts import fars_year_contract_revision


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
            "county_status": "reported",
            "county_code_system": "nhtsa_fars_gsa_2024",
        },
    }


def _feasibility(*, california_count: int = 1) -> dict[str, object]:
    records = [
        _record(case=index, state=state, county="001", modes=["pedestrian"])
        for index, state in enumerate(
            (state for state in FARS_2024_STATE_CODES if state != "43"), start=1
        )
    ]
    records.extend(
        _record(case=len(records) + offset, state="6", county="001", modes=["pedestrian"])
        for offset in range(1, california_count)
    )
    return feasibility._build_county_feasibility(
        records,
        contract=fars_year_contract_revision(2024, 1),
        normalized_sha256=hashlib.sha256(b"county-publication-fixture").hexdigest(),
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


def _crosswalk() -> dict[str, object]:
    rows = [
        {
            "state_code": state_code,
            "county_code": "001",
            "mapping_status": "exact",
            "review_note": "Synthetic national mapping fixture for public shard validation",
            "presentation": _presentation(state_code),
        }
        for state_code in FARS_2024_STATE_CODES
        if state_code != "43"
    ]
    return crosswalk.build_fars_county_crosswalk(
        rows,
        year=2024,
        contract_revision=1,
        review_reference="county-publication-fixture-20260718",
        boundary=boundaries._boundary_source(),
    )


def _feature(state_code: str) -> dict[str, object]:
    presentation = _presentation(state_code)
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


def _boundaries() -> dict[str, dict[str, object]]:
    return {
        f"{int(state_code):02d}": boundaries._shard(
            f"{int(state_code):02d}", [_feature(state_code)]
        )
        for state_code in FARS_2024_STATE_CODES
        if state_code != "43"
    }


def _inputs(
    *, california_count: int = 1
) -> tuple[dict[str, object], dict[str, object], dict[str, object], dict[str, dict[str, object]]]:
    feasibility_artifact = _feasibility(california_count=california_count)
    crosswalk_artifact = _crosswalk()
    private_boundary_shards = _boundaries()
    projection_artifact = projection.build_private_fars_county_projection(
        feasibility_artifact, crosswalk_artifact, private_boundary_shards
    )
    public_boundary_shards = {
        state_fips: boundary_publication.build_public_fars_county_boundary_state_artifact(shard)
        for state_fips, shard in private_boundary_shards.items()
    }
    return feasibility_artifact, crosswalk_artifact, projection_artifact, public_boundary_shards


def _artifact(*, california_count: int = 1) -> dict[str, object]:
    feasibility_artifact, crosswalk_artifact, projection_artifact, boundary_shards = _inputs(
        california_count=california_count
    )
    return publication.build_public_fars_county_state_artifact(
        feasibility_artifact,
        crosswalk_artifact,
        projection_artifact,
        boundary_shards["06"],
        state_fips="06",
    )


def test_below_floor_count_is_publicly_indistinguishable_from_zero() -> None:
    artifact = _artifact(california_count=1)
    publication.validate_public_fars_county_state_artifact(artifact)
    county = cast(list[dict[str, Any]], artifact["counties"])[0]
    assert county["geoid"] == "06001"
    assert county["cells"] == [
        {"involved_mode": mode, "status": "suppressed_or_zero"} for mode in MODE_ORDER
    ]
    assert artifact["accounting"] == {
        "county_count": 1,
        "county_mode_cell_count": 6,
        "published_cell_count": 0,
        "suppressed_or_zero_cell_count": 6,
    }


def test_count_at_floor_is_published_without_exposing_private_lineage() -> None:
    artifact = _artifact(california_count=10)
    county = cast(list[dict[str, Any]], artifact["counties"])[0]
    pedestrian = county["cells"][3]
    assert pedestrian == {
        "involved_mode": "pedestrian",
        "status": "published",
        "crash_count": 10,
    }
    payload = publication.canonical_public_fars_county_state_bytes(artifact)
    assert b'"feasibility_sha256"' not in payload
    assert b'"projection_sha256"' not in payload
    assert b'"county_code"' not in payload
    assert b'"source_record_id"' not in payload
    assert b"nearmiss.private.us_county_boundary_shard" not in payload


def test_canonical_bytes_are_stable_and_suppressed_cells_have_no_numeric_field() -> None:
    artifact = _artifact(california_count=1)
    first = publication.canonical_public_fars_county_state_bytes(artifact)
    second = publication.canonical_public_fars_county_state_bytes(copy.deepcopy(artifact))
    assert first == second
    assert first.endswith(b"\n") and b"\n" not in first[:-1]
    assert b'"crash_count"' not in first


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (b"", "byte safety limit"),
        (b" " * (publication.FARS_COUNTY_PUBLIC_ARTIFACT_MAX_BYTES + 1), "byte safety limit"),
        (b"\xff", "not UTF-8"),
        (b"{", "invalid JSON"),
        (b"[]", "must be an object"),
        (b'{"value":NaN}', "non-finite"),
        (b'{"state":1,"state":2}', "duplicate key"),
    ],
)
def test_public_county_loader_rejects_unsafe_or_noncanonical_payloads(
    payload: bytes, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        publication.load_public_fars_county_state_bytes(payload)


def test_public_county_loader_requires_exact_canonical_bytes() -> None:
    payload = publication.canonical_public_fars_county_state_bytes(_artifact(california_count=10))
    assert publication.load_public_fars_county_state_bytes(payload)["dataset_year"] == 2024
    pretty = json.dumps(json.loads(payload), indent=2).encode("utf-8")
    with pytest.raises(ValueError, match="not canonical"):
        publication.load_public_fars_county_state_bytes(pretty)


def test_input_lineage_and_boundary_identity_fail_closed() -> None:
    feasibility_artifact, crosswalk_artifact, projection_artifact, boundary_shards = _inputs()
    source = cast(dict[str, str], feasibility_artifact["source_lineage"])
    source["normalized_sha256"] = hashlib.sha256(b"changed").hexdigest()
    with pytest.raises(ValueError, match="detached from reviewed inputs"):
        publication.build_public_fars_county_state_artifact(
            feasibility_artifact,
            crosswalk_artifact,
            projection_artifact,
            boundary_shards["06"],
            state_fips="06",
        )

    feasibility_artifact, crosswalk_artifact, projection_artifact, boundary_shards = _inputs()
    shard = cast(dict[str, Any], boundary_shards["06"])
    features = cast(list[dict[str, object]], shard["features"])
    feature = features[0]
    properties = cast(dict[str, str], feature["properties"])
    properties["name"] = "Incorrect identity"
    with pytest.raises(ValueError, match="matching boundary county"):
        publication.build_public_fars_county_state_artifact(
            feasibility_artifact,
            crosswalk_artifact,
            projection_artifact,
            boundary_shards["06"],
            state_fips="06",
        )


def test_validator_rejects_numeric_suppression_leak_and_low_published_value() -> None:
    artifact = _artifact(california_count=1)
    county = cast(list[dict[str, Any]], artifact["counties"])[0]
    county["cells"][0]["crash_count"] = 1
    with pytest.raises(ValueError, match="not valid under"):
        publication.validate_public_fars_county_state_artifact(artifact)

    artifact = _artifact(california_count=10)
    county = cast(list[dict[str, Any]], artifact["counties"])[0]
    county["cells"][3]["crash_count"] = 9
    with pytest.raises(ValueError, match="not valid under"):
        publication.validate_public_fars_county_state_artifact(artifact)


def test_effective_k_cannot_be_lowered_below_the_publication_floor() -> None:
    feasibility_artifact, crosswalk_artifact, projection_artifact, boundary_shards = _inputs()
    with pytest.raises(ValueError, match="outside its reviewed safety bounds"):
        publication.build_public_fars_county_state_artifact(
            feasibility_artifact,
            crosswalk_artifact,
            projection_artifact,
            boundary_shards["06"],
            state_fips="06",
            effective_k=9,
        )


def test_higher_effective_k_changes_the_exact_public_caveat() -> None:
    feasibility_artifact, crosswalk_artifact, projection_artifact, boundary_shards = _inputs(
        california_count=11
    )
    artifact = publication.build_public_fars_county_state_artifact(
        feasibility_artifact,
        crosswalk_artifact,
        projection_artifact,
        boundary_shards["06"],
        state_fips="06",
        effective_k=11,
    )
    assert "floor k=11" in cast(str, artifact["caveat"])
    county = cast(list[dict[str, Any]], artifact["counties"])[0]
    assert county["cells"][3]["status"] == "published"


@pytest.mark.parametrize("state_fips", ["CA", "00"])
def test_state_fips_must_be_a_reviewed_fars_coverage_state(state_fips: str) -> None:
    with pytest.raises(ValueError, match="state"):
        publication._state_code_from_fips(state_fips)


def test_validator_rejects_source_state_county_and_mode_identity_drift() -> None:
    artifact = _artifact()
    source = cast(dict[str, object], artifact["source"])
    source["source_id"] = "wrong-source"
    with pytest.raises(ValueError, match="source lineage"):
        publication.validate_public_fars_county_state_artifact(artifact)

    artifact = _artifact()
    state = cast(dict[str, str], artifact["state"])
    state["state_fips"] = "00"
    with pytest.raises(ValueError, match="outside reviewed coverage"):
        publication.validate_public_fars_county_state_artifact(artifact)

    artifact = _artifact()
    county = cast(list[dict[str, Any]], artifact["counties"])[0]
    county["county_fips"] = "002"
    with pytest.raises(ValueError, match="county identity"):
        publication.validate_public_fars_county_state_artifact(artifact)

    artifact = _artifact()
    county = cast(list[dict[str, Any]], artifact["counties"])[0]
    cells = cast(list[dict[str, object]], county["cells"])
    county["cells"] = list(reversed(cells))
    with pytest.raises(ValueError, match="not valid under"):
        publication.validate_public_fars_county_state_artifact(artifact)


def test_builder_rejects_year_and_crosswalk_lineage_mismatches() -> None:
    feasibility_artifact, crosswalk_artifact, projection_artifact, boundary_shards = _inputs()
    projection_artifact["dataset_year"] = 2023
    with pytest.raises(ValueError, match="different dataset years"):
        publication.build_public_fars_county_state_artifact(
            feasibility_artifact,
            crosswalk_artifact,
            projection_artifact,
            boundary_shards["06"],
            state_fips="06",
        )


def test_internal_safety_guards_reject_invalid_metadata_and_shapes() -> None:
    with pytest.raises(ValueError, match="invalid fixture"):
        publication._mapping([], label="fixture")
    with pytest.raises(ValueError, match="invalid fixture"):
        publication._sequence({}, label="fixture")
    with pytest.raises(ValueError, match="effective k"):
        publication.fars_county_public_caveat(2024, effective_k=9)

    artifact = _artifact()
    source = copy.deepcopy(cast(dict[str, object], artifact["source"]))
    source["contract_revision"] = "1"
    with pytest.raises(ValueError, match="contract revision"):
        publication._validate_public_source(source, year=2024)
    source["contract_revision"] = 999
    with pytest.raises(ValueError, match="unregistered annual contract"):
        publication._validate_public_source(source, year=2024)

    artifact = _artifact()
    state = cast(dict[str, str], artifact["state"])
    state["state_abbreviation"] = "ZZ"
    with pytest.raises(ValueError, match="state identity"):
        publication.validate_public_fars_county_state_artifact(artifact)

    artifact = _artifact()
    artifact["caveat"] = "not the reviewed caveat"
    with pytest.raises(ValueError, match="caveat"):
        publication.validate_public_fars_county_state_artifact(artifact)

    artifact = _artifact()
    accounting = cast(dict[str, int], artifact["accounting"])
    accounting["published_cell_count"] = 1
    with pytest.raises(ValueError, match="accounting"):
        publication.validate_public_fars_county_state_artifact(artifact)

    feasibility_artifact, crosswalk_artifact, projection_artifact, boundary_shards = _inputs()
    source = cast(dict[str, object], crosswalk_artifact["source_lineage"])
    source["source_revision_id"] = "wrong-review"
    with pytest.raises(ValueError, match="source lineage is inconsistent"):
        publication.build_public_fars_county_state_artifact(
            feasibility_artifact,
            crosswalk_artifact,
            projection_artifact,
            boundary_shards["06"],
            state_fips="06",
        )
