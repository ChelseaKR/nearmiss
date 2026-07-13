# SPDX-License-Identifier: Apache-2.0
"""Immutable ingestion contracts for official 2020--2024 National FARS data."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from .adapters.fars import validate_fars_distribution_url

SUPPORTED_FARS_YEARS = (2020, 2021, 2022, 2023, 2024)
FARS_ACCIDENT_ROW_CAP = 45_000
FARS_PERSON_ROW_CAP = 110_000

_ACCIDENT_MEMBER = "accident.csv"
_PERSON_MEMBER = "person.csv"
_EARLY_SEMANTIC_REGIME = "fars_per_typ_2020_2021_v1"
_LATE_SEMANTIC_REGIME = "fars_per_typ_2022_2024_v1"
# Audited from the official National URLs on 2026-07-12. NHTSA reposts files
# under stable URLs, so changing any identity is a reviewed source revision.
_PINNED_RAW_IDENTITIES = {
    2020: (31_016_385, "b2806902b3da9b45c632499f82e1c74fd108238ae7f67e108ebf40360ee4c9c3"),
    2021: (35_190_858, "743c19a13884614430d295289e655c5ad32b0a025a11e5b2149dfb57acae389b"),
    2022: (34_689_724, "989448d7a2f3964264c96a3cdb220f6c413c782a33eb759781f520c5acb5f744"),
    2023: (34_174_899, "edde841eb493e55751961b36bac2d1ce8750f601cb8e6e183a525723bb62bab0"),
    2024: (32_672_161, "5112727a8c0dc91ffee27ca05bddb073934f2d192ce4fae997da767dccdbe04f"),
}


def _official_national_distribution_url(year: int) -> str:
    return (
        f"https://static.nhtsa.gov/nhtsa/downloads/FARS/{year}/National/FARS{year}NationalCSV.zip"
    )


def _expected_accident_encoding(year: int) -> str:
    return "cp1252" if year == 2020 else "utf-8-sig"


def _expected_semantic_regime(year: int) -> str:
    return _EARLY_SEMANTIC_REGIME if year <= 2021 else _LATE_SEMANTIC_REGIME


def _expected_encoding_profile(year: int) -> str:
    return "fars_2020_mixed_text_v1" if year == 2020 else "fars_utf8_sig_2021_2024_v1"


@dataclass(frozen=True, slots=True)
class FarsYearContract:
    """Exact reviewed inputs and bounds for one fixed-year ingestion chain."""

    year: int
    source_id: str
    distribution_url: str
    accident_member: str
    accident_encoding: str
    person_member: str
    person_encoding: str
    semantic_regime_id: str
    table_encoding_profile: str
    source_record_id_scheme: str
    state_code_system: str
    county_code_system: str
    release_stage: str
    accident_row_cap: int
    person_row_cap: int
    raw_size_bytes: int
    raw_sha256: str

    def __post_init__(self) -> None:
        if isinstance(self.year, bool) or not isinstance(self.year, int):
            raise TypeError("FARS contract year must be an integer")
        if self.year not in SUPPORTED_FARS_YEARS:
            raise ValueError("FARS contract year must be between 2020 and 2024")
        self._validate_transport()
        self._validate_semantics()
        self._validate_bounds_and_raw_identity()

    def _validate_transport(self) -> None:
        expected_url = _official_national_distribution_url(self.year)
        validated_url = validate_fars_distribution_url(
            self.distribution_url,
            expected_year=self.year,
        )
        if validated_url != expected_url:
            raise ValueError("FARS contract distribution URL is not the reviewed National archive")
        if self.source_id != f"fars-joined-{self.year}":
            raise ValueError("FARS contract source_id does not match its fixed year")
        if self.accident_member != _ACCIDENT_MEMBER or self.person_member != _PERSON_MEMBER:
            raise ValueError("FARS contract selected CSV members do not match the reviewed tables")
        if self.accident_encoding != _expected_accident_encoding(self.year):
            raise ValueError("FARS contract accident encoding does not match its reviewed year")
        if self.person_encoding != "utf-8-sig":
            raise ValueError("FARS contract person encoding does not match its reviewed year")

    def _validate_semantics(self) -> None:
        if self.semantic_regime_id != _expected_semantic_regime(self.year):
            raise ValueError("FARS contract semantic regime does not match its reviewed year")
        if self.table_encoding_profile != _expected_encoding_profile(self.year):
            raise ValueError(
                "FARS contract table encoding profile does not match its reviewed year"
            )
        if self.source_record_id_scheme != "fars_year_st_case_v1":
            raise ValueError("FARS contract source record identity scheme is invalid")
        if self.state_code_system != f"nhtsa_fars_state_{self.year}":
            raise ValueError("FARS contract state code system does not match its reviewed year")
        if self.county_code_system != f"nhtsa_fars_gsa_{self.year}":
            raise ValueError("FARS contract county code system does not match its reviewed year")
        if self.release_stage != "final":
            raise ValueError("FARS contract release stage must be final")

    def _validate_bounds_and_raw_identity(self) -> None:
        if (self.raw_size_bytes, self.raw_sha256) != _PINNED_RAW_IDENTITIES[self.year]:
            raise ValueError("FARS contract raw archive identity does not match its reviewed year")
        self._validate_row_cap(
            self.accident_row_cap,
            expected=FARS_ACCIDENT_ROW_CAP,
            label="accident",
        )
        self._validate_row_cap(
            self.person_row_cap,
            expected=FARS_PERSON_ROW_CAP,
            label="person",
        )

    @staticmethod
    def _validate_row_cap(value: int, *, expected: int, label: str) -> None:
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError(f"FARS contract {label} row cap must be an integer")
        if value != expected:
            raise ValueError(f"FARS contract {label} row cap does not match its reviewed bound")

    def validate_distribution_url(self, value: str) -> str:
        """Validate that ``value`` is this contract's exact official archive."""
        validated = validate_fars_distribution_url(value, expected_year=self.year)
        if validated != self.distribution_url:
            raise ValueError("FARS distribution URL does not match the fixed-year contract")
        return validated

    def validate_raw_identity(self, *, size: int, sha256: str) -> None:
        """Require the exact reviewed bytes, independently of the mutable URL."""
        if isinstance(size, bool) or not isinstance(size, int):
            raise TypeError("FARS raw archive size must be an integer")
        if not isinstance(sha256, str):
            raise TypeError("FARS raw archive SHA-256 must be a string")
        if size != self.raw_size_bytes or sha256 != self.raw_sha256:
            raise ValueError("FARS raw archive identity does not match the fixed-year contract")

    def validate_raw_package(self, payload: bytes) -> None:
        """Hash exact package bytes and require this contract's reviewed identity."""
        if not isinstance(payload, bytes):
            raise TypeError("FARS raw archive payload must be bytes")
        self.validate_raw_identity(size=len(payload), sha256=hashlib.sha256(payload).hexdigest())


