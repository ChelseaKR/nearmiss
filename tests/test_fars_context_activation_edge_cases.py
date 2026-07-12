from __future__ import annotations

import copy
import hashlib
import io
import json
import os
import zipfile
from pathlib import Path
from typing import Any, cast

import pytest

import nearmiss.fars_context_activation as activation
import nearmiss.verified_outcomes as outcome_verifier
from nearmiss.adapters.fars import FARS_MAPPING_VERSION
from nearmiss.adapters.fars_joined import (
    PERSON_MODE_MAPPING_VERSION,
    collect_joined,
    read_joined_export_bytes,
)
from nearmiss.fars_context_activation import VerifiedFarsContextEvidence
from nearmiss.joined_outcome_artifacts import (
    build_joined_outcome_artifact,
    canonical_joined_outcome_artifact_bytes,
)
from nearmiss.verified_outcomes import VerificationError

FARS_URL = "https://static.nhtsa.gov/nhtsa/downloads/FARS/2024/National/FARS2024.zip"


def _raw(number: int) -> bytes:
    accident = ["STATE,ST_CASE,YEAR,MONTH,DAY,HOUR,MINUTE,LATITUDE,LONGITUD,FATALS"]
    person = ["STATE,ST_CASE,VEH_NO,PER_NO,PER_TYP,INJ_SEV,BODY_TYP"]
    for index in range(number):
        case = 100001 + index
        accident.append(f"6,{case},2024,5,1,12,0,38.540000,-121.740000,1")
        person.append(f"6,{case},0,1,5,4,")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("FARS/accident.csv", "\n".join(accident) + "\n")
        archive.writestr("FARS/person.csv", "\n".join(person) + "\n")
    return buffer.getvalue()


def _snapshot(number: int) -> outcome_verifier._VerifiedJoinedSnapshot:
    raw = _raw(number)
    outcomes, summaries, crash, person = collect_joined(
        read_joined_export_bytes(raw), release_status="final"
    )
    normalized = canonical_joined_outcome_artifact_bytes(
        build_joined_outcome_artifact(
            outcomes,
            summaries,
            person,
            crash,
            distribution_url=FARS_URL,
            max_invalid_fraction=0.05,
        )
    )
    evidence = outcome_verifier.VerifiedJoinedOutcomeEvidence(
        source_id="fars-joined",
        dataset_year=2024,
        crash_mapping_version=FARS_MAPPING_VERSION,
        person_mapping_version=PERSON_MODE_MAPPING_VERSION,
        release_status="final",
        crash_records_read=crash.records_read,
        crash_records_accepted=crash.records_accepted,
        crash_records_rejected=crash.records_read - crash.records_accepted,
        person_records_read=person.records_read,
        person_records_accepted=person.records_accepted,
        person_records_excluded=person.records_excluded_with_rejected_crash,
        cases_joined=person.cases_joined,
        cases_excluded=person.cases_excluded_with_rejected_crash,
        raw_sha256=hashlib.sha256(raw).hexdigest(),
        accident_sha256=person.accident_sha256,
        person_sha256=person.person_sha256,
        normalized_sha256=hashlib.sha256(normalized).hexdigest(),
        attempt_id=f"source-{number}",
        _proof_token=outcome_verifier._JOINED_PROOF_TOKEN,
    )
    return outcome_verifier._VerifiedJoinedSnapshot(
        evidence=evidence,
        normalized_bytes=normalized,
        _proof_token=outcome_verifier._JOINED_SNAPSHOT_PROOF_TOKEN,
    )


def _config() -> bytes:
    return b"""city = "Test City"
streets = "/private/network.geojson"
reports = "/private/reports.json"
exposure = "/private/exposure.json"

[window]
start = "2024-01-01"
end = "2024-12-31"

[thresholds]
min_publish_n = 5
"""


