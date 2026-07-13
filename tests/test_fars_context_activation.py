from __future__ import annotations

import datetime as dt
import hashlib
import io
import json
import stat
import zipfile
from pathlib import Path
from typing import Any, cast

import pytest

import nearmiss.fars_context_activation as activation
import nearmiss.verified_outcomes as verifier
from nearmiss.adapters.fars import FARS_MAPPING_VERSION
from nearmiss.adapters.fars_joined import (
    PERSON_MODE_MAPPING_VERSION,
    collect_joined,
    read_joined_export_bytes,
)
from nearmiss.fars_context import canonical_fars_context_bytes
from nearmiss.fars_context_activation import (
    ACTIVATION_STATUS,
    activate_fars_context_audit_only,
    build_dependency_package,
    context_source_id,
    require_private_activation_root,
)
from nearmiss.ingestion import IngestionRunError
from nearmiss.joined_outcome_artifacts import (
    build_joined_outcome_artifact,
    canonical_joined_outcome_artifact_bytes,
)
from nearmiss.verified_outcomes import VerifiedJoinedOutcomeEvidence, _VerifiedJoinedSnapshot

NOW = dt.datetime(2026, 7, 12, 19, tzinfo=dt.UTC)
FARS_URL = "https://static.nhtsa.gov/nhtsa/downloads/FARS/2024/National/FARS2024.zip"
PRIVATE_PATH = "/operator/private/home/secret-network.geojson"


def _clock() -> dt.datetime:
    return NOW


def _raw(number: int, *, release_offset: int = 0, rejected: int = 0) -> bytes:
    accident = ["STATE,ST_CASE,YEAR,MONTH,DAY,HOUR,MINUTE,LATITUDE,LONGITUD,FATALS"]
    person = ["STATE,ST_CASE,VEH_NO,PER_NO,PER_TYP,INJ_SEV,BODY_TYP"]
    for index in range(number):
        case = 100001 + index + release_offset
        accident.append(f"6,{case},2024,5,1,12,0,38.540000,-121.740000,1")
        person.append(f"6,{case},0,1,5,4,")
    for index in range(rejected):
        case = 200001 + index + release_offset
        accident.append(f"6,{case},2024,5,1,12,0,999,-121.740000,1")
        person.append(f"6,{case},0,1,5,4,")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("FARS/accident.csv", "\n".join(accident) + "\n")
        archive.writestr("FARS/person.csv", "\n".join(person) + "\n")
    return buffer.getvalue()


def _snapshot(
    number: int, *, release_status: str = "final", rejected: int = 0
) -> _VerifiedJoinedSnapshot:
    raw = _raw(number, rejected=rejected)
    outcomes, summaries, crash, person = collect_joined(
        read_joined_export_bytes(raw), release_status=release_status
    )
    artifact = build_joined_outcome_artifact(
        outcomes,
        summaries,
        person,
        crash,
        distribution_url=FARS_URL,
        max_invalid_fraction=1.0 if rejected else 0.05,
    )
    normalized = canonical_joined_outcome_artifact_bytes(artifact)
    evidence = VerifiedJoinedOutcomeEvidence(
        source_id="fars-joined",
        dataset_year=2024,
        crash_mapping_version=FARS_MAPPING_VERSION,
        person_mapping_version=PERSON_MODE_MAPPING_VERSION,
        release_status=release_status,
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
        attempt_id=f"source-{number}-{rejected}-{release_status}",
        _proof_token=verifier._JOINED_PROOF_TOKEN,
    )
    return _VerifiedJoinedSnapshot(
        evidence=evidence,
        normalized_bytes=normalized,
        _proof_token=verifier._JOINED_SNAPSHOT_PROOF_TOKEN,
    )


def _config(*, minimum_k: int = 5, start: str = "2024-01-01") -> bytes:
    return f'''city = "Test City"
streets = "{PRIVATE_PATH}"
reports = "/operator/private/reports.json"
exposure = "/operator/private/exposure.json"

[window]
start = "{start}"
end = "2024-12-31"

[thresholds]
min_publish_n = {minimum_k}
'''.encode()