def _contract(year: int) -> FarsYearContract:
    raw_size_bytes, raw_sha256 = _PINNED_RAW_IDENTITIES[year]
    return FarsYearContract(
        year=year,
        source_id=f"fars-joined-{year}",
        distribution_url=_official_national_distribution_url(year),
        accident_member=_ACCIDENT_MEMBER,
        accident_encoding=_expected_accident_encoding(year),
        person_member=_PERSON_MEMBER,
        person_encoding="utf-8-sig",
        semantic_regime_id=_expected_semantic_regime(year),
        table_encoding_profile=_expected_encoding_profile(year),
        source_record_id_scheme="fars_year_st_case_v1",
        state_code_system=f"nhtsa_fars_state_{year}",
        county_code_system=f"nhtsa_fars_gsa_{year}",
        release_stage="final",
        accident_row_cap=FARS_ACCIDENT_ROW_CAP,
        person_row_cap=FARS_PERSON_ROW_CAP,
        raw_size_bytes=raw_size_bytes,
        raw_sha256=raw_sha256,
    )


FARS_YEAR_CONTRACTS: Mapping[int, FarsYearContract] = MappingProxyType(
    {year: _contract(year) for year in SUPPORTED_FARS_YEARS}
)


def fars_year_contract(year: int) -> FarsYearContract:
    """Return the immutable reviewed contract for an exact supported year."""
    if isinstance(year, bool) or not isinstance(year, int):
        raise TypeError("FARS contract year must be an integer")
    try:
        return FARS_YEAR_CONTRACTS[year]
    except KeyError as exc:
        raise ValueError("FARS contract year must be between 2020 and 2024") from exc
