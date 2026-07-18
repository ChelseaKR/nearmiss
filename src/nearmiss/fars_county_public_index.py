# SPDX-License-Identifier: Apache-2.0
"""Immutable release-set contracts for public county FARS context.

County values are only safe to load after a small, canonical index has pinned
both their exact bytes and the exact public geometry bytes they require.  This
module intentionally knows nothing about the site build or browser: it validates
a reviewable static release set and refuses private paths, unpinned JSON, and
silent revision replacement.
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

from .fars_county_boundary_publication import (
    FARS_COUNTY_PUBLIC_BOUNDARY_MAX_BYTES,
    canonical_public_fars_county_boundary_state_bytes,
    load_public_fars_county_boundary_state_bytes,
)
from .fars_county_crosswalk import (
    FARS_COUNTY_BOUNDARY_PRESENTATION_VINTAGE,
    FARS_COUNTY_CROSSWALK_VERSION,
)
from .fars_county_publication import (
    FARS_COUNTY_PUBLIC_ARTIFACT_MAX_BYTES,
    FARS_COUNTY_PUBLIC_MAX_EFFECTIVE_K,
    FARS_COUNTY_PUBLIC_MIN_EFFECTIVE_K,
    load_public_fars_county_state_bytes,
)
from .fars_public_context import FARS_PUBLIC_STATE_CROSSWALK
from .fars_year_contracts import (
    SUPPORTED_FARS_YEARS,
    fars_year_contract_revision,
    fars_year_contract_sha256,
)

FARS_COUNTY_PUBLIC_INDEX_SCHEMA_VERSION = "1.0.0"
FARS_COUNTY_PUBLIC_INDEX_ARTIFACT_TYPE = "nearmiss.public.fars_county_context_index"
FARS_COUNTY_PUBLIC_INDEX_FILENAME = "fars-county-mode-index-v1.json"
FARS_COUNTY_PUBLIC_CORRECTIONS_FILENAME = "fars-county-release-corrections.json"
FARS_COUNTY_PUBLIC_CORRECTIONS_ARTIFACT_TYPE = "nearmiss.public.fars_county_release_corrections"
FARS_COUNTY_PUBLIC_CORRECTIONS_SCHEMA_VERSION = "1.0.0"
FARS_COUNTY_PUBLIC_INDEX_MAX_BYTES = 512 * 1024
FARS_COUNTY_PUBLIC_MAX_CORRECTIONS = 1_024

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$", re.ASCII)
_STATE_FIPS_RE = re.compile(r"^[0-9]{2}$", re.ASCII)
_RELEASE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$", re.ASCII)
_DATE_RE = re.compile(r"^20[0-9]{2}-[0-1][0-9]-[0-3][0-9]$", re.ASCII)
_CORRECTION_ID_RE = re.compile(r"^county-[a-z0-9][a-z0-9-]{2,95}$", re.ASCII)
_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$", re.ASCII)
_VALUE_PATH_RE = re.compile(r"^fars/([0-9]{4})/counties/([0-9]{2})-r([1-9][0-9]*)\.json$", re.ASCII)
_BOUNDARY_PATH_RE = re.compile(r"^counties/([0-9]{2})\.json$", re.ASCII)
_STATE_BY_FIPS = {
    f"{int(code):02d}": (abbreviation, name)
    for code, (abbreviation, name) in FARS_PUBLIC_STATE_CROSSWALK.items()
}


def _closed(properties: Mapping[str, object]) -> dict[str, object]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": list(properties),
        "properties": dict(properties),
    }


_SHA256 = {"type": "string", "pattern": "^[0-9a-f]{64}$"}
_PIN_SCHEMA = _closed(
    {
        "bytes": {"type": "integer", "minimum": 1},
        "path": {"type": "string", "minLength": 1, "maxLength": 256},
        "sha256": _SHA256,
    }
)
_VALUE_PIN_SCHEMA = _closed(
    {
        "bytes": {"type": "integer", "minimum": 1},
        "path": {"type": "string", "minLength": 1, "maxLength": 256},
        "revision": {"type": "integer", "minimum": 1},
        "sha256": _SHA256,
    }
)
_STATE_SCHEMA = _closed(
    {
        "state_abbreviation": {"type": "string", "pattern": "^[A-Z]{2}$"},
        "state_fips": {"type": "string", "pattern": "^[0-9]{2}$"},
        "state_name": {"type": "string", "minLength": 1, "maxLength": 64},
    }
)
_STATE_RELEASE_SCHEMA = _closed(
    {"boundary": _PIN_SCHEMA, "state": _STATE_SCHEMA, "value": _VALUE_PIN_SCHEMA}
)
_RELEASE_SCHEMA = _closed(
    {
        "contract": _closed(
            {
                "contract_revision": {"type": "integer", "minimum": 1},
                "contract_sha256": _SHA256,
                "semantic_regime_id": {"type": "string", "minLength": 1, "maxLength": 128},
            }
        ),
        "dataset_year": {"type": "integer", "minimum": min(SUPPORTED_FARS_YEARS)},
        "effective_k": {
            "type": "integer",
            "minimum": FARS_COUNTY_PUBLIC_MIN_EFFECTIVE_K,
            "maximum": FARS_COUNTY_PUBLIC_MAX_EFFECTIVE_K,
        },
        "geography": _closed(
            {
                "crosswalk_sha256": _SHA256,
                "crosswalk_version": {"type": "string", "minLength": 1, "maxLength": 128},
                "presentation_vintage": {"type": "integer", "minimum": 2024},
            }
        ),
        "states": {"type": "array", "minItems": 1, "maxItems": 51, "items": _STATE_RELEASE_SCHEMA},
    }
)

FARS_COUNTY_PUBLIC_INDEX_SCHEMA: dict[str, object] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "https://nearmiss.dev/schema/public-fars-county-context-index.schema.json",
    "title": "Public NearMiss FARS county context release index",
    "type": "object",
    "additionalProperties": False,
    "required": [
        "schema_version",
        "artifact_type",
        "visibility",
        "release_id",
        "correction_ledger",
        "releases",
    ],
    "properties": {
        "schema_version": {"const": FARS_COUNTY_PUBLIC_INDEX_SCHEMA_VERSION},
        "artifact_type": {"const": FARS_COUNTY_PUBLIC_INDEX_ARTIFACT_TYPE},
        "visibility": {"const": "public"},
        "release_id": {"type": "string", "pattern": "^[a-z0-9][a-z0-9-]{0,63}$"},
        "correction_ledger": _PIN_SCHEMA,
        "releases": {
            "type": "array",
            "minItems": 1,
            "maxItems": len(SUPPORTED_FARS_YEARS),
            "items": _RELEASE_SCHEMA,
        },
    },
}

_IMPACT_SCHEMA = _closed(
    {
        "copy": {"type": "boolean"},
        "geometry": {"type": "boolean"},
        "identities": {"type": "boolean"},
        "values": {"type": "boolean"},
    }
)
_CORRECTION_SCHEMA = _closed(
    {
        "affected": _closed(
            {
                "dataset_year": {"type": "integer", "minimum": min(SUPPORTED_FARS_YEARS)},
                "state_fips": {"type": "string", "pattern": "^[0-9]{2}$"},
            }
        ),
        "correction_id": {"type": "string", "pattern": "^county-[a-z0-9][a-z0-9-]{2,95}$"},
        "impact": _IMPACT_SCHEMA,
        "prior_boundary": _PIN_SCHEMA,
        "prior_value": _VALUE_PIN_SCHEMA,
        "reason": {"type": "string", "minLength": 1, "maxLength": 1_000},
        "replacement_boundary": _PIN_SCHEMA,
        "replacement_deployment_commit": {"type": "string", "pattern": "^[0-9a-f]{40}$"},
        "replacement_value": _VALUE_PIN_SCHEMA,
        "review_date": {"type": "string", "pattern": "^20[0-9]{2}-[0-1][0-9]-[0-3][0-9]$"},
    }
)
FARS_COUNTY_PUBLIC_CORRECTIONS_SCHEMA: dict[str, object] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "https://nearmiss.dev/schema/public-fars-county-release-corrections.schema.json",
    "title": "Public NearMiss county context correction ledger",
    "type": "object",
    "additionalProperties": False,
    "required": ["schema_version", "artifact_type", "visibility", "corrections"],
    "properties": {
        "schema_version": {"const": FARS_COUNTY_PUBLIC_CORRECTIONS_SCHEMA_VERSION},
        "artifact_type": {"const": FARS_COUNTY_PUBLIC_CORRECTIONS_ARTIFACT_TYPE},
        "visibility": {"const": "public"},
        "corrections": {
            "type": "array",
            "maxItems": FARS_COUNTY_PUBLIC_MAX_CORRECTIONS,
            "items": _CORRECTION_SCHEMA,
        },
    },
}


def _canonical_json_bytes(value: Mapping[str, object]) -> bytes:
    return (
        json.dumps(
            value, ensure_ascii=False, allow_nan=False, separators=(",", ":"), sort_keys=True
        )
        + "\n"
    ).encode("utf-8")


def _reject_constant(_value: str) -> NoReturn:
    raise ValueError("public county release JSON contains a non-finite number")


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("public county release JSON contains a duplicate key")
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


def _exact_keys(value: Mapping[str, object], expected: tuple[str, ...], label: str) -> None:
    if set(value) != set(expected):
        raise ValueError(f"{label} has missing or unexpected fields")


def _integer(value: object, label: str, *, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise ValueError(f"{label} must be an integer between {minimum} and {maximum}")
    return value


def _string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be a nonempty string")
    return value


def _sha256(value: object, label: str) -> str:
    text = _string(value, label)
    if _SHA256_RE.fullmatch(text) is None:
        raise ValueError(f"{label} must be a lowercase SHA-256 digest")
    return text


def _state_identity(value: Mapping[str, object], *, expected_fips: str) -> None:
    _exact_keys(value, ("state_abbreviation", "state_fips", "state_name"), "county index state")
    expected = _STATE_BY_FIPS.get(expected_fips)
    if expected is None or value != {
        "state_fips": expected_fips,
        "state_abbreviation": expected[0],
        "state_name": expected[1],
    }:
        raise ValueError("county index state identity is inconsistent")


def _pin(
    value: Mapping[str, object], *, label: str, maximum: int, value_pin: bool
) -> tuple[str, int, str, int | None]:
    fields = ("bytes", "path", "revision", "sha256") if value_pin else ("bytes", "path", "sha256")
    _exact_keys(value, fields, label)
    path = _string(value["path"], f"{label} path")
    size = _integer(value["bytes"], f"{label} bytes", minimum=1, maximum=maximum)
    digest = _sha256(value["sha256"], f"{label} digest")
    revision: int | None = None
    if value_pin:
        revision = _integer(value["revision"], f"{label} revision", minimum=1, maximum=9_999)
    return path, size, digest, revision


def _value_path(path: str, *, year: int, state_fips: str, revision: int) -> None:
    match = _VALUE_PATH_RE.fullmatch(path)
    if match is None or (int(match.group(1)), match.group(2), int(match.group(3))) != (
        year,
        state_fips,
        revision,
    ):
        raise ValueError("county value artifact path is not canonical")


def _boundary_path(path: str, *, state_fips: str) -> None:
    match = _BOUNDARY_PATH_RE.fullmatch(path)
    if match is None or match.group(1) != state_fips:
        raise ValueError("county boundary artifact path is not canonical")


def _validate_correction_pin_pair(
    correction: Mapping[str, object], *, year: int, state_fips: str
) -> None:
    prior_value = _mapping(correction["prior_value"], "county correction prior value")
    replacement_value = _mapping(
        correction["replacement_value"], "county correction replacement value"
    )
    prior_boundary = _mapping(correction["prior_boundary"], "county correction prior boundary")
    replacement_boundary = _mapping(
        correction["replacement_boundary"], "county correction replacement boundary"
    )
    prior_value_path, _size, prior_value_digest, prior_value_revision = _pin(
        prior_value,
        label="county correction prior value",
        maximum=FARS_COUNTY_PUBLIC_ARTIFACT_MAX_BYTES,
        value_pin=True,
    )
    replacement_value_path, _size, replacement_value_digest, replacement_value_revision = _pin(
        replacement_value,
        label="county correction replacement value",
        maximum=FARS_COUNTY_PUBLIC_ARTIFACT_MAX_BYTES,
        value_pin=True,
    )
    prior_boundary_path, _size, prior_boundary_digest, _ = _pin(
        prior_boundary,
        label="county correction prior boundary",
        maximum=FARS_COUNTY_PUBLIC_BOUNDARY_MAX_BYTES,
        value_pin=False,
    )
    replacement_boundary_path, _size, replacement_boundary_digest, _ = _pin(
        replacement_boundary,
        label="county correction replacement boundary",
        maximum=FARS_COUNTY_PUBLIC_BOUNDARY_MAX_BYTES,
        value_pin=False,
    )
    assert prior_value_revision is not None and replacement_value_revision is not None
    _value_path(prior_value_path, year=year, state_fips=state_fips, revision=prior_value_revision)
    _value_path(
        replacement_value_path,
        year=year,
        state_fips=state_fips,
        revision=replacement_value_revision,
    )
    _boundary_path(prior_boundary_path, state_fips=state_fips)
    _boundary_path(replacement_boundary_path, state_fips=state_fips)
    impact = _mapping(correction["impact"], "county correction impact")
    _exact_keys(impact, ("copy", "geometry", "identities", "values"), "county correction impact")
    if not all(isinstance(value, bool) for value in impact.values()) or not any(impact.values()):
        raise ValueError("county correction impact must contain at least one boolean change")
    value_changed = (prior_value_path, prior_value_digest) != (
        replacement_value_path,
        replacement_value_digest,
    )
    boundary_changed = (prior_boundary_path, prior_boundary_digest) != (
        replacement_boundary_path,
        replacement_boundary_digest,
    )
    if bool(impact["values"]) != value_changed:
        raise ValueError("county correction value impact does not match its pins")
    if bool(impact["geometry"]) != boundary_changed:
        raise ValueError("county correction geometry impact does not match its pins")


def validate_fars_county_public_correction_ledger(  # noqa: C901 - adjacent ledger safety checks
    ledger: Mapping[str, object],
) -> None:
    """Validate a closed, count-free correction ledger before it can be indexed."""

    _exact_keys(
        ledger,
        ("schema_version", "artifact_type", "visibility", "corrections"),
        "county correction ledger",
    )
    if (
        ledger["schema_version"] != FARS_COUNTY_PUBLIC_CORRECTIONS_SCHEMA_VERSION
        or ledger["artifact_type"] != FARS_COUNTY_PUBLIC_CORRECTIONS_ARTIFACT_TYPE
        or ledger["visibility"] != "public"
    ):
        raise ValueError("county correction ledger identity is invalid")
    corrections = _list(ledger["corrections"], "county corrections")
    if len(corrections) > FARS_COUNTY_PUBLIC_MAX_CORRECTIONS:
        raise ValueError("county correction ledger exceeds its safety limit")
    identifiers: list[str] = []
    for item in corrections:
        correction = _mapping(item, "county correction")
        _exact_keys(
            correction,
            (
                "affected",
                "correction_id",
                "impact",
                "prior_boundary",
                "prior_value",
                "reason",
                "replacement_boundary",
                "replacement_deployment_commit",
                "replacement_value",
                "review_date",
            ),
            "county correction",
        )
        identifier = _string(correction["correction_id"], "county correction id")
        if _CORRECTION_ID_RE.fullmatch(identifier) is None:
            raise ValueError("county correction id is invalid")
        identifiers.append(identifier)
        affected = _mapping(correction["affected"], "county correction affected scope")
        _exact_keys(affected, ("dataset_year", "state_fips"), "county correction affected scope")
        year = _integer(
            affected["dataset_year"],
            "county correction year",
            minimum=min(SUPPORTED_FARS_YEARS),
            maximum=max(SUPPORTED_FARS_YEARS),
        )
        if year not in SUPPORTED_FARS_YEARS:
            raise ValueError("county correction year is unsupported")
        state_fips = _string(affected["state_fips"], "county correction state FIPS")
        if _STATE_FIPS_RE.fullmatch(state_fips) is None or state_fips not in _STATE_BY_FIPS:
            raise ValueError("county correction state is outside reviewed coverage")
        if (
            _DATE_RE.fullmatch(_string(correction["review_date"], "county correction review date"))
            is None
        ):
            raise ValueError("county correction review date is invalid")
        if (
            _COMMIT_RE.fullmatch(
                _string(
                    correction["replacement_deployment_commit"],
                    "county correction deployment commit",
                )
            )
            is None
        ):
            raise ValueError("county correction deployment commit is invalid")
        _string(correction["reason"], "county correction reason")
        if len(cast(str, correction["reason"])) > 1_000:
            raise ValueError("county correction reason exceeds its safety limit")
        _validate_correction_pin_pair(correction, year=year, state_fips=state_fips)
    if identifiers != sorted(set(identifiers)):
        raise ValueError("county corrections must have unique canonical ordering")


def canonical_fars_county_public_correction_ledger_bytes(ledger: Mapping[str, object]) -> bytes:
    """Return canonical bytes for a closed county correction ledger."""

    validate_fars_county_public_correction_ledger(ledger)
    return _canonical_json_bytes(ledger)


def load_fars_county_public_correction_ledger_bytes(payload: bytes) -> dict[str, object]:
    """Load exact canonical correction-ledger bytes from an untrusted release tree."""

    ledger = _strict_json(
        payload, label="county correction ledger", maximum=FARS_COUNTY_PUBLIC_INDEX_MAX_BYTES
    )
    validate_fars_county_public_correction_ledger(ledger)
    if canonical_fars_county_public_correction_ledger_bytes(ledger) != payload:
        raise ValueError("county correction ledger is not canonical")
    return copy.deepcopy(ledger)


def empty_fars_county_public_correction_ledger() -> dict[str, object]:
    """Return the only valid pre-publication ledger: no correction claims yet."""

    return {
        "schema_version": FARS_COUNTY_PUBLIC_CORRECTIONS_SCHEMA_VERSION,
        "artifact_type": FARS_COUNTY_PUBLIC_CORRECTIONS_ARTIFACT_TYPE,
        "visibility": "public",
        "corrections": [],
    }


def _index_entry(
    *, value_path: str, value_payload: bytes, boundary_path: str, boundary_payload: bytes
) -> tuple[int, str, dict[str, object], dict[str, object], dict[str, object]]:
    value = load_public_fars_county_state_bytes(value_payload)
    boundary = load_public_fars_county_boundary_state_bytes(boundary_payload)
    year = cast(int, value["dataset_year"])
    state = _mapping(value["state"], "county value state")
    state_fips = cast(str, state["state_fips"])
    value_match = _VALUE_PATH_RE.fullmatch(value_path)
    if value_match is None:
        raise ValueError("county value artifact path is not canonical")
    value_revision = int(value_match.group(3))
    _value_path(value_path, year=year, state_fips=state_fips, revision=value_revision)
    _boundary_path(boundary_path, state_fips=state_fips)
    boundary_state = _mapping(boundary["state"], "county boundary state")
    if boundary_state != state:
        raise ValueError("county value and boundary state identities differ")
    geography = _mapping(value["geography"], "county value geography")
    expected_boundary_digest = hashlib.sha256(
        canonical_public_fars_county_boundary_state_bytes(boundary)
    ).hexdigest()
    if geography["boundary_sha256"] != expected_boundary_digest:
        raise ValueError("county value is detached from its indexed public boundary")
    return (
        year,
        state_fips,
        {
            "state": dict(state),
            "value": {
                "path": value_path,
                "bytes": len(value_payload),
                "sha256": hashlib.sha256(value_payload).hexdigest(),
                "revision": value_revision,
            },
            "boundary": {
                "path": boundary_path,
                "bytes": len(boundary_payload),
                "sha256": hashlib.sha256(boundary_payload).hexdigest(),
            },
        },
        {
            "presentation_vintage": geography["presentation_vintage"],
            "crosswalk_version": geography["crosswalk_version"],
            "crosswalk_sha256": geography["crosswalk_sha256"],
        },
        {
            "source": dict(_mapping(value["source"], "county value source")),
            "metric": dict(_mapping(value["metric"], "county value metric")),
        },
    )


def build_fars_county_public_release_index(  # noqa: C901 - retain all cross-artifact checks together
    value_artifacts: Mapping[str, bytes],
    boundary_artifacts: Mapping[str, bytes],
    correction_ledger: bytes,
    *,
    release_id: str,
) -> dict[str, object]:
    """Build one index from explicit canonical public files; no directory discovery occurs."""

    if _RELEASE_ID_RE.fullmatch(release_id) is None:
        raise ValueError("county release id is invalid")
    ledger = load_fars_county_public_correction_ledger_bytes(correction_ledger)
    if not value_artifacts or not boundary_artifacts:
        raise ValueError("county release index requires explicit value and boundary artifacts")
    boundaries: dict[str, tuple[str, bytes]] = {}
    for path, payload in boundary_artifacts.items():
        if not isinstance(path, str) or type(payload) is not bytes:
            raise TypeError("county boundary artifacts require string paths and bytes payloads")
        match = _BOUNDARY_PATH_RE.fullmatch(path)
        if match is None:
            raise ValueError("county boundary artifact path is not canonical")
        boundary = load_public_fars_county_boundary_state_bytes(payload)
        state_fips = cast(str, cast(Mapping[str, object], boundary["state"])["state_fips"])
        _boundary_path(path, state_fips=state_fips)
        if state_fips in boundaries:
            raise ValueError("county boundary artifact state was supplied more than once")
        boundaries[state_fips] = (path, payload)

    release_states: dict[int, list[dict[str, object]]] = {}
    release_geography: dict[int, Mapping[str, object]] = {}
    release_source_metric: dict[int, Mapping[str, object]] = {}
    for path, payload in value_artifacts.items():
        if not isinstance(path, str) or type(payload) is not bytes:
            raise TypeError("county value artifacts require string paths and bytes payloads")
        match = _VALUE_PATH_RE.fullmatch(path)
        if match is None:
            raise ValueError("county value artifact path is not canonical")
        state_fips = match.group(2)
        boundary_entry = boundaries.get(state_fips)
        if boundary_entry is None:
            raise ValueError("county value artifact has no explicitly supplied boundary")
        year, resolved_state_fips, state_entry, geography, source_metric = _index_entry(
            value_path=path,
            value_payload=payload,
            boundary_path=boundary_entry[0],
            boundary_payload=boundary_entry[1],
        )
        if resolved_state_fips != state_fips:
            raise ValueError("county value artifact path state differs from payload")
        states = release_states.setdefault(year, [])
        if any(
            cast(Mapping[str, object], entry["state"])["state_fips"] == state_fips
            for entry in states
        ):
            raise ValueError("county release includes a state more than once per year")
        existing_geography = release_geography.setdefault(year, geography)
        if existing_geography != geography:
            raise ValueError("county release geography differs across states")
        existing_source_metric = release_source_metric.setdefault(year, source_metric)
        source = _mapping(source_metric, "county source metric bundle")
        if _mapping(source["source"], "county release source") != _mapping(
            existing_source_metric["source"], "county release source"
        ):
            raise ValueError("county release source differs across states")
        if _mapping(source["metric"], "county release metric") != _mapping(
            existing_source_metric["metric"], "county release metric"
        ):
            raise ValueError("county release metric differs across states")
        states.append(state_entry)
    if set(boundaries) != {
        cast(str, cast(Mapping[str, object], entry["state"])["state_fips"])
        for entries in release_states.values()
        for entry in entries
    }:
        raise ValueError("county boundary artifacts must be exactly the indexed state set")

    releases: list[dict[str, object]] = []
    for year in sorted(release_states):
        if year not in SUPPORTED_FARS_YEARS:
            raise ValueError("county release year is unsupported")
        states = sorted(
            release_states[year],
            key=lambda entry: int(
                cast(str, cast(Mapping[str, object], entry["state"])["state_fips"])
            ),
        )
        bundle = _mapping(release_source_metric[year], "county release source metric bundle")
        source = _mapping(bundle["source"], "county release source")
        metric = _mapping(bundle["metric"], "county release metric")
        revision = cast(int, source["contract_revision"])
        annual = fars_year_contract_revision(year, revision)
        if source["contract_sha256"] != fars_year_contract_sha256(annual):
            raise ValueError("county release source contract digest is inconsistent")
        release_geography_value = release_geography[year]
        if (
            release_geography_value["presentation_vintage"]
            != FARS_COUNTY_BOUNDARY_PRESENTATION_VINTAGE
            or release_geography_value["crosswalk_version"] != FARS_COUNTY_CROSSWALK_VERSION
        ):
            raise ValueError("county release geography contract is inconsistent")
        releases.append(
            {
                "dataset_year": year,
                "contract": {
                    "contract_revision": annual.revision,
                    "contract_sha256": fars_year_contract_sha256(annual),
                    "semantic_regime_id": annual.semantic_regime_id,
                },
                "geography": dict(release_geography_value),
                "effective_k": metric["effective_k"],
                "states": states,
            }
        )
    index: dict[str, object] = {
        "schema_version": FARS_COUNTY_PUBLIC_INDEX_SCHEMA_VERSION,
        "artifact_type": FARS_COUNTY_PUBLIC_INDEX_ARTIFACT_TYPE,
        "visibility": "public",
        "release_id": release_id,
        "correction_ledger": {
            "path": FARS_COUNTY_PUBLIC_CORRECTIONS_FILENAME,
            "bytes": len(correction_ledger),
            "sha256": hashlib.sha256(correction_ledger).hexdigest(),
        },
        "releases": releases,
    }
    validate_fars_county_public_release_index(index)
    # Preserve the parsed ledger validation in this pure builder; it is intentionally not embedded.
    del ledger
    return index


def validate_fars_county_public_release_index(  # noqa: C901 - preserve index safety checks together
    index: Mapping[str, object],
) -> None:
    """Validate the client allowlist without loading a single filesystem path."""

    _exact_keys(
        index,
        (
            "schema_version",
            "artifact_type",
            "visibility",
            "release_id",
            "correction_ledger",
            "releases",
        ),
        "county release index",
    )
    if (
        index["schema_version"] != FARS_COUNTY_PUBLIC_INDEX_SCHEMA_VERSION
        or index["artifact_type"] != FARS_COUNTY_PUBLIC_INDEX_ARTIFACT_TYPE
        or index["visibility"] != "public"
        or _RELEASE_ID_RE.fullmatch(_string(index["release_id"], "county release id")) is None
    ):
        raise ValueError("county release index identity is invalid")
    ledger = _mapping(index["correction_ledger"], "county release correction ledger")
    ledger_path, _size, _digest, _ = _pin(
        ledger,
        label="county release correction ledger",
        maximum=FARS_COUNTY_PUBLIC_INDEX_MAX_BYTES,
        value_pin=False,
    )
    if ledger_path != FARS_COUNTY_PUBLIC_CORRECTIONS_FILENAME:
        raise ValueError("county release correction ledger path is invalid")
    releases = _list(index["releases"], "county release index releases")
    if not 1 <= len(releases) <= len(SUPPORTED_FARS_YEARS):
        raise ValueError("county release index has an invalid release count")
    observed_years: list[int] = []
    for item in releases:
        release = _mapping(item, "county release")
        _exact_keys(
            release,
            ("contract", "dataset_year", "effective_k", "geography", "states"),
            "county release",
        )
        year = _integer(
            release["dataset_year"],
            "county release year",
            minimum=min(SUPPORTED_FARS_YEARS),
            maximum=max(SUPPORTED_FARS_YEARS),
        )
        if year not in SUPPORTED_FARS_YEARS:
            raise ValueError("county release year is unsupported")
        observed_years.append(year)
        contract = _mapping(release["contract"], "county release contract")
        _exact_keys(
            contract,
            ("contract_revision", "contract_sha256", "semantic_regime_id"),
            "county release contract",
        )
        revision = _integer(
            contract["contract_revision"],
            "county release contract revision",
            minimum=1,
            maximum=9_999,
        )
        annual = fars_year_contract_revision(year, revision)
        if contract != {
            "contract_revision": annual.revision,
            "contract_sha256": fars_year_contract_sha256(annual),
            "semantic_regime_id": annual.semantic_regime_id,
        }:
            raise ValueError("county release contract provenance is invalid")
        effective_k = _integer(
            release["effective_k"],
            "county release effective k",
            minimum=FARS_COUNTY_PUBLIC_MIN_EFFECTIVE_K,
            maximum=FARS_COUNTY_PUBLIC_MAX_EFFECTIVE_K,
        )
        geography = _mapping(release["geography"], "county release geography")
        _exact_keys(
            geography,
            ("crosswalk_sha256", "crosswalk_version", "presentation_vintage"),
            "county release geography",
        )
        if (
            geography["presentation_vintage"] != FARS_COUNTY_BOUNDARY_PRESENTATION_VINTAGE
            or geography["crosswalk_version"] != FARS_COUNTY_CROSSWALK_VERSION
        ):
            raise ValueError("county release geography contract is invalid")
        _sha256(geography["crosswalk_sha256"], "county release crosswalk digest")
        states = _list(release["states"], "county release states")
        if not 1 <= len(states) <= len(_STATE_BY_FIPS):
            raise ValueError("county release has an invalid state count")
        state_fipses: list[str] = []
        for state_item in states:
            state_entry = _mapping(state_item, "county release state")
            _exact_keys(state_entry, ("boundary", "state", "value"), "county release state")
            state = _mapping(state_entry["state"], "county release state identity")
            state_fips = _string(state["state_fips"], "county release state FIPS")
            _state_identity(state, expected_fips=state_fips)
            value = _mapping(state_entry["value"], "county release value pin")
            value_path, _size, _digest, value_revision = _pin(
                value,
                label="county release value",
                maximum=FARS_COUNTY_PUBLIC_ARTIFACT_MAX_BYTES,
                value_pin=True,
            )
            assert value_revision is not None
            _value_path(value_path, year=year, state_fips=state_fips, revision=value_revision)
            boundary = _mapping(state_entry["boundary"], "county release boundary pin")
            boundary_path, _size, _digest, _ = _pin(
                boundary,
                label="county release boundary",
                maximum=FARS_COUNTY_PUBLIC_BOUNDARY_MAX_BYTES,
                value_pin=False,
            )
            _boundary_path(boundary_path, state_fips=state_fips)
            state_fipses.append(state_fips)
        if state_fipses != sorted(set(state_fipses), key=int):
            raise ValueError("county release states must be unique and canonically ordered")
        if not isinstance(effective_k, int):  # keeps type narrowing explicit for static analyzers
            raise ValueError("county release effective k is invalid")
    if observed_years != sorted(set(observed_years)):
        raise ValueError("county releases must be unique and ordered by year")


def canonical_fars_county_public_release_index_bytes(index: Mapping[str, object]) -> bytes:
    """Return canonical bytes for the sole client county-artifact allowlist."""

    validate_fars_county_public_release_index(index)
    return _canonical_json_bytes(index)


def load_fars_county_public_release_index_bytes(payload: bytes) -> dict[str, object]:
    """Load exact canonical county-index bytes with a bounded duplicate-key parser."""

    index = _strict_json(
        payload, label="county release index", maximum=FARS_COUNTY_PUBLIC_INDEX_MAX_BYTES
    )
    validate_fars_county_public_release_index(index)
    if canonical_fars_county_public_release_index_bytes(index) != payload:
        raise ValueError("county release index is not canonical")
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


def _verify_pin(root: Path, pin: Mapping[str, object], *, maximum: int, label: str) -> bytes:
    path, expected_bytes, expected_digest, _ = _pin(
        pin, label=label, maximum=maximum, value_pin="revision" in pin
    )
    payload = _bounded_regular_file(root / path, maximum=maximum, label=label)
    if len(payload) != expected_bytes or hashlib.sha256(payload).hexdigest() != expected_digest:
        raise ValueError(f"{label} does not match its index pin")
    return payload


def _correction_pins(ledger: Mapping[str, object]) -> list[tuple[Mapping[str, object], int, str]]:
    pins: list[tuple[Mapping[str, object], int, str]] = []
    for item in cast(list[object], ledger["corrections"]):
        correction = cast(Mapping[str, object], item)
        pins.extend(
            [
                (
                    cast(Mapping[str, object], correction["prior_value"]),
                    FARS_COUNTY_PUBLIC_ARTIFACT_MAX_BYTES,
                    "county retained prior value",
                ),
                (
                    cast(Mapping[str, object], correction["replacement_value"]),
                    FARS_COUNTY_PUBLIC_ARTIFACT_MAX_BYTES,
                    "county retained replacement value",
                ),
                (
                    cast(Mapping[str, object], correction["prior_boundary"]),
                    FARS_COUNTY_PUBLIC_BOUNDARY_MAX_BYTES,
                    "county retained prior boundary",
                ),
                (
                    cast(Mapping[str, object], correction["replacement_boundary"]),
                    FARS_COUNTY_PUBLIC_BOUNDARY_MAX_BYTES,
                    "county retained replacement boundary",
                ),
            ]
        )
    return pins


def verify_fars_county_public_release_directory(root: str | Path) -> dict[str, object]:
    """Verify a complete, pre-approved county release directory before site assembly.

    It is intentionally not wired into the public site yet: calling code must opt
    in only after a methods and publication review approves real county artifacts.
    """

    directory = Path(root)
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError("county release directory must be a real directory")
    index_payload = _bounded_regular_file(
        directory / FARS_COUNTY_PUBLIC_INDEX_FILENAME,
        maximum=FARS_COUNTY_PUBLIC_INDEX_MAX_BYTES,
        label="county release index",
    )
    index = load_fars_county_public_release_index_bytes(index_payload)
    ledger_pin = cast(Mapping[str, object], index["correction_ledger"])
    ledger_payload = _verify_pin(
        directory,
        ledger_pin,
        maximum=FARS_COUNTY_PUBLIC_INDEX_MAX_BYTES,
        label="county correction ledger",
    )
    ledger = load_fars_county_public_correction_ledger_bytes(ledger_payload)

    values: dict[str, bytes] = {}
    boundaries: dict[str, bytes] = {}
    active_paths = {FARS_COUNTY_PUBLIC_INDEX_FILENAME, FARS_COUNTY_PUBLIC_CORRECTIONS_FILENAME}
    for release_item in cast(list[object], index["releases"]):
        release = cast(Mapping[str, object], release_item)
        for state_item in cast(list[object], release["states"]):
            state = cast(Mapping[str, object], state_item)
            value_pin = cast(Mapping[str, object], state["value"])
            boundary_pin = cast(Mapping[str, object], state["boundary"])
            value_payload = _verify_pin(
                directory,
                value_pin,
                maximum=FARS_COUNTY_PUBLIC_ARTIFACT_MAX_BYTES,
                label="county value artifact",
            )
            boundary_payload = _verify_pin(
                directory,
                boundary_pin,
                maximum=FARS_COUNTY_PUBLIC_BOUNDARY_MAX_BYTES,
                label="county boundary artifact",
            )
            value_path = cast(str, value_pin["path"])
            boundary_path = cast(str, boundary_pin["path"])
            values[value_path] = value_payload
            boundaries[boundary_path] = boundary_payload
            active_paths |= {value_path, boundary_path}
    rebuilt = canonical_fars_county_public_release_index_bytes(
        build_fars_county_public_release_index(
            values, boundaries, ledger_payload, release_id=cast(str, index["release_id"])
        )
    )
    if rebuilt != index_payload:
        raise ValueError("county release index metadata drifted from its pinned artifacts")

    retained_paths: set[str] = set()
    for pin, maximum, label in _correction_pins(ledger):
        payload = _verify_pin(directory, pin, maximum=maximum, label=label)
        path = cast(str, pin["path"])
        retained_paths.add(path)
        if maximum == FARS_COUNTY_PUBLIC_ARTIFACT_MAX_BYTES:
            load_public_fars_county_state_bytes(payload)
        else:
            load_public_fars_county_boundary_state_bytes(payload)
    observed_paths = {
        path.relative_to(directory).as_posix()
        for path in directory.rglob("*")
        if (path.is_file() or path.is_symlink())
        and (
            _VALUE_PATH_RE.fullmatch(path.relative_to(directory).as_posix())
            or _BOUNDARY_PATH_RE.fullmatch(path.relative_to(directory).as_posix())
        )
    }
    if observed_paths != (active_paths | retained_paths) - {
        FARS_COUNTY_PUBLIC_INDEX_FILENAME,
        FARS_COUNTY_PUBLIC_CORRECTIONS_FILENAME,
    }:
        raise ValueError("county release directory contains missing or unindexed shard artifacts")
    return index


__all__ = [
    "FARS_COUNTY_PUBLIC_CORRECTIONS_ARTIFACT_TYPE",
    "FARS_COUNTY_PUBLIC_CORRECTIONS_FILENAME",
    "FARS_COUNTY_PUBLIC_CORRECTIONS_SCHEMA",
    "FARS_COUNTY_PUBLIC_CORRECTIONS_SCHEMA_VERSION",
    "FARS_COUNTY_PUBLIC_INDEX_ARTIFACT_TYPE",
    "FARS_COUNTY_PUBLIC_INDEX_FILENAME",
    "FARS_COUNTY_PUBLIC_INDEX_MAX_BYTES",
    "FARS_COUNTY_PUBLIC_INDEX_SCHEMA",
    "FARS_COUNTY_PUBLIC_INDEX_SCHEMA_VERSION",
    "build_fars_county_public_release_index",
    "canonical_fars_county_public_correction_ledger_bytes",
    "canonical_fars_county_public_release_index_bytes",
    "empty_fars_county_public_correction_ledger",
    "load_fars_county_public_correction_ledger_bytes",
    "load_fars_county_public_release_index_bytes",
    "validate_fars_county_public_correction_ledger",
    "validate_fars_county_public_release_index",
    "verify_fars_county_public_release_directory",
]