def _network() -> bytes:
    return (
        json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "properties": {"segment_id": "main", "name": "Main"},
                        "geometry": {
                            "type": "LineString",
                            "coordinates": [[-121.74, 38.53], [-121.74, 38.55]],
                        },
                    }
                ],
            },
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode()


def _zip_entries(payload: bytes) -> dict[str, bytes]:
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


def _package() -> tuple[outcome_verifier._VerifiedJoinedSnapshot, bytes]:
    snapshot = _snapshot(6)
    package = activation.build_dependency_package(
        snapshot,
        config_path=Path("operator.toml"),
        config_bytes=_config(),
        network_bytes=_network(),
        fars_snap_max_m=50.0,
        ambiguity_margin_m=5.0,
    )
    return snapshot, package


def _manifest_package() -> tuple[dict[str, Any], activation._DependencyPackage]:
    _snapshot_value, payload = _package()
    parsed = activation._parse_package(payload)
    return copy.deepcopy(dict(parsed.manifest)), parsed


def test_strict_json_and_exact_bytes_reject_ambiguous_inputs() -> None:
    with pytest.raises(ValueError, match="duplicate"):
        activation._strict_object([("key", 1), ("key", 2)])
    with pytest.raises(ValueError, match="Unicode scalar"):
        activation._canonical("\ud800")
    for payload in (b"\xff", b"{", b"[]", b'{"value":NaN}'):
        with pytest.raises(ValueError):
            activation._strict_json(payload, "edge JSON")
    with pytest.raises(TypeError, match="exact immutable bytes"):
        activation._exact_bytes(bytearray(b"x"), "edge", 2)
    for payload in (b"", b"xxx"):
        with pytest.raises(ValueError, match="byte safety limit"):
            activation._exact_bytes(payload, "edge", 2)


def test_review_source_and_config_helpers_fail_closed() -> None:
    assert activation._review_reference(None, "review") is None
    for value in (23, " leading", "bad\u200bref", "\ud800"):
        with pytest.raises(ValueError, match="safe review"):
            activation._review_reference(value, "review")
    with pytest.raises(TypeError, match="proof-bound"):
        activation._source_reference(object())  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="both exact window bounds"):
        activation._replay_config(b'city="City"\nstreets="s"\nreports="r"\nexposure="e"\n', "toml")

    located_config = _config().replace(
        b"\n[window]\n", b"\nref_lat = 38.5\nref_lon = -121.7\n\n[window]\n"
    )
    replay, city = activation._replay_config(located_config, "toml")
    decoded = json.loads(replay)
    assert city == "Test City"
    assert decoded["ref_lat"] == 38.5
    assert decoded["ref_lon"] == -121.7


@pytest.mark.parametrize(
    ("snap", "margin"),
    [(True, 5.0), (float("nan"), 5.0), (0.0, 5.0), (50.0, -1.0)],
)
def test_builder_rejects_unsafe_replay_numbers(snap: object, margin: object) -> None:
    with pytest.raises(ValueError, match="supported range"):
        activation.build_dependency_package(
            _snapshot(6),
            config_path=Path("operator.toml"),
            config_bytes=_config(),
            network_bytes=_network(),
            fars_snap_max_m=cast(float, snap),
            ambiguity_margin_m=cast(float, margin),
        )


