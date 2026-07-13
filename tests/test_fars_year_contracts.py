# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import json
from dataclasses import FrozenInstanceError, replace

import pytest

import nearmiss.fars_year_contracts as year_contracts
from nearmiss.fars_year_contracts import (
    FARS_ACCIDENT_ROW_CAP,
    FARS_PERSON_ROW_CAP,
    FARS_RAW_ARCHIVE_MAX_BYTES,
    FARS_YEAR_CONTRACT_HISTORY,
    FARS_YEAR_CONTRACTS,
    SUPPORTED_FARS_YEARS,
    FarsYearContract,
    canonical_fars_year_contract_bytes,
    fars_year_contract,
    fars_year_contract_descriptor,
    fars_year_contract_from_descriptor,
    fars_year_contract_revision,
    fars_year_contract_sha256,
    validate_fars_year_contract_registry,
)


def test_registry_pins_exact_fixed_year_contracts() -> None:
    assert tuple(FARS_YEAR_CONTRACTS) == SUPPORTED_FARS_YEARS
    assert tuple(FARS_YEAR_CONTRACT_HISTORY) == SUPPORTED_FARS_YEARS
    raw_identities = {
        2020: (31_016_385, "b2806902b3da9b45c632499f82e1c74fd108238ae7f67e108ebf40360ee4c9c3"),
        2021: (35_190_858, "743c19a13884614430d295289e655c5ad32b0a025a11e5b2149dfb57acae389b"),
        2022: (34_689_724, "989448d7a2f3964264c96a3cdb220f6c413c782a33eb759781f520c5acb5f744"),
        2023: (34_174_899, "edde841eb493e55751961b36bac2d1ce8750f601cb8e6e183a525723bb62bab0"),
        2024: (32_672_161, "5112727a8c0dc91ffee27ca05bddb073934f2d192ce4fae997da767dccdbe04f"),
    }

    for year in SUPPORTED_FARS_YEARS:
        contract = fars_year_contract(year)
        assert contract.year == year
        assert contract.source_id == f"fars-joined-{year}"
        assert FARS_YEAR_CONTRACT_HISTORY[year] == (contract,)
        assert contract.revision == 1
        assert contract.source_revision_id == f"reviewed-20260712-{contract.raw_sha256[:12]}"
        assert contract.distribution_url == (
            f"https://static.nhtsa.gov/nhtsa/downloads/FARS/{year}/National/"
            f"FARS{year}NationalCSV.zip"
        )
        assert contract.accident_member == "accident.csv"
        assert contract.person_member == "person.csv"
        assert contract.person_encoding == "utf-8-sig"
        assert contract.release_stage == "final"
        assert contract.crash_mapping_version == "1.0.0"
        assert contract.person_mapping_version == "1.0.0"
        assert contract.source_record_id_scheme == "fars_year_st_case_v1"
        assert contract.state_code_system == f"nhtsa_fars_state_{year}"
        assert contract.county_code_system == f"nhtsa_fars_gsa_{year}"
        assert contract.accident_row_cap >= 45_000
        assert contract.person_row_cap >= 110_000
        assert (contract.raw_size_bytes, contract.raw_sha256) == raw_identities[year]
        contract.validate_raw_identity(
            size=contract.raw_size_bytes,
            sha256=contract.raw_sha256,
        )


def test_registry_pins_reviewed_encodings_and_semantic_regimes() -> None:
    assert fars_year_contract(2020).accident_encoding == "cp1252"
    assert {fars_year_contract(year).accident_encoding for year in (2021, 2022, 2023, 2024)} == {
        "utf-8-sig"
    }
    assert {fars_year_contract(year).semantic_regime_id for year in (2020, 2021)} == {
        "fars_per_typ_2020_2021_v1"
    }
    assert {fars_year_contract(year).semantic_regime_id for year in (2022, 2023, 2024)} == {
        "fars_per_typ_2022_2024_v1"
    }
    assert fars_year_contract(2020).table_encoding_profile == "fars_2020_mixed_text_v1"
    assert {
        fars_year_contract(year).table_encoding_profile for year in (2021, 2022, 2023, 2024)
    } == {"fars_utf8_sig_2021_2024_v1"}


@pytest.mark.parametrize("year", [True, False, "2024", 2024.0, None])
def test_contract_lookup_rejects_non_integer_years(year: object) -> None:
    with pytest.raises(TypeError, match="year must be an integer"):
        fars_year_contract(year)  # type: ignore[arg-type]


@pytest.mark.parametrize("year", [1975, 2019, 2025, 9999])
def test_contract_lookup_rejects_unsupported_years(year: int) -> None:
    with pytest.raises(ValueError, match="between 2020 and 2024"):
        fars_year_contract(year)


