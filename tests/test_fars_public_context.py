"""Contract, privacy, and known-answer tests for public 2024 FARS state burden."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any, cast

import pytest
from jsonschema import Draft202012Validator
from tools.export_fars_public_context import _atomic_write_public_context

import nearmiss.fars_year_contracts as year_contracts
from nearmiss.adapters.fars import FARS_MAPPING_VERSION
from nearmiss.adapters.fars_joined import MODE_ORDER, PERSON_MODE_MAPPING_VERSION
from nearmiss.fars_national_context import (
    FARS_NATIONAL_CONTEXT_ALGORITHM_VERSION,
    FARS_NATIONAL_CONTEXT_ARTIFACT_TYPE,
    FARS_NATIONAL_CONTEXT_CAVEAT,
    FARS_NATIONAL_CONTEXT_MINIMUM_K,
    FARS_NATIONAL_CONTEXT_SCHEMA_VERSION,
    FARS_STATE_CODEBOOK_VERSION,
    fars_state_codebook_sha256,
)
from nearmiss.fars_public_context import (
    FARS_PUBLIC_CONTEXT_ARTIFACT_SCHEMA,
    FARS_PUBLIC_CONTEXT_CAVEAT,
    FARS_PUBLIC_CONTEXT_DISTRIBUTION_URL,
    FARS_PUBLIC_CONTEXT_EFFECTIVE_K,
    FARS_PUBLIC_CONTEXT_RAW_SHA256,
    FARS_PUBLIC_CONTEXT_RAW_SIZE_BYTES,
    FARS_PUBLIC_CONTEXT_SOURCE_REVISION_ID,
    FARS_PUBLIC_STATE_CROSSWALK,
    FARS_PUBLIC_STATE_CROSSWALK_VERSION,
    _build_fars_public_context,
    build_verified_fars_public_context,
    canonical_fars_public_context_bytes,
    fars_public_state_crosswalk_sha256,
    load_fars_public_context_bytes,
    validate_fars_public_context_artifact,
)

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schema" / "public-fars-state-context.schema.json"
PUBLIC_PATH = ROOT / "data" / "published" / "fars-2024-state-mode.json"


def _private_context() -> dict[str, object]:
    """Build a nationally complete synthetic private contract for projector tests."""
    codes = sorted(FARS_PUBLIC_STATE_CROSSWALK, key=int)
    base, remainder = divmod(30_000, len(codes))
    cells = [
        {
            "state_code": code,
            "involved_mode": "motor_vehicle_occupant",
            "crash_count": base + (1 if index < remainder else 0),
        }
        for index, code in enumerate(codes)
    ]
    return {
        "schema_version": FARS_NATIONAL_CONTEXT_SCHEMA_VERSION,
        "artifact_type": FARS_NATIONAL_CONTEXT_ARTIFACT_TYPE,
        "visibility": "private",
        "caveat": FARS_NATIONAL_CONTEXT_CAVEAT,
        "source_lineage": {
            "source_id": "fars-joined",
            "dataset_year": 2024,
            "release_status": "final",
            "attempt_id": "public-projector-test",
            "raw_sha256": FARS_PUBLIC_CONTEXT_RAW_SHA256,
            "normalized_sha256": "a" * 64,
            "accident_sha256": "b" * 64,
            "person_sha256": "c" * 64,
            "joined_schema_version": "1.1.0",
            "crash_mapping_version": FARS_MAPPING_VERSION,
            "person_mapping_version": PERSON_MODE_MAPPING_VERSION,
            "crash_records_read": 30_000,
            "crash_records_accepted": 30_000,
            "crash_records_rejected": 0,
            "person_records_read": 30_000,
            "person_records_accepted": 30_000,
            "person_records_excluded": 0,
            "cases_joined": 30_000,
            "cases_excluded": 0,
        },
        "method": {
            "algorithm_version": FARS_NATIONAL_CONTEXT_ALGORITHM_VERSION,
            "geography": "fars_state_code",
            "coverage": "official_2024_national_50_states_and_dc",
            "coverage_state_codes": codes,
            "dimension": "involved_mode",
            "contribution_unit": "distinct_crash_once_per_involved_mode",
            "minimum_k": FARS_NATIONAL_CONTEXT_MINIMUM_K,
            "effective_k": FARS_PUBLIC_CONTEXT_EFFECTIVE_K,
            "state_codebook_version": FARS_STATE_CODEBOOK_VERSION,
            "state_codebook_sha256": fars_state_codebook_sha256(),
            "modes_non_additive": True,
        },
        "accounting": {
            "case_count": 30_000,
            "states_with_records": 51,
            "states_with_eligible_cells": 51,
            "positive_candidate_cell_count": 51,
            "eligible_cell_count": 51,
            "suppressed_cell_count": 0,
            "crash_contribution_total": 30_000,
            "eligible_crash_contribution_total": 30_000,
            "suppressed_crash_contribution_total": 0,
        },
        "cells": cells,
    }


def _states(artifact: dict[str, object]) -> list[dict[str, Any]]:
    return cast(list[dict[str, Any]], artifact["states"])


def _accounting(artifact: dict[str, object]) -> dict[str, int]:
    return cast(dict[str, int], artifact["accounting"])


def test_static_schema_matches_embedded_contract() -> None:
    assert json.loads(SCHEMA_PATH.read_text(encoding="utf-8")) == (
        FARS_PUBLIC_CONTEXT_ARTIFACT_SCHEMA
    )
    Draft202012Validator.check_schema(FARS_PUBLIC_CONTEXT_ARTIFACT_SCHEMA)


def test_crosswalk_is_complete_unique_pinned_and_excludes_puerto_rico() -> None:
    assert len(FARS_PUBLIC_STATE_CROSSWALK) == 51
    assert "43" not in FARS_PUBLIC_STATE_CROSSWALK
    assert len({value[0] for value in FARS_PUBLIC_STATE_CROSSWALK.values()}) == 51
    assert len({value[1] for value in FARS_PUBLIC_STATE_CROSSWALK.values()}) == 51
    assert fars_public_state_crosswalk_sha256() == (
        "6744b12717b0bd52a79c73aba3037286dde9257698a2aa0630f995c8a82ba25c"
    )
    assert FARS_PUBLIC_STATE_CROSSWALK_VERSION == "fars-usps-50-states-dc-2024-v1"
    with pytest.raises(TypeError):
        FARS_PUBLIC_STATE_CROSSWALK["1"] = ("XX", "Forged")  # type: ignore[index]


def test_projector_emits_every_mode_without_minting_false_zeroes() -> None:
    artifact = _build_fars_public_context(_private_context())
    states = _states(artifact)
    assert len(states) == 51
    assert [state["state_name"] for state in states] == sorted(
        state["state_name"] for state in states
    )
    assert all(
        [cell["involved_mode"] for cell in state["cells"]] == list(MODE_ORDER) for state in states
    )
    assert all(len(state["cells"]) == 6 for state in states)
    for state in states:
        published = state["cells"][0]
        assert published["status"] == "published"
        assert published["crash_count"] >= 10
        for cell in state["cells"][1:]:
            assert cell == {
                "involved_mode": cell["involved_mode"],
                "status": "suppressed_or_zero",
            }
            assert "crash_count" not in cell
    assert _accounting(artifact)["published_cell_count"] == 51
    assert _accounting(artifact)["suppressed_or_zero_cell_count"] == 255


def test_projection_is_canonical_deterministic_and_strips_private_lineage() -> None:
    first = _build_fars_public_context(_private_context())
    second = _build_fars_public_context(copy.deepcopy(_private_context()))
    assert first == second
    payload = canonical_fars_public_context_bytes(first)
    assert payload == canonical_fars_public_context_bytes(copy.deepcopy(first))
    assert load_fars_public_context_bytes(payload) == first
    assert payload.endswith(b"\n") and b"\n" not in payload[:-1]
    forbidden = (
        b'"attempt_id"',
        b'"normalized_sha256"',
        b'"accident_sha256"',
        b'"person_sha256"',
        b'"source_record_id"',
        b'"occurred_on"',
        b'"occurred_time_local"',
        b'"location"',
        b'"latitude"',
        b'"longitude"',
        b'"rate"',
        b'"rank"',
    )
    assert all(token not in payload for token in forbidden)


def test_public_builder_rejects_an_unsealed_private_mapping() -> None:
    with pytest.raises(TypeError, match="proof-bound joined snapshot"):
        build_verified_fars_public_context(_private_context())  # type: ignore[arg-type]


def test_public_release_pin_does_not_follow_the_active_contract_pointer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    private = _private_context()
    expected = _build_fars_public_context(private)
    monkeypatch.setattr(year_contracts, "FARS_YEAR_CONTRACTS", {2024: object()})
    assert _build_fars_public_context(private) == expected
    assert cast(dict[str, Any], expected["source"]) == {
        "name": "NHTSA Fatality Analysis Reporting System (FARS)",
        "release_stage": "final",
        "distribution_url": FARS_PUBLIC_CONTEXT_DISTRIBUTION_URL,
        "source_revision_id": FARS_PUBLIC_CONTEXT_SOURCE_REVISION_ID,
        "raw_size_bytes": FARS_PUBLIC_CONTEXT_RAW_SIZE_BYTES,
        "raw_sha256": FARS_PUBLIC_CONTEXT_RAW_SHA256,
    }


def test_projector_requires_exact_final_k10_national_source() -> None:
    mutations = [
        ("source_lineage", "release_status", "preliminary"),
        ("source_lineage", "raw_sha256", "0" * 64),
        ("method", "coverage", "state_codes_present_in_verified_snapshot"),
        ("method", "effective_k", 9),
    ]
    for section, key, value in mutations:
        private = _private_context()
        cast(dict[str, Any], private[section])[key] = value
        with pytest.raises(ValueError):
            _build_fars_public_context(private)


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda value: _states(value)[0].update(state_name="Forged"),
            "state",
        ),
        (
            lambda value: _states(value).reverse(),
            "crosswalk|ordering",
        ),
        (
            lambda value: _states(value)[0]["cells"].reverse(),
            "mode cells",
        ),
        (
            lambda value: _accounting(value).__setitem__("published_cell_count", 50),
            "accounting",
        ),
        (
            lambda value: _states(value)[0]["cells"][1].update(crash_count=0),
            "invalid public",
        ),
        (
            lambda value: cast(dict[str, Any], value["source"]).__setitem__("raw_sha256", "0" * 64),
            "invalid public",
        ),
        (
            lambda value: value.update(attempt_id="private"),
            "invalid public",
        ),
    ],
    ids=[
        "crosswalk",
        "state-order",
        "mode-order",
        "accounting",
        "false-zero",
        "source-pin",
        "private-extra",
    ],
)
def test_public_semantic_validator_rejects_tampering(
    mutate: Any,
    message: str,
) -> None:
    artifact = _build_fars_public_context(_private_context())
    mutate(artifact)
    with pytest.raises(ValueError, match=message):
        validate_fars_public_context_artifact(artifact)


def test_public_accounting_rejects_impossible_suppression_and_contribution_bounds() -> None:
    artifact = _build_fars_public_context(_private_context())
    accounting = _accounting(artifact)
    accounting["positive_suppressed_cell_count"] = 0
    accounting["positive_candidate_cell_count"] = accounting["published_cell_count"]
    accounting["suppressed_crash_contribution_total"] = 1
    accounting["crash_contribution_total"] = accounting["published_crash_contribution_total"] + 1
    with pytest.raises(ValueError, match="accounting"):
        validate_fars_public_context_artifact(artifact)

    artifact = _build_fars_public_context(_private_context())
    _accounting(artifact)["case_count"] = 45_000
    with pytest.raises(ValueError, match="accounting"):
        validate_fars_public_context_artifact(artifact)


def test_public_accounting_rejects_a_cell_above_the_source_case_count() -> None:
    artifact = _build_fars_public_context(_private_context())
    published = _states(artifact)[0]["cells"][0]
    previous = cast(int, published["crash_count"])
    published["crash_count"] = 45_000
    accounting = _accounting(artifact)
    delta = 45_000 - previous
    accounting["published_crash_contribution_total"] += delta
    accounting["crash_contribution_total"] += delta
    with pytest.raises(ValueError, match="exceeds the source case count"):
        validate_fars_public_context_artifact(artifact)


def test_public_projection_requires_complementary_suppression_for_one_positive_cell() -> None:
    private = _private_context()
    accounting = cast(dict[str, int], private["accounting"])
    accounting["positive_candidate_cell_count"] += 1
    accounting["suppressed_cell_count"] = 1
    accounting["crash_contribution_total"] += 1
    accounting["suppressed_crash_contribution_total"] = 1
    with pytest.raises(ValueError, match="accounting"):
        _build_fars_public_context(private)


def test_canonical_loader_rejects_unsafe_or_noncanonical_bytes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = canonical_fars_public_context_bytes(_build_fars_public_context(_private_context()))
    with pytest.raises(ValueError, match="not canonical"):
        load_fars_public_context_bytes(payload[:-1])
    with pytest.raises(ValueError, match="duplicate key"):
        load_fars_public_context_bytes(b'{"x":1,"x":1}\n')
    with pytest.raises(ValueError, match="non-finite"):
        load_fars_public_context_bytes(b'{"x":NaN}\n')

    def unexpected_parse(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("oversized public bytes reached the JSON decoder")

    monkeypatch.setattr(json, "loads", unexpected_parse)
    with pytest.raises(ValueError, match="byte safety limit"):
        load_fars_public_context_bytes(b" " * (256 * 1024 + 1))


def test_atomic_export_preserves_prior_file_on_replace_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    destination = tmp_path / "public.json"
    destination.write_bytes(b"prior\n")

    def fail_replace(_source: object, _destination: object) -> None:
        raise OSError("simulated atomic replace failure")

    monkeypatch.setattr(Path, "replace", fail_replace)
    with pytest.raises(OSError, match="simulated"):
        _atomic_write_public_context(destination, b"replacement\n")
    assert destination.read_bytes() == b"prior\n"
    assert list(tmp_path.iterdir()) == [destination]


def test_checked_in_real_artifact_has_verified_known_answer_accounting() -> None:
    payload = PUBLIC_PATH.read_bytes()
    artifact = load_fars_public_context_bytes(payload)
    assert _accounting(artifact) == {
        "case_count": 36_127,
        "state_count": 51,
        "state_mode_cell_count": 306,
        "published_cell_count": 206,
        "suppressed_or_zero_cell_count": 100,
        "positive_candidate_cell_count": 292,
        "positive_suppressed_cell_count": 86,
        "crash_contribution_total": 48_524,
        "published_crash_contribution_total": 48_154,
        "suppressed_crash_contribution_total": 370,
    }
    assert cast(dict[str, Any], artifact["source"]) == {
        "name": "NHTSA Fatality Analysis Reporting System (FARS)",
        "release_stage": "final",
        "distribution_url": FARS_PUBLIC_CONTEXT_DISTRIBUTION_URL,
        "source_revision_id": FARS_PUBLIC_CONTEXT_SOURCE_REVISION_ID,
        "raw_size_bytes": FARS_PUBLIC_CONTEXT_RAW_SIZE_BYTES,
        "raw_sha256": FARS_PUBLIC_CONTEXT_RAW_SHA256,
    }
    alabama = next(state for state in _states(artifact) if state["state_abbreviation"] == "AL")
    by_mode = {cell["involved_mode"]: cell for cell in alabama["cells"]}
    assert by_mode["motor_vehicle_occupant"]["crash_count"] == 839
    assert by_mode["pedalcyclist"]["crash_count"] == 10
    assert artifact["caveat"] == FARS_PUBLIC_CONTEXT_CAVEAT
    assert hashlib.sha256(payload).hexdigest() == (
        "29b5dc2673987cc7bedd0a83b2147e724e1fb2a2cb1458053af3d017ac8d6578"
    )