def _network(*, name: str = "Public Main") -> bytes:
    return (
        json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "properties": {"segment_id": "main", "name": name},
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


def _roots(tmp_path: Path) -> tuple[Path, Path]:
    repository = tmp_path / "repo"
    repository.mkdir()
    return tmp_path / "private-context", repository


def _activate(
    tmp_path: Path,
    snapshot: _VerifiedJoinedSnapshot,
    attempt: str,
    **changes: object,
) -> activation.FarsContextAuditActivation:
    root, repository = (
        _roots(tmp_path)
        if not (tmp_path / "repo").exists()
        else (
            tmp_path / "private-context",
            tmp_path / "repo",
        )
    )
    values: dict[str, object] = {
        "root": root,
        "repository_root": repository,
        "snapshot": snapshot,
        "config_path": Path("operator.toml"),
        "config_bytes": _config(),
        "network_bytes": _network(),
        "fars_snap_max_m": 50.0,
        "ambiguity_margin_m": 5.0,
        "clock": _clock,
        "attempt_id": attempt,
    }
    values.update(changes)
    return activate_fars_context_audit_only(**values)  # type: ignore[arg-type]


def _zip_entries(payload: bytes) -> dict[str, bytes]:
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


def _active_bytes(result: activation.FarsContextAuditActivation) -> bytes:
    return result.ingestion.normalized_path.read_bytes()


def test_dependency_zip_is_deterministic_exact_and_sanitized_by_layer() -> None:
    snapshot = _snapshot(6)
    config = _config()
    network = _network()
    first = build_dependency_package(
        snapshot,
        config_path=Path("operator.toml"),
        config_bytes=config,
        network_bytes=network,
        fars_snap_max_m=50.0,
        ambiguity_margin_m=5.0,
    )
    second = build_dependency_package(
        snapshot,
        config_path=Path("operator.toml"),
        config_bytes=config,
        network_bytes=network,
        fars_snap_max_m=50.0,
        ambiguity_margin_m=5.0,
    )
    entries = _zip_entries(first)
    manifest = json.loads(entries["manifest.json"])

    assert first == second
    assert entries["config.original"] == config
    assert entries["network.original"] == network
    assert PRIVATE_PATH.encode() in entries["config.original"]
    assert PRIVATE_PATH.encode() not in entries["config.replay.json"]
    assert PRIVATE_PATH.encode() not in entries["manifest.json"]
    assert (
        manifest["dependency_reference"]["original_config_sha256"]
        == hashlib.sha256(config).hexdigest()
    )
    assert manifest["policy"]["activation_status"] == ACTIVATION_STATUS
    assert manifest["policy"]["specialized_full_history_verifier_required"] is True
    package_text = entries["manifest.json"] + entries["config.replay.json"]
    for forbidden in (b"source_record_id", b"mode_summary", b"snap_result", b"distance_m"):
        assert forbidden not in package_text


def test_atomic_activation_stores_only_package_and_eligible_artifact_with_audit_status(
    tmp_path: Path,
) -> None:
    result = _activate(tmp_path, _snapshot(6), "first")
    artifact = json.loads(_active_bytes(result))
    receipt = result.ingestion.receipt_path.read_text()

    assert result.status == ACTIVATION_STATUS
    assert result.specialized_verifier_required is True
    assert result.ingestion.source_id == context_source_id("Test City")
    assert result.ingestion.raw_snapshot.stat().st_mode & stat.S_IWUSR == 0
    assert artifact["cells"][0]["crash_count"] == 6
    assert PRIVATE_PATH not in json.dumps(artifact)
    assert PRIVATE_PATH not in receipt
    assert "100001" not in json.dumps(artifact)
    assert "historically_valid_potentially_stale" not in receipt
    canonical_fars_context_bytes(artifact)


def test_identical_rerun_reuses_artifacts_and_is_allowed(tmp_path: Path) -> None:
    snapshot = _snapshot(6)
    first = _activate(tmp_path, snapshot, "same-1")
    second = _activate(tmp_path, snapshot, "same-2")

    assert first.ingestion.raw_snapshot == second.ingestion.raw_snapshot
    assert first.ingestion.normalized_path == second.ingestion.normalized_path
    assert _active_bytes(first) == _active_bytes(second)


def test_composition_change_requires_review_and_failure_preserves_previous(
    tmp_path: Path,
) -> None:
    snapshot = _snapshot(6)
    first = _activate(tmp_path, snapshot, "composition-1")
    previous = first.ingestion.current_path.read_bytes()

    with pytest.raises(IngestionRunError) as raised:
        _activate(
            tmp_path,
            snapshot,
            "composition-fail",
            network_bytes=_network(name="Renamed Public Main"),
        )
    assert first.ingestion.current_path.read_bytes() == previous
    failure = raised.value.receipt_path.read_text()
    assert "composition review" not in failure
    assert PRIVATE_PATH not in failure

    accepted = _activate(
        tmp_path,
        snapshot,
        "composition-reviewed",
        network_bytes=_network(name="Renamed Public Main"),
        composition_review_reference="review-COMP-1",
    )
    assert accepted.ingestion.normalized_path != first.ingestion.normalized_path


def test_any_exact_original_config_change_is_hash_bound_and_reviewed(tmp_path: Path) -> None:
    case_root = tmp_path / "config-composition"
    case_root.mkdir()
    snapshot = _snapshot(6)
    first = _activate(case_root, snapshot, "config-1")
    changed_config = _config().replace(
        b"/operator/private/reports.json", b"/different/private/reports.json"
    )

    with pytest.raises(IngestionRunError):
        _activate(case_root, snapshot, "config-fail", config_bytes=changed_config)

    accepted = _activate(
        case_root,
        snapshot,
        "config-reviewed",
        config_bytes=changed_config,
        composition_review_reference="review-CONFIG-1",
    )
    previous = json.loads(_active_bytes(first))["input_lineage"]["config_raw_sha256"]
    current = json.loads(_active_bytes(accepted))["input_lineage"]["config_raw_sha256"]
    assert previous != current


@pytest.mark.parametrize(
    "changes",
    [
        {"fars_snap_max_m": 60.0},
        {"config_bytes": _config(start="2024-04-01")},
    ],
)
def test_method_and_window_changes_require_composition_review(
    tmp_path: Path, changes: dict[str, object]
) -> None:
    case_root = tmp_path / hashlib.sha256(repr(changes).encode()).hexdigest()[:8]
    case_root.mkdir()
    snapshot = _snapshot(6)
    _activate(case_root, snapshot, "method-1")
    with pytest.raises(IngestionRunError):
        _activate(case_root, snapshot, "method-fail", **changes)
    accepted = _activate(
        case_root,
        snapshot,
        "method-reviewed",
        composition_review_reference="review-METHOD-1",
        methodology_change_review_reference="review-METHODOLOGY-1",
        **changes,
    )
    assert accepted.status == ACTIVATION_STATUS


def test_source_accounting_and_cell_regression_need_all_explicit_overrides(
    tmp_path: Path,
) -> None:
    first = _activate(tmp_path, _snapshot(6), "regression-1")
    previous = first.ingestion.current_path.read_bytes()

    with pytest.raises(IngestionRunError):
        _activate(tmp_path, _snapshot(5), "regression-none")
    assert first.ingestion.current_path.read_bytes() == previous

    with pytest.raises(IngestionRunError):
        _activate(
            tmp_path,
            _snapshot(5),
            "regression-partial",
            source_regression_override_reference="source-override-1",
        )
    assert first.ingestion.current_path.read_bytes() == previous

    accepted = _activate(
        tmp_path,
        _snapshot(5),
        "regression-reviewed",
        source_regression_override_reference="source-override-1",
        quality_regression_override_reference="quality-override-1",
    )
    package = _zip_entries(accepted.ingestion.raw_snapshot.read_bytes())
    reviews = json.loads(package["manifest.json"])["reviews"]
    assert reviews["source_regression_override_reference"] == "source-override-1"
    assert json.loads(_active_bytes(accepted))["cells"][0]["crash_count"] == 5


@pytest.mark.parametrize(
    "field",
    ["crash_records_rejected", "person_records_excluded", "cases_excluded"],
)
def test_each_adverse_source_counter_increase_is_a_rollback(field: str) -> None:
    prior = _snapshot(6).evidence.as_dict()
    current = prior.copy()
    current[field] = cast(int, current[field]) + 1

    assert activation._source_rollback({"source_lineage": current}, {"source_lineage": prior})


def test_rejected_source_records_require_source_rollback_override(tmp_path: Path) -> None:
    first = _activate(tmp_path, _snapshot(6), "adverse-source-1")
    previous = first.ingestion.current_path.read_bytes()

    with pytest.raises(IngestionRunError):
        _activate(tmp_path, _snapshot(6, rejected=1), "adverse-source-fail")
    assert first.ingestion.current_path.read_bytes() == previous

    accepted = _activate(
        tmp_path,
        _snapshot(6, rejected=1),
        "adverse-source-reviewed",
        source_regression_override_reference="source-adverse-1",
    )
    package = _zip_entries(accepted.ingestion.raw_snapshot.read_bytes())
    reviews = json.loads(package["manifest.json"])["reviews"]
    source = json.loads(_active_bytes(accepted))["source_lineage"]
    assert reviews["source_regression_override_reference"] == "source-adverse-1"
    assert source["crash_records_rejected"] == 1
    assert source["person_records_excluded"] == 1
    assert source["cases_excluded"] == 1


def test_hard_k_floor_survives_replay_package(tmp_path: Path) -> None:
    result = _activate(
        tmp_path,
        _snapshot(5),
        "hard-k",
        config_bytes=_config(minimum_k=2),
    )
    artifact = json.loads(_active_bytes(result))
    assert artifact["method"]["privacy"]["requested_k"] == 2
    assert artifact["method"]["privacy"]["effective_k"] == 5


def test_package_linkage_and_regenerated_replay_config_are_fail_closed() -> None:
    snapshot = _snapshot(6)
    package_bytes = build_dependency_package(
        snapshot,
        config_path=Path("operator.toml"),
        config_bytes=_config(),
        network_bytes=_network(),
        fars_snap_max_m=50.0,
        ambiguity_margin_m=5.0,
    )
    package = activation._parse_package(package_bytes)
    candidate = activation._normalize(package_bytes, snapshot)
    artifact = cast(dict[str, Any], json.loads(candidate))
    artifact["city_key"] = "forged-city"
    forged = canonical_fars_context_bytes(artifact)
    with pytest.raises(ValueError, match="not linked"):
        activation._validate_candidate(forged, None, package_bytes, snapshot)

    entries = _zip_entries(package_bytes)
    replay = cast(dict[str, Any], json.loads(entries["config.replay.json"]))
    replay["city"] = "forged-city"
    entries["config.replay.json"] = activation._canonical(replay)
    manifest = cast(dict[str, Any], json.loads(entries["manifest.json"]))
    dependency = cast(dict[str, Any], manifest["dependency_reference"])
    dependency["replay_config_sha256"] = hashlib.sha256(entries["config.replay.json"]).hexdigest()
    dependency["replay_config_byte_count"] = len(entries["config.replay.json"])
    entries["manifest.json"] = activation._canonical(manifest)
    tampered = activation._canonical_zip(entries)
    with pytest.raises(ValueError, match="replay config"):
        activation._parse_package(tampered)
    assert package.original_config == _config()


def test_root_preflight_is_exposed_and_mutates_nothing_inside_repository(tmp_path: Path) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    inside = repository / "private"
    with pytest.raises(ValueError, match="outside"):
        require_private_activation_root(inside, repository)
    assert not inside.exists()
    outside = tmp_path / "outside"
    assert require_private_activation_root(outside, repository) == outside.resolve()
    with pytest.raises(ValueError, match="activation root preflight failed"):
        require_private_activation_root("bad\0root", repository)
    with pytest.raises(ValueError, match="repository root preflight failed"):
        require_private_activation_root(outside, "bad\0repository")


def test_derived_source_path_collision_is_rejected_before_mutation(tmp_path: Path) -> None:
    private_root = tmp_path / "private-context"
    repository = private_root / context_source_id("Test City")
    repository.mkdir(parents=True)
    mode_before = stat.S_IMODE(repository.stat().st_mode)

    with pytest.raises(ValueError, match="outside"):
        activate_fars_context_audit_only(
            root=private_root,
            repository_root=repository,
            snapshot=_snapshot(6),
            config_path=Path("operator.toml"),
            config_bytes=_config(),
            network_bytes=_network(),
            fars_snap_max_m=50.0,
            ambiguity_margin_m=5.0,
            clock=_clock,
            attempt_id="source-path-collision",
        )

    assert list(repository.iterdir()) == []
    assert stat.S_IMODE(repository.stat().st_mode) == mode_before


def test_package_cap_and_review_reference_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    snapshot = _snapshot(5)
    monkeypatch.setattr(activation, "MAX_DEPENDENCY_PACKAGE_BYTES", 100)
    with pytest.raises(ValueError, match="byte safety limit"):
        build_dependency_package(
            snapshot,
            config_path=Path("operator.toml"),
            config_bytes=_config(),
            network_bytes=_network(),
            fars_snap_max_m=50.0,
            ambiguity_margin_m=5.0,
        )
    with pytest.raises(ValueError, match="nonempty safe"):
        activation._review_reference("   ", "review")
    with pytest.raises(ValueError, match="nonempty safe"):
        activation._review_reference("safe\u202ereversed", "review")


def test_manifest_bytes_and_individual_zip_entry_caps_are_canonical(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    package = build_dependency_package(
        _snapshot(6),
        config_path=Path("operator.toml"),
        config_bytes=_config(),
        network_bytes=_network(),
        fars_snap_max_m=50.0,
        ambiguity_margin_m=5.0,
    )
    entries = _zip_entries(package)
    manifest = json.loads(entries["manifest.json"])
    entries["manifest.json"] = (json.dumps(manifest, indent=2) + "\n").encode()
    with pytest.raises(ValueError, match="manifest encoding"):
        activation._parse_package(activation._canonical_zip(entries))

    entries = _zip_entries(package)
    monkeypatch.setitem(activation._ENTRY_LIMITS, "config.original", 1)
    with pytest.raises(ValueError, match="entry exceeds"):
        activation._parse_package(activation._canonical_zip(entries))


def test_manifest_has_exactly_five_distinct_typed_review_gates() -> None:
    snapshot = _snapshot(6)
    package = build_dependency_package(
        snapshot,
        config_path=Path("operator.toml"),
        config_bytes=_config(),
        network_bytes=_network(),
        fars_snap_max_m=50.0,
        ambiguity_margin_m=5.0,
        composition_review_reference="composition-1",
        methodology_change_review_reference="methodology-1",
        privacy_regression_override_reference="privacy-1",
        source_regression_override_reference="source-1",
        quality_regression_override_reference="quality-1",
    )
    reviews = json.loads(_zip_entries(package)["manifest.json"])["reviews"]
    assert set(reviews) == {
        "composition_review_reference",
        "methodology_change_review_reference",
        "privacy_regression_override_reference",
        "source_regression_override_reference",
        "quality_regression_override_reference",
    }
    assert len(set(reviews.values())) == 5

    with pytest.raises(ValueError, match="distinct"):
        build_dependency_package(
            snapshot,
            config_path=Path("operator.toml"),
            config_bytes=_config(),
            network_bytes=_network(),
            fars_snap_max_m=50.0,
            ambiguity_margin_m=5.0,
            composition_review_reference="reused-review",
            methodology_change_review_reference="reused-review",
        )


def test_privacy_regression_needs_its_own_gate_and_k_never_falls_below_five(
    tmp_path: Path,
) -> None:
    snapshot = _snapshot(6)
    _activate(tmp_path, snapshot, "privacy-1", config_bytes=_config(minimum_k=6))
    with pytest.raises(IngestionRunError):
        _activate(
            tmp_path,
            snapshot,
            "privacy-wrong-gate",
            config_bytes=_config(minimum_k=2),
            composition_review_reference="composition-only",
        )
    accepted = _activate(
        tmp_path,
        snapshot,
        "privacy-reviewed",
        config_bytes=_config(minimum_k=2),
        composition_review_reference="composition-privacy",
        privacy_regression_override_reference="privacy-override",
    )
    privacy = json.loads(_active_bytes(accepted))["method"]["privacy"]
    assert privacy["requested_k"] == 2
    assert privacy["effective_k"] == 5


def test_methodology_comparison_retains_static_privacy_contract() -> None:
    snapshot = _snapshot(6)
    artifact = cast(
        dict[str, Any],
        json.loads(
            activation._normalize(
                build_dependency_package(
                    snapshot,
                    config_path=Path("operator.toml"),
                    config_bytes=_config(),
                    network_bytes=_network(),
                    fars_snap_max_m=50.0,
                    ambiguity_margin_m=5.0,
                ),
                snapshot,
            )
        ),
    )
    dynamic = json.loads(json.dumps(artifact))
    dynamic["method"]["privacy"]["requested_k"] = 4
    dynamic["method"]["privacy"]["effective_k"] = 5
    assert not activation._methodology_changed(dynamic, artifact)
    static = json.loads(json.dumps(artifact))
    static["method"]["privacy"]["eligibility_rule"] = "changed-rule"
    assert activation._methodology_changed(static, artifact)


@pytest.mark.parametrize(
    ("block", "mutation"),
    [
        ("source_reference", lambda value: value.update({"extra": "forged"})),
        ("replay", lambda value: value.update({"extra": 1})),
        ("reviews", lambda value: value.pop("quality_regression_override_reference")),
    ],
)
def test_nested_manifest_shapes_are_closed(block: str, mutation: Any) -> None:
    package = build_dependency_package(
        _snapshot(6),
        config_path=Path("operator.toml"),
        config_bytes=_config(),
        network_bytes=_network(),
        fars_snap_max_m=50.0,
        ambiguity_margin_m=5.0,
    )
    entries = _zip_entries(package)
    manifest = json.loads(entries["manifest.json"])
    mutation(manifest[block])
    entries["manifest.json"] = activation._canonical(manifest)
    with pytest.raises(ValueError):
        activation._parse_package(activation._canonical_zip(entries))