def test_registry_and_contracts_are_immutable() -> None:
    registry = FARS_YEAR_CONTRACTS  # retain its Mapping type for a runtime mutation check
    with pytest.raises(TypeError):
        registry[2024] = fars_year_contract(2024)  # type: ignore[index]
    with pytest.raises(FrozenInstanceError):
        fars_year_contract(2024).source_id = "fars-joined-2023"  # type: ignore[misc]


def test_registry_retains_no_mutable_backing_alias() -> None:
    assert not hasattr(year_contracts, "_REGISTERED_HISTORY")
    history = FARS_YEAR_CONTRACT_HISTORY
    current = FARS_YEAR_CONTRACTS
    with pytest.raises(TypeError):
        history[2024] = ()  # type: ignore[index]
    with pytest.raises(TypeError):
        current[2024] = fars_year_contract(2023)  # type: ignore[index]
    assert current[2024] is history[2024][-1]


def test_contract_descriptor_and_digest_are_canonical_and_complete() -> None:
    contract = fars_year_contract(2020)
    descriptor = fars_year_contract_descriptor(contract)
    assert descriptor["source_revision_id"] == contract.source_revision_id
    assert descriptor["predecessor_contract_sha256"] is None
    assert descriptor["allowed_regressions"] == []
    payload = canonical_fars_year_contract_bytes(contract)
    assert payload.endswith(b"\n") and b"\n" not in payload[:-1]
    assert len(fars_year_contract_sha256(contract)) == 64
    assert fars_year_contract_from_descriptor(descriptor) is contract
    decoded = json.loads(payload)
    assert decoded == descriptor
    assert fars_year_contract_from_descriptor(decoded) is contract
    assert set(decoded) == {
        "contract_schema_version",
        "year",
        "revision",
        "predecessor_contract_sha256",
        "transition_review_reference",
        "allowed_regressions",
        "source_id",
        "source_revision_id",
        "distribution_url",
        "release_stage",
        "raw_size_bytes",
        "raw_sha256",
        "accident_member",
        "accident_encoding",
        "person_member",
        "person_encoding",
        "semantic_regime_id",
        "table_encoding_profile",
        "crash_mapping_version",
        "person_mapping_version",
        "source_record_id_scheme",
        "state_code_system",
        "county_code_system",
        "accident_row_cap",
        "person_row_cap",
    }
    with pytest.raises(ValueError, match="not a registered revision"):
        fars_year_contract_descriptor(replace(contract))


def test_registered_revision_digests_are_golden_append_only_identities() -> None:
    expected = {
        (2020, 1): "c6294413066bb2e83b2aea02408dcfa2fa40441dda7de115983a45fb8aab132c",
        (2021, 1): "5c2c198cd4e3eee80f9e27874e3f42521b0e0b7cbc53a8bd0bf2684ef66a855e",
        (2022, 1): "18713f23f657334459febf729e4005bfd9e94492da37afb0255d9e5fd4159158",
        (2023, 1): "557a8edf2418c7794d349c932ae2237db6cad7165f62c80a2e7f3b15baeca143",
        (2024, 1): "f6bc3dd55cf3dfb360c265308c7702cdf7f6df66894cf792afd6be83c09c72f8",
    }
    assert {
        (year, contract.revision): fars_year_contract_sha256(contract)
        for year, history in FARS_YEAR_CONTRACT_HISTORY.items()
        for contract in history
    } == expected


def _future_2024_revision(**changes: object) -> FarsYearContract:
    previous = fars_year_contract_revision(2024, 1)
    raw_sha256 = "1" * 64
    values: dict[str, object] = {
        "revision": 2,
        "predecessor_contract_sha256": fars_year_contract_sha256(previous),
        "transition_review_reference": "nearmiss-fars-source-audit-20260713",
        "allowed_regressions": ("mode_counts", "record_counts"),
        "source_revision_id": f"reviewed-20260713-{raw_sha256[:12]}",
        "raw_size_bytes": previous.raw_size_bytes + 1,
        "raw_sha256": raw_sha256,
    }
    values.update(changes)
    return replace(previous, **values)  # type: ignore[arg-type]


def _registry_with_future_2024(
    revision: FarsYearContract,
) -> dict[int, tuple[FarsYearContract, ...]]:
    registry = dict(FARS_YEAR_CONTRACT_HISTORY)
    registry[2024] = (fars_year_contract_revision(2024, 1), revision)
    return registry


def test_registry_validator_supports_a_contiguous_reviewed_future_revision() -> None:
    revision = _future_2024_revision()
    assert revision.revision == 2
    assert revision.allowed_regressions == ("mode_counts", "record_counts")
    validate_fars_year_contract_registry(_registry_with_future_2024(revision))


