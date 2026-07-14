# SPDX-License-Identifier: Apache-2.0
"""Deterministic index and release-set contract for public annual FARS context.

The browser consumes one small index followed by exactly one per-year public
artifact.  The index is an allowlist, not discovery metadata: an annual file is
publishable only when its canonical bytes, exact digest, reviewed NHTSA source
identity, geography crosswalk, and closed public schema all agree.

This module deliberately has no third-party imports so the minimal Pages build
can verify the release set before copying any public files.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
import stat
from collections.abc import Mapping
from pathlib import Path
from typing import Any, NoReturn, cast

from .fars_year_contracts import (
    FARS_YEAR_CONTRACT_HISTORY,
    SUPPORTED_FARS_YEARS,
    FarsYearContract,
    fars_year_contract_revision,
    fars_year_contract_sha256,
)

FARS_PUBLIC_INDEX_SCHEMA_VERSION = "1.0.0"
FARS_PUBLIC_INDEX_ARTIFACT_TYPE = "nearmiss.public.fars_state_context_index"
FARS_PUBLIC_INDEX_FILENAME = "fars-state-mode-index-v2.json"
FARS_PUBLIC_LEGACY_INDEX_FILENAME = "fars-state-mode-index.json"
FARS_PUBLIC_CORRECTIONS_FILENAME = "fars-release-corrections.json"
FARS_PUBLIC_ARTIFACT_SCHEMA_VERSION = "1.0.0"
FARS_PUBLIC_ARTIFACT_TYPE = "nearmiss.public.fars_state_context"
FARS_PUBLIC_ALGORITHM_VERSION = "state-involved-mode-v1"
FARS_PUBLIC_EFFECTIVE_K = 10
FARS_PUBLIC_STATE_COUNT = 51
FARS_PUBLIC_MODES = (
    "motor_vehicle_occupant",
    "motorcyclist",
    "pedalcyclist",
    "pedestrian",
    "other_road_user",
    "unknown",
)

_MAX_INDEX_BYTES = 64 * 1024
_MAX_ARTIFACT_BYTES = 256 * 1024
_MAX_CASES = 45_000
_MIN_CASES = 30_000
_MAX_CONTRIBUTIONS = _MAX_CASES * len(FARS_PUBLIC_MODES)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$", re.ASCII)
_ARTIFACT_NAME_RE = re.compile(
    r"^fars-([0-9]{4})-state-mode(?:-r([2-9][0-9]*))?\.json$",
    re.ASCII,
)
_CORRECTION_ID = "fars-2024-release-stage-arf-20260712"
_CORRECTION_AUTHORITY_URL = "https://rosap.ntl.bts.gov/view/dot/89797"
_CORRECTION_REASON = (
    "NHTSA identifies the 2024 release as the Annual Report File; revision 2 corrects "
    "provenance metadata without changing counts."
)
_IMMUTABLE_2024_R1_BYTES = 27_590
_IMMUTABLE_2024_R1_SHA256 = "29b5dc2673987cc7bedd0a83b2147e724e1fb2a2cb1458053af3d017ac8d6578"
_IMMUTABLE_INDEX_V1_BYTES = 5_270
_IMMUTABLE_INDEX_V1_SHA256 = "64d73ea4f25de4ef1321e6f8bed56215b9585fdc7ee74bc05bf47ec74bedaa48"

# Canonical source-native FARS state code, USPS abbreviation, and display name,
# ordered by display name. Puerto Rico is intentionally absent from the audited
# National archive contract.
_EXPECTED_STATES = (
    ("1", "AL", "Alabama"),
    ("2", "AK", "Alaska"),
    ("4", "AZ", "Arizona"),
    ("5", "AR", "Arkansas"),
    ("6", "CA", "California"),
    ("8", "CO", "Colorado"),
    ("9", "CT", "Connecticut"),
    ("10", "DE", "Delaware"),
    ("11", "DC", "District of Columbia"),
    ("12", "FL", "Florida"),
    ("13", "GA", "Georgia"),
    ("15", "HI", "Hawaii"),
    ("16", "ID", "Idaho"),
    ("17", "IL", "Illinois"),
    ("18", "IN", "Indiana"),
    ("19", "IA", "Iowa"),
    ("20", "KS", "Kansas"),
    ("21", "KY", "Kentucky"),
    ("22", "LA", "Louisiana"),
    ("23", "ME", "Maine"),
    ("24", "MD", "Maryland"),
    ("25", "MA", "Massachusetts"),
    ("26", "MI", "Michigan"),
    ("27", "MN", "Minnesota"),
    ("28", "MS", "Mississippi"),
    ("29", "MO", "Missouri"),
    ("30", "MT", "Montana"),
    ("31", "NE", "Nebraska"),
    ("32", "NV", "Nevada"),
    ("33", "NH", "New Hampshire"),
    ("34", "NJ", "New Jersey"),
    ("35", "NM", "New Mexico"),
    ("36", "NY", "New York"),
    ("37", "NC", "North Carolina"),
    ("38", "ND", "North Dakota"),
    ("39", "OH", "Ohio"),
    ("40", "OK", "Oklahoma"),
    ("41", "OR", "Oregon"),
    ("42", "PA", "Pennsylvania"),
    ("44", "RI", "Rhode Island"),
    ("45", "SC", "South Carolina"),
    ("46", "SD", "South Dakota"),
    ("47", "TN", "Tennessee"),
    ("48", "TX", "Texas"),
    ("49", "UT", "Utah"),
    ("50", "VT", "Vermont"),
    ("51", "VA", "Virginia"),
    ("53", "WA", "Washington"),
    ("54", "WV", "West Virginia"),
    ("55", "WI", "Wisconsin"),
    ("56", "WY", "Wyoming"),
)


def _canonical_json_bytes(value: Mapping[str, object]) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def _reject_constant(_value: str) -> NoReturn:
    raise ValueError("public FARS JSON contains a non-finite number")


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("public FARS JSON contains a duplicate key")
        result[key] = value
    return result


def _strict_json(payload: bytes, *, label: str, maximum: int) -> dict[str, object]:
    if type(payload) is not bytes:
        raise TypeError(f"{label} payload must be bytes")
    if not payload or len(payload) > maximum:
        raise ValueError(f"{label} exceeds its byte safety limit")
    try:
        value = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_strict_object,
            parse_constant=_reject_constant,
        )
    except UnicodeDecodeError as exc:
        raise ValueError(f"{label} is not UTF-8") from exc
    except (json.JSONDecodeError, RecursionError) as exc:
        raise ValueError(f"{label} is invalid JSON") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return cast(dict[str, object], value)


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{label} must be an object")
    return cast(Mapping[str, object], value)


def _list(value: object, label: str) -> list[object]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be an array")
    return cast(list[object], value)


def _integer(value: object, label: str, *, minimum: int = 0, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise ValueError(f"{label} must be an integer between {minimum} and {maximum}")
    return value


def _string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be a nonempty string")
    return value


def _exact_keys(value: Mapping[str, object], expected: tuple[str, ...], label: str) -> None:
    if set(value) != set(expected):
        raise ValueError(f"{label} has missing or unexpected fields")


def _sha256(value: object, label: str) -> str:
    text = _string(value, label)
    if _SHA256_RE.fullmatch(text) is None:
        raise ValueError(f"{label} must be a lowercase SHA-256 digest")
    return text


def fars_public_artifact_title(year: int) -> str:
    """Return the closed annual public title for one supported year."""
    if year not in SUPPORTED_FARS_YEARS:
        raise ValueError("public FARS artifact year is not supported")
    return f"{year} US fatal-crash burden by state and involved mode"


def fars_public_artifact_filename(year: int, contract_revision: int) -> str:
    """Return the immutable public filename for one registered annual revision."""
    contract = fars_year_contract_revision(year, contract_revision)
    suffix = "" if contract.revision == 1 else f"-r{contract.revision}"
    return f"fars-{year}-state-mode{suffix}.json"


def _artifact_contract(artifact: Mapping[str, object], *, expected_year: int) -> FarsYearContract:
    """Resolve exact artifact provenance to one registered immutable contract."""
    source = _mapping(artifact["source"], "public FARS source")
    matches = [
        contract
        for contract in FARS_YEAR_CONTRACT_HISTORY[expected_year]
        if source.get("release_stage") == contract.release_stage
        and source.get("distribution_url") == contract.distribution_url
        and source.get("source_revision_id") == contract.source_revision_id
        and source.get("raw_size_bytes") == contract.raw_size_bytes
        and source.get("raw_sha256") == contract.raw_sha256
    ]
    if len(matches) != 1:
        raise ValueError("public FARS source does not match a registered annual contract revision")
    return matches[0]


def fars_public_artifact_caveat(year: int) -> str:
    """Return the exact annual caveat included in canonical public bytes."""
    if year not in SUPPORTED_FARS_YEARS:
        raise ValueError("public FARS artifact year is not supported")
    return (
        f"Counts are distinct {year} FARS fatal crashes with at least one person in the involved "
        "mode, counted at most once per crash per mode. They are fatal-crash burden context, not "
        "exposure-normalized risk, incidence, causation, nonfatal crashes, near misses, record "
        "linkage, outcome validation, or a safety ranking. Mode cells overlap and are "
        "non-additive. A suppressed_or_zero cell combines a true zero with a positive count below "
        "k=10 and must never be read as zero. k=10 is a stability and publication guard for "
        f"already-public FARS data, not a confidentiality guarantee. The official {year} National "
        "archive covers the 50 states and District of Columbia; Puerto Rico requires a separately "
        "verified source."
    )


def fars_public_crosswalk_version(year: int) -> str:
    """Return the fixed-year public presentation-crosswalk version."""
    if year not in SUPPORTED_FARS_YEARS:
        raise ValueError("public FARS artifact year is not supported")
    return f"fars-usps-50-states-dc-{year}-v1"


def fars_public_crosswalk_sha256(year: int) -> str:
    """Return the digest of the exact fixed-year public state crosswalk."""
    payload: dict[str, object] = {
        "states": [
            {
                "state_code": code,
                "state_abbreviation": abbreviation,
                "state_name": name,
            }
            for code, abbreviation, name in _EXPECTED_STATES
        ],
        "version": fars_public_crosswalk_version(year),
    }
    return hashlib.sha256(_canonical_json_bytes(payload)).hexdigest()


def _validate_public_artifact(  # noqa: C901 - keep the closed annual contract adjacent
    artifact: Mapping[str, object], *, expected_year: int
) -> None:
    _exact_keys(
        artifact,
        (
            "schema_version",
            "artifact_type",
            "visibility",
            "title",
            "dataset_year",
            "source",
            "geography",
            "metric",
            "accounting",
            "caveat",
            "states",
        ),
        "public FARS artifact",
    )
    if expected_year not in SUPPORTED_FARS_YEARS:
        raise ValueError("public FARS artifact year is not supported")
    if (
        artifact["schema_version"] != FARS_PUBLIC_ARTIFACT_SCHEMA_VERSION
        or artifact["artifact_type"] != FARS_PUBLIC_ARTIFACT_TYPE
        or artifact["visibility"] != "public"
        or artifact["dataset_year"] != expected_year
        or artifact["title"] != fars_public_artifact_title(expected_year)
        or artifact["caveat"] != fars_public_artifact_caveat(expected_year)
    ):
        raise ValueError("public FARS artifact identity does not match its reviewed year")

    source = _mapping(artifact["source"], "public FARS source")
    _exact_keys(
        source,
        (
            "name",
            "release_stage",
            "distribution_url",
            "source_revision_id",
            "raw_size_bytes",
            "raw_sha256",
        ),
        "public FARS source",
    )
    if source["name"] != "NHTSA Fatality Analysis Reporting System (FARS)":
        raise ValueError("public FARS source does not match the registered annual contract")
    _artifact_contract(artifact, expected_year=expected_year)

    geography = _mapping(artifact["geography"], "public FARS geography")
    _exact_keys(
        geography,
        (
            "type",
            "coverage",
            "state_count",
            "state_crosswalk_version",
            "state_crosswalk_sha256",
        ),
        "public FARS geography",
    )
    if (
        geography["type"] != "fars_state_code"
        or geography["coverage"] != f"official_{expected_year}_national_50_states_and_dc"
        or geography["state_count"] != FARS_PUBLIC_STATE_COUNT
        or geography["state_crosswalk_version"] != fars_public_crosswalk_version(expected_year)
        or geography["state_crosswalk_sha256"] != fars_public_crosswalk_sha256(expected_year)
    ):
        raise ValueError("public FARS geography does not match its fixed-year contract")

    metric = _mapping(artifact["metric"], "public FARS metric")
    _exact_keys(
        metric,
        (
            "algorithm_version",
            "dimension",
            "contribution_unit",
            "effective_k",
            "modes_non_additive",
            "modes",
        ),
        "public FARS metric",
    )
    if (
        metric["algorithm_version"] != FARS_PUBLIC_ALGORITHM_VERSION
        or metric["dimension"] != "involved_mode"
        or metric["contribution_unit"] != "distinct_crash_once_per_involved_mode"
        or metric["effective_k"] != FARS_PUBLIC_EFFECTIVE_K
        or metric["modes_non_additive"] is not True
        or tuple(_list(metric["modes"], "public FARS modes")) != FARS_PUBLIC_MODES
    ):
        raise ValueError("public FARS metric contract is invalid")

    accounting = _mapping(artifact["accounting"], "public FARS accounting")
    accounting_fields = (
        "case_count",
        "state_count",
        "state_mode_cell_count",
        "published_cell_count",
        "suppressed_or_zero_cell_count",
        "positive_candidate_cell_count",
        "positive_suppressed_cell_count",
        "crash_contribution_total",
        "published_crash_contribution_total",
        "suppressed_crash_contribution_total",
    )
    _exact_keys(accounting, accounting_fields, "public FARS accounting")
    expected_cells = FARS_PUBLIC_STATE_COUNT * len(FARS_PUBLIC_MODES)
    cell_accounting_fields = {
        "state_mode_cell_count",
        "published_cell_count",
        "suppressed_or_zero_cell_count",
        "positive_candidate_cell_count",
        "positive_suppressed_cell_count",
    }
    values = {
        field: _integer(
            accounting[field],
            f"public FARS accounting.{field}",
            minimum=_MIN_CASES if field == "case_count" else 0,
            maximum=(
                _MAX_CASES
                if field == "case_count"
                else FARS_PUBLIC_STATE_COUNT
                if field == "state_count"
                else expected_cells
                if field in cell_accounting_fields
                else _MAX_CONTRIBUTIONS
            ),
        )
        for field in accounting_fields
    }
    if values["state_count"] != FARS_PUBLIC_STATE_COUNT:
        raise ValueError("public FARS accounting state count is invalid")
    if values["state_mode_cell_count"] != expected_cells:
        raise ValueError("public FARS accounting cell count is invalid")

    states = _list(artifact["states"], "public FARS states")
    if len(states) != FARS_PUBLIC_STATE_COUNT:
        raise ValueError("public FARS artifact must contain 50 states and DC")
    observed_published = 0
    observed_withheld = 0
    observed_published_contributions = 0
    for index, state_value in enumerate(states):
        state = _mapping(state_value, "public FARS state")
        _exact_keys(
            state,
            ("state_code", "state_abbreviation", "state_name", "cells"),
            "public FARS state",
        )
        expected_state = _EXPECTED_STATES[index]
        actual_state = (
            state["state_code"],
            state["state_abbreviation"],
            state["state_name"],
        )
        if actual_state != expected_state:
            raise ValueError("public FARS state crosswalk or ordering is invalid")
        cells = _list(state["cells"], "public FARS state cells")
        if len(cells) != len(FARS_PUBLIC_MODES):
            raise ValueError("public FARS state does not contain every canonical mode")
        for mode_index, cell_value in enumerate(cells):
            cell = _mapping(cell_value, "public FARS cell")
            expected_mode = FARS_PUBLIC_MODES[mode_index]
            if cell.get("involved_mode") != expected_mode:
                raise ValueError("public FARS cell modes are not canonically ordered")
            if cell.get("status") == "published":
                _exact_keys(
                    cell,
                    ("involved_mode", "status", "crash_count"),
                    "published public FARS cell",
                )
                count = _integer(
                    cell["crash_count"],
                    "public FARS crash count",
                    minimum=FARS_PUBLIC_EFFECTIVE_K,
                    maximum=values["case_count"],
                )
                observed_published += 1
                observed_published_contributions += count
            elif cell.get("status") == "suppressed_or_zero":
                _exact_keys(
                    cell,
                    ("involved_mode", "status"),
                    "withheld public FARS cell",
                )
                observed_withheld += 1
            else:
                raise ValueError("public FARS cell publication status is invalid")

    positive_suppressed = values["positive_suppressed_cell_count"]
    suppressed_total = values["suppressed_crash_contribution_total"]
    suppressed_valid = (positive_suppressed == 0 and suppressed_total == 0) or (
        positive_suppressed >= 2
        and positive_suppressed
        <= suppressed_total
        <= positive_suppressed * (FARS_PUBLIC_EFFECTIVE_K - 1)
    )
    if not (
        values["published_cell_count"] == observed_published
        and values["suppressed_or_zero_cell_count"] == observed_withheld
        and observed_published + observed_withheld == expected_cells
        and values["positive_candidate_cell_count"] == observed_published + positive_suppressed
        and positive_suppressed <= observed_withheld
        and values["published_crash_contribution_total"] == observed_published_contributions
        and values["crash_contribution_total"]
        == observed_published_contributions + suppressed_total
        and values["case_count"]
        <= values["crash_contribution_total"]
        <= values["case_count"] * len(FARS_PUBLIC_MODES)
        and suppressed_valid
    ):
        raise ValueError("public FARS accounting does not reconcile")


def load_fars_public_release_bytes(
    payload: bytes,
    *,
    expected_year: int,
) -> dict[str, object]:
    """Load one canonical, closed, fixed-year public artifact."""
    artifact = _strict_json(
        payload,
        label="public FARS annual artifact",
        maximum=_MAX_ARTIFACT_BYTES,
    )
    _validate_public_artifact(artifact, expected_year=expected_year)
    if _canonical_json_bytes(artifact) != payload:
        raise ValueError("public FARS annual artifact is not canonical")
    return copy.deepcopy(artifact)


def _index_contract() -> dict[str, object]:
    return {
        "algorithm_version": FARS_PUBLIC_ALGORITHM_VERSION,
        "artifact_schema_version": FARS_PUBLIC_ARTIFACT_SCHEMA_VERSION,
        "artifact_type": FARS_PUBLIC_ARTIFACT_TYPE,
        "contribution_unit": "distinct_crash_once_per_involved_mode",
        "dimension": "involved_mode",
        "effective_k": FARS_PUBLIC_EFFECTIVE_K,
        "modes": list(FARS_PUBLIC_MODES),
        "modes_non_additive": True,
        "state_count": FARS_PUBLIC_STATE_COUNT,
    }


def _release_entry(year: int, payload: bytes, artifact: Mapping[str, object]) -> dict[str, object]:
    source = _mapping(artifact["source"], "public FARS source")
    geography = _mapping(artifact["geography"], "public FARS geography")
    annual = _artifact_contract(artifact, expected_year=year)
    return {
        "artifact_bytes": len(payload),
        "artifact_path": fars_public_artifact_filename(year, annual.revision),
        "artifact_sha256": hashlib.sha256(payload).hexdigest(),
        "contract": {
            "contract_revision": annual.revision,
            "contract_sha256": fars_year_contract_sha256(annual),
            "crash_mapping_version": annual.crash_mapping_version,
            "person_mapping_version": annual.person_mapping_version,
            "semantic_regime_id": annual.semantic_regime_id,
            "state_code_system": annual.state_code_system,
        },
        "dataset_year": year,
        "geography": {
            "coverage": geography["coverage"],
            "state_crosswalk_sha256": geography["state_crosswalk_sha256"],
            "state_crosswalk_version": geography["state_crosswalk_version"],
        },
        "source": {
            "distribution_url": source["distribution_url"],
            "raw_sha256": source["raw_sha256"],
            "raw_size_bytes": source["raw_size_bytes"],
            "source_revision_id": source["source_revision_id"],
        },
    }


def build_fars_public_release_index(
    releases: Mapping[int, bytes],
) -> dict[str, object]:
    """Build an index from explicitly supplied canonical annual artifacts."""
    if not isinstance(releases, Mapping):
        raise TypeError("public FARS releases must be a mapping")
    if not releases or len(releases) > len(SUPPORTED_FARS_YEARS):
        raise ValueError("public FARS release set must contain one to five annual artifacts")
    supplied_years = list(releases)
    if any(isinstance(year, bool) or not isinstance(year, int) for year in supplied_years):
        raise TypeError("public FARS release years must be integers")
    years = sorted(supplied_years)
    if any(year not in SUPPORTED_FARS_YEARS for year in years):
        raise ValueError("public FARS release year is not supported")

    entries: list[dict[str, object]] = []
    for year in years:
        payload = releases[year]
        if type(payload) is not bytes:
            raise TypeError("public FARS annual artifact payloads must be bytes")
        artifact = load_fars_public_release_bytes(payload, expected_year=year)
        entries.append(_release_entry(year, payload, artifact))
    index: dict[str, object] = {
        "artifact_type": FARS_PUBLIC_INDEX_ARTIFACT_TYPE,
        "contract": _index_contract(),
        "default_year": years[-1],
        "releases": entries,
        "schema_version": FARS_PUBLIC_INDEX_SCHEMA_VERSION,
        "visibility": "public",
    }
    validate_fars_public_release_index(index)
    return index


def validate_fars_public_release_index(  # noqa: C901 - keep each index pin adjacent
    index: Mapping[str, object],
) -> None:
    """Reject an index that is open-ended, stale-defaulted, or internally inconsistent."""
    _exact_keys(
        index,
        (
            "schema_version",
            "artifact_type",
            "visibility",
            "default_year",
            "contract",
            "releases",
        ),
        "public FARS release index",
    )
    if (
        index["schema_version"] != FARS_PUBLIC_INDEX_SCHEMA_VERSION
        or index["artifact_type"] != FARS_PUBLIC_INDEX_ARTIFACT_TYPE
        or index["visibility"] != "public"
    ):
        raise ValueError("public FARS release index identity is invalid")
    contract_value = _mapping(index["contract"], "public FARS index contract")
    expected_contract = _index_contract()
    if contract_value != expected_contract:
        raise ValueError("public FARS release index contract is invalid")

    releases = _list(index["releases"], "public FARS index releases")
    if not 1 <= len(releases) <= len(SUPPORTED_FARS_YEARS):
        raise ValueError("public FARS release index must contain one to five releases")
    observed_years: list[int] = []
    for release_value in releases:
        release = _mapping(release_value, "public FARS index release")
        _exact_keys(
            release,
            (
                "artifact_bytes",
                "artifact_path",
                "artifact_sha256",
                "contract",
                "dataset_year",
                "geography",
                "source",
            ),
            "public FARS index release",
        )
        year = _integer(
            release["dataset_year"],
            "public FARS release year",
            minimum=min(SUPPORTED_FARS_YEARS),
            maximum=max(SUPPORTED_FARS_YEARS),
        )
        if year not in SUPPORTED_FARS_YEARS:
            raise ValueError("public FARS release year is not supported")
        observed_years.append(year)
        _integer(
            release["artifact_bytes"],
            "public FARS release artifact bytes",
            minimum=1,
            maximum=_MAX_ARTIFACT_BYTES,
        )
        _sha256(release["artifact_sha256"], "public FARS release artifact digest")

        contract = _mapping(release["contract"], "public FARS release contract")
        _exact_keys(
            contract,
            (
                "contract_revision",
                "contract_sha256",
                "crash_mapping_version",
                "person_mapping_version",
                "semantic_regime_id",
                "state_code_system",
            ),
            "public FARS release contract",
        )
        revision = _integer(
            contract["contract_revision"],
            "public FARS release contract revision",
            minimum=1,
            maximum=len(FARS_YEAR_CONTRACT_HISTORY[year]),
        )
        try:
            annual = fars_year_contract_revision(year, revision)
        except ValueError as exc:
            raise ValueError("public FARS release contract revision is invalid") from exc
        if release["artifact_path"] != fars_public_artifact_filename(year, revision):
            raise ValueError("public FARS release artifact path is not canonical")
        if contract != {
            "contract_revision": annual.revision,
            "contract_sha256": fars_year_contract_sha256(annual),
            "crash_mapping_version": annual.crash_mapping_version,
            "person_mapping_version": annual.person_mapping_version,
            "semantic_regime_id": annual.semantic_regime_id,
            "state_code_system": annual.state_code_system,
        }:
            raise ValueError("public FARS release contract provenance is invalid")
        source = _mapping(release["source"], "public FARS release source")
        _exact_keys(
            source,
            (
                "distribution_url",
                "raw_sha256",
                "raw_size_bytes",
                "source_revision_id",
            ),
            "public FARS release source",
        )
        if source != {
            "distribution_url": annual.distribution_url,
            "raw_sha256": annual.raw_sha256,
            "raw_size_bytes": annual.raw_size_bytes,
            "source_revision_id": annual.source_revision_id,
        }:
            raise ValueError("public FARS release source pin is invalid")
        geography = _mapping(release["geography"], "public FARS release geography")
        _exact_keys(
            geography,
            ("coverage", "state_crosswalk_sha256", "state_crosswalk_version"),
            "public FARS release geography",
        )
        if geography != {
            "coverage": f"official_{year}_national_50_states_and_dc",
            "state_crosswalk_sha256": fars_public_crosswalk_sha256(year),
            "state_crosswalk_version": fars_public_crosswalk_version(year),
        }:
            raise ValueError("public FARS release geography pin is invalid")

    if observed_years != sorted(set(observed_years)):
        raise ValueError("public FARS releases must be unique and ordered by year")
    default_year = _integer(
        index["default_year"],
        "public FARS default year",
        minimum=min(SUPPORTED_FARS_YEARS),
        maximum=max(SUPPORTED_FARS_YEARS),
    )
    if default_year != observed_years[-1]:
        raise ValueError("public FARS default year must be the newest published release")


def canonical_fars_public_release_index_bytes(index: Mapping[str, object]) -> bytes:
    """Serialize one valid release index as canonical UTF-8 JSON."""
    validate_fars_public_release_index(index)
    return _canonical_json_bytes(index)


def load_fars_public_release_index_bytes(payload: bytes) -> dict[str, object]:
    """Load exact canonical release-index bytes with a closed size bound."""
    index = _strict_json(
        payload,
        label="public FARS release index",
        maximum=_MAX_INDEX_BYTES,
    )
    validate_fars_public_release_index(index)
    if canonical_fars_public_release_index_bytes(index) != payload:
        raise ValueError("public FARS release index is not canonical")
    return copy.deepcopy(index)


def _bounded_regular_file(path: Path, *, maximum: int, label: str) -> bytes:
    if path.is_symlink():
        raise ValueError(f"{label} must not be a symlink")
    try:
        metadata = path.stat()
    except OSError as exc:
        raise ValueError(f"{label} is unavailable") from exc
    if not stat.S_ISREG(metadata.st_mode) or not 1 <= metadata.st_size <= maximum:
        raise ValueError(f"{label} is not a bounded regular file")
    payload = path.read_bytes()
    if len(payload) != metadata.st_size:
        raise ValueError(f"{label} changed while it was read")
    return payload


def _load_correction_ledger(payload: bytes) -> dict[str, object]:
    ledger = _strict_json(
        payload,
        label="public FARS correction ledger",
        maximum=_MAX_INDEX_BYTES,
    )
    _exact_keys(
        ledger,
        ("schema_version", "artifact_type", "visibility", "corrections"),
        "public FARS correction ledger",
    )
    if (
        ledger["schema_version"] != "1.0.0"
        or ledger["artifact_type"] != "nearmiss.public.fars_release_corrections"
        or ledger["visibility"] != "public"
    ):
        raise ValueError("public FARS correction ledger identity is invalid")
    corrections = _list(ledger["corrections"], "public FARS corrections")
    if len(corrections) != 1:
        raise ValueError("public FARS correction ledger must contain the reviewed correction")
    correction = _mapping(corrections[0], "public FARS correction")
    _exact_keys(
        correction,
        (
            "affected_year",
            "authority_url",
            "corrected_value",
            "correction_id",
            "field",
            "prior_artifact",
            "prior_index",
            "prior_value",
            "reason",
            "replacement_artifact",
            "replacement_index",
        ),
        "public FARS correction",
    )
    if (
        correction["correction_id"] != _CORRECTION_ID
        or correction["affected_year"] != 2024
        or correction["authority_url"] != _CORRECTION_AUTHORITY_URL
        or correction["field"] != "source.release_stage"
        or correction["prior_value"] != "final"
        or correction["corrected_value"] != "annual_report_file"
        or correction["reason"] != _CORRECTION_REASON
    ):
        raise ValueError("public FARS correction ledger semantics are invalid")
    for field, expected_path in (
        ("prior_artifact", "fars-2024-state-mode.json"),
        ("replacement_artifact", "fars-2024-state-mode-r2.json"),
        ("prior_index", FARS_PUBLIC_LEGACY_INDEX_FILENAME),
        ("replacement_index", FARS_PUBLIC_INDEX_FILENAME),
    ):
        pin = _mapping(correction[field], f"public FARS correction {field}")
        _exact_keys(pin, ("bytes", "path", "sha256"), f"public FARS correction {field}")
        if pin["path"] != expected_path:
            raise ValueError("public FARS correction ledger path is invalid")
        _integer(
            pin["bytes"],
            f"public FARS correction {field} bytes",
            minimum=1,
            maximum=_MAX_ARTIFACT_BYTES,
        )
        _sha256(pin["sha256"], f"public FARS correction {field} digest")
    if _canonical_json_bytes(ledger) != payload:
        raise ValueError("public FARS correction ledger is not canonical")
    return copy.deepcopy(ledger)


def _verify_correction_pin(directory: Path, pin: Mapping[str, object], *, label: str) -> None:
    path = directory / cast(str, pin["path"])
    payload = _bounded_regular_file(path, maximum=_MAX_ARTIFACT_BYTES, label=label)
    if len(payload) != pin["bytes"] or hashlib.sha256(payload).hexdigest() != pin["sha256"]:
        raise ValueError(f"{label} does not match the correction ledger pin")


def _verify_index_releases(directory: Path, index: Mapping[str, object]) -> set[str]:
    releases = cast(list[Mapping[str, object]], index["releases"])
    declared: set[str] = set()
    for release in releases:
        year = cast(int, release["dataset_year"])
        name = cast(str, release["artifact_path"])
        declared.add(name)
        payload = _bounded_regular_file(
            directory / name,
            maximum=_MAX_ARTIFACT_BYTES,
            label=f"public FARS {year} annual artifact",
        )
        if (
            len(payload) != release["artifact_bytes"]
            or hashlib.sha256(payload).hexdigest() != release["artifact_sha256"]
        ):
            raise ValueError(f"public FARS {year} artifact does not match its index pin")
        artifact = load_fars_public_release_bytes(payload, expected_year=year)
        if _release_entry(year, payload, artifact) != release:
            raise ValueError(f"public FARS {year} artifact metadata drifted from its index")
    return declared


def _verify_provenance_only_public_delta(
    *,
    legacy_index: Mapping[str, object],
    current_index: Mapping[str, object],
    legacy_artifact: Mapping[str, object],
    current_artifact: Mapping[str, object],
) -> None:
    """Require revision 2 to change only registered provenance and byte pins."""
    normalized_artifact = copy.deepcopy(current_artifact)
    normalized_artifact_source = cast(dict[str, object], normalized_artifact["source"])
    legacy_artifact_source = cast(Mapping[str, object], legacy_artifact["source"])
    normalized_artifact_source["release_stage"] = legacy_artifact_source["release_stage"]
    normalized_artifact_source["source_revision_id"] = legacy_artifact_source["source_revision_id"]
    if normalized_artifact != legacy_artifact:
        raise ValueError("corrected public FARS artifact changed non-provenance content")

    normalized_index = copy.deepcopy(current_index)
    normalized_releases = cast(list[dict[str, object]], normalized_index["releases"])
    legacy_releases = cast(list[Mapping[str, object]], legacy_index["releases"])
    if [release["dataset_year"] for release in normalized_releases] != [
        release["dataset_year"] for release in legacy_releases
    ]:
        raise ValueError("corrected public FARS index changed the annual inventory")
    for position, (normalized, legacy) in enumerate(
        zip(normalized_releases, legacy_releases, strict=True)
    ):
        if normalized["dataset_year"] != 2024:
            if normalized != legacy:
                raise ValueError("corrected public FARS index changed an unaffected release")
            continue
        normalized["artifact_bytes"] = legacy["artifact_bytes"]
        normalized["artifact_path"] = legacy["artifact_path"]
        normalized["artifact_sha256"] = legacy["artifact_sha256"]
        normalized["contract"] = copy.deepcopy(legacy["contract"])
        normalized_source = cast(dict[str, object], normalized["source"])
        legacy_source = cast(Mapping[str, object], legacy["source"])
        normalized_source["source_revision_id"] = legacy_source["source_revision_id"]
        if normalized != legacy:
            raise ValueError(
                f"corrected public FARS index changed unexpected 2024 metadata at {position}"
            )
    if normalized_index != legacy_index:
        raise ValueError("corrected public FARS index changed non-correction content")


def build_fars_public_correction_ledger_bytes(
    *,
    prior_artifact: bytes,
    replacement_artifact: bytes,
    prior_index: bytes,
    replacement_index: bytes,
) -> bytes:
    """Build the canonical correction ledger from four exact reviewed payloads."""
    if (
        len(prior_artifact) != _IMMUTABLE_2024_R1_BYTES
        or hashlib.sha256(prior_artifact).hexdigest() != _IMMUTABLE_2024_R1_SHA256
    ):
        raise ValueError("prior public FARS artifact is not the immutable published revision")
    if (
        len(prior_index) != _IMMUTABLE_INDEX_V1_BYTES
        or hashlib.sha256(prior_index).hexdigest() != _IMMUTABLE_INDEX_V1_SHA256
    ):
        raise ValueError("prior public FARS index is not the immutable published revision")
    legacy_artifact_value = load_fars_public_release_bytes(prior_artifact, expected_year=2024)
    replacement_artifact_value = load_fars_public_release_bytes(
        replacement_artifact,
        expected_year=2024,
    )
    legacy_index_value = load_fars_public_release_index_bytes(prior_index)
    replacement_index_value = load_fars_public_release_index_bytes(replacement_index)
    legacy_releases = cast(list[Mapping[str, object]], legacy_index_value["releases"])
    current_releases = cast(list[Mapping[str, object]], replacement_index_value["releases"])
    legacy_2024 = [release for release in legacy_releases if release["dataset_year"] == 2024]
    current_2024 = [release for release in current_releases if release["dataset_year"] == 2024]
    if len(legacy_2024) != 1 or len(current_2024) != 1:
        raise ValueError("correction indexes must each contain exactly one 2024 release")
    legacy_release = legacy_2024[0]
    current_release = current_2024[0]
    current_contract = cast(Mapping[str, object], current_release["contract"])
    if (
        legacy_release["artifact_path"] != "fars-2024-state-mode.json"
        or current_release["artifact_path"] != "fars-2024-state-mode-r2.json"
        or current_contract["contract_revision"] != 2
    ):
        raise ValueError("correction indexes do not select the reviewed 2024 revisions")
    for release, payload, label in (
        (legacy_release, prior_artifact, "prior"),
        (current_release, replacement_artifact, "replacement"),
    ):
        if (
            release["artifact_bytes"] != len(payload)
            or release["artifact_sha256"] != hashlib.sha256(payload).hexdigest()
        ):
            raise ValueError(f"{label} public FARS artifact does not match its index pin")
    _verify_provenance_only_public_delta(
        legacy_index=legacy_index_value,
        current_index=replacement_index_value,
        legacy_artifact=legacy_artifact_value,
        current_artifact=replacement_artifact_value,
    )
    ledger: dict[str, object] = {
        "artifact_type": "nearmiss.public.fars_release_corrections",
        "corrections": [
            {
                "affected_year": 2024,
                "authority_url": _CORRECTION_AUTHORITY_URL,
                "corrected_value": "annual_report_file",
                "correction_id": _CORRECTION_ID,
                "field": "source.release_stage",
                "prior_artifact": {
                    "bytes": len(prior_artifact),
                    "path": "fars-2024-state-mode.json",
                    "sha256": hashlib.sha256(prior_artifact).hexdigest(),
                },
                "prior_index": {
                    "bytes": len(prior_index),
                    "path": FARS_PUBLIC_LEGACY_INDEX_FILENAME,
                    "sha256": hashlib.sha256(prior_index).hexdigest(),
                },
                "prior_value": "final",
                "reason": _CORRECTION_REASON,
                "replacement_artifact": {
                    "bytes": len(replacement_artifact),
                    "path": "fars-2024-state-mode-r2.json",
                    "sha256": hashlib.sha256(replacement_artifact).hexdigest(),
                },
                "replacement_index": {
                    "bytes": len(replacement_index),
                    "path": FARS_PUBLIC_INDEX_FILENAME,
                    "sha256": hashlib.sha256(replacement_index).hexdigest(),
                },
            }
        ],
        "schema_version": "1.0.0",
        "visibility": "public",
    }
    payload = _canonical_json_bytes(ledger)
    _load_correction_ledger(payload)
    return payload


def verify_fars_public_release_directory(root: str | Path) -> dict[str, object]:
    """Verify current and retained immutable releases before site assembly."""
    directory = Path(root)
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError("public FARS release directory must be a real directory")
    current_index_payload = _bounded_regular_file(
        directory / FARS_PUBLIC_INDEX_FILENAME,
        maximum=_MAX_INDEX_BYTES,
        label="public FARS release index",
    )
    legacy_index_payload = _bounded_regular_file(
        directory / FARS_PUBLIC_LEGACY_INDEX_FILENAME,
        maximum=_MAX_INDEX_BYTES,
        label="retained public FARS release index",
    )
    ledger_payload = _bounded_regular_file(
        directory / FARS_PUBLIC_CORRECTIONS_FILENAME,
        maximum=_MAX_INDEX_BYTES,
        label="public FARS correction ledger",
    )
    current_index = load_fars_public_release_index_bytes(current_index_payload)
    legacy_index = load_fars_public_release_index_bytes(legacy_index_payload)
    if (
        len(legacy_index_payload) != _IMMUTABLE_INDEX_V1_BYTES
        or hashlib.sha256(legacy_index_payload).hexdigest() != _IMMUTABLE_INDEX_V1_SHA256
    ):
        raise ValueError("retained public FARS index changed from its published identity")
    ledger = _load_correction_ledger(ledger_payload)
    corrections = cast(list[Mapping[str, object]], ledger["corrections"])
    correction = corrections[0]
    for field, label in (
        ("prior_artifact", "retained public FARS artifact"),
        ("replacement_artifact", "corrected public FARS artifact"),
        ("prior_index", "retained public FARS index"),
        ("replacement_index", "current public FARS index"),
    ):
        _verify_correction_pin(
            directory,
            cast(Mapping[str, object], correction[field]),
            label=label,
        )
    declared = _verify_index_releases(directory, legacy_index)
    declared |= _verify_index_releases(directory, current_index)
    legacy_artifact_payload = _bounded_regular_file(
        directory / "fars-2024-state-mode.json",
        maximum=_MAX_ARTIFACT_BYTES,
        label="retained public FARS 2024 artifact",
    )
    if (
        len(legacy_artifact_payload) != _IMMUTABLE_2024_R1_BYTES
        or hashlib.sha256(legacy_artifact_payload).hexdigest() != _IMMUTABLE_2024_R1_SHA256
    ):
        raise ValueError("retained public FARS 2024 artifact changed from its published identity")
    current_2024_releases = [
        release
        for release in cast(list[Mapping[str, object]], current_index["releases"])
        if release["dataset_year"] == 2024
    ]
    if len(current_2024_releases) != 1:
        raise ValueError("current public FARS index must contain corrected 2024 release")
    current_2024_release = current_2024_releases[0]
    current_2024_contract = cast(Mapping[str, object], current_2024_release["contract"])
    if (
        current_2024_release["artifact_path"] != "fars-2024-state-mode-r2.json"
        or current_2024_contract["contract_revision"] != 2
    ):
        raise ValueError("current public FARS index does not select 2024 revision 2")
    current_artifact_payload = _bounded_regular_file(
        directory / current_2024_release["artifact_path"],
        maximum=_MAX_ARTIFACT_BYTES,
        label="corrected public FARS 2024 artifact",
    )
    _verify_provenance_only_public_delta(
        legacy_index=legacy_index,
        current_index=current_index,
        legacy_artifact=load_fars_public_release_bytes(
            legacy_artifact_payload,
            expected_year=2024,
        ),
        current_artifact=load_fars_public_release_bytes(
            current_artifact_payload,
            expected_year=2024,
        ),
    )
    allowed_namespace = declared | {
        FARS_PUBLIC_INDEX_FILENAME,
        FARS_PUBLIC_LEGACY_INDEX_FILENAME,
        FARS_PUBLIC_CORRECTIONS_FILENAME,
    }
    observed_namespace = {
        path.relative_to(directory).as_posix()
        for path in directory.rglob("*")
        if (path.is_file() or path.is_symlink())
        and path.name.casefold().startswith("fars-")
        and path.suffix.casefold() == ".json"
    }
    if observed_namespace != allowed_namespace:
        raise ValueError("public FARS namespace contains missing or unindexed JSON artifacts")

    on_disk = {
        path.relative_to(directory).as_posix()
        for path in directory.rglob("*")
        if _ARTIFACT_NAME_RE.fullmatch(path.name)
    }
    if on_disk != declared:
        raise ValueError("public FARS annual artifacts and release index do not match")
    return current_index


__all__ = [
    "FARS_PUBLIC_ALGORITHM_VERSION",
    "FARS_PUBLIC_ARTIFACT_SCHEMA_VERSION",
    "FARS_PUBLIC_ARTIFACT_TYPE",
    "FARS_PUBLIC_CORRECTIONS_FILENAME",
    "FARS_PUBLIC_EFFECTIVE_K",
    "FARS_PUBLIC_INDEX_ARTIFACT_TYPE",
    "FARS_PUBLIC_INDEX_FILENAME",
    "FARS_PUBLIC_INDEX_SCHEMA_VERSION",
    "FARS_PUBLIC_LEGACY_INDEX_FILENAME",
    "FARS_PUBLIC_MODES",
    "FARS_PUBLIC_STATE_COUNT",
    "build_fars_public_correction_ledger_bytes",
    "build_fars_public_release_index",
    "canonical_fars_public_release_index_bytes",
    "fars_public_artifact_caveat",
    "fars_public_artifact_filename",
    "fars_public_artifact_title",
    "fars_public_crosswalk_sha256",
    "fars_public_crosswalk_version",
    "load_fars_public_release_bytes",
    "load_fars_public_release_index_bytes",
    "validate_fars_public_release_index",
    "verify_fars_public_release_directory",
]