def test_zip_reader_rejects_names_comments_encoding_size_and_invalid_bytes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _snapshot_value, package = _package()
    entries = _zip_entries(package)

    wrong_names = io.BytesIO()
    with zipfile.ZipFile(wrong_names, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr("wrong", b"x")
    with pytest.raises(ValueError, match="members"):
        activation._read_zip_entries(wrong_names.getvalue())

    commented = io.BytesIO(package)
    with zipfile.ZipFile(commented, "a") as archive:
        archive.comment = b"not canonical"
    with pytest.raises(ValueError, match="metadata"):
        activation._read_zip_entries(commented.getvalue())

    compressed = io.BytesIO()
    with zipfile.ZipFile(compressed, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in activation._ENTRY_ORDER:
            archive.writestr(name, entries[name])
    with pytest.raises(ValueError, match="encoding"):
        activation._read_zip_entries(compressed.getvalue())

    monkeypatch.setattr(
        activation,
        "MAX_DEPENDENCY_PACKAGE_BYTES",
        sum(len(value) for value in entries.values()) - 1,
    )
    with pytest.raises(ValueError, match="expands"):
        activation._read_zip_entries(package)
    with pytest.raises(ValueError, match="safe ZIP"):
        activation._read_zip_entries(b"not-a-zip")


@pytest.mark.parametrize(
    "mutation",
    [
        lambda value: value.update({"extra": True}),
        lambda value: value.update({"schema_version": "0"}),
        lambda value: value.update({"city_key": " "}),
        lambda value: value.update({"source_reference": {}}),
        lambda value: cast(dict[str, Any], value["source_reference"]).update(
            {"dataset_year": 2023}
        ),
        lambda value: value.update({"replay": {}}),
        lambda value: cast(dict[str, Any], value["replay"]).update({"fars_snap_max_m": True}),
        lambda value: value.update({"reviews": {}}),
        lambda value: cast(dict[str, Any], value["reviews"]).update(
            {
                "composition_review_reference": "same",
                "methodology_change_review_reference": "same",
            }
        ),
        lambda value: value.update({"policy": {}}),
    ],
)
def test_manifest_contract_rejects_each_closed_block(mutation: Any) -> None:
    manifest, _parsed = _manifest_package()
    mutation(manifest)
    with pytest.raises(ValueError):
        activation._validate_manifest(manifest)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda manifest, _package: cast(dict[str, Any], manifest["dependency_reference"]).pop(
            "original_config_sha256"
        ),
        lambda manifest, _package: cast(dict[str, Any], manifest["dependency_reference"]).update(
            {"original_config_sha256": "bad"}
        ),
        lambda manifest, _package: cast(dict[str, Any], manifest["dependency_reference"]).update(
            {"original_config_byte_count": True}
        ),
        lambda manifest, _package: cast(dict[str, Any], manifest["dependency_reference"]).update(
            {"original_config_sha256": "0" * 64}
        ),
        lambda manifest, _package: cast(dict[str, Any], manifest["dependency_reference"]).update(
            {"original_config_byte_count": 999999}
        ),
        lambda manifest, _package: cast(dict[str, Any], manifest["dependency_reference"]).update(
            {"original_config_format": "yaml"}
        ),
        lambda manifest, _package: manifest.update({"city_key": "Different City"}),
    ],
)
def test_linked_entry_reference_rejects_each_mismatch(mutation: Any) -> None:
    manifest, parsed = _manifest_package()
    mutation(manifest, parsed)
    forged = activation._DependencyPackage(
        manifest, parsed.original_config, parsed.replay_config, parsed.original_network
    )
    with pytest.raises(ValueError):
        activation._validate_linked_entries(forged)


def test_package_normalization_and_artifact_canonicality_are_bound() -> None:
    snapshot, package = _package()
    with pytest.raises(ValueError, match="source reference"):
        activation._normalize(package, _snapshot(7))

    candidate = activation._normalize(package, snapshot)
    noncanonical = (json.dumps(json.loads(candidate), indent=2) + "\n").encode()
    with pytest.raises(ValueError, match="not canonical"):
        activation._artifact(noncanonical)
    with pytest.raises(ValueError, match="comparison path"):
        activation._nested({"outer": 1}, ("outer", "inner"))


def test_joined_reference_and_empty_context_chain_fail_closed() -> None:
    _snapshot_value, payload = _package()
    package = activation._parse_package(payload)
    manifest = copy.deepcopy(dict(package.manifest))

    for source in (None, {"attempt_id": 3}, {"attempt_id": "missing"}):
        manifest["source_reference"] = source
        forged = activation._DependencyPackage(
            copy.deepcopy(manifest),
            package.original_config,
            package.replay_config,
            package.original_network,
        )
        with pytest.raises(VerificationError):
            activation._joined_reference_for_package(forged, {})

    with pytest.raises(VerificationError, match="no successful receipt"):
        activation._verify_context_chain([], 0, 0, 0, {}, cast(Any, None), "City", "source")


