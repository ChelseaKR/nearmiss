# SPDX-License-Identifier: Apache-2.0
"""Known-answer and adversarial tests for private county crosswalk contracts."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any, cast

import pytest
from jsonschema import Draft202012Validator

from nearmiss import fars_county_crosswalk as crosswalk

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schema" / "fars-county-crosswalk.schema.json"


def _digest(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def _boundary() -> dict[str, object]:
    return {
        "presentation_vintage": 2024,
        "distribution_url": (
            "https://www2.census.gov/geo/tiger/GENZ2024/kml/cb_2024_us_county_20m.zip"
        ),
        "raw_zip_sha256": _digest("county-boundaries-raw"),
        "raw_zip_size_bytes": 123_456,
        "member_name": "cb_2024_us_county_20m.kml",
        "member_sha256": _digest("county-boundaries-member"),
        "resolution": "1:20,000,000",
        "conversion_version": "county-boundary-kml-to-rfc7946-v1",
    }


def _row(
    *,
    state: str,
    county: str,
    county_fips: str,
    name: str,
    namelsad: str,
    entity_class: str,
    status: str = "exact",
) -> dict[str, object]:
    state_fips = f"{int(state):02d}"
    return {
        "state_code": state,
        "county_code": county,
        "mapping_status": status,
        "review_note": "Synthetic reviewed mapping fixture for contract validation",
        "presentation": {
            "state_fips": state_fips,
            "county_fips": county_fips,
            "geoid": state_fips + county_fips,
            "name": name,
            "namelsad": namelsad,
            "entity_class": entity_class,
        },
    }


def _rows() -> list[dict[str, object]]:
    return [
        _row(
            state="6",
            county="001",
            county_fips="001",
            name="Alameda",
            namelsad="Alameda County",
            entity_class="county",
        ),
        _row(
            state="51",
            county="760",
            county_fips="760",
            name="Richmond",
            namelsad="Richmond city",
            entity_class="independent_city",
        ),
        _row(
            state="2",
            county="013",
            county_fips="013",
            name="Aleutians East",
            namelsad="Aleutians East Borough",
            entity_class="borough",
        ),
        _row(
            state="22",
            county="001",
            county_fips="001",
            name="Acadia",
            namelsad="Acadia Parish",
            entity_class="parish",
        ),
        _row(
            state="11",
            county="001",
            county_fips="001",
            name="District of Columbia",
            namelsad="District of Columbia",
            entity_class="district",
        ),
    ]


def _artifact(rows: list[dict[str, object]] | None = None) -> dict[str, object]:
    return crosswalk.build_fars_county_crosswalk(
        list(reversed(_rows() if rows is None else rows)),
        year=2024,
        contract_revision=1,
        review_reference="county-crosswalk-fixture-20260718",
        boundary=_boundary(),
    )


def test_builds_canonical_crosswalk_for_county_equivalent_cases() -> None:
    artifact = _artifact()
    rows = cast(list[dict[str, Any]], artifact["rows"])
    assert [(row["state_code"], row["county_code"]) for row in rows] == [
        ("2", "013"),
        ("6", "001"),
        ("11", "001"),
        ("22", "001"),
        ("51", "760"),
    ]
    assert rows[-1]["presentation"] == {
        "state_fips": "51",
        "county_fips": "760",
        "geoid": "51760",
        "name": "Richmond",
        "namelsad": "Richmond city",
        "entity_class": "independent_city",
    }
    assert artifact["accounting"] == {
        "source_row_count": 5,
        "resolved_row_count": 5,
        "unresolved_row_count": 0,
        "state_count": 5,
        "presentation_geoid_count": 5,
    }


def test_crosswalk_canonical_bytes_and_digest_do_not_contain_private_rows() -> None:
    artifact = _artifact()
    crosswalk.validate_fars_county_crosswalk_artifact(artifact)
    first = crosswalk.canonical_fars_county_crosswalk_bytes(artifact)
    second = crosswalk.canonical_fars_county_crosswalk_bytes(copy.deepcopy(artifact))
    assert first == second
    assert first.endswith(b"\n") and b"\n" not in first[:-1]
    assert crosswalk.fars_county_crosswalk_sha256(artifact) == hashlib.sha256(first).hexdigest()
    assert b'"source_record_id"' not in first
    assert b'"latitude"' not in first
    assert b'"longitude"' not in first


@pytest.mark.parametrize("sentinel", ["000", "997", "998", "999"])
def test_sentinel_county_codes_cannot_enter_a_crosswalk(sentinel: str) -> None:
    row = _rows()[0]
    row["county_code"] = sentinel
    with pytest.raises(ValueError, match="sentinel county code"):
        _artifact([row])


def test_cross_state_presentation_target_fails_closed() -> None:
    row = _rows()[0]
    presentation = cast(dict[str, str], row["presentation"])
    presentation["state_fips"] = "51"
    presentation["geoid"] = "51001"
    with pytest.raises(ValueError, match="crosses a state boundary"):
        _artifact([row])


def test_unresolved_rows_remain_private_and_block_future_public_projection() -> None:
    row = _rows()[0]
    row["mapping_status"] = "unresolved"
    row["presentation"] = None
    artifact = _artifact([row])
    crosswalk.validate_fars_county_crosswalk_artifact(artifact)
    assert artifact["accounting"] == {
        "source_row_count": 1,
        "resolved_row_count": 0,
        "unresolved_row_count": 1,
        "state_count": 1,
        "presentation_geoid_count": 0,
    }
    with pytest.raises(ValueError, match="unresolved source county codes"):
        crosswalk.require_fars_county_crosswalk_resolved(artifact)


def test_duplicate_source_key_and_unreviewed_many_to_one_target_fail_closed() -> None:
    duplicate_source = _rows()[:2]
    duplicate_source[1]["state_code"] = "6"
    duplicate_source[1]["county_code"] = "001"
    with pytest.raises(ValueError, match="uniquely canonically ordered"):
        _artifact(duplicate_source)

    duplicate_target = _rows()[:2]
    duplicate_target[1]["state_code"] = "6"
    duplicate_target[1]["county_code"] = "003"
    presentation = cast(dict[str, str], duplicate_target[1]["presentation"])
    presentation.update(
        {
            "state_fips": "06",
            "county_fips": "001",
            "geoid": "06001",
            "name": "Alameda",
            "namelsad": "Alameda County",
            "entity_class": "county",
        }
    )
    with pytest.raises(ValueError, match="duplicate presentation GEOID"):
        _artifact(duplicate_target)


def test_explicit_retired_to_current_mapping_can_share_a_reviewed_target() -> None:
    retired = _rows()[:2]
    retired[1]["state_code"] = "6"
    retired[1]["county_code"] = "003"
    retired[1]["mapping_status"] = "retired_to_current"
    presentation = cast(dict[str, str], retired[1]["presentation"])
    presentation.update(
        {
            "state_fips": "06",
            "county_fips": "001",
            "geoid": "06001",
            "name": "Alameda",
            "namelsad": "Alameda County",
            "entity_class": "county",
        }
    )
    artifact = _artifact(retired)
    assert cast(dict[str, int], artifact["accounting"])["presentation_geoid_count"] == 1
    crosswalk.require_fars_county_crosswalk_resolved(artifact)


def test_source_lineage_is_bound_to_the_selected_annual_contract() -> None:
    artifact = _artifact()
    source = cast(dict[str, Any], artifact["source_lineage"])
    source["county_code_system"] = "census_geoid"
    with pytest.raises(ValueError, match="source lineage is inconsistent"):
        crosswalk.validate_fars_county_crosswalk_artifact(artifact)


def test_repository_schema_matches_embedded_contract() -> None:
    assert json.loads(SCHEMA_PATH.read_text(encoding="utf-8")) == (
        crosswalk.FARS_COUNTY_CROSSWALK_ARTIFACT_SCHEMA
    )
    Draft202012Validator.check_schema(crosswalk.FARS_COUNTY_CROSSWALK_ARTIFACT_SCHEMA)
