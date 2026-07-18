# SPDX-License-Identifier: Apache-2.0
"""County release-index tests keep public delivery separate from the site allowlist."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any, cast

import pytest
from jsonschema import Draft202012Validator
from tools import build_fars_county_public_index as index_builder
from tools import build_us_county_boundaries as private_boundaries

from nearmiss import fars_county_boundary_publication as boundary_publication
from nearmiss import fars_county_crosswalk as crosswalk
from nearmiss import fars_county_feasibility as feasibility
from nearmiss import fars_county_projection as projection
from nearmiss import fars_county_public_index as release_index
from nearmiss import fars_county_publication as publication
from nearmiss.fars_national_context import FARS_2024_STATE_CODES
from nearmiss.fars_year_contracts import fars_year_contract_revision

ROOT = Path(__file__).resolve().parents[1]
INDEX_SCHEMA_PATH = ROOT / "schema" / "public-fars-county-context-index.schema.json"
CORRECTION_SCHEMA_PATH = ROOT / "schema" / "public-fars-county-release-corrections.schema.json"
VALUE_R1 = "fars/2024/counties/06-r1.json"
VALUE_R2 = "fars/2024/counties/06-r2.json"
BOUNDARY = "counties/06.json"


def _record(*, case: int, state: str, county: str) -> dict[str, object]:
    source_id = f"2024:{case}"
    return {
        "outcome": {"source_record_id": source_id, "state_code": state},
        "mode_summary": {"source_record_id": source_id, "involved_modes": ["pedestrian"]},
        "jurisdiction": {
            "source_record_id": source_id,
            "state_code": state,
            "state_code_system": "nhtsa_fars_state_2024",
            "county_code": county,
            "county_status": "reported",
            "county_code_system": "nhtsa_fars_gsa_2024",
        },
    }


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


def _inputs(
    california_count: int,
) -> tuple[dict[str, object], dict[str, object], dict[str, object], dict[str, dict[str, object]]]:
    state_codes = [state for state in FARS_2024_STATE_CODES if state != "43"]
    records = [
        _record(case=index, state=state, county="001")
        for index, state in enumerate(state_codes, start=1)
    ]
    records.extend(
        _record(case=len(records) + offset, state="6", county="001")
        for offset in range(1, california_count)
    )
    feasibility_artifact = feasibility._build_county_feasibility(
        records,
        contract=fars_year_contract_revision(2024, 1),
        normalized_sha256=hashlib.sha256(b"county-index-fixture").hexdigest(),
        require_national_coverage=True,
    )
    rows = [
        {
            "state_code": state_code,
            "county_code": "001",
            "mapping_status": "exact",
            "review_note": "Synthetic national mapping fixture for county index validation",
            "presentation": _presentation(state_code),
        }
        for state_code in state_codes
    ]
    crosswalk_artifact = crosswalk.build_fars_county_crosswalk(
        rows,
        year=2024,
        contract_revision=1,
        review_reference="county-index-fixture-20260718",
        boundary=private_boundaries._boundary_source(),
    )
    private_shards: dict[str, dict[str, object]] = {}
    for state_code in state_codes:
        presentation = _presentation(state_code)
        feature = {
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
        state_fips = presentation["state_fips"]
        private_shards[state_fips] = private_boundaries._shard(state_fips, [feature])
    projection_artifact = projection.build_private_fars_county_projection(
        feasibility_artifact, crosswalk_artifact, private_shards
    )
    public_shards = {
        state_fips: boundary_publication.build_public_fars_county_boundary_state_artifact(shard)
        for state_fips, shard in private_shards.items()
    }
    return feasibility_artifact, crosswalk_artifact, projection_artifact, public_shards


def _value_and_boundary() -> tuple[bytes, bytes]:
    feasibility, crosswalk, projection, boundaries = _inputs(california_count=10)
    value = publication.build_public_fars_county_state_artifact(
        feasibility,
        crosswalk,
        projection,
        boundaries["06"],
        state_fips="06",
    )
    return (
        publication.canonical_public_fars_county_state_bytes(value),
        json.dumps(
            boundaries["06"],
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        + b"\n",
    )


def _empty_ledger() -> bytes:
    return release_index.canonical_fars_county_public_correction_ledger_bytes(
        release_index.empty_fars_county_public_correction_ledger()
    )


def _index(
    *, value_path: str = VALUE_R1, ledger: bytes | None = None
) -> tuple[dict[str, object], bytes, bytes, bytes]:
    value, boundary = _value_and_boundary()
    ledger_payload = _empty_ledger() if ledger is None else ledger
    index = release_index.build_fars_county_public_release_index(
        {value_path: value},
        {BOUNDARY: boundary},
        ledger_payload,
        release_id="county-pilot-2024-r1",
    )
    return index, value, boundary, ledger_payload


def _pin(path: str, payload: bytes, *, revision: int | None = None) -> dict[str, object]:
    pin: dict[str, object] = {
        "path": path,
        "bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
    }
    if revision is not None:
        pin["revision"] = revision
    return pin


def _correction_ledger(value: bytes, boundary: bytes) -> bytes:
    ledger = release_index.empty_fars_county_public_correction_ledger()
    ledger["corrections"] = [
        {
            "correction_id": "county-ca-r1-r2",
            "affected": {"dataset_year": 2024, "state_fips": "06"},
            "prior_value": _pin(VALUE_R1, value, revision=1),
            "replacement_value": _pin(VALUE_R2, value, revision=2),
            "prior_boundary": _pin(BOUNDARY, boundary),
            "replacement_boundary": _pin(BOUNDARY, boundary),
            "impact": {"values": True, "identities": False, "geometry": False, "copy": False},
            "reason": "Synthetic immutable revision fixture for release-contract validation.",
            "review_date": "2026-07-18",
            "replacement_deployment_commit": "a" * 40,
        }
    ]
    return release_index.canonical_fars_county_public_correction_ledger_bytes(ledger)


def test_index_pins_value_boundary_crosswalk_and_correction_ledger() -> None:
    index, value, boundary, ledger = _index()
    release_index.validate_fars_county_public_release_index(index)
    payload = release_index.canonical_fars_county_public_release_index_bytes(index)
    assert release_index.load_fars_county_public_release_index_bytes(payload) == index
    assert payload.endswith(b"\n") and b"\n" not in payload[:-1]
    assert b'"source_record_id"' not in payload
    release = cast(list[dict[str, Any]], index["releases"])[0]
    state = release["states"][0]
    assert state["value"] == _pin(VALUE_R1, value, revision=1)
    assert state["boundary"] == _pin(BOUNDARY, boundary)
    assert index["correction_ledger"] == _pin(
        release_index.FARS_COUNTY_PUBLIC_CORRECTIONS_FILENAME, ledger
    )


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (b"", "byte safety limit"),
        (b" " * (release_index.FARS_COUNTY_PUBLIC_INDEX_MAX_BYTES + 1), "byte safety limit"),
        (b"\xff", "not UTF-8"),
        (b"{", "invalid JSON"),
        (b"[]", "must be an object"),
        (b'{"value":NaN}', "non-finite"),
        (b'{"state":1,"state":2}', "duplicate key"),
    ],
)
def test_index_loader_rejects_unsafe_or_noncanonical_payloads(payload: bytes, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        release_index.load_fars_county_public_release_index_bytes(payload)


def test_index_rejects_detached_boundary_and_noncanonical_state_path() -> None:
    _index_value, value, boundary, ledger = _index()
    boundary_value = json.loads(boundary)
    boundary_value["features"][0]["properties"]["name"] = "Detached fixture county"
    detached = (
        json.dumps(
            boundary_value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")
    with pytest.raises(ValueError, match="detached from its indexed public boundary"):
        release_index.build_fars_county_public_release_index(
            {VALUE_R1: value}, {BOUNDARY: detached}, ledger, release_id="county-pilot-2024-r1"
        )
    with pytest.raises(ValueError, match="path is not canonical"):
        release_index.build_fars_county_public_release_index(
            {"fars/2024/counties/CA-r1.json": value},
            {BOUNDARY: boundary},
            ledger,
            release_id="county-pilot-2024-r1",
        )


def test_release_directory_verifies_exact_files_and_rejects_unindexed_shards(
    tmp_path: Path,
) -> None:
    _index_value, value, boundary, _ledger = _index()
    ledger = _correction_ledger(value, boundary)
    index, _value, _boundary, _ledger = _index(value_path=VALUE_R2, ledger=ledger)
    root = tmp_path / "published"
    (root / VALUE_R1).parent.mkdir(parents=True)
    (root / VALUE_R1).write_bytes(value)
    (root / VALUE_R2).write_bytes(value)
    (root / BOUNDARY).parent.mkdir(parents=True)
    (root / BOUNDARY).write_bytes(boundary)
    (root / release_index.FARS_COUNTY_PUBLIC_CORRECTIONS_FILENAME).write_bytes(ledger)
    expected_index = release_index.canonical_fars_county_public_release_index_bytes(index)
    assert (
        index_builder.build_index(
            root=root,
            values=[VALUE_R2],
            boundaries=[BOUNDARY],
            release_id="county-pilot-2024-r1",
        )
        == expected_index
    )
    with pytest.raises(ValueError, match="relative"):
        index_builder.build_index(
            root=root,
            values=["../private.json"],
            boundaries=[BOUNDARY],
            release_id="county-pilot-2024-r1",
        )
    (root / release_index.FARS_COUNTY_PUBLIC_INDEX_FILENAME).write_bytes(expected_index)
    assert release_index.verify_fars_county_public_release_directory(root) == index

    (root / "fars/2024/counties/06-r3.json").write_bytes(value)
    with pytest.raises(ValueError, match="missing or unindexed"):
        release_index.verify_fars_county_public_release_directory(root)


def test_correction_ledger_rejects_unsorted_ids_or_dishonest_impact() -> None:
    _index_value, value, boundary, _ledger = _index()
    ledger_value = json.loads(_correction_ledger(value, boundary))
    correction = ledger_value["corrections"][0]
    correction["impact"]["values"] = False
    correction["impact"]["identities"] = True
    with pytest.raises(ValueError, match="value impact"):
        release_index.validate_fars_county_public_correction_ledger(ledger_value)

    ledger_value = json.loads(_correction_ledger(value, boundary))
    second = copy.deepcopy(ledger_value["corrections"][0])
    second["correction_id"] = "county-aa-r1-r2"
    ledger_value["corrections"].append(second)
    with pytest.raises(ValueError, match="canonical ordering"):
        release_index.validate_fars_county_public_correction_ledger(ledger_value)


def test_correction_ledger_rejects_invalid_identity_metadata_and_noncanonical_bytes() -> None:
    _index_value, value, boundary, _ledger = _index()
    ledger_value = json.loads(_correction_ledger(value, boundary))
    ledger_value["artifact_type"] = "wrong"
    with pytest.raises(ValueError, match="identity"):
        release_index.validate_fars_county_public_correction_ledger(ledger_value)

    ledger_value = json.loads(_correction_ledger(value, boundary))
    ledger_value["corrections"][0]["correction_id"] = "wrong"
    with pytest.raises(ValueError, match="correction id"):
        release_index.validate_fars_county_public_correction_ledger(ledger_value)

    ledger_value = json.loads(_correction_ledger(value, boundary))
    ledger_value["corrections"][0]["review_date"] = "2026/07/18"
    with pytest.raises(ValueError, match="review date"):
        release_index.validate_fars_county_public_correction_ledger(ledger_value)

    ledger_value = json.loads(_correction_ledger(value, boundary))
    ledger_value["corrections"][0]["replacement_deployment_commit"] = "not-a-commit"
    with pytest.raises(ValueError, match="deployment commit"):
        release_index.validate_fars_county_public_correction_ledger(ledger_value)

    ledger_value = json.loads(_correction_ledger(value, boundary))
    ledger_value["corrections"][0]["impact"]["geometry"] = True
    with pytest.raises(ValueError, match="geometry impact"):
        release_index.validate_fars_county_public_correction_ledger(ledger_value)

    ledger_value = json.loads(_correction_ledger(value, boundary))
    ledger_value["corrections"][0]["impact"] = {
        "values": False,
        "identities": False,
        "geometry": False,
        "copy": False,
    }
    with pytest.raises(ValueError, match="at least one boolean"):
        release_index.validate_fars_county_public_correction_ledger(ledger_value)

    ledger_value = json.loads(_correction_ledger(value, boundary))
    ledger_value["corrections"][0]["affected"]["state_fips"] = "00"
    with pytest.raises(ValueError, match="outside reviewed coverage"):
        release_index.validate_fars_county_public_correction_ledger(ledger_value)

    ledger_value = json.loads(_correction_ledger(value, boundary))
    ledger_value["corrections"][0]["reason"] = "x" * 1_001
    with pytest.raises(ValueError, match="reason exceeds"):
        release_index.validate_fars_county_public_correction_ledger(ledger_value)

    pretty = json.dumps(json.loads(_correction_ledger(value, boundary)), indent=2).encode("utf-8")
    with pytest.raises(ValueError, match="not canonical"):
        release_index.load_fars_county_public_correction_ledger_bytes(pretty)


def test_index_and_internal_guards_reject_type_confusion_and_identity_drift(tmp_path: Path) -> None:
    index, value, boundary, ledger = _index()
    malformed = copy.deepcopy(index)
    malformed["release_id"] = "BAD"
    with pytest.raises(ValueError, match="identity"):
        release_index.validate_fars_county_public_release_index(malformed)

    malformed = copy.deepcopy(index)
    cast(dict[str, object], malformed["correction_ledger"])["path"] = "outside.json"
    with pytest.raises(ValueError, match="ledger path"):
        release_index.validate_fars_county_public_release_index(malformed)

    malformed = copy.deepcopy(index)
    malformed["releases"] = []
    with pytest.raises(ValueError, match="release count"):
        release_index.validate_fars_county_public_release_index(malformed)

    malformed = copy.deepcopy(index)
    release = cast(list[dict[str, object]], malformed["releases"])[0]
    cast(dict[str, object], release["contract"])["contract_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="contract provenance"):
        release_index.validate_fars_county_public_release_index(malformed)

    malformed = copy.deepcopy(index)
    release = cast(list[dict[str, object]], malformed["releases"])[0]
    cast(dict[str, object], release["geography"])["crosswalk_version"] = "unreviewed"
    with pytest.raises(ValueError, match="geography contract"):
        release_index.validate_fars_county_public_release_index(malformed)

    malformed = copy.deepcopy(index)
    release = cast(list[dict[str, object]], malformed["releases"])[0]
    release["states"] = []
    with pytest.raises(ValueError, match="state count"):
        release_index.validate_fars_county_public_release_index(malformed)

    with pytest.raises(ValueError, match="release id"):
        release_index.build_fars_county_public_release_index(
            {VALUE_R1: value}, {BOUNDARY: boundary}, ledger, release_id="BAD"
        )
    with pytest.raises(ValueError, match="requires explicit"):
        release_index.build_fars_county_public_release_index(
            {}, {}, ledger, release_id="county-pilot"
        )
    with pytest.raises(TypeError, match="boundary artifacts"):
        release_index.build_fars_county_public_release_index(
            {VALUE_R1: value},
            {BOUNDARY: bytearray(boundary)},  # type: ignore[dict-item]
            ledger,
            release_id="county-pilot",
        )
    with pytest.raises(ValueError, match="requires explicit"):
        release_index.build_fars_county_public_release_index(
            {VALUE_R1: value}, {}, ledger, release_id="county-pilot"
        )
    with pytest.raises(ValueError, match="state more than once"):
        release_index.build_fars_county_public_release_index(
            {VALUE_R1: value, VALUE_R2: value},
            {BOUNDARY: boundary},
            ledger,
            release_id="county-pilot",
        )

    pretty = json.dumps(index, indent=2).encode("utf-8")
    with pytest.raises(ValueError, match="not canonical"):
        release_index.load_fars_county_public_release_index_bytes(pretty)
    with pytest.raises(TypeError, match="payload must be bytes"):
        release_index._strict_json("{}", label="fixture", maximum=10)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="object"):
        release_index._mapping([], "fixture")
    with pytest.raises(ValueError, match="array"):
        release_index._list({}, "fixture")
    with pytest.raises(ValueError, match="missing or unexpected"):
        release_index._exact_keys({}, ("required",), "fixture")
    with pytest.raises(ValueError, match="integer"):
        release_index._integer(True, "fixture", minimum=1, maximum=2)
    with pytest.raises(ValueError, match="nonempty"):
        release_index._string("", "fixture")
    with pytest.raises(ValueError, match="digest"):
        release_index._sha256("not-a-digest", "fixture")
    with pytest.raises(ValueError, match="state identity"):
        release_index._state_identity(
            {"state_fips": "06", "state_abbreviation": "ZZ", "state_name": "California"},
            expected_fips="06",
        )
    with pytest.raises(ValueError, match="value artifact path"):
        release_index._value_path(
            "fars/2024/counties/06-r2.json", year=2024, state_fips="06", revision=1
        )
    with pytest.raises(ValueError, match="boundary artifact path"):
        release_index._boundary_path("counties/12.json", state_fips="06")
    with pytest.raises(ValueError, match="real directory"):
        release_index.verify_fars_county_public_release_directory(tmp_path / "missing")
    with pytest.raises(ValueError, match="unavailable"):
        release_index._bounded_regular_file(tmp_path / "missing.json", maximum=10, label="fixture")


def test_repository_schemas_match_embedded_contracts() -> None:
    index_schema = json.loads(INDEX_SCHEMA_PATH.read_text(encoding="utf-8"))
    correction_schema = json.loads(CORRECTION_SCHEMA_PATH.read_text(encoding="utf-8"))
    assert index_schema == release_index.FARS_COUNTY_PUBLIC_INDEX_SCHEMA
    assert correction_schema == release_index.FARS_COUNTY_PUBLIC_CORRECTIONS_SCHEMA
    Draft202012Validator.check_schema(index_schema)
    Draft202012Validator.check_schema(correction_schema)
