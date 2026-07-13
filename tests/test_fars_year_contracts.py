# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from dataclasses import FrozenInstanceError, replace

import pytest

from nearmiss.fars_year_contracts import (
    FARS_ACCIDENT_ROW_CAP,
    FARS_PERSON_ROW_CAP,
    FARS_YEAR_CONTRACTS,
    SUPPORTED_FARS_YEARS,
    FarsYearContract,
    fars_year_contract,
)


def test_registry_pins_exact_fixed_year_contracts() -> None:
    assert tuple(FARS_YEAR_CONTRACTS) == SUPPORTED_FARS_YEARS
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
        assert contract.distribution_url == (
            f"https://static.nhtsa.gov/nhtsa/downloads/FARS/{year}/National/"
            f"FARS{year}NationalCSV.zip"
        )
        assert contract.accident_member == "accident.csv"
        assert contract.person_member == "person.csv"
        assert contract.person_encoding == "utf-8-sig"
        assert contract.release_stage == "final"
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


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"source_id": "fars-joined"}, "source_id"),
        ({"accident_encoding": "utf-8-sig"}, "accident encoding"),
        ({"person_encoding": "cp1252"}, "person encoding"),
        ({"semantic_regime_id": "fars_per_typ_2022_2024_v1"}, "semantic regime"),
        ({"table_encoding_profile": "fallback"}, "encoding profile"),
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
        ({"raw_size_bytes": 1}, "raw archive identity"),
        ({"raw_sha256": "0" * 64}, "raw archive identity"),
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
