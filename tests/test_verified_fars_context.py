from __future__ import annotations

import datetime as dt
import hashlib
import inspect
import io
import json
import stat
import zipfile
from collections.abc import Callable
from pathlib import Path

import pytest

import nearmiss.fars_context_activation as activation
import nearmiss.verified_outcomes as joined_verifier
from nearmiss.adapters.fars_joined import collect_joined, read_joined_export_bytes
from nearmiss.fars_context_activation import (
    VerifiedFarsContextEvidence,
    activate_fars_context_audit_only,
    activate_fars_context_full_history,
    context_source_id,
    verify_active_fars_context,
)
from nearmiss.ingestion import IngestionRunError, run_ingestion
from nearmiss.joined_outcome_artifacts import (
    build_joined_outcome_artifact,
    canonical_joined_outcome_artifact_bytes,
)
from nearmiss.verified_outcomes import VerificationError

URL = "https://static.nhtsa.gov/nhtsa/downloads/FARS/2024/National/FARS2024.zip"


def _raw(number: int, *, offset: int = 0) -> bytes:
    accident = ["STATE,ST_CASE,YEAR,MONTH,DAY,HOUR,MINUTE,LATITUDE,LONGITUD,FATALS"]
    person = ["STATE,ST_CASE,VEH_NO,PER_NO,PER_TYP,INJ_SEV,BODY_TYP"]
    for index in range(number):
        case = 100001 + offset + index
        accident.append(f"6,{case},2024,5,1,12,0,38.540000,-121.740000,1")
        person.append(f"6,{case},0,1,5,4,")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("FARS/accident.csv", "\n".join(accident) + "\n")
        archive.writestr("FARS/person.csv", "\n".join(person) + "\n")
    return buffer.getvalue()


def _joined_normalized(raw: bytes) -> bytes:
    outcomes, summaries, crash, person = collect_joined(
        read_joined_export_bytes(raw), release_status="final"
    )
    return canonical_joined_outcome_artifact_bytes(
        build_joined_outcome_artifact(
            outcomes,
            summaries,
            person,
            crash,
            distribution_url=URL,
            max_invalid_fraction=0.05,
        )
    )


def _clock(hour: int) -> Callable[[], dt.datetime]:
    return lambda: dt.datetime(2026, 7, 12, hour, tzinfo=dt.UTC)


def _ingest_joined(root: Path, attempt: str, hour: int, *, offset: int = 0) -> None:
    raw = _raw(6, offset=offset)
    normalized = _joined_normalized(raw)
    run_ingestion(
        root=root,
        source_id="fars-joined",
        fetch=lambda: raw,
        normalize=lambda _raw: normalized,
        attempt_id=attempt,
        clock=_clock(hour),
    )


def _config(*, minimum_k: int = 5) -> bytes:
    return f"""city = "Test City"
streets = "/private/network.geojson"
reports = "/private/reports.json"
exposure = "/private/exposure.json"

[window]
start = "2024-01-01"
end = "2024-12-31"

[thresholds]
min_publish_n = {minimum_k}
""".encode()


def _network(*, name: str = "Main") -> bytes:
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


def _activate(
    root: Path,
    repository: Path,
    attempt: str,
    hour: int,
    **changes: object,
) -> activation.FarsContextAuditActivation:
    values: dict[str, object] = {
        "root": root,
        "repository_root": repository,
        "joined_root": root,
        "config_path": Path("operator.toml"),
        "config_bytes": _config(),
        "network_bytes": _network(),
        "fars_snap_max_m": 50.0,
        "ambiguity_margin_m": 5.0,
        "attempt_id": attempt,
        "clock": _clock(hour),
    }
    values.update(changes)
    full = activate_fars_context_full_history(**values)  # type: ignore[arg-type]
    assert full.evidence.status == "verified_at_activation"
    return full.activation