def test_registry_validator_allows_mapping_revision_to_reuse_raw_archive() -> None:
    previous = fars_year_contract_revision(2024, 1)
    revision = _future_2024_revision(
        source_revision_id="reviewed-20260713-222222222222",
        raw_size_bytes=previous.raw_size_bytes,
        raw_sha256=previous.raw_sha256,
        crash_mapping_version="1.1.0",
        person_mapping_version="1.1.0",
    )
    validate_fars_year_contract_registry(_registry_with_future_2024(revision))


def test_registry_validator_rejects_noop_mapping_revision_reusing_raw_archive() -> None:
    previous = fars_year_contract_revision(2024, 1)
    revision = _future_2024_revision(
        source_revision_id="reviewed-20260713-222222222222",
        raw_size_bytes=previous.raw_size_bytes,
        raw_sha256=previous.raw_sha256,
    )
    with pytest.raises(ValueError, match="must advance a mapping version"):
        validate_fars_year_contract_registry(_registry_with_future_2024(revision))


def test_registry_validator_rejects_mapping_rollback_when_reusing_raw_archive() -> None:
    previous = fars_year_contract_revision(2024, 1)
    revision = _future_2024_revision(
        source_revision_id="reviewed-20260713-222222222222",
        raw_size_bytes=previous.raw_size_bytes,
        raw_sha256=previous.raw_sha256,
        crash_mapping_version="0.9.0",
        person_mapping_version="1.1.0",
    )
    with pytest.raises(ValueError, match="mapping versions must not regress"):
        validate_fars_year_contract_registry(_registry_with_future_2024(revision))


def test_registry_validator_rejects_mapping_rollback_with_new_raw_archive() -> None:
    revision = _future_2024_revision(
        crash_mapping_version="0.9.0",
        person_mapping_version="1.0.0",
    )
    with pytest.raises(ValueError, match="mapping versions must not regress"):
        validate_fars_year_contract_registry(_registry_with_future_2024(revision))


def test_registry_validator_rejects_raw_archive_reuse_across_fixed_years() -> None:
    source = fars_year_contract(2024)
    duplicate = replace(
        fars_year_contract(2023),
        source_revision_id="reviewed-20260713-222222222222",
        raw_size_bytes=source.raw_size_bytes,
        raw_sha256=source.raw_sha256,
    )
    registry = dict(FARS_YEAR_CONTRACT_HISTORY)
    registry[2023] = (duplicate,)
    with pytest.raises(ValueError, match="unique across fixed years"):
        validate_fars_year_contract_registry(registry)


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"revision": 3}, "contiguous"),
        ({"predecessor_contract_sha256": "0" * 64}, "predecessor digest"),
        (
            {"source_revision_id": fars_year_contract(2024).source_revision_id},
            "globally unique",
        ),
        (
            {
                "raw_size_bytes": fars_year_contract(2024).raw_size_bytes + 99,
                "raw_sha256": fars_year_contract(2024).raw_sha256,
                "source_revision_id": "reviewed-20260713-222222222222",
            },
            "different archive size",
        ),
    ],
)
def test_registry_validator_rejects_broken_future_history(
    changes: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        validate_fars_year_contract_registry(
            _registry_with_future_2024(_future_2024_revision(**changes))
        )


def test_registry_validator_rejects_invalid_initial_revision_metadata() -> None:
    first = replace(
        fars_year_contract(2024),
        predecessor_contract_sha256="0" * 64,
        allowed_regressions=("record_counts",),
    )
    registry = dict(FARS_YEAR_CONTRACT_HISTORY)
    registry[2024] = (first,)
    with pytest.raises(ValueError, match="initial contract revision metadata"):
        validate_fars_year_contract_registry(registry)


@pytest.mark.parametrize(
    "allowed",
    [
        ("record_counts", "mode_counts"),
        ("mode_counts", "mode_counts"),
        ("records",),
        ["record_counts"],
    ],
)
def test_contract_requires_closed_sorted_immutable_regression_categories(
    allowed: object,
) -> None:
    with pytest.raises((TypeError, ValueError), match="allowed regressions"):
        replace(
            fars_year_contract(2024),
            allowed_regressions=allowed,  # type: ignore[arg-type]
        )


@pytest.mark.parametrize("revision", [True, 1.0, "1", None])
def test_contract_revision_lookup_rejects_non_integer_revision(revision: object) -> None:
    with pytest.raises(TypeError, match="revision must be an integer"):
        fars_year_contract_revision(2024, revision)  # type: ignore[arg-type]


@pytest.mark.parametrize("revision", [-1, 0, 2, 999])
def test_contract_revision_lookup_rejects_unregistered_revision(revision: int) -> None:
    with pytest.raises(ValueError, match="revision is not registered"):
        fars_year_contract_revision(2024, revision)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("year", True),
        ("revision", 1.0),
        ("source_id", "fars-joined-2023"),
        ("allowed_regressions", ()),
        ("raw_size_bytes", True),
        ("unexpected", "field"),
    ],
)
def test_contract_descriptor_lookup_rejects_noncanonical_or_mutated_values(
    field: str,
    value: object,
) -> None:
    descriptor = fars_year_contract_descriptor(fars_year_contract(2024))
    descriptor[field] = value
    with pytest.raises((TypeError, ValueError), match=r"descriptor|year|revision"):
        fars_year_contract_from_descriptor(descriptor)


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"source_id": "fars-joined"}, "source_id"),
        ({"source_revision_id": "latest"}, "source revision ID"),
        ({"accident_encoding": "utf-8-sig"}, "accident encoding"),
        ({"person_encoding": "cp1252"}, "person encoding"),
        ({"semantic_regime_id": "fars_per_typ_2022_2024_v1"}, "semantic regime"),
        ({"table_encoding_profile": "fallback"}, "encoding profile"),
        ({"crash_mapping_version": "latest"}, "crash mapping version"),
        ({"person_mapping_version": "1.0"}, "person mapping version"),
        ({"source_record_id_scheme": "case_only"}, "identity scheme"),
        ({"state_code_system": "census_state"}, "state code system"),
        ({"county_code_system": "census_geoid"}, "county code system"),
        ({"release_stage": "preliminary"}, "release stage"),
        ({"accident_member": "accident_aux.csv"}, "selected CSV members"),
        ({"person_member": "person_aux.csv"}, "selected CSV members"),
        ({"accident_row_cap": 44_999}, "accident row cap"),
        ({"accident_row_cap": 45_001}, "accident row cap"),
        ({"person_row_cap": 109_999}, "person row cap"),
        ({"person_row_cap": 110_001}, "person row cap"),
        ({"raw_size_bytes": 0}, "raw archive size"),
        ({"raw_size_bytes": FARS_RAW_ARCHIVE_MAX_BYTES + 1}, "raw archive size"),
        ({"raw_sha256": "0" * 63}, "raw archive digest"),
    ],
)
def test_contract_rejects_reviewed_field_mutation(
    changes: dict[str, object],
    message: str,
) -> None:
    with pytest.raises((TypeError, ValueError), match=message):
        replace(fars_year_contract(2020), **changes)  # type: ignore[arg-type]


