# SPDX-License-Identifier: Apache-2.0
"""Deterministic packaging, activation, and verification for private FARS context.

The explicitly weaker audit-only entry point stores historically inspectable
candidates but does not attest current usability.  Production callers use the
full-history entry point, which requires the joined store, validates both chains
under the context lock, and returns post-activation current-usability evidence.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import io
import json
import math
import os
import re
import zipfile
from collections.abc import Mapping
from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, NoReturn, cast

from . import verified_outcomes as outcome_verifier
from .config import load_config_bytes
from .fars_context import (
    FARS_CONTEXT_MINIMUM_K,
    build_verified_fars_context,
    canonical_fars_context_bytes,
    fars_context_contract_descriptor,
    validate_fars_context_artifact,
)
from .ingestion import Clock, IngestionResult, run_ingestion
from .loaders import load_streets_bytes
from .verified_outcomes import (
    VerificationError,
    VerifiedJoinedOutcomeEvidence,
    _VerifiedJoinedSnapshot,
)

DEPENDENCY_PACKAGE_SCHEMA_VERSION = "1.0.0"
DEPENDENCY_PACKAGE_TYPE = "nearmiss.private.fars_context_dependencies"
MAX_DEPENDENCY_PACKAGE_BYTES = 64 * 1024 * 1024
MAX_NORMALIZED_CONTEXT_BYTES = 64 * 1024 * 1024
ACTIVATION_STATUS: Literal["historically_valid_potentially_stale"] = (
    "historically_valid_potentially_stale"
)

_MANIFEST_NAME = "manifest.json"
_CONFIG_ORIGINAL_NAME = "config.original"
_CONFIG_REPLAY_NAME = "config.replay.json"
_NETWORK_ORIGINAL_NAME = "network.original"
_ENTRY_ORDER = (
    _MANIFEST_NAME,
    _CONFIG_ORIGINAL_NAME,
    _CONFIG_REPLAY_NAME,
    _NETWORK_ORIGINAL_NAME,
)
_ENTRY_LIMITS = {
    _MANIFEST_NAME: 1024 * 1024,
    _CONFIG_ORIGINAL_NAME: 1024 * 1024,
    _CONFIG_REPLAY_NAME: 1024 * 1024,
    _NETWORK_ORIGINAL_NAME: 64 * 1024 * 1024,
}
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_SAFE_REF_RE = re.compile(r"^[\x21-\x7e]{1,256}$")
_REVIEW_KEYS = {
    "composition_review_reference",
    "methodology_change_review_reference",
    "privacy_regression_override_reference",
    "source_regression_override_reference",
    "quality_regression_override_reference",
}
_MANIFEST_KEYS = {
    "schema_version",
    "package_type",
    "city_key",
    "source_reference",
    "dependency_reference",
    "replay",
    "reviews",
    "policy",
}
_COMPOSITION_FIELDS = (
    ("city_key",),
    ("input_lineage", "config_raw_sha256"),
    ("input_lineage", "network_raw_sha256"),
    ("input_lineage", "network_canonical_sha256"),
)
_SOURCE_COUNT_FIELDS = (
    "crash_records_read",
    "crash_records_accepted",
    "person_records_read",
    "person_records_accepted",
    "cases_joined",
)
_SOURCE_ADVERSE_FIELDS = (
    "crash_records_rejected",
    "person_records_excluded",
    "cases_excluded",
)
_ACCOUNTING_PROTECTED_FIELDS = (
    "records_received",
    "records_in_window",
    "uniquely_snapped_crashes",
    "uniquely_snapped_timed_crashes",
    "positive_candidate_cell_count",
    "eligible_cell_count",
    "crash_contribution_total",
    "eligible_crash_contribution_total",
)
_ACCOUNTING_ADVERSE_FIELDS = (
    "records_outside_window",
    "ambiguous_crashes",
    "unsnapped_crashes",
    "uniquely_snapped_unknown_time_crashes",
    "suppressed_positive_cell_count",
    "suppressed_crash_contribution_total",
)
_CONTEXT_PROOF_TOKEN = object()


@dataclass(frozen=True)
class _DependencyPackage:
    manifest: Mapping[str, object]
    original_config: bytes
    replay_config: bytes
    original_network: bytes


@dataclass(frozen=True)
class FarsContextAuditActivation:
    """Atomic storage result that deliberately does not attest current usability."""

    ingestion: IngestionResult
    status: Literal["historically_valid_potentially_stale"] = ACTIVATION_STATUS
    specialized_verifier_required: bool = True


@dataclass(frozen=True)
class FarsContextFullHistoryActivation:
    """Production activation plus post-commit current-usability evidence."""

    activation: FarsContextAuditActivation
    evidence: VerifiedFarsContextEvidence


@dataclass(frozen=True, init=False)
class VerifiedFarsContextEvidence:
    """Safe metadata verified at one explicit observation or activation boundary."""

    source_id: str
    city_key: str
    attempt_id: str
    raw_sha256: str
    normalized_sha256: str
    effective_k: int
    eligible_cell_count: int
    joined_source: VerifiedJoinedOutcomeEvidence
    status: Literal["verified_at_observation", "verified_at_activation"]

    def __init__(
        self,
        *,
        source_id: str,
        city_key: str,
        attempt_id: str,
        raw_sha256: str,
        normalized_sha256: str,
        effective_k: int,
        eligible_cell_count: int,
        joined_source: VerifiedJoinedOutcomeEvidence,
        status: Literal["verified_at_observation", "verified_at_activation"],
        _proof_token: object,
    ) -> None:
        caps = cast(Mapping[str, int], fars_context_contract_descriptor()["caps"])
        try:
            expected_source_id = context_source_id(city_key)
        except ValueError:
            expected_source_id = ""
        if (
            _proof_token is not _CONTEXT_PROOF_TOKEN
            or source_id != expected_source_id
            or not isinstance(attempt_id, str)
            or outcome_verifier._SAFE_ATTEMPT_ID.fullmatch(attempt_id) is None
            or not isinstance(raw_sha256, str)
            or _SHA256_RE.fullmatch(raw_sha256) is None
            or not isinstance(normalized_sha256, str)
            or _SHA256_RE.fullmatch(normalized_sha256) is None
            or isinstance(effective_k, bool)
            or not isinstance(effective_k, int)
            or not FARS_CONTEXT_MINIMUM_K <= effective_k <= caps["max_records"]
            or isinstance(eligible_cell_count, bool)
            or not isinstance(eligible_cell_count, int)
            or not 0 <= eligible_cell_count <= caps["max_cells"]
            or type(joined_source) is not VerifiedJoinedOutcomeEvidence
            or joined_source.source_id != "fars-joined"
            or status not in {"verified_at_observation", "verified_at_activation"}
        ):
            raise VerificationError("verified FARS context evidence requires an internal proof")
        values: dict[str, object] = {
            "source_id": source_id,
            "city_key": city_key,
            "attempt_id": attempt_id,
            "raw_sha256": raw_sha256,
            "normalized_sha256": normalized_sha256,
            "effective_k": effective_k,
            "eligible_cell_count": eligible_cell_count,
            "joined_source": joined_source,
            "status": status,
        }
        for name, value in values.items():
            object.__setattr__(self, name, value)

    def as_dict(self) -> dict[str, object]:
        """Return only aggregate-safe context and joined-source evidence."""

        return {
            "source_id": self.source_id,
            "city_key": self.city_key,
            "attempt_id": self.attempt_id,
            "raw_sha256": self.raw_sha256,
            "normalized_sha256": self.normalized_sha256,
            "effective_k": self.effective_k,
            "eligible_cell_count": self.eligible_cell_count,
            "joined_source": self.joined_source.as_dict(),
            "status": self.status,
        }


@dataclass(frozen=True)
class _JoinedHistoryReference:
    evidence: VerifiedJoinedOutcomeEvidence
    completed_at: dt.datetime


def _canonical(value: object) -> bytes:
    try:
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
    except UnicodeEncodeError:
        raise ValueError("FARS context dependency text must use Unicode scalar values") from None


def _reject_constant(_value: str) -> NoReturn:
    raise ValueError("FARS context dependency JSON contains a non-finite number")


def _strict_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("FARS context dependency JSON contains a duplicate key")
        result[key] = value
    return result


def _strict_json(payload: bytes, label: str) -> Mapping[str, object]:
    try:
        value: object = json.loads(
            payload.decode("utf-8", errors="strict"),
            object_pairs_hook=_strict_object,
            parse_constant=_reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ValueError(f"{label} is not strict JSON") from exc
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be a JSON object")
    return cast(Mapping[str, object], value)


def _exact_bytes(value: object, label: str, maximum: int) -> bytes:
    if type(value) is not bytes:
        raise TypeError(f"{label} must be exact immutable bytes")
    payload = value
    if not 0 < len(payload) <= maximum:
        raise ValueError(f"{label} is outside its byte safety limit")
    return payload


def _review_reference(value: object, label: str) -> str | None:
    if value is None:
        return None
    if (
        not isinstance(value, str)
        or _SAFE_REF_RE.fullmatch(value) is None
        or value != value.strip()
        or any(0xD800 <= ord(character) <= 0xDFFF for character in value)
    ):
        raise ValueError(f"{label} must be a nonempty safe review reference")
    return value


def _source_reference(snapshot: _VerifiedJoinedSnapshot) -> dict[str, object]:
    if type(snapshot) is not _VerifiedJoinedSnapshot:
        raise TypeError("FARS context activation requires a proof-bound joined snapshot")
    return dict(snapshot.evidence.as_dict())


def _config_format(path: str | Path) -> str:
    return "json" if Path(path).suffix.lower() == ".json" else "toml"


def _replay_config(original: bytes, config_format: str) -> tuple[bytes, str]:
    config = load_config_bytes(Path(f"operator.{config_format}"), original)
    if config.window_start is None or config.window_end is None:
        raise ValueError("FARS context activation requires both exact window bounds")
    sanitized: dict[str, object] = {
        "city": config.city,
        "streets": "network.original",
        "reports": "redacted.json",
        "exposure": "redacted.json",
        # Bind every exact original-config change into the replay-config hash
        # without exposing any original path or value outside the private ZIP.
        "dataset_note": f"original-config-sha256:{hashlib.sha256(original).hexdigest()}",
        "window": {"start": config.window_start, "end": config.window_end},
        "thresholds": {"min_publish_n": config.min_publish_n},
    }
    if config.ref_lat is not None:
        sanitized["ref_lat"] = config.ref_lat
    if config.ref_lon is not None:
        sanitized["ref_lon"] = config.ref_lon
    return _canonical(sanitized), config.city


def _zip_info(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_STORED
    info.create_system = 3
    info.external_attr = 0o100400 << 16
    return info


def _canonical_zip(entries: Mapping[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_STORED) as archive:
        for name in _ENTRY_ORDER:
            archive.writestr(_zip_info(name), entries[name])
    payload = buffer.getvalue()
    if len(payload) > MAX_DEPENDENCY_PACKAGE_BYTES:
        raise ValueError("FARS context dependency package exceeds its byte safety limit")
    return payload


def _dependency_reference(
    original_config: bytes,
    replay_config: bytes,
    original_network: bytes,
    config_format: str,
) -> dict[str, object]:
    return {
        "original_config_format": config_format,
        "original_config_sha256": hashlib.sha256(original_config).hexdigest(),
        "original_config_byte_count": len(original_config),
        "replay_config_sha256": hashlib.sha256(replay_config).hexdigest(),
        "replay_config_byte_count": len(replay_config),
        "original_network_sha256": hashlib.sha256(original_network).hexdigest(),
        "original_network_byte_count": len(original_network),
    }


def _reviews(
    composition: str | None,
    methodology: str | None,
    privacy: str | None,
    source: str | None,
    quality: str | None,
) -> dict[str, object]:
    return {
        "composition_review_reference": _review_reference(
            composition, "composition_review_reference"
        ),
        "methodology_change_review_reference": _review_reference(
            methodology, "methodology_change_review_reference"
        ),
        "privacy_regression_override_reference": _review_reference(
            privacy, "privacy_regression_override_reference"
        ),
        "source_regression_override_reference": _review_reference(
            source, "source_regression_override_reference"
        ),
        "quality_regression_override_reference": _review_reference(
            quality, "quality_regression_override_reference"
        ),
    }


def build_dependency_package(
    snapshot: _VerifiedJoinedSnapshot,
    *,
    config_path: str | Path,
    config_bytes: bytes,
    network_bytes: bytes,
    fars_snap_max_m: float,
    ambiguity_margin_m: float,
    composition_review_reference: str | None = None,
    methodology_change_review_reference: str | None = None,
    privacy_regression_override_reference: str | None = None,
    source_regression_override_reference: str | None = None,
    quality_regression_override_reference: str | None = None,
) -> bytes:
    """Package exact private inputs plus a regenerated, closed replay config."""

    original_config = _exact_bytes(config_bytes, "config bytes", 1024 * 1024)
    original_network = _exact_bytes(network_bytes, "network bytes", 64 * 1024 * 1024)
    load_streets_bytes(Path("network.original"), original_network)
    config_format = _config_format(config_path)
    replay_config, city = _replay_config(original_config, config_format)
    for value, label, positive in (
        (fars_snap_max_m, "fars_snap_max_m", True),
        (ambiguity_margin_m, "ambiguity_margin_m", False),
    ):
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
            or (float(value) <= 0 if positive else float(value) < 0)
        ):
            raise ValueError(f"{label} is outside its supported range")
    manifest: dict[str, object] = {
        "schema_version": DEPENDENCY_PACKAGE_SCHEMA_VERSION,
        "package_type": DEPENDENCY_PACKAGE_TYPE,
        "city_key": city,
        "source_reference": _source_reference(snapshot),
        "dependency_reference": _dependency_reference(
            original_config, replay_config, original_network, config_format
        ),
        "replay": {
            "fars_snap_max_m": float(fars_snap_max_m),
            "ambiguity_margin_m": float(ambiguity_margin_m),
        },
        "reviews": _reviews(
            composition_review_reference,
            methodology_change_review_reference,
            privacy_regression_override_reference,
            source_regression_override_reference,
            quality_regression_override_reference,
        ),
        "policy": {
            "activation_status": ACTIVATION_STATUS,
            "specialized_full_history_verifier_required": True,
            "original_config_visibility": "private_raw_replay_only",
            "original_network_visibility": "public",
            "normalized_visibility": "private_eligible_aggregates_only",
        },
    }
    entries = {
        _MANIFEST_NAME: _canonical(manifest),
        _CONFIG_ORIGINAL_NAME: original_config,
        _CONFIG_REPLAY_NAME: replay_config,
        _NETWORK_ORIGINAL_NAME: original_network,
    }
    payload = _canonical_zip(entries)
    _parse_package(payload)
    return payload


def _read_zip_entries(payload: bytes) -> dict[str, bytes]:
    try:
        with zipfile.ZipFile(io.BytesIO(payload), "r") as archive:
            members = archive.infolist()
            if tuple(member.filename for member in members) != _ENTRY_ORDER:
                raise ValueError("FARS context dependency ZIP members are invalid")
            if archive.comment:
                raise ValueError("FARS context dependency ZIP metadata is invalid")
            if any(
                member.is_dir()
                or member.flag_bits & 0x1
                or member.compress_type != zipfile.ZIP_STORED
                or member.file_size != member.compress_size
                or member.date_time != (1980, 1, 1, 0, 0, 0)
                or member.create_system != 3
                or member.external_attr != 0o100400 << 16
                or member.extra
                or member.comment
                for member in members
            ):
                raise ValueError("FARS context dependency ZIP encoding is invalid")
            if sum(member.file_size for member in members) > MAX_DEPENDENCY_PACKAGE_BYTES:
                raise ValueError("FARS context dependency ZIP expands beyond its safety limit")
            if any(
                member.file_size < 1 or member.file_size > _ENTRY_LIMITS[member.filename]
                for member in members
            ):
                raise ValueError("FARS context dependency ZIP entry exceeds its safety limit")
            return {member.filename: archive.read(member) for member in members}
    except (zipfile.BadZipFile, RuntimeError, OSError):
        raise ValueError("FARS context dependency package is not a safe ZIP") from None


def _validate_manifest(manifest: Mapping[str, object]) -> None:  # noqa: C901
    if set(manifest) != _MANIFEST_KEYS:
        raise ValueError("FARS context dependency manifest shape is invalid")
    if (
        manifest["schema_version"] != DEPENDENCY_PACKAGE_SCHEMA_VERSION
        or manifest["package_type"] != DEPENDENCY_PACKAGE_TYPE
    ):
        raise ValueError("FARS context dependency package contract is unsupported")
    city_key = manifest["city_key"]
    if not isinstance(city_key, str) or not city_key or city_key != city_key.strip():
        raise ValueError("FARS context dependency city identity is invalid")
    context_source_id(city_key)
    source = manifest["source_reference"]
    if not isinstance(source, Mapping) or set(source) != set(
        VerifiedJoinedOutcomeEvidence.__dataclass_fields__
    ):
        raise ValueError("FARS context dependency source reference is invalid")
    try:
        VerifiedJoinedOutcomeEvidence(
            **source,
            _proof_token=outcome_verifier._JOINED_PROOF_TOKEN,
        )
    except VerificationError:
        raise ValueError("FARS context dependency source reference is invalid") from None
    replay = manifest["replay"]
    if not isinstance(replay, Mapping) or set(replay) != {
        "fars_snap_max_m",
        "ambiguity_margin_m",
    }:
        raise ValueError("FARS context dependency replay block is invalid")
    for key, positive in (("fars_snap_max_m", True), ("ambiguity_margin_m", False)):
        value = replay[key]
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
            or (float(value) <= 0 if positive else float(value) < 0)
        ):
            raise ValueError("FARS context dependency replay block is invalid")
    reviews = manifest["reviews"]
    if not isinstance(reviews, Mapping) or set(reviews) != _REVIEW_KEYS:
        raise ValueError("FARS context dependency review block is invalid")
    for key in _REVIEW_KEYS:
        _review_reference(reviews[key], key)
    present_reviews = [value for value in reviews.values() if value is not None]
    if len(present_reviews) != len(set(present_reviews)):
        raise ValueError("FARS context review references must be distinct by category")
    policy = manifest["policy"]
    if policy != {
        "activation_status": ACTIVATION_STATUS,
        "specialized_full_history_verifier_required": True,
        "original_config_visibility": "private_raw_replay_only",
        "original_network_visibility": "public",
        "normalized_visibility": "private_eligible_aggregates_only",
    }:
        raise ValueError("FARS context dependency policy is invalid")


def _validate_linked_entries(package: _DependencyPackage) -> None:
    reference = package.manifest["dependency_reference"]
    if not isinstance(reference, Mapping) or set(reference) != {
        "original_config_format",
        "original_config_sha256",
        "original_config_byte_count",
        "replay_config_sha256",
        "replay_config_byte_count",
        "original_network_sha256",
        "original_network_byte_count",
    }:
        raise ValueError("FARS context dependency reference is invalid")
    for key, payload in (
        ("original_config", package.original_config),
        ("replay_config", package.replay_config),
        ("original_network", package.original_network),
    ):
        digest_value = reference[f"{key}_sha256"]
        byte_count = reference[f"{key}_byte_count"]
        if not isinstance(digest_value, str) or _SHA256_RE.fullmatch(digest_value) is None:
            raise ValueError("FARS context dependency reference is invalid")
        if isinstance(byte_count, bool) or not isinstance(byte_count, int) or byte_count < 1:
            raise ValueError("FARS context dependency reference is invalid")
        if digest_value != hashlib.sha256(payload).hexdigest():
            raise ValueError("FARS context dependency entry hash mismatch")
        if byte_count != len(payload):
            raise ValueError("FARS context dependency entry length mismatch")
    config_format = reference["original_config_format"]
    if config_format not in {"json", "toml"}:
        raise ValueError("FARS context original config format is invalid")
    regenerated, city = _replay_config(package.original_config, cast(str, config_format))
    if regenerated != package.replay_config or city != package.manifest["city_key"]:
        raise ValueError("sanitized replay config does not match exact original config")


def _parse_package(payload: bytes) -> _DependencyPackage:
    exact = _exact_bytes(payload, "dependency package", MAX_DEPENDENCY_PACKAGE_BYTES)
    entries = _read_zip_entries(exact)
    if _canonical_zip(entries) != exact:
        raise ValueError("FARS context dependency package encoding is not canonical")
    manifest = _strict_json(entries[_MANIFEST_NAME], "FARS context dependency manifest")
    if entries[_MANIFEST_NAME] != _canonical(manifest):
        raise ValueError("FARS context dependency manifest encoding is not canonical")
    _validate_manifest(manifest)
    package = _DependencyPackage(
        manifest,
        entries[_CONFIG_ORIGINAL_NAME],
        entries[_CONFIG_REPLAY_NAME],
        entries[_NETWORK_ORIGINAL_NAME],
    )
    _validate_linked_entries(package)
    return package


def _normalize(package_bytes: bytes, snapshot: _VerifiedJoinedSnapshot) -> bytes:
    package = _parse_package(package_bytes)
    if package.manifest["source_reference"] != _source_reference(snapshot):
        raise ValueError("dependency package source reference does not match verified snapshot")
    replay = package.manifest["replay"]
    if not isinstance(replay, Mapping):
        raise ValueError("FARS context dependency replay block is invalid")
    artifact = build_verified_fars_context(
        snapshot,
        config_path=Path("config.replay.json"),
        config_bytes=package.replay_config,
        network_bytes=package.original_network,
        fars_snap_max_m=cast(float, replay["fars_snap_max_m"]),
        ambiguity_margin_m=cast(float, replay["ambiguity_margin_m"]),
    )
    return canonical_fars_context_bytes(artifact)


def _artifact(payload: bytes) -> Mapping[str, object]:
    value = _strict_json(payload, "FARS context artifact")
    validate_fars_context_artifact(value)
    if canonical_fars_context_bytes(value) != payload:
        raise ValueError("FARS context artifact is not canonical")
    return value


def _nested(value: Mapping[str, object], path: tuple[str, ...]) -> object:
    current: object = value
    for key in path:
        if not isinstance(current, Mapping):
            raise ValueError("FARS context comparison path is invalid")
        current = current[key]
    return current


def _has_reference(package: _DependencyPackage, key: str) -> bool:
    reviews = cast(Mapping[str, object], package.manifest["reviews"])
    return _review_reference(reviews[key], key) is not None


def _source_rollback(candidate: Mapping[str, object], previous: Mapping[str, object]) -> bool:
    current = cast(Mapping[str, object], candidate["source_lineage"])
    prior = cast(Mapping[str, object], previous["source_lineage"])
    ranks = {"preliminary": 0, "final": 1}
    if ranks[cast(str, current["release_status"])] < ranks[cast(str, prior["release_status"])]:
        return True
    protected_decreased = any(
        cast(int, current[key]) < cast(int, prior[key]) for key in _SOURCE_COUNT_FIELDS
    )
    adverse_increased = any(
        cast(int, current[key]) > cast(int, prior[key]) for key in _SOURCE_ADVERSE_FIELDS
    )
    return protected_decreased or adverse_increased


def _accounting_regressed(candidate: Mapping[str, object], previous: Mapping[str, object]) -> bool:
    current = cast(Mapping[str, object], candidate["accounting"])
    prior = cast(Mapping[str, object], previous["accounting"])
    protected_decreased = any(
        cast(int, current[key]) < cast(int, prior[key]) for key in _ACCOUNTING_PROTECTED_FIELDS
    )
    adverse_increased = any(
        cast(int, current[key]) > cast(int, prior[key]) for key in _ACCOUNTING_ADVERSE_FIELDS
    )
    return protected_decreased or adverse_increased


def _cells_decreased(candidate: Mapping[str, object], previous: Mapping[str, object]) -> bool:
    def cells(artifact: Mapping[str, object]) -> dict[tuple[str, str, str], int]:
        values = cast(list[Mapping[str, object]], artifact["cells"])
        return {
            (
                cast(str, value["segment_id"]),
                cast(str, value["part_of_day"]),
                cast(str, value["involved_mode"]),
            ): cast(int, value["crash_count"])
            for value in values
        }

    current, prior = cells(candidate), cells(previous)
    return any(current.get(key, 0) < count for key, count in prior.items())


def _methodology_changed(candidate: Mapping[str, object], previous: Mapping[str, object]) -> bool:
    current = dict(cast(Mapping[str, object], candidate["method"]))
    prior = dict(cast(Mapping[str, object], previous["method"]))
    current_privacy = dict(cast(Mapping[str, object], current["privacy"]))
    prior_privacy = dict(cast(Mapping[str, object], prior["privacy"]))
    for key in ("requested_k", "effective_k"):
        current_privacy.pop(key, None)
        prior_privacy.pop(key, None)
    current["privacy"] = current_privacy
    prior["privacy"] = prior_privacy
    return current != prior


def _privacy_regressed(candidate: Mapping[str, object], previous: Mapping[str, object]) -> bool:
    current_method = cast(Mapping[str, object], candidate["method"])
    prior_method = cast(Mapping[str, object], previous["method"])
    current = cast(Mapping[str, object], current_method["privacy"])
    prior = cast(Mapping[str, object], prior_method["privacy"])
    return any(
        cast(int, current[key]) < cast(int, prior[key]) for key in ("requested_k", "effective_k")
    )


def _validate_candidate(
    candidate_bytes: bytes,
    previous_bytes: bytes | None,
    package_bytes: bytes,
    snapshot: _VerifiedJoinedSnapshot,
) -> None:
    package = _parse_package(package_bytes)
    if _normalize(package_bytes, snapshot) != candidate_bytes:
        raise ValueError("candidate artifact is not linked to its dependency package")
    candidate = _artifact(candidate_bytes)
    if previous_bytes is None:
        return
    previous = _artifact(previous_bytes)
    if candidate_bytes == previous_bytes:
        return
    composition_changed = any(
        _nested(candidate, path) != _nested(previous, path) for path in _COMPOSITION_FIELDS
    )
    if composition_changed and not _has_reference(package, "composition_review_reference"):
        raise ValueError("context composition changed without a composition review reference")
    if _methodology_changed(candidate, previous) and not _has_reference(
        package, "methodology_change_review_reference"
    ):
        raise ValueError("context methodology changed without a methodology review reference")
    if _privacy_regressed(candidate, previous) and not _has_reference(
        package, "privacy_regression_override_reference"
    ):
        raise ValueError("context privacy regression requires an explicit override reference")
    if _source_rollback(candidate, previous) and not _has_reference(
        package, "source_regression_override_reference"
    ):
        raise ValueError("context source rollback requires an explicit override reference")
    if (
        _accounting_regressed(candidate, previous) or _cells_decreased(candidate, previous)
    ) and not _has_reference(package, "quality_regression_override_reference"):
        raise ValueError("context quality regression requires an explicit override reference")


@dataclass(frozen=True)
class _VerifiedContextGeneration:
    receipt: outcome_verifier._ReceiptRecord
    package: _DependencyPackage
    artifact: Mapping[str, object]
    normalized_bytes: bytes
    joined: _JoinedHistoryReference


def _context_fail(message: str) -> NoReturn:
    raise VerificationError(message)


def _joined_reference_for_package(
    package: _DependencyPackage,
    joined_history: Mapping[str, _JoinedHistoryReference],
) -> _JoinedHistoryReference:
    source_reference = package.manifest["source_reference"]
    if not isinstance(source_reference, Mapping):
        _context_fail("FARS context joined-source reference is invalid")
    attempt_id = source_reference.get("attempt_id")
    if not isinstance(attempt_id, str):
        _context_fail("FARS context joined-source reference is invalid")
    reference = joined_history.get(attempt_id)
    if reference is None or source_reference != reference.evidence.as_dict():
        _context_fail("FARS context joined-source reference is not verified")
    return reference


def _joined_snapshot_for_reference(
    reference: _JoinedHistoryReference,
    normalized_hashes: int,
    active: outcome_verifier._VerifiedGeneration,
) -> _VerifiedJoinedSnapshot:
    if (
        active.receipt.attempt_id == reference.evidence.attempt_id
        and active.normalized_bytes is not None
    ):
        normalized = active.normalized_bytes
    else:
        digest = reference.evidence.normalized_sha256
        normalized, observed = outcome_verifier._read_file(
            normalized_hashes,
            f"{digest}.bin",
            maximum=outcome_verifier._MAX_JOINED_NORMALIZED_BYTES,
        )
        if observed != digest:
            _context_fail("FARS context historical joined artifact hash mismatch")
    return _VerifiedJoinedSnapshot(
        evidence=reference.evidence,
        normalized_bytes=normalized,
        _proof_token=outcome_verifier._JOINED_SNAPSHOT_PROOF_TOKEN,
    )


def _verify_context_generation(
    receipt: outcome_verifier._ReceiptRecord,
    raw_hashes: int,
    normalized_hashes: int,
    joined_normalized_hashes: int,
    joined_history: Mapping[str, _JoinedHistoryReference],
    active_joined: outcome_verifier._VerifiedGeneration,
    previous_bytes: bytes | None,
    expected_city_key: str,
    expected_source_id: str,
) -> _VerifiedContextGeneration:
    raw_digest = cast(str, receipt.receipt["raw_sha256"])
    normalized_digest = cast(str, receipt.receipt["normalized_sha256"])
    raw, observed_raw = outcome_verifier._read_file(
        raw_hashes,
        f"{raw_digest}.bin",
        maximum=MAX_DEPENDENCY_PACKAGE_BYTES,
    )
    if observed_raw != raw_digest:
        _context_fail("FARS context dependency artifact hash mismatch")
    normalized, observed_normalized = outcome_verifier._read_file(
        normalized_hashes,
        f"{normalized_digest}.bin",
        maximum=MAX_NORMALIZED_CONTEXT_BYTES,
    )
    if observed_normalized != normalized_digest:
        _context_fail("FARS context normalized artifact hash mismatch")
    try:
        package = _parse_package(raw)
        package_city = package.manifest["city_key"]
        if (
            package_city != expected_city_key
            or not isinstance(package_city, str)
            or context_source_id(package_city) != expected_source_id
        ):
            _context_fail("FARS context historical city identity is invalid")
        joined = _joined_reference_for_package(package, joined_history)
        if (
            receipt.completed_at is None
            or receipt.started_at < joined.completed_at
            or receipt.completed_at < joined.completed_at
        ):
            _context_fail("FARS context predates its referenced joined generation")
        snapshot = _joined_snapshot_for_reference(joined, joined_normalized_hashes, active_joined)
        _validate_candidate(normalized, previous_bytes, raw, snapshot)
        artifact = _artifact(normalized)
        if artifact["city_key"] != expected_city_key:
            _context_fail("FARS context historical city identity is invalid")
    except VerificationError:
        raise
    except (KeyError, OSError, TypeError, ValueError):
        _context_fail("FARS context deterministic replay failed")
    return _VerifiedContextGeneration(receipt, package, artifact, normalized, joined)


def _verify_context_chain(
    receipts: list[outcome_verifier._ReceiptRecord],
    raw_hashes: int,
    normalized_hashes: int,
    joined_normalized_hashes: int,
    joined_history: Mapping[str, _JoinedHistoryReference],
    active_joined: outcome_verifier._VerifiedGeneration,
    expected_city_key: str,
    expected_source_id: str,
) -> _VerifiedContextGeneration:
    previous: _VerifiedContextGeneration | None = None
    seen_normalized: set[str] = set()
    for receipt in receipts:
        expected_previous = (
            None if previous is None else previous.receipt.receipt["normalized_sha256"]
        )
        if receipt.receipt["previous_normalized_sha256"] != expected_previous:
            _context_fail("FARS context predecessor link is invalid")
        normalized_digest = cast(str, receipt.receipt["normalized_sha256"])
        if (
            previous is not None
            and normalized_digest != previous.receipt.receipt["normalized_sha256"]
            and normalized_digest in seen_normalized
        ):
            _context_fail("FARS context reused an older normalized generation")
        generation = _verify_context_generation(
            receipt,
            raw_hashes,
            normalized_hashes,
            joined_normalized_hashes,
            joined_history,
            active_joined,
            None if previous is None else previous.normalized_bytes,
            expected_city_key,
            expected_source_id,
        )
        seen_normalized.add(normalized_digest)
        previous = generation
    if previous is None:
        _context_fail("FARS context receipt history has no successful receipt")
    return previous


def _context_lock_present(source: int) -> None:
    try:
        metadata = os.stat(".ingestion.lock", dir_fd=source, follow_symlinks=False)
    except OSError:
        _context_fail("FARS context ingestion lock is not held")
    outcome_verifier._validate_metadata(metadata, directory=True)


def _reject_orphan_success_history(source: int, *, source_id: str) -> None:
    try:
        os.stat("receipts", dir_fd=source, follow_symlinks=False)
    except FileNotFoundError:
        return
    except OSError:
        _context_fail("FARS context receipt history preflight failed")
    receipts = outcome_verifier._open_directory(source, "receipts")
    try:
        if any(
            receipt.receipt["status"] == "success"
            for receipt in outcome_verifier._scan_receipts(receipts, expected_source_id=source_id)
        ):
            _context_fail("FARS context active marker is missing from successful history")
    finally:
        os.close(receipts)


def _verify_active_fars_context_history(  # noqa: C901
    root: str | Path,
    city_key: str,
    *,
    joined_root: str | Path | None = None,
    require_current_joined: bool,
    context_lock_required: bool,
    candidate_normalized: bytes | None = None,
    candidate_package_bytes: bytes | None = None,
    candidate_started_at: str | None = None,
) -> VerifiedFarsContextEvidence:
    source_id = context_source_id(city_key)
    outcome_verifier._require_posix_filesystem_support()
    with ExitStack() as stack:
        context_root_fd = outcome_verifier._open_root(root)
        stack.callback(os.close, context_root_fd)
        if joined_root is None:
            joined_root_fd = context_root_fd
        else:
            joined_root_fd = outcome_verifier._open_root(joined_root)
            stack.callback(os.close, joined_root_fd)

        context_source_fd = outcome_verifier._open_directory(context_root_fd, source_id)
        stack.callback(os.close, context_source_fd)
        joined_source_fd = outcome_verifier._open_directory(joined_root_fd, "fars-joined")
        stack.callback(os.close, joined_source_fd)
        if context_lock_required:
            _context_lock_present(context_source_fd)
        else:
            outcome_verifier._lock_absent(context_source_fd)
        outcome_verifier._lock_absent(joined_source_fd)

        context_raw_fd = outcome_verifier._open_directory(context_source_fd, "raw")
        stack.callback(os.close, context_raw_fd)
        context_raw_hashes_fd = outcome_verifier._open_directory(context_raw_fd, "sha256")
        stack.callback(os.close, context_raw_hashes_fd)
        context_normalized_fd = outcome_verifier._open_directory(context_source_fd, "normalized")
        stack.callback(os.close, context_normalized_fd)
        context_normalized_hashes_fd = outcome_verifier._open_directory(
            context_normalized_fd, "sha256"
        )
        stack.callback(os.close, context_normalized_hashes_fd)
        context_receipts_fd = outcome_verifier._open_directory(context_source_fd, "receipts")
        stack.callback(os.close, context_receipts_fd)

        joined_raw_fd = outcome_verifier._open_directory(joined_source_fd, "raw")
        stack.callback(os.close, joined_raw_fd)
        joined_raw_hashes_fd = outcome_verifier._open_directory(joined_raw_fd, "sha256")
        stack.callback(os.close, joined_raw_hashes_fd)
        joined_normalized_fd = outcome_verifier._open_directory(joined_source_fd, "normalized")
        stack.callback(os.close, joined_normalized_fd)
        joined_normalized_hashes_fd = outcome_verifier._open_directory(
            joined_normalized_fd, "sha256"
        )
        stack.callback(os.close, joined_normalized_hashes_fd)
        joined_receipts_fd = outcome_verifier._open_directory(joined_source_fd, "receipts")
        stack.callback(os.close, joined_receipts_fd)

        context_current_bytes, context_current_digest = outcome_verifier._read_file(
            context_normalized_fd,
            "current.json",
            maximum=outcome_verifier._MAX_RECEIPT_BYTES,
        )
        context_current = outcome_verifier._parse_receipt(
            context_current_bytes, expected_source_id=source_id
        )
        outcome_verifier._active_success(context_current.receipt)
        joined_current_bytes, joined_current_digest = outcome_verifier._read_file(
            joined_normalized_fd,
            "current.json",
            maximum=outcome_verifier._MAX_RECEIPT_BYTES,
        )
        joined_current = outcome_verifier._parse_receipt(
            joined_current_bytes, expected_source_id="fars-joined"
        )
        outcome_verifier._active_success(joined_current.receipt)

        context_successes = outcome_verifier._ordered_successes(
            context_current,
            outcome_verifier._scan_receipts(context_receipts_fd, expected_source_id=source_id),
        )
        if candidate_normalized is not None:
            candidate_digest = hashlib.sha256(candidate_normalized).hexdigest()
            latest_digest = cast(str, context_successes[-1].receipt["normalized_sha256"])
            if candidate_digest != latest_digest and any(
                record.receipt["normalized_sha256"] == candidate_digest
                for record in context_successes[:-1]
            ):
                _context_fail("FARS context candidate reuses an older normalized generation")
        joined_successes = outcome_verifier._ordered_successes(
            joined_current,
            outcome_verifier._scan_receipts(joined_receipts_fd, expected_source_id="fars-joined"),
        )

        joined_history: dict[str, _JoinedHistoryReference] = {}

        def observe_joined(generation: outcome_verifier._VerifiedGeneration) -> None:
            completed_at = generation.receipt.completed_at
            if completed_at is None:
                _context_fail("FARS context joined-source chronology is invalid")
            evidence = outcome_verifier._joined_evidence_from(
                generation.receipt, generation.artifact
            )
            if evidence.attempt_id in joined_history:
                _context_fail("FARS context joined-source history is ambiguous")
            joined_history[evidence.attempt_id] = _JoinedHistoryReference(evidence, completed_at)

        active_joined = outcome_verifier._verify_joined_chain(
            joined_successes,
            joined_raw_hashes_fd,
            joined_normalized_hashes_fd,
            observe_generation=observe_joined,
        )
        if active_joined.receipt.attempt_id != joined_current.attempt_id:
            _context_fail("FARS context joined-source active generation is invalid")
        if candidate_package_bytes is not None or candidate_started_at is not None:
            if candidate_package_bytes is None or candidate_started_at is None:
                _context_fail("FARS context history candidate metadata is incomplete")
            try:
                candidate_package = _parse_package(candidate_package_bytes)
                if candidate_package.manifest["city_key"] != city_key:
                    _context_fail("FARS context candidate city identity is invalid")
                candidate_joined = _joined_reference_for_package(candidate_package, joined_history)
                candidate_start = outcome_verifier._timestamp(candidate_started_at)
            except VerificationError:
                raise
            except (KeyError, TypeError, ValueError):
                _context_fail("FARS context history candidate metadata is invalid")
            if candidate_start < candidate_joined.completed_at:
                _context_fail("FARS context candidate predates its joined generation")
            active_candidate_joined = joined_history[joined_current.attempt_id]
            if candidate_joined.evidence != active_candidate_joined.evidence:
                _context_fail("FARS context candidate joined-source reference is stale")
        active_context = _verify_context_chain(
            context_successes,
            context_raw_hashes_fd,
            context_normalized_hashes_fd,
            joined_normalized_hashes_fd,
            joined_history,
            active_joined,
            city_key,
            source_id,
        )
        if active_context.receipt.attempt_id != context_current.attempt_id:
            _context_fail("FARS context active generation is invalid")
        active_joined_reference = joined_history[joined_current.attempt_id]
        if (
            require_current_joined
            and active_context.joined.evidence != active_joined_reference.evidence
        ):
            _context_fail("FARS context active joined-source reference is stale")
        if active_context.artifact["city_key"] != city_key:
            _context_fail("FARS context city identity is invalid")

        final_context_bytes, final_context_digest = outcome_verifier._read_file(
            context_normalized_fd,
            "current.json",
            maximum=outcome_verifier._MAX_RECEIPT_BYTES,
        )
        final_joined_bytes, final_joined_digest = outcome_verifier._read_file(
            joined_normalized_fd,
            "current.json",
            maximum=outcome_verifier._MAX_RECEIPT_BYTES,
        )
        if (
            final_context_digest != context_current_digest
            or final_context_bytes != context_current_bytes
            or final_joined_digest != joined_current_digest
            or final_joined_bytes != joined_current_bytes
        ):
            _context_fail("FARS context active state changed during verification")
        if context_lock_required:
            _context_lock_present(context_source_fd)
        else:
            outcome_verifier._lock_absent(context_source_fd)
        outcome_verifier._lock_absent(joined_source_fd)

        method = cast(Mapping[str, object], active_context.artifact["method"])
        privacy = cast(Mapping[str, object], method["privacy"])
        accounting = cast(Mapping[str, object], active_context.artifact["accounting"])
        return VerifiedFarsContextEvidence(
            source_id=source_id,
            city_key=city_key,
            attempt_id=context_current.attempt_id,
            raw_sha256=cast(str, context_current.receipt["raw_sha256"]),
            normalized_sha256=cast(str, context_current.receipt["normalized_sha256"]),
            effective_k=cast(int, privacy["effective_k"]),
            eligible_cell_count=cast(int, accounting["eligible_cell_count"]),
            joined_source=active_joined_reference.evidence,
            status="verified_at_observation",
            _proof_token=_CONTEXT_PROOF_TOKEN,
        )


def verify_active_fars_context(
    root: str | Path,
    city_key: str,
    *,
    joined_root: str | Path | None = None,
) -> VerifiedFarsContextEvidence:
    """Verify full context and joined histories, returning only currently usable evidence."""

    return _verify_active_fars_context_history(
        root,
        city_key,
        joined_root=joined_root,
        require_current_joined=True,
        context_lock_required=False,
    )


def _validate_context_history_candidate_locked(  # noqa: C901
    source_root: Path,
    candidate_normalized: bytes,
    *,
    city_key: str,
    joined_root: str | Path,
    package_bytes: bytes,
    started_at: str,
    expected_joined_state: list[outcome_verifier._VerifiedJoinedActivationState],
) -> None:
    """Replay the complete prior chain and reject non-adjacent normalized reuse."""

    if type(candidate_normalized) is not bytes:
        raise TypeError("FARS context history candidate must be exact immutable bytes")
    try:
        (source_root / "normalized" / "current.json").stat(follow_symlinks=False)
    except FileNotFoundError:
        with ExitStack() as stack:
            source_fd = outcome_verifier._open_root(source_root)
            stack.callback(os.close, source_fd)
            _context_lock_present(source_fd)
            _reject_orphan_success_history(source_fd, source_id=context_source_id(city_key))
            _context_lock_present(source_fd)
        joined_state = outcome_verifier._load_verified_active_fars_joined_activation_state(
            joined_root
        )
        snapshot = joined_state.snapshot
        try:
            package = _parse_package(package_bytes)
            if package.manifest["city_key"] != city_key:
                _context_fail("FARS context candidate city identity is invalid")
            if package.manifest["source_reference"] != snapshot.evidence.as_dict():
                _context_fail("FARS context candidate joined-source reference is stale")
            if outcome_verifier._timestamp(started_at) < joined_state.completed_at:
                _context_fail("FARS context candidate predates its joined generation")
        except VerificationError:
            raise
        except (KeyError, OSError, TypeError, ValueError):
            _context_fail("FARS context history candidate metadata is invalid")
        if expected_joined_state:
            _context_fail("FARS context joined activation state was captured more than once")
        expected_joined_state.append(joined_state)
        return
    except OSError:
        _context_fail("FARS context history preflight failed")
    _verify_active_fars_context_history(
        source_root.parent,
        city_key,
        joined_root=joined_root,
        require_current_joined=False,
        context_lock_required=True,
        candidate_normalized=candidate_normalized,
        candidate_package_bytes=package_bytes,
        candidate_started_at=started_at,
    )
    joined_state = outcome_verifier._load_verified_active_fars_joined_activation_state(joined_root)
    package = _parse_package(package_bytes)
    if (
        package.manifest["source_reference"] != joined_state.snapshot.evidence.as_dict()
        or outcome_verifier._timestamp(started_at) < joined_state.completed_at
        or expected_joined_state
    ):
        _context_fail("FARS context joined activation state is invalid")
    expected_joined_state.append(joined_state)


def _reject_context_normalized_reuse_locked(
    source_root: Path, candidate_normalized: bytes, *, source_id: str
) -> None:
    """Apply the history-wide normalized-reuse rule without joined replay."""

    try:
        (source_root / "normalized" / "current.json").stat(follow_symlinks=False)
    except FileNotFoundError:
        with ExitStack() as stack:
            source_fd = outcome_verifier._open_root(source_root)
            stack.callback(os.close, source_fd)
            _context_lock_present(source_fd)
            _reject_orphan_success_history(source_fd, source_id=source_id)
        return
    except OSError:
        _context_fail("FARS context history preflight failed")
    with ExitStack() as stack:
        source_fd = outcome_verifier._open_root(source_root)
        stack.callback(os.close, source_fd)
        _context_lock_present(source_fd)
        normalized_fd = outcome_verifier._open_directory(source_fd, "normalized")
        stack.callback(os.close, normalized_fd)
        receipts_fd = outcome_verifier._open_directory(source_fd, "receipts")
        stack.callback(os.close, receipts_fd)
        current_bytes, current_digest = outcome_verifier._read_file(
            normalized_fd, "current.json", maximum=outcome_verifier._MAX_RECEIPT_BYTES
        )
        current = outcome_verifier._parse_receipt(current_bytes, expected_source_id=source_id)
        outcome_verifier._active_success(current.receipt)
        successes = outcome_verifier._ordered_successes(
            current,
            outcome_verifier._scan_receipts(receipts_fd, expected_source_id=source_id),
        )
        candidate_digest = hashlib.sha256(candidate_normalized).hexdigest()
        latest_digest = cast(str, successes[-1].receipt["normalized_sha256"])
        if candidate_digest != latest_digest and any(
            record.receipt["normalized_sha256"] == candidate_digest for record in successes[:-1]
        ):
            _context_fail("FARS context candidate reuses an older normalized generation")
        final_bytes, final_digest = outcome_verifier._read_file(
            normalized_fd, "current.json", maximum=outcome_verifier._MAX_RECEIPT_BYTES
        )
        if final_digest != current_digest or final_bytes != current_bytes:
            _context_fail("FARS context active state changed during history validation")
        _context_lock_present(source_fd)


def _verify_activated_context_locked(
    source_root: Path,
    candidate_normalized: bytes,
    success_marker: bytes,
    *,
    package_bytes: bytes,
    joined_root: str | Path,
    city_key: str,
    expected_joined_state: outcome_verifier._VerifiedJoinedActivationState,
) -> VerifiedFarsContextEvidence:
    """Mint activation-time evidence only while the candidate marker is locked active."""

    if type(candidate_normalized) is not bytes or type(success_marker) is not bytes:
        _context_fail("FARS context activated candidate bytes are invalid")
    source_id = context_source_id(city_key)
    try:
        package = _parse_package(package_bytes)
        artifact = _artifact(candidate_normalized)
        marker = outcome_verifier._parse_receipt(success_marker, expected_source_id=source_id)
        outcome_verifier._active_success(marker.receipt)
    except VerificationError:
        raise
    except (KeyError, TypeError, ValueError):
        _context_fail("FARS context activated candidate validation failed")
    if (
        package.manifest["city_key"] != city_key
        or artifact["city_key"] != city_key
        or marker.receipt["raw_sha256"] != hashlib.sha256(package_bytes).hexdigest()
        or marker.receipt["normalized_sha256"] != hashlib.sha256(candidate_normalized).hexdigest()
    ):
        _context_fail("FARS context activated candidate binding failed")

    with ExitStack() as stack:
        source_fd = outcome_verifier._open_root(source_root)
        stack.callback(os.close, source_fd)
        _context_lock_present(source_fd)
        raw_fd = outcome_verifier._open_directory(source_fd, "raw")
        stack.callback(os.close, raw_fd)
        raw_hashes_fd = outcome_verifier._open_directory(raw_fd, "sha256")
        stack.callback(os.close, raw_hashes_fd)
        normalized_fd = outcome_verifier._open_directory(source_fd, "normalized")
        stack.callback(os.close, normalized_fd)
        normalized_hashes_fd = outcome_verifier._open_directory(normalized_fd, "sha256")
        stack.callback(os.close, normalized_hashes_fd)

        raw_digest = marker.receipt["raw_sha256"]
        normalized_digest = marker.receipt["normalized_sha256"]
        observed_package, observed_package_digest = outcome_verifier._read_file(
            raw_hashes_fd,
            f"{raw_digest}.bin",
            maximum=MAX_DEPENDENCY_PACKAGE_BYTES,
        )
        observed_candidate, observed_candidate_digest = outcome_verifier._read_file(
            normalized_hashes_fd,
            f"{normalized_digest}.bin",
            maximum=MAX_NORMALIZED_CONTEXT_BYTES,
        )
        current_bytes, current_digest = outcome_verifier._read_file(
            normalized_fd,
            "current.json",
            maximum=outcome_verifier._MAX_RECEIPT_BYTES,
        )
        if (
            observed_package != package_bytes
            or observed_package_digest != raw_digest
            or observed_candidate != candidate_normalized
            or observed_candidate_digest != normalized_digest
            or current_bytes != success_marker
        ):
            _context_fail("FARS context activated filesystem binding failed")

        joined_state = outcome_verifier._load_verified_active_fars_joined_activation_state(
            joined_root
        )
        joined_snapshot = joined_state.snapshot
        if (
            joined_state.current_bytes != expected_joined_state.current_bytes
            or joined_state.current_digest != expected_joined_state.current_digest
            or joined_state.completed_at != expected_joined_state.completed_at
            or joined_snapshot.evidence != expected_joined_state.snapshot.evidence
            or package.manifest["source_reference"] != joined_snapshot.evidence.as_dict()
            or artifact["source_lineage"] != joined_snapshot.evidence.as_dict()
            or marker.started_at < joined_state.completed_at
        ):
            _context_fail("FARS context activated joined-source binding failed")

        final_current, final_digest = outcome_verifier._read_file(
            normalized_fd,
            "current.json",
            maximum=outcome_verifier._MAX_RECEIPT_BYTES,
        )
        if final_digest != current_digest or final_current != current_bytes:
            _context_fail("FARS context active state changed during activation verification")
        _context_lock_present(source_fd)

    method = cast(Mapping[str, object], artifact["method"])
    privacy = cast(Mapping[str, object], method["privacy"])
    accounting = cast(Mapping[str, object], artifact["accounting"])
    return VerifiedFarsContextEvidence(
        source_id=source_id,
        city_key=city_key,
        attempt_id=marker.attempt_id,
        raw_sha256=raw_digest,
        normalized_sha256=normalized_digest,
        effective_k=cast(int, privacy["effective_k"]),
        eligible_cell_count=cast(int, accounting["eligible_cell_count"]),
        joined_source=joined_snapshot.evidence,
        status="verified_at_activation",
        _proof_token=_CONTEXT_PROOF_TOKEN,
    )


def _capture_activated_context_evidence(
    source_root: Path,
    candidate_normalized: bytes,
    success_marker: bytes,
    *,
    package_bytes: bytes,
    joined_root: str | Path,
    city_key: str,
    expected_joined_state: list[outcome_verifier._VerifiedJoinedActivationState],
    captured_evidence: list[VerifiedFarsContextEvidence],
) -> None:
    if len(expected_joined_state) != 1 or captured_evidence:
        _context_fail("FARS context activation proof handoff is invalid")
    captured_evidence.append(
        _verify_activated_context_locked(
            source_root,
            candidate_normalized,
            success_marker,
            package_bytes=package_bytes,
            joined_root=joined_root,
            city_key=city_key,
            expected_joined_state=expected_joined_state[0],
        )
    )


def context_source_id(city_key: str) -> str:
    """Return a stable collision-resistant city-scoped ingestion source id."""

    if not isinstance(city_key, str) or not city_key:
        raise ValueError("city key must be nonempty")
    slug = re.sub(r"[^A-Za-z0-9]+", "-", city_key).strip("-").lower() or "city"
    try:
        suffix = hashlib.sha256(city_key.encode("utf-8")).hexdigest()[:12]
    except UnicodeEncodeError:
        raise ValueError("city key must contain only Unicode scalar values") from None
    return f"fars-context-{slug[:64]}-{suffix}"


def require_private_activation_root(root: str | Path, repository_root: str | Path) -> Path:
    """Reject activation storage inside the repository before any mutation."""

    try:
        resolved_root = Path(root).expanduser().resolve(strict=False)
        resolved_repository = Path(repository_root).expanduser().resolve(strict=True)
        resolved_root.relative_to(resolved_repository)
    except ValueError:
        return resolved_root
    except OSError:
        raise ValueError("FARS context activation root preflight failed") from None
    raise ValueError("FARS context activation root must remain outside the repository")


def activate_fars_context_audit_only(
    *,
    root: str | Path,
    repository_root: str | Path,
    snapshot: _VerifiedJoinedSnapshot,
    joined_root: str | Path | None = None,
    config_path: str | Path,
    config_bytes: bytes,
    network_bytes: bytes,
    fars_snap_max_m: float,
    ambiguity_margin_m: float,
    composition_review_reference: str | None = None,
    methodology_change_review_reference: str | None = None,
    privacy_regression_override_reference: str | None = None,
    source_regression_override_reference: str | None = None,
    quality_regression_override_reference: str | None = None,
    clock: Clock | None = None,
    attempt_id: str | None = None,
    _capture_activated_evidence: list[VerifiedFarsContextEvidence] | None = None,
) -> FarsContextAuditActivation:
    """Store an explicitly non-production audit candidate without usability evidence.

    Omitting ``joined_root`` is intentionally weaker and must not be used by a
    CLI, service, or other production activation path.
    """

    private_root = require_private_activation_root(root, repository_root)
    package_bytes = build_dependency_package(
        snapshot,
        config_path=config_path,
        config_bytes=config_bytes,
        network_bytes=network_bytes,
        fars_snap_max_m=fars_snap_max_m,
        ambiguity_margin_m=ambiguity_margin_m,
        composition_review_reference=composition_review_reference,
        methodology_change_review_reference=methodology_change_review_reference,
        privacy_regression_override_reference=privacy_regression_override_reference,
        source_regression_override_reference=source_regression_override_reference,
        quality_regression_override_reference=quality_regression_override_reference,
    )
    package = _parse_package(package_bytes)
    source_id = context_source_id(cast(str, package.manifest["city_key"]))
    city_key = cast(str, package.manifest["city_key"])
    expected_joined_state: list[outcome_verifier._VerifiedJoinedActivationState] = []
    if _capture_activated_evidence is not None and joined_root is None:
        raise ValueError("full-history activation requires a joined root")
    require_private_activation_root(private_root / source_id, repository_root)
    run_kwargs: dict[str, object] = {}
    if clock is not None:
        run_kwargs["clock"] = clock
    if attempt_id is not None:
        run_kwargs["attempt_id"] = attempt_id
    ingestion = run_ingestion(
        root=private_root,
        source_id=source_id,
        fetch=lambda: package_bytes,
        normalize=lambda raw: _normalize(raw, snapshot),
        validate_normalized=lambda candidate, previous: _validate_candidate(
            candidate, previous, package_bytes, snapshot
        ),
        validate_history=(
            (
                lambda source_root, candidate, started_at: (
                    _validate_context_history_candidate_locked(
                        source_root,
                        candidate,
                        city_key=cast(str, package.manifest["city_key"]),
                        joined_root=joined_root,
                        package_bytes=package_bytes,
                        started_at=started_at,
                        expected_joined_state=expected_joined_state,
                    )
                )
            )
            if joined_root is not None
            else (
                lambda source_root, candidate, _started_at: _reject_context_normalized_reuse_locked(
                    source_root, candidate, source_id=source_id
                )
            )
        ),
        validate_activated=(
            (
                lambda source_root, candidate, marker: _capture_activated_context_evidence(
                    source_root,
                    candidate,
                    marker,
                    package_bytes=package_bytes,
                    joined_root=joined_root,
                    city_key=city_key,
                    expected_joined_state=expected_joined_state,
                    captured_evidence=_capture_activated_evidence,
                )
            )
            if joined_root is not None and _capture_activated_evidence is not None
            else None
        ),
        max_raw_bytes=MAX_DEPENDENCY_PACKAGE_BYTES,
        max_normalized_bytes=MAX_NORMALIZED_CONTEXT_BYTES,
        **run_kwargs,  # type: ignore[arg-type]
    )
    return FarsContextAuditActivation(ingestion)


def activate_fars_context_full_history(
    *,
    root: str | Path,
    repository_root: str | Path,
    joined_root: str | Path,
    config_path: str | Path,
    config_bytes: bytes,
    network_bytes: bytes,
    fars_snap_max_m: float,
    ambiguity_margin_m: float,
    composition_review_reference: str | None = None,
    methodology_change_review_reference: str | None = None,
    privacy_regression_override_reference: str | None = None,
    source_regression_override_reference: str | None = None,
    quality_regression_override_reference: str | None = None,
    clock: Clock | None = None,
    attempt_id: str | None = None,
) -> FarsContextFullHistoryActivation:
    """Activate only after the complete context and joined histories verify under lock."""

    snapshot = outcome_verifier._load_verified_active_fars_joined_snapshot(joined_root)
    captured_evidence: list[VerifiedFarsContextEvidence] = []
    activation = activate_fars_context_audit_only(
        root=root,
        repository_root=repository_root,
        joined_root=joined_root,
        snapshot=snapshot,
        config_path=config_path,
        config_bytes=config_bytes,
        network_bytes=network_bytes,
        fars_snap_max_m=fars_snap_max_m,
        ambiguity_margin_m=ambiguity_margin_m,
        composition_review_reference=composition_review_reference,
        methodology_change_review_reference=methodology_change_review_reference,
        privacy_regression_override_reference=privacy_regression_override_reference,
        source_regression_override_reference=source_regression_override_reference,
        quality_regression_override_reference=quality_regression_override_reference,
        clock=clock,
        attempt_id=attempt_id,
        _capture_activated_evidence=captured_evidence,
    )
    if len(captured_evidence) != 1:
        _context_fail("FARS context activation evidence was not captured")
    return FarsContextFullHistoryActivation(activation, captured_evidence[0])


__all__ = [
    "ACTIVATION_STATUS",
    "DEPENDENCY_PACKAGE_SCHEMA_VERSION",
    "DEPENDENCY_PACKAGE_TYPE",
    "MAX_DEPENDENCY_PACKAGE_BYTES",
    "FarsContextAuditActivation",
    "FarsContextFullHistoryActivation",
    "VerifiedFarsContextEvidence",
    "activate_fars_context_audit_only",
    "activate_fars_context_full_history",
    "build_dependency_package",
    "context_source_id",
    "require_private_activation_root",
    "verify_active_fars_context",
]