@pytest.fixture
def store(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "private"
    repository = tmp_path / "repo"
    repository.mkdir()
    _ingest_joined(root, "joined-1", 18)
    _activate(root, repository, "context-1", 19)
    return root, repository


def test_full_history_verifier_returns_only_current_usable_evidence(
    store: tuple[Path, Path],
) -> None:
    root, _repository = store
    evidence = verify_active_fars_context(root, "Test City")

    assert isinstance(evidence, VerifiedFarsContextEvidence)
    assert evidence.status == "verified_at_observation"
    assert evidence.attempt_id == "context-1"
    assert evidence.joined_source.attempt_id == "joined-1"
    assert evidence.effective_k == 5
    assert evidence.eligible_cell_count == 1
    assert "cells" not in evidence.as_dict()


def test_production_activation_requires_joined_root() -> None:
    parameter = inspect.signature(activate_fars_context_full_history).parameters["joined_root"]
    assert parameter.default is inspect.Parameter.empty


def test_production_result_is_bound_to_exact_activated_marker(tmp_path: Path) -> None:
    root = tmp_path / "private"
    repository = tmp_path / "repo"
    repository.mkdir()
    _ingest_joined(root, "joined-production", 18)
    result = activate_fars_context_full_history(
        root=root,
        repository_root=repository,
        joined_root=root,
        config_path=Path("operator.toml"),
        config_bytes=_config(),
        network_bytes=_network(),
        fars_snap_max_m=50.0,
        ambiguity_margin_m=5.0,
        attempt_id="context-production",
        clock=_clock(19),
    )

    assert result.evidence.status == "verified_at_activation"
    assert result.evidence.attempt_id == "context-production"
    assert result.evidence.raw_sha256 == result.activation.ingestion.raw_sha256
    assert result.evidence.normalized_sha256 == result.activation.ingestion.normalized_sha256
    marker = json.loads(result.activation.ingestion.current_path.read_text())
    assert marker["attempt_id"] == result.evidence.attempt_id


def test_corrupt_prior_history_preserves_current_marker(store: tuple[Path, Path]) -> None:
    root, repository = store
    source = root / context_source_id("Test City")
    current = source / "normalized" / "current.json"
    before = current.read_bytes()
    history = source / "receipts" / "context-1.json"
    history.chmod(0o600)
    history.write_bytes(history.read_bytes() + b" ")
    history.chmod(0o400)

    with pytest.raises(IngestionRunError):
        _activate(root, repository, "context-after-corruption", 20)
    assert current.read_bytes() == before


def _replace_private(path: Path, payload: bytes) -> None:
    path.chmod(0o600)
    path.write_bytes(payload)
    path.chmod(0o400)


def test_joined_raw_race_after_precommit_rolls_back_prior_current(
    store: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    root, repository = store
    context_source = root / context_source_id("Test City")
    current = context_source / "normalized" / "current.json"
    previous = current.read_bytes()
    original = activation._verify_activated_context_locked

    def race(*args: object, **kwargs: object) -> VerifiedFarsContextEvidence:
        joined_current = json.loads(
            (root / "fars-joined" / "normalized" / "current.json").read_text()
        )
        raw = root / "fars-joined" / "raw" / "sha256" / f"{joined_current['raw_sha256']}.bin"
        _replace_private(raw, raw.read_bytes() + b"forged-after-precommit")
        return original(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(activation, "_verify_activated_context_locked", race)
    with pytest.raises(IngestionRunError):
        _activate(root, repository, "context-joined-raw-race", 20)

    assert current.read_bytes() == previous
    failure = json.loads((context_source / "receipts" / "context-joined-raw-race.json").read_text())
    assert failure["status"] == "failure"
    assert failure["activated"] is False


def test_backdated_joined_current_after_precommit_removes_first_current(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "private"
    repository = tmp_path / "repo"
    repository.mkdir()
    _ingest_joined(root, "joined-backdate", 18)
    original = activation._verify_activated_context_locked

    def race(*args: object, **kwargs: object) -> VerifiedFarsContextEvidence:
        joined_source = root / "fars-joined"
        current_path = joined_source / "normalized" / "current.json"
        receipt_path = joined_source / "receipts" / "joined-backdate.json"
        receipt = json.loads(current_path.read_text())
        receipt["started_at"] = "2026-07-12T17:00:00Z"
        receipt["completed_at"] = "2026-07-12T17:00:00Z"
        payload = (json.dumps(receipt, indent=2, sort_keys=True) + "\n").encode()
        _replace_private(current_path, payload)
        _replace_private(receipt_path, payload)
        return original(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(activation, "_verify_activated_context_locked", race)
    with pytest.raises(IngestionRunError):
        _activate(root, repository, "context-backdated-race", 19)

    context_source = root / context_source_id("Test City")
    assert not (context_source / "normalized" / "current.json").exists()
    failure = json.loads((context_source / "receipts" / "context-backdated-race.json").read_text())
    assert failure["status"] == "failure"
    assert failure["activated"] is False


def test_historical_joined_generation_is_replayed_once_and_current_ref_must_match(
    store: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    root, repository = store
    _ingest_joined(root, "joined-2", 20, offset=100)
    replay_count = 0
    original = joined_verifier._replay_joined

    def counted(raw: bytes, normalized: bytes, artifact: object) -> None:
        nonlocal replay_count
        replay_count += 1
        original(raw, normalized, artifact)  # type: ignore[arg-type]

    monkeypatch.setattr(joined_verifier, "_replay_joined", counted)
    with pytest.raises(VerificationError, match="stale"):
        verify_active_fars_context(root, "Test City")
    assert replay_count == 2

    _activate(root, repository, "context-2", 21)
    assert verify_active_fars_context(root, "Test City").attempt_id == "context-2"


def test_context_start_must_not_predate_referenced_joined_completion(tmp_path: Path) -> None:
    root = tmp_path / "private"
    repository = tmp_path / "repo"
    repository.mkdir()
    _ingest_joined(root, "joined-late", 20)
    moments = iter(
        (
            dt.datetime(2026, 7, 12, 19, tzinfo=dt.UTC),
            dt.datetime(2026, 7, 12, 21, tzinfo=dt.UTC),
        )
    )
    with pytest.raises(IngestionRunError):
        _activate(root, repository, "context-early", 19, clock=lambda: next(moments))
    assert not (root / context_source_id("Test City") / "normalized" / "current.json").exists()


def test_nonadjacent_normalized_reuse_is_rejected_before_current_replacement(
    store: tuple[Path, Path],
) -> None:
    root, repository = store
    first_current = root / context_source_id("Test City") / "normalized" / "current.json"
    _activate(
        root,
        repository,
        "context-b",
        20,
        network_bytes=_network(name="Changed"),
        composition_review_reference="composition-b",
    )
    b_marker = first_current.read_bytes()

    with pytest.raises(IngestionRunError):
        _activate(
            root,
            repository,
            "context-a-again",
            21,
            composition_review_reference="composition-a-again",
        )
    assert first_current.read_bytes() == b_marker


def test_immediate_identical_generation_remains_allowed(store: tuple[Path, Path]) -> None:
    root, repository = store
    repeated = _activate(root, repository, "context-identical", 20)
    assert verify_active_fars_context(root, "Test City").attempt_id == "context-identical"
    assert (
        repeated.ingestion.normalized_sha256
        == json.loads(
            (root / context_source_id("Test City") / "receipts" / "context-1.json").read_text()
        )["normalized_sha256"]
    )


@pytest.mark.parametrize("target", ["root", "source", "raw", "normalized", "receipts"])
def test_exact_directory_modes_are_required(store: tuple[Path, Path], target: str) -> None:
    root, _repository = store
    source = root / context_source_id("Test City")
    paths = {
        "root": root,
        "source": source,
        "raw": source / "raw",
        "normalized": source / "normalized",
        "receipts": source / "receipts",
    }
    paths[target].chmod(0o750)
    with pytest.raises(VerificationError, match="filesystem"):
        verify_active_fars_context(root, "Test City")


def test_context_lock_and_unsafe_file_metadata_fail_closed(store: tuple[Path, Path]) -> None:
    root, _repository = store
    source = root / context_source_id("Test City")
    lock = source / ".ingestion.lock"
    lock.mkdir(mode=0o700)
    with pytest.raises(VerificationError, match="locked"):
        verify_active_fars_context(root, "Test City")
    lock.rmdir()

    artifact = next((source / "normalized" / "sha256").glob("*.bin"))
    artifact.chmod(0o600)
    with pytest.raises(VerificationError, match="filesystem"):
        verify_active_fars_context(root, "Test City")


@pytest.mark.parametrize("kind", ["package", "artifact", "current"])
def test_tampered_context_bytes_fail_closed(store: tuple[Path, Path], kind: str) -> None:
    root, _repository = store
    source = root / context_source_id("Test City")
    if kind == "package":
        target = next((source / "raw" / "sha256").glob("*.bin"))
    elif kind == "artifact":
        target = next((source / "normalized" / "sha256").glob("*.bin"))
    else:
        target = source / "normalized" / "current.json"
    target.chmod(0o600)
    target.write_bytes(target.read_bytes() + b" ")
    target.chmod(0o400)

    with pytest.raises(VerificationError):
        verify_active_fars_context(root, "Test City")


def test_every_historical_generation_is_bound_to_requested_city(
    store: tuple[Path, Path],
) -> None:
    root, repository = store
    joined = joined_verifier._load_verified_active_fars_joined_snapshot(root)
    other_config = _config().replace(b"Test City", b"Other City")
    activate_fars_context_audit_only(
        root=root,
        repository_root=repository,
        snapshot=joined,
        config_path=Path("operator.toml"),
        config_bytes=other_config,
        network_bytes=_network(),
        fars_snap_max_m=50.0,
        ambiguity_margin_m=5.0,
        attempt_id="other-context",
        clock=_clock(18),
    )
    expected_source = root / context_source_id("Test City")
    other_source = root / context_source_id("Other City")
    other_receipt = json.loads((other_source / "receipts" / "other-context.json").read_text())
    other_receipt.update(
        {
            "attempt_id": "foreign-history",
            "source_id": context_source_id("Test City"),
            "started_at": "2026-07-12T18:00:00Z",
            "completed_at": "2026-07-12T18:00:00Z",
        }
    )
    for area, digest_key in (("raw", "raw_sha256"), ("normalized", "normalized_sha256")):
        digest = other_receipt[digest_key]
        source_file = other_source / area / "sha256" / f"{digest}.bin"
        destination = expected_source / area / "sha256" / f"{digest}.bin"
        destination.write_bytes(source_file.read_bytes())
        destination.chmod(0o400)
    foreign_bytes = (json.dumps(other_receipt, indent=2, sort_keys=True) + "\n").encode()
    foreign_receipt = expected_source / "receipts" / "foreign-history.json"
    foreign_receipt.write_bytes(foreign_bytes)
    foreign_receipt.chmod(0o400)

    current_path = expected_source / "normalized" / "current.json"
    current = json.loads(current_path.read_text())
    current["previous_normalized_sha256"] = other_receipt["normalized_sha256"]
    current_bytes = (json.dumps(current, indent=2, sort_keys=True) + "\n").encode()
    for target in (
        current_path,
        expected_source / "receipts" / "context-1.json",
    ):
        target.chmod(0o600)
        target.write_bytes(current_bytes)
        target.chmod(0o400)

    with pytest.raises(VerificationError, match="historical city"):
        verify_active_fars_context(root, "Test City")


def test_evidence_cannot_be_forged(store: tuple[Path, Path]) -> None:
    root, _repository = store
    evidence = verify_active_fars_context(root, "Test City")
    with pytest.raises(VerificationError, match="internal proof"):
        VerifiedFarsContextEvidence(
            source_id=evidence.source_id,
            city_key=evidence.city_key,
            attempt_id=evidence.attempt_id,
            raw_sha256=hashlib.sha256(b"raw").hexdigest(),
            normalized_sha256=hashlib.sha256(b"normalized").hexdigest(),
            effective_k=5,
            eligible_cell_count=1,
            joined_source=evidence.joined_source,
            status="verified_at_activation",
            _proof_token=object(),
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("source_id", "fars-context-wrong"),
        ("city_key", "Other City"),
        ("attempt_id", "unsafe/attempt"),
        ("raw_sha256", "0" * 63),
        ("effective_k", 4),
        ("effective_k", True),
        ("eligible_cell_count", True),
    ],
)
def test_internal_token_does_not_bypass_evidence_invariants(
    store: tuple[Path, Path], field: str, value: object
) -> None:
    evidence = verify_active_fars_context(store[0], "Test City")
    values: dict[str, object] = {
        "source_id": evidence.source_id,
        "city_key": evidence.city_key,
        "attempt_id": evidence.attempt_id,
        "raw_sha256": evidence.raw_sha256,
        "normalized_sha256": evidence.normalized_sha256,
        "effective_k": evidence.effective_k,
        "eligible_cell_count": evidence.eligible_cell_count,
        "joined_source": evidence.joined_source,
        "status": "verified_at_activation",
    }
    values[field] = value
    with pytest.raises(VerificationError, match="internal proof"):
        VerifiedFarsContextEvidence(
            **values,  # type: ignore[arg-type]
            _proof_token=activation._CONTEXT_PROOF_TOKEN,
        )


def test_file_mode_fixture_is_exact(store: tuple[Path, Path]) -> None:
    root, _repository = store
    source = root / context_source_id("Test City")
    assert stat.S_IMODE(source.stat().st_mode) == 0o700
    assert all(
        stat.S_IMODE(path.stat().st_mode) == 0o400 for path in (source / "receipts").glob("*.json")
    )


def test_requested_city_selects_a_collision_resistant_source(store: tuple[Path, Path]) -> None:
    root, _repository = store
    with pytest.raises(VerificationError, match="filesystem"):
        verify_active_fars_context(root, "Other City")