@pytest.mark.parametrize("field", ["accident_row_cap", "person_row_cap"])
@pytest.mark.parametrize("value", [True, 45_000.0, "110000"])
def test_contract_rejects_non_integer_row_caps(field: str, value: object) -> None:
    with pytest.raises(TypeError, match="row cap must be an integer"):
        replace(fars_year_contract(2024), **{field: value})  # type: ignore[arg-type]


def test_contract_requires_exact_official_national_distribution_url() -> None:
    contract = fars_year_contract(2024)
    assert (
        contract.validate_distribution_url(contract.distribution_url) == contract.distribution_url
    )

    with pytest.raises(ValueError, match="fixed-year contract"):
        contract.validate_distribution_url(
            "https://static.nhtsa.gov/nhtsa/downloads/FARS/2024/National/accident.csv"
        )
    with pytest.raises(ValueError, match="release year"):
        contract.validate_distribution_url(fars_year_contract(2023).distribution_url)


def test_contract_rejects_wrong_raw_identity_and_non_bytes_payload() -> None:
    contract = fars_year_contract(2024)
    with pytest.raises(ValueError, match="raw archive identity"):
        contract.validate_raw_identity(
            size=contract.raw_size_bytes,
            sha256="0" * 64,
        )
    with pytest.raises(TypeError, match="size must be an integer"):
        contract.validate_raw_identity(size=True, sha256=contract.raw_sha256)
    with pytest.raises(TypeError, match="payload must be bytes"):
        contract.validate_raw_package(bytearray())  # type: ignore[arg-type]


def test_direct_construction_rejects_bool_year() -> None:
    contract = fars_year_contract(2024)
    values = {
        field: getattr(contract, field)
        for field in FarsYearContract.__dataclass_fields__
        if field != "year"
    }
    with pytest.raises(TypeError, match="year must be an integer"):
        FarsYearContract(year=True, **values)


def test_published_minimum_caps_match_reviewed_bounds() -> None:
    assert FARS_ACCIDENT_ROW_CAP == 45_000
    assert FARS_PERSON_ROW_CAP == 110_000
    assert FARS_RAW_ARCHIVE_MAX_BYTES == 256 * 1024 * 1024
