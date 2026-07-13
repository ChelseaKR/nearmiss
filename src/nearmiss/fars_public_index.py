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
    SUPPORTED_FARS_YEARS,
    fars_year_contract,
    fars_year_contract_sha256,
)

FARS_PUBLIC_INDEX_SCHEMA_VERSION = "1.0.0"
FARS_PUBLIC_INDEX_ARTIFACT_TYPE = "nearmiss.public.fars_state_context_index"
FARS_PUBLIC_INDEX_FILENAME = "fars-state-mode-index.json"
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
_ARTIFACT_NAME_RE = re.compile(r"^fars-([0-9]{4})-state-mode\.json$", re.ASCII)

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

    contract = fars_year_contract(expected_year)
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
    if (
        source["name"] != "NHTSA Fatality Analysis Reporting System (FARS)"
        or source["release_stage"] != "final"
        or source["distribution_url"] != contract.distribution_url
        or source["source_revision_id"] != contract.source_revision_id
        or source["raw_size_bytes"] != contract.raw_size_bytes
        or source["raw_sha256"] != contract.raw_sha256
    ):
        raise ValueError("public FARS source does not match the registered annual contract")

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
    annual = fars_year_contract(year)
    return {
        "artifact_bytes": len(payload),
        "artifact_path": f"fars-{year}-state-mode.json",
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
        if release["artifact_path"] != f"fars-{year}-state-mode.json":
            raise ValueError("public FARS release artifact path is not canonical")
        _integer(
            release["artifact_bytes"],
            "public FARS release artifact bytes",
            minimum=1,
            maximum=_MAX_ARTIFACT_BYTES,
        )
        _sha256(release["artifact_sha256"], "public FARS release artifact digest")

        annual = fars_year_contract(year)
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


def verify_fars_public_release_directory(root: str | Path) -> dict[str, object]:
    """Verify the index and every declared annual file before site assembly."""
    directory = Path(root)
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError("public FARS release directory must be a real directory")
    index_payload = _bounded_regular_file(
        directory / FARS_PUBLIC_INDEX_FILENAME,
        maximum=_MAX_INDEX_BYTES,
        label="public FARS release index",
    )
    index = load_fars_public_release_index_bytes(index_payload)
    releases = cast(list[Mapping[str, object]], index["releases"])
    declared = {cast(str, release["artifact_path"]) for release in releases}
    allowed_namespace = declared | {FARS_PUBLIC_INDEX_FILENAME}
    observed_namespace = {
        path.relative_to(directory).as_posix()
        for path in directory.rglob("*")
        if (path.is_file() or path.is_symlink())
        and path.name.casefold().startswith("fars-")
        and path.suffix.casefold() == ".json"
    }
    if observed_namespace != allowed_namespace:
        raise ValueError("public FARS namespace contains missing or unindexed JSON artifacts")

    for release in releases:
        year = cast(int, release["dataset_year"])
        name = cast(str, release["artifact_path"])
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

    on_disk = {
        path.relative_to(directory).as_posix()
        for path in directory.rglob("*")
        if _ARTIFACT_NAME_RE.fullmatch(path.name)
    }
    if on_disk != declared:
        raise ValueError("public FARS annual artifacts and release index do not match")
    return index


__all__ = [
    "FARS_PUBLIC_ALGORITHM_VERSION",
    "FARS_PUBLIC_ARTIFACT_SCHEMA_VERSION",
    "FARS_PUBLIC_ARTIFACT_TYPE",
    "FARS_PUBLIC_EFFECTIVE_K",
    "FARS_PUBLIC_INDEX_ARTIFACT_TYPE",
    "FARS_PUBLIC_INDEX_FILENAME",
    "FARS_PUBLIC_INDEX_SCHEMA_VERSION",
    "FARS_PUBLIC_MODES",
    "FARS_PUBLIC_STATE_COUNT",
    "build_fars_public_release_index",
    "canonical_fars_public_release_index_bytes",
    "fars_public_artifact_caveat",
    "fars_public_artifact_title",
    "fars_public_crosswalk_sha256",
    "fars_public_crosswalk_version",
    "load_fars_public_release_bytes",
    "load_fars_public_release_index_bytes",
    "validate_fars_public_release_index",
    "verify_fars_public_release_directory",
]
