# SPDX-License-Identifier: Apache-2.0
"""Tests for the private FARS county crosswalk review workflow."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import subprocess
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any, cast

import pytest

from nearmiss import fars_county_crosswalk_review as review
from nearmiss import fars_county_feasibility as feasibility
from nearmiss.fars_national_context import FARS_2024_STATE_CODES
from nearmiss.fars_year_contracts import fars_year_contract_revision

ROOT = Path(__file__).resolve().parents[1]


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


def _feasibility() -> dict[str, object]:
    records = [
        _record(case=index, state=state, county="001", modes=["pedestrian"])
        for index, state in enumerate(
            (state for state in FARS_2024_STATE_CODES if state != "43"), start=1
        )
    ]
    return feasibility._build_county_feasibility(
        records,
        contract=fars_year_contract_revision(2024, 1),
        normalized_sha256=hashlib.sha256(b"review-fixture").hexdigest(),
        require_national_coverage=True,
    )


def _boundary() -> dict[str, object]:
    return {
        "presentation_vintage": 2024,
        "distribution_url": (
            "https://www2.census.gov/geo/tiger/GENZ2024/kml/cb_2024_us_county_20m.zip"
        ),
        "raw_zip_sha256": hashlib.sha256(b"boundary-raw").hexdigest(),
        "raw_zip_size_bytes": 123_456,
        "member_name": "cb_2024_us_county_20m.kml",
        "member_sha256": hashlib.sha256(b"boundary-member").hexdigest(),
        "resolution": "1:20,000,000",
        "conversion_version": "county-boundary-kml-to-rfc7946-v1",
    }


def _review() -> dict[str, object]:
    return review.build_fars_county_crosswalk_review_template(_feasibility())


def test_template_covers_every_reported_source_code_without_counts_or_record_ids() -> None:
    artifact = _review()
    rows = cast(list[dict[str, Any]], artifact["rows"])
    assert len(rows) == 51
    assert [(row["state_code"], row["county_code"]) for row in rows] == [
        (state, "001") for state in FARS_2024_STATE_CODES if state != "43"
    ]
    assert all(row["mapping_status"] == "unresolved" for row in rows)
    payload = review.canonical_fars_county_crosswalk_review_bytes(artifact)
    assert b"crash_count" not in payload
    assert b"source_record_id" not in payload
    assert b"2024:1" not in payload


def test_review_packet_is_canonical_and_binds_the_exact_feasibility_artifact() -> None:
    feasibility_artifact = _feasibility()
    artifact = _review()
    source = cast(dict[str, str], artifact["source_lineage"])
    expected = hashlib.sha256(
        feasibility.canonical_fars_county_feasibility_bytes(feasibility_artifact)
    ).hexdigest()
    assert source["feasibility_sha256"] == expected
    assert (
        review.fars_county_crosswalk_review_sha256(artifact)
        == hashlib.sha256(review.canonical_fars_county_crosswalk_review_bytes(artifact)).hexdigest()
    )


def test_crosswalk_build_rejects_the_unedited_template() -> None:
    feasibility_artifact = _feasibility()
    with pytest.raises(ValueError, match="pending reference"):
        review.build_fars_county_crosswalk_from_review(
            _review(), feasibility_artifact=feasibility_artifact, boundary=_boundary()
        )


def test_crosswalk_build_preserves_explicit_unresolved_review_rows() -> None:
    feasibility_artifact = _feasibility()
    artifact = _review()
    artifact["review_reference"] = "county-review-20260718"
    output = review.build_fars_county_crosswalk_from_review(
        artifact, feasibility_artifact=feasibility_artifact, boundary=_boundary()
    )
    assert output["accounting"] == {
        "source_row_count": 51,
        "resolved_row_count": 0,
        "unresolved_row_count": 51,
        "state_count": 51,
        "presentation_geoid_count": 0,
    }


def test_review_packet_fails_closed_when_a_source_code_is_omitted() -> None:
    feasibility_artifact = _feasibility()
    artifact = _review()
    rows = cast(list[dict[str, object]], artifact["rows"])
    artifact["rows"] = rows[:-1]
    artifact["accounting"] = {"source_row_count": len(rows) - 1}
    artifact["review_reference"] = "county-review-20260718"
    with pytest.raises(ValueError, match="does not cover feasibility source codes"):
        review.build_fars_county_crosswalk_from_review(
            artifact, feasibility_artifact=feasibility_artifact, boundary=_boundary()
        )


def test_review_packet_fails_closed_when_detached_from_feasibility() -> None:
    feasibility_artifact = _feasibility()
    artifact = _review()
    artifact["review_reference"] = "county-review-20260718"
    source = cast(dict[str, str], artifact["source_lineage"])
    source["normalized_sha256"] = hashlib.sha256(b"wrong").hexdigest()
    with pytest.raises(ValueError, match="detached from feasibility"):
        review.build_fars_county_crosswalk_from_review(
            artifact, feasibility_artifact=feasibility_artifact, boundary=_boundary()
        )


def test_review_validation_rejects_noncanonical_row_order() -> None:
    artifact = _review()
    rows = cast(list[dict[str, object]], artifact["rows"])
    artifact["rows"] = list(reversed(rows))
    with pytest.raises(ValueError, match="canonically ordered"):
        review.validate_fars_county_crosswalk_review_artifact(copy.deepcopy(artifact))


def test_cli_writes_a_private_no_count_review_template(tmp_path: Path) -> None:
    feasibility_path = tmp_path / "feasibility.json"
    template_path = tmp_path / "review.json"
    feasibility_path.write_bytes(
        feasibility.canonical_fars_county_feasibility_bytes(_feasibility())
    )
    environment = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
    result = subprocess.run(
        [
            sys.executable,
            "tools/build_fars_county_crosswalk.py",
            "--feasibility",
            str(feasibility_path),
            "--template-out",
            str(template_path),
        ],
        cwd=ROOT,
        capture_output=True,
        check=False,
        env=environment,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    template = json.loads(template_path.read_text(encoding="utf-8"))
    assert template["visibility"] == "private"
    assert template["accounting"] == {"source_row_count": 51}
    assert "crash_count" not in template_path.read_text(encoding="utf-8")
