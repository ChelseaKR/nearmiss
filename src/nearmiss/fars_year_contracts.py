# SPDX-License-Identifier: Apache-2.0
"""Immutable ingestion contracts for official 2020--2024 National FARS data."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, replace
from types import MappingProxyType

from .fars_distribution import validate_fars_distribution_url

SUPPORTED_FARS_YEARS = (2020, 2021, 2022, 2023, 2024)
FARS_RELEASE_STAGES = ("preliminary", "annual_report_file", "final")
FARS_ACCIDENT_ROW_CAP = 45_000
FARS_PERSON_ROW_CAP = 110_000
FARS_RAW_ARCHIVE_MAX_BYTES = 256 * 1024 * 1024

_ACCIDENT_MEMBER = "accident.csv"
_PERSON_MEMBER = "person.csv"
_EARLY_SEMANTIC_REGIME = "fars_per_typ_2020_2021_v1"
_LATE_SEMANTIC_REGIME = "fars_per_typ_2022_2024_v1"
_CONTRACT_SCHEMA_VERSION = "1.0.0"
_INITIAL_REVIEW_REFERENCE = "nearmiss-fars-source-audit-20260712"
_2024_ARF_REVIEW_REFERENCE = "nearmiss-fars-2024-arf-provenance-review-20260712"
_REVIEWED_2024_R1_CONTRACT_SHA256 = (
    "f6bc3dd55cf3dfb360c265308c7702cdf7f6df66894cf792afd6be83c09c72f8"
)
_REVIEWED_2024_ARF_CONTRACT_SHA256 = (
    "2a24d2cad5341a8ffbe77272b59ccaf0c983a2e9beb763551bb3df7f4ef02b63"
)
_ALLOWED_REGRESSION_CATEGORIES = ("mode_counts", "record_counts")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$", re.ASCII)
_SEMVER_RE = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$", re.ASCII)
_REVISION_ID_RE = re.compile(r"^reviewed-[0-9]{8}-[0-9a-f]{12}$", re.ASCII)
_REVIEW_REFERENCE_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{2,127}$", re.ASCII)
# Audited from the official National URLs on 2026-07-12. NHTSA reposts files
# under stable URLs, so changing any identity is a reviewed source revision.
_PINNED_RAW_IDENTITIES = {
    2020: (31_016_385, "b2806902b3da9b45c632499f82e1c74fd108238ae7f67e108ebf40360ee4c9c3"),
    2021: (35_190_858, "743c19a13884614430d295289e655c5ad32b0a025a11e5b2149dfb57acae389b"),
    2022: (34_689_724, "989448d7a2f3964264c96a3cdb220f6c413c782a33eb759781f520c5acb5f744"),
    2023: (34_174_899, "edde841eb493e55751961b36bac2d1ce8750f601cb8e6e183a525723bb62bab0"),
    2024: (32_672_161, "5112727a8c0dc91ffee27ca05bddb073934f2d192ce4fae997da767dccdbe04f"),
}
_RELEASE_STAGE_RANK = MappingProxyType(
    {stage: rank for rank, stage in enumerate(FARS_RELEASE_STAGES)}
)


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
    contract_schema_version: str
    revision: int
    predecessor_contract_sha256: str | None
    transition_review_reference: str
    allowed_regressions: tuple[str, ...]
    source_id: str
    source_revision_id: str
    distribution_url: str
    accident_member: str
    accident_encoding: str
    person_member: str
    person_encoding: str
    semantic_regime_id: str
    table_encoding_profile: str
    crash_mapping_version: str
    person_mapping_version: str
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
        self._validate_revision_metadata()
        expected_url = _official_national_distribution_url(self.year)
        validated_url = validate_fars_distribution_url(
            self.distribution_url,
            expected_year=self.year,
        )
        if validated_url != expected_url:
            raise ValueError("FARS contract distribution URL is not the reviewed National archive")
        if self.source_id != f"fars-joined-{self.year}":
            raise ValueError("FARS contract source_id does not match its fixed year")
        if (
            not isinstance(self.source_revision_id, str)
            or _REVISION_ID_RE.fullmatch(self.source_revision_id) is None
        ):
            raise ValueError("FARS contract source revision ID is invalid")
        if self.accident_member != _ACCIDENT_MEMBER or self.person_member != _PERSON_MEMBER:
            raise ValueError("FARS contract selected CSV members do not match the reviewed tables")
        if self.accident_encoding != _expected_accident_encoding(self.year):
            raise ValueError("FARS contract accident encoding does not match its reviewed year")
        if self.person_encoding != "utf-8-sig":
            raise ValueError("FARS contract person encoding does not match its reviewed year")

    def _validate_revision_metadata(self) -> None:
        if self.contract_schema_version != _CONTRACT_SCHEMA_VERSION:
            raise ValueError("FARS contract schema version is invalid")
        if isinstance(self.revision, bool) or not isinstance(self.revision, int):
            raise TypeError("FARS contract revision must be an integer")
        if self.revision < 1:
            raise ValueError("FARS contract revision must be positive")
        if self.predecessor_contract_sha256 is not None and (
            not isinstance(self.predecessor_contract_sha256, str)
            or _SHA256_RE.fullmatch(self.predecessor_contract_sha256) is None
        ):
            raise ValueError("FARS contract predecessor digest is invalid")
        if (
            not isinstance(self.transition_review_reference, str)
            or _REVIEW_REFERENCE_RE.fullmatch(self.transition_review_reference) is None
        ):
            raise ValueError("FARS contract transition review reference is invalid")
        if not isinstance(self.allowed_regressions, tuple):
            raise TypeError("FARS contract allowed regressions must be an immutable tuple")
        if (
            any(
                not isinstance(category, str) or category not in _ALLOWED_REGRESSION_CATEGORIES
                for category in self.allowed_regressions
            )
            or tuple(sorted(self.allowed_regressions)) != self.allowed_regressions
            or len(set(self.allowed_regressions)) != len(self.allowed_regressions)
        ):
            raise ValueError("FARS contract allowed regressions are invalid or noncanonical")

    def _validate_semantics(self) -> None:
        if self.semantic_regime_id != _expected_semantic_regime(self.year):
            raise ValueError("FARS contract semantic regime does not match its reviewed year")
        if self.table_encoding_profile != _expected_encoding_profile(self.year):
            raise ValueError(
                "FARS contract table encoding profile does not match its reviewed year"
            )
        for label, version in (
            ("crash", self.crash_mapping_version),
            ("person", self.person_mapping_version),
        ):
            if not isinstance(version, str) or _SEMVER_RE.fullmatch(version) is None:
                raise ValueError(f"FARS contract {label} mapping version is invalid")
        if self.source_record_id_scheme != "fars_year_st_case_v1":
            raise ValueError("FARS contract source record identity scheme is invalid")
        if self.state_code_system != f"nhtsa_fars_state_{self.year}":
            raise ValueError("FARS contract state code system does not match its reviewed year")
        if self.county_code_system != f"nhtsa_fars_gsa_{self.year}":
            raise ValueError("FARS contract county code system does not match its reviewed year")
        if self.release_stage not in FARS_RELEASE_STAGES:
            raise ValueError("FARS contract release stage is invalid")

    def _validate_bounds_and_raw_identity(self) -> None:
        if (
            isinstance(self.raw_size_bytes, bool)
            or not isinstance(self.raw_size_bytes, int)
            or self.raw_size_bytes < 1
            or self.raw_size_bytes > FARS_RAW_ARCHIVE_MAX_BYTES
        ):
            raise ValueError("FARS contract raw archive size is invalid")
        if not isinstance(self.raw_sha256, str) or _SHA256_RE.fullmatch(self.raw_sha256) is None:
            raise ValueError("FARS contract raw archive digest is invalid")
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


def _contract_descriptor_value(contract: FarsYearContract) -> dict[str, object]:
    return {
        "contract_schema_version": contract.contract_schema_version,
        "year": contract.year,
        "revision": contract.revision,
        "predecessor_contract_sha256": contract.predecessor_contract_sha256,
        "transition_review_reference": contract.transition_review_reference,
        "allowed_regressions": list(contract.allowed_regressions),
        "source_id": contract.source_id,
        "source_revision_id": contract.source_revision_id,
        "distribution_url": contract.distribution_url,
        "release_stage": contract.release_stage,
        "raw_size_bytes": contract.raw_size_bytes,
        "raw_sha256": contract.raw_sha256,
        "accident_member": contract.accident_member,
        "accident_encoding": contract.accident_encoding,
        "person_member": contract.person_member,
        "person_encoding": contract.person_encoding,
        "semantic_regime_id": contract.semantic_regime_id,
        "table_encoding_profile": contract.table_encoding_profile,
        "crash_mapping_version": contract.crash_mapping_version,
        "person_mapping_version": contract.person_mapping_version,
        "source_record_id_scheme": contract.source_record_id_scheme,
        "state_code_system": contract.state_code_system,
        "county_code_system": contract.county_code_system,
        "accident_row_cap": contract.accident_row_cap,
        "person_row_cap": contract.person_row_cap,
    }


_CONTRACT_DESCRIPTOR_KEYS = frozenset(
    {
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
)


def _canonical_fars_year_contract_descriptor_bytes(
    descriptor: Mapping[str, object],
) -> bytes:
    return (
        json.dumps(
            descriptor,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def _unregistered_contract_sha256(contract: FarsYearContract) -> str:
    payload = _canonical_fars_year_contract_descriptor_bytes(_contract_descriptor_value(contract))
    return hashlib.sha256(payload).hexdigest()


def fars_release_stage_rank(release_stage: str) -> int:
    """Return the monotonic publication rank of a closed FARS release stage."""
    if not isinstance(release_stage, str):
        raise TypeError("FARS release stage must be a string")
    try:
        return _RELEASE_STAGE_RANK[release_stage]
    except KeyError as exc:
        raise ValueError("FARS release stage is invalid") from exc


def _2024_arf_source_revision_id(raw_sha256: str) -> str:
    material = f"{raw_sha256}:annual_report_file:{_2024_ARF_REVIEW_REFERENCE}"
    suffix = hashlib.sha256(material.encode("ascii")).hexdigest()[:12]
    return f"reviewed-20260712-{suffix}"


def is_fars_provenance_only_same_archive_correction(
    current: object,
    previous: object,
) -> bool:
    """Prove the single reviewed 2024 final-to-ARF provenance correction."""
    if not isinstance(current, FarsYearContract) or not isinstance(previous, FarsYearContract):
        return False
    if not (
        previous.year == current.year == 2024
        and previous.revision == 1
        and current.revision == 2
        and previous.predecessor_contract_sha256 is None
        and previous.transition_review_reference == _INITIAL_REVIEW_REFERENCE
        and previous.allowed_regressions == current.allowed_regressions == ()
        and previous.release_stage == "final"
        and current.release_stage == "annual_report_file"
        and current.predecessor_contract_sha256 == _unregistered_contract_sha256(previous)
        and current.transition_review_reference == _2024_ARF_REVIEW_REFERENCE
        and previous.source_revision_id == f"reviewed-20260712-{previous.raw_sha256[:12]}"
        and current.source_revision_id == _2024_arf_source_revision_id(current.raw_sha256)
        and _unregistered_contract_sha256(previous) == _REVIEWED_2024_R1_CONTRACT_SHA256
        and _unregistered_contract_sha256(current) == _REVIEWED_2024_ARF_CONTRACT_SHA256
    ):
        return False
    allowed_changes = frozenset(
        {
            "revision",
            "predecessor_contract_sha256",
            "transition_review_reference",
            "source_revision_id",
            "release_stage",
        }
    )
    previous_descriptor = _contract_descriptor_value(previous)
    current_descriptor = _contract_descriptor_value(current)
    return all(
        current_descriptor[key] == value
        for key, value in previous_descriptor.items()
        if key not in allowed_changes
    )


def _validate_predecessor(
    contract: FarsYearContract,
    previous: FarsYearContract | None,
) -> None:
    if previous is None:
        if (
            contract.predecessor_contract_sha256 is not None
            or contract.transition_review_reference != _INITIAL_REVIEW_REFERENCE
            or contract.allowed_regressions
            or contract.release_stage != "final"
        ):
            raise ValueError("FARS initial contract revision metadata is invalid")
        return
    if contract.predecessor_contract_sha256 != _unregistered_contract_sha256(previous):
        raise ValueError("FARS contract predecessor digest does not match prior revision")


def _semantic_version_tuple(value: str) -> tuple[int, int, int]:
    major, minor, patch = value.split(".")
    return int(major), int(minor), int(patch)


def _validate_revision_mapping_semantics(
    contract: FarsYearContract,
    previous: FarsYearContract | None,
) -> None:
    if previous is None:
        return
    previous_versions = (
        _semantic_version_tuple(previous.crash_mapping_version),
        _semantic_version_tuple(previous.person_mapping_version),
    )
    current_versions = (
        _semantic_version_tuple(contract.crash_mapping_version),
        _semantic_version_tuple(contract.person_mapping_version),
    )
    if any(
        current < prior for current, prior in zip(current_versions, previous_versions, strict=True)
    ):
        raise ValueError("FARS contract mapping versions must not regress")
    provenance_only_correction = is_fars_provenance_only_same_archive_correction(
        contract,
        previous,
    )
    if (
        fars_release_stage_rank(contract.release_stage)
        < fars_release_stage_rank(previous.release_stage)
        and not provenance_only_correction
    ):
        raise ValueError("FARS contract release stage must not regress")
    reuses_raw_archive = (
        contract.raw_size_bytes,
        contract.raw_sha256,
    ) == (
        previous.raw_size_bytes,
        previous.raw_sha256,
    )
    if (
        reuses_raw_archive
        and not provenance_only_correction
        and not any(
            current > prior
            for current, prior in zip(current_versions, previous_versions, strict=True)
        )
    ):
        raise ValueError("FARS reused-archive revision must advance a mapping version")


def _validate_history_entry(
    *,
    year: int,
    expected_revision: int,
    contract: FarsYearContract,
    previous: FarsYearContract | None,
    seen_revision_ids: set[str],
    raw_owner_by_sha256: dict[str, tuple[int, int]],
) -> None:
    if contract.year != year or contract.source_id != f"fars-joined-{year}":
        raise ValueError("FARS contract history changed its stable year or source")
    if contract.revision != expected_revision:
        raise ValueError("FARS contract history revisions must be contiguous")
    _validate_predecessor(contract, previous)
    _validate_revision_mapping_semantics(contract, previous)
    if contract.source_revision_id in seen_revision_ids:
        raise ValueError("FARS contract source revision IDs must be globally unique")
    previous_raw_owner = raw_owner_by_sha256.get(contract.raw_sha256)
    if previous_raw_owner is not None:
        previous_year, previous_raw_size = previous_raw_owner
        if previous_raw_size != contract.raw_size_bytes:
            raise ValueError("FARS contract reused a raw digest with a different archive size")
        if previous_year != year:
            raise ValueError("FARS contract raw identities must be unique across fixed years")
    seen_revision_ids.add(contract.source_revision_id)
    raw_owner_by_sha256[contract.raw_sha256] = (year, contract.raw_size_bytes)


def validate_fars_year_contract_registry(
    registry: Mapping[int, tuple[FarsYearContract, ...]],
) -> None:
    """Validate append-only sequencing and identity invariants across annual histories."""
    if not isinstance(registry, Mapping):
        raise TypeError("FARS contract registry must be a mapping")
    if tuple(registry) != SUPPORTED_FARS_YEARS:
        raise ValueError("FARS contract registry must contain the ordered supported years")
    seen_revision_ids: set[str] = set()
    raw_owner_by_sha256: dict[str, tuple[int, int]] = {}
    for year, history in registry.items():
        if not isinstance(history, tuple) or not history:
            raise ValueError("FARS contract history must be a nonempty immutable tuple")
        previous: FarsYearContract | None = None
        for expected_revision, contract in enumerate(history, start=1):
            if not isinstance(contract, FarsYearContract):
                raise TypeError("FARS contract history contains an invalid contract")
            _validate_history_entry(
                year=year,
                expected_revision=expected_revision,
                contract=contract,
                previous=previous,
                seen_revision_ids=seen_revision_ids,
                raw_owner_by_sha256=raw_owner_by_sha256,
            )
            previous = contract


def _contract(year: int) -> FarsYearContract:
    raw_size_bytes, raw_sha256 = _PINNED_RAW_IDENTITIES[year]
    return FarsYearContract(
        year=year,
        contract_schema_version=_CONTRACT_SCHEMA_VERSION,
        revision=1,
        predecessor_contract_sha256=None,
        transition_review_reference=_INITIAL_REVIEW_REFERENCE,
        allowed_regressions=(),
        source_id=f"fars-joined-{year}",
        source_revision_id=f"reviewed-20260712-{raw_sha256[:12]}",
        distribution_url=_official_national_distribution_url(year),
        accident_member=_ACCIDENT_MEMBER,
        accident_encoding=_expected_accident_encoding(year),
        person_member=_PERSON_MEMBER,
        person_encoding="utf-8-sig",
        semantic_regime_id=_expected_semantic_regime(year),
        table_encoding_profile=_expected_encoding_profile(year),
        crash_mapping_version="1.0.0",
        person_mapping_version="1.0.0",
        source_record_id_scheme="fars_year_st_case_v1",
        state_code_system=f"nhtsa_fars_state_{year}",
        county_code_system=f"nhtsa_fars_gsa_{year}",
        release_stage="final",
        accident_row_cap=FARS_ACCIDENT_ROW_CAP,
        person_row_cap=FARS_PERSON_ROW_CAP,
        raw_size_bytes=raw_size_bytes,
        raw_sha256=raw_sha256,
    )


def _2024_arf_provenance_correction(previous: FarsYearContract) -> FarsYearContract:
    return replace(
        previous,
        revision=2,
        predecessor_contract_sha256=_unregistered_contract_sha256(previous),
        transition_review_reference=_2024_ARF_REVIEW_REFERENCE,
        allowed_regressions=(),
        source_revision_id=_2024_arf_source_revision_id(previous.raw_sha256),
        release_stage="annual_report_file",
    )


def _validated_registered_history() -> Mapping[int, tuple[FarsYearContract, ...]]:
    history: dict[int, tuple[FarsYearContract, ...]] = {
        year: (_contract(year),) for year in SUPPORTED_FARS_YEARS
    }
    previous_2024 = history[2024][0]
    history[2024] = (previous_2024, _2024_arf_provenance_correction(previous_2024))
    validate_fars_year_contract_registry(history)
    return MappingProxyType(history)


FARS_YEAR_CONTRACT_HISTORY = _validated_registered_history()
FARS_YEAR_CONTRACTS: Mapping[int, FarsYearContract] = MappingProxyType(
    {year: history[-1] for year, history in FARS_YEAR_CONTRACT_HISTORY.items()}
)


def fars_year_contract(year: int) -> FarsYearContract:
    """Return the immutable reviewed contract for an exact supported year."""
    if isinstance(year, bool) or not isinstance(year, int):
        raise TypeError("FARS contract year must be an integer")
    try:
        return FARS_YEAR_CONTRACTS[year]
    except KeyError as exc:
        raise ValueError("FARS contract year must be between 2020 and 2024") from exc


def fars_year_contract_revision(year: int, revision: int) -> FarsYearContract:
    """Resolve one exact append-only contract revision."""
    if isinstance(year, bool) or not isinstance(year, int):
        raise TypeError("FARS contract year must be an integer")
    if isinstance(revision, bool) or not isinstance(revision, int):
        raise TypeError("FARS contract revision must be an integer")
    try:
        history = FARS_YEAR_CONTRACT_HISTORY[year]
    except KeyError as exc:
        raise ValueError("FARS contract year must be between 2020 and 2024") from exc
    if revision < 1 or revision > len(history):
        raise ValueError("FARS contract revision is not registered for its year")
    contract = history[revision - 1]
    if contract.revision != revision:
        raise RuntimeError("FARS contract history is not contiguous")
    return contract


def fars_year_contract_descriptor(contract: FarsYearContract) -> dict[str, object]:
    """Return the complete closed descriptor embedded in a v2 annual artifact."""
    if not isinstance(contract, FarsYearContract):
        raise TypeError("FARS year contract descriptor requires a registered contract")
    if fars_year_contract_revision(contract.year, contract.revision) is not contract:
        raise ValueError("FARS year contract is not a registered revision")
    return _contract_descriptor_value(contract)


def fars_year_contract_from_descriptor(
    descriptor: Mapping[str, object],
) -> FarsYearContract:
    """Resolve an exact registered revision from its complete closed descriptor."""
    if not isinstance(descriptor, Mapping):
        raise TypeError("FARS year contract descriptor must be a mapping")
    materialized = dict(descriptor)
    if not all(isinstance(key, str) for key in materialized):
        raise TypeError("FARS year contract descriptor keys must be strings")
    if materialized.keys() != _CONTRACT_DESCRIPTOR_KEYS:
        raise ValueError("FARS year contract descriptor keys are not exact")
    year = materialized.get("year")
    revision = materialized.get("revision")
    if isinstance(year, bool) or not isinstance(year, int):
        raise TypeError("FARS year contract descriptor year must be an integer")
    if isinstance(revision, bool) or not isinstance(revision, int):
        raise TypeError("FARS year contract descriptor revision must be an integer")
    allowed_regressions = materialized.get("allowed_regressions")
    if not isinstance(allowed_regressions, list) or not all(
        isinstance(category, str) for category in allowed_regressions
    ):
        raise TypeError("FARS year contract descriptor allowed regressions must be a string array")
    contract = fars_year_contract_revision(year, revision)
    try:
        encoded = _canonical_fars_year_contract_descriptor_bytes(materialized)
    except (TypeError, ValueError) as exc:
        raise ValueError("FARS year contract descriptor is not canonical JSON") from exc
    if encoded != canonical_fars_year_contract_bytes(contract):
        raise ValueError("FARS year contract descriptor is not a registered revision")
    return contract


def canonical_fars_year_contract_bytes(contract: FarsYearContract) -> bytes:
    """Serialize a registered annual source contract canonically."""
    return _canonical_fars_year_contract_descriptor_bytes(fars_year_contract_descriptor(contract))


def fars_year_contract_sha256(contract: FarsYearContract) -> str:
    """Return the canonical identity of one append-only source revision."""
    return hashlib.sha256(canonical_fars_year_contract_bytes(contract)).hexdigest()