def test_lock_history_and_activation_handoff_preconditions(tmp_path: Path) -> None:
    tmp_path.chmod(0o700)
    descriptor = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        with pytest.raises(VerificationError, match="lock is not held"):
            activation._context_lock_present(descriptor)
        activation._reject_orphan_success_history(descriptor, source_id="source")
    finally:
        os.close(descriptor)

    with pytest.raises(TypeError, match="exact immutable bytes"):
        activation._validate_context_history_candidate_locked(
            tmp_path,
            bytearray(b"candidate"),  # type: ignore[arg-type]
            city_key="City",
            joined_root=tmp_path,
            package_bytes=b"package",
            started_at="2026-01-01T00:00:00Z",
            expected_joined_state=[],
        )
    with pytest.raises(VerificationError, match="candidate bytes"):
        activation._verify_activated_context_locked(
            tmp_path,
            bytearray(b"candidate"),  # type: ignore[arg-type]
            b"marker",
            package_bytes=b"package",
            joined_root=tmp_path,
            city_key="City",
            expected_joined_state=cast(Any, None),
        )
    with pytest.raises(VerificationError, match="proof handoff"):
        activation._capture_activated_context_evidence(
            tmp_path,
            b"candidate",
            b"marker",
            package_bytes=b"package",
            joined_root=tmp_path,
            city_key="City",
            expected_joined_state=[],
            captured_evidence=[],
        )


def test_evidence_city_source_status_and_bounds_remain_proof_bound() -> None:
    snapshot = _snapshot(6)
    values: dict[str, Any] = {
        "source_id": activation.context_source_id("City"),
        "city_key": "City",
        "attempt_id": "attempt",
        "raw_sha256": "0" * 64,
        "normalized_sha256": "1" * 64,
        "effective_k": 5,
        "eligible_cell_count": 0,
        "joined_source": snapshot.evidence,
        "status": "verified_at_activation",
        "_proof_token": activation._CONTEXT_PROOF_TOKEN,
    }
    for field, invalid in (
        ("city_key", "\ud800"),
        ("normalized_sha256", "bad"),
        ("effective_k", 10**12),
        ("eligible_cell_count", -1),
        ("joined_source", object()),
        ("status", "currently_usable"),
    ):
        forged = dict(values)
        forged[field] = invalid
        with pytest.raises(VerificationError, match="internal proof"):
            VerifiedFarsContextEvidence(**forged)


def test_source_id_root_and_wrapper_capture_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(ValueError, match="nonempty"):
        activation.context_source_id("")
    with pytest.raises(ValueError, match="Unicode scalar"):
        activation.context_source_id("\ud800")

    def fail_resolve(_self: Path, *, strict: bool = False) -> Path:
        raise OSError

    monkeypatch.setattr(Path, "resolve", fail_resolve)
    with pytest.raises(ValueError, match="preflight failed"):
        activation.require_private_activation_root(tmp_path / "private", tmp_path)
    monkeypatch.undo()

    snapshot = _snapshot(6)
    monkeypatch.setattr(
        outcome_verifier,
        "_load_verified_active_fars_joined_snapshot",
        lambda _root: snapshot,
    )
    monkeypatch.setattr(
        activation,
        "activate_fars_context_audit_only",
        lambda **_kwargs: cast(Any, object()),
    )
    with pytest.raises(VerificationError, match="was not captured"):
        activation.activate_fars_context_full_history(
            root=tmp_path / "private",
            repository_root=tmp_path,
            joined_root=tmp_path,
            config_path=Path("operator.toml"),
            config_bytes=_config(),
            network_bytes=_network(),
            fars_snap_max_m=50.0,
            ambiguity_margin_m=5.0,
        )
