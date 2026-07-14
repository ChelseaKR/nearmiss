# SPDX-License-Identifier: Apache-2.0
"""Production-boundary tests for exact fixed-year FARS activation."""

from __future__ import annotations

import hashlib
import inspect
import io
import json
import os
import stat
import zipfile
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator, FormatChecker

import nearmiss.fars_year_activation as activation
import nearmiss.fars_year_contracts as year_contracts
import nearmiss.joined_outcome_artifacts_v2 as artifacts_v2
import nearmiss.verified_fars_years as verifier
import nearmiss.verified_outcomes as lineage
from nearmiss.ingestion import IngestionError, IngestionRunError, run_ingestion
from nearmiss.verified_outcomes import VerificationError

ROOT = Path(__file__).resolve().parents[1]
BASE_ACCIDENT = (
    (ROOT / "tests" / "fixtures" / "fars" / "accident.csv")
    .read_bytes()
    .replace(b",2023,", b",2024,")
)
PERSON = b"""STATE,ST_CASE,VEH_NO,PER_NO,PER_TYP,INJ_SEV,BODY_TYP
6,100001,1,1,1,4,4
6,100001,0,1,5,2,
6,100002,1,1,1,4,80
6,100002,0,1,6,4,
"""


def _accident(year: int) -> bytes:
    lines = BASE_ACCIDENT.decode().replace(",2024,", f",{year},").splitlines()
    result = [lines[0].replace(",FATALS", ",COUNTY,FATALS")]
    for line, county in zip(lines[1:3], ("113", "997"), strict=True):
        values = line.split(",")
        values.insert(-1, county)
        result.append(",".join(values))
    encoding = "cp1252" if year == 2020 else "utf-8-sig"
    return ("\n".join(result) + "\n").encode(encoding)


def _archive(year: int) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in (
            ("National/accident.csv", _accident(year)),
            ("National/person.csv", PERSON),
        ):
            member = zipfile.ZipInfo(name, date_time=(year, 1, 1, 0, 0, 0))
            member.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(member, payload)
    return buffer.getvalue()


def _archive_with_comment(year: int, comment_size: int) -> bytes:
    buffer = io.BytesIO(_archive(year))
    with zipfile.ZipFile(buffer, "a") as archive:
        archive.comment = b"reviewed-padding-" + b"x" * comment_size
    return buffer.getvalue()


@pytest.fixture(autouse=True)
def _register_exact_fixture_archives(monkeypatch: pytest.MonkeyPatch) -> None:
    history: dict[int, tuple[Any, ...]] = {}
    contracts: dict[int, Any] = {}
    for year, registered_history in year_contracts.FARS_YEAR_CONTRACT_HISTORY.items():
        raw = _archive(year)
        raw_sha256 = hashlib.sha256(raw).hexdigest()
        fixture_history: list[Any] = []
        for registered in registered_history:
            if registered.revision == 1:
                fixture = replace(
                    registered,
                    source_revision_id=f"reviewed-20260712-{raw_sha256[:12]}",
                    raw_size_bytes=len(raw),
                    raw_sha256=raw_sha256,
                )
            else:
                fixture = replace(
                    registered,
                    predecessor_contract_sha256=year_contracts._unregistered_contract_sha256(
                        fixture_history[-1]
                    ),
                    source_revision_id=year_contracts._2024_arf_source_revision_id(raw_sha256),
                    raw_size_bytes=len(raw),
                    raw_sha256=raw_sha256,
                )
            fixture_history.append(fixture)
        history[year] = tuple(fixture_history)
        contracts[year] = fixture_history[-1]
    fixture_2024 = history[2024]
    monkeypatch.setattr(
        year_contracts,
        "_REVIEWED_2024_R1_CONTRACT_SHA256",
        year_contracts._unregistered_contract_sha256(fixture_2024[0]),
    )
    monkeypatch.setattr(
        year_contracts,
        "_REVIEWED_2024_ARF_CONTRACT_SHA256",
        year_contracts._unregistered_contract_sha256(fixture_2024[1]),
    )
    year_contracts.validate_fars_year_contract_registry(history)
    monkeypatch.setattr(year_contracts, "FARS_YEAR_CONTRACT_HISTORY", history)
    monkeypatch.setattr(year_contracts, "FARS_YEAR_CONTRACTS", contracts)
    monkeypatch.setattr(artifacts_v2, "FARS_YEAR_CONTRACT_HISTORY", history)
    schema = artifacts_v2._schema()
    monkeypatch.setattr(
        artifacts_v2,
        "_VALIDATOR",
        Draft202012Validator(schema, format_checker=FormatChecker()),
    )


def _write_archive(tmp_path: Path, year: int = 2024) -> Path:
    path = tmp_path / f"fars-{year}.zip"
    path.write_bytes(_archive(year))
    return path


def _activate(
    tmp_path: Path,
    *,
    year: int = 2024,
    contract_revision: int = 1,
    attempt_id: str = "annual-activation",
) -> verifier.VerifiedFarsYearEvidence:
    return activation.activate_fars_year(
        root=tmp_path / "private",
        repository_root=ROOT,
        raw_archive_path=_write_archive(tmp_path, year),
        year=year,
        contract_revision=contract_revision,
        attempt_id=attempt_id,
    )


def test_activation_is_exact_locked_and_returns_only_aggregate_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_history = verifier._validate_fars_year_history_candidate_locked
    original_activated = verifier._verify_activated_fars_year_locked
    original_preflight = verifier._preflight_fars_year_ingestion_locked
    stages: list[tuple[str, int, int]] = []

    def preflight(
        source_root: Path,
        *,
        year: int,
        contract_revision: int,
    ) -> verifier._FarsYearIngestionPreflight:
        assert stat.S_ISDIR((source_root / ".ingestion.lock").stat().st_mode)
        stages.append(("preflight", year, contract_revision))
        return original_preflight(
            source_root,
            year=year,
            contract_revision=contract_revision,
        )

    def history(
        source_root: Path,
        candidate: bytes,
        *,
        year: int,
        contract_revision: int,
        started_at: str,
        expected_preflight: verifier._FarsYearIngestionPreflight,
    ) -> None:
        assert stat.S_ISDIR((source_root / ".ingestion.lock").stat().st_mode)
        assert started_at.endswith("Z")
        stages.append(("history", year, contract_revision))
        original_history(
            source_root,
            candidate,
            year=year,
            contract_revision=contract_revision,
            started_at=started_at,
            expected_preflight=expected_preflight,
        )

    def activated(
        source_root: Path,
        candidate: bytes,
        success_marker: bytes,
        *,
        year: int,
        contract_revision: int,
        expected_preflight: verifier._FarsYearIngestionPreflight,
    ) -> verifier._VerifiedFarsYearSnapshot:
        assert stat.S_ISDIR((source_root / ".ingestion.lock").stat().st_mode)
        assert (source_root / "normalized" / "current.json").read_bytes() == success_marker
        stages.append(("activated", year, contract_revision))
        return original_activated(
            source_root,
            candidate,
            success_marker,
            year=year,
            contract_revision=contract_revision,
            expected_preflight=expected_preflight,
        )

    monkeypatch.setattr(verifier, "_preflight_fars_year_ingestion_locked", preflight)
    monkeypatch.setattr(verifier, "_validate_fars_year_history_candidate_locked", history)
    monkeypatch.setattr(verifier, "_verify_activated_fars_year_locked", activated)
    evidence = _activate(tmp_path)

    assert stages == [
        ("preflight", 2024, 1),
        ("history", 2024, 1),
        ("activated", 2024, 1),
    ]
    assert evidence.source_id == "fars-joined-2024"
    assert evidence.dataset_year == 2024
    assert evidence.contract_revision == 1
    assert evidence.attempt_id == "annual-activation"
    assert evidence.raw_sha256 == hashlib.sha256(_archive(2024)).hexdigest()
    assert not any(isinstance(value, Path) for value in evidence.as_dict().values())
    assert (
        verifier.verify_active_fars_year(
            tmp_path / "private",
            year=2024,
            contract_revision=1,
        )
        == evidence
    )


def test_same_exact_revision_replays_complete_prior_history(tmp_path: Path) -> None:
    first = _activate(tmp_path, attempt_id="annual-first")
    second = _activate(tmp_path, attempt_id="annual-second")

    assert first.normalized_sha256 == second.normalized_sha256
    assert first.raw_sha256 == second.raw_sha256
    assert second.attempt_id == "annual-second"
    source = tmp_path / "private" / "fars-joined-2024"
    success_receipts = [
        json.loads(path.read_bytes())
        for path in sorted((source / "receipts").glob("*.json"))
        if json.loads(path.read_bytes())["status"] == "success"
    ]
    assert len(success_receipts) == 2
    assert success_receipts[1]["previous_normalized_sha256"] == first.normalized_sha256
    assert (
        verifier.verify_active_fars_year(tmp_path / "private", year=2024, contract_revision=1)
        == second
    )


def test_exact_2024_arf_provenance_correction_activates_over_the_same_archive(
    tmp_path: Path,
) -> None:
    r1 = _activate(tmp_path, contract_revision=1, attempt_id="annual-r1-final")
    r2 = _activate(tmp_path, contract_revision=2, attempt_id="annual-r2-arf")

    assert r1.raw_sha256 == r2.raw_sha256
    assert r1.crash_mapping_version == r2.crash_mapping_version == "1.0.0"
    assert r1.person_mapping_version == r2.person_mapping_version == "1.0.0"
    assert r1.release_status == "final"
    assert r2.release_status == "annual_report_file"
    assert r1.normalized_sha256 != r2.normalized_sha256
    assert (
        verifier.verify_active_fars_year(
            tmp_path / "private",
            year=2024,
            contract_revision=2,
        )
        == r2
    )


def test_smaller_registered_followup_archive_activates_after_larger_revision(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    larger_raw = _archive_with_comment(2024, 20_000)
    smaller_raw = _archive(2024)
    assert len(smaller_raw) < len(larger_raw)
    registered = year_contracts.fars_year_contract_revision(2024, 1)
    first = replace(
        registered,
        source_revision_id=f"reviewed-20260713-{hashlib.sha256(larger_raw).hexdigest()[:12]}",
        raw_size_bytes=len(larger_raw),
        raw_sha256=hashlib.sha256(larger_raw).hexdigest(),
    )
    initial_history = dict(year_contracts.FARS_YEAR_CONTRACT_HISTORY)
    initial_history[2024] = (first,)
    initial_contracts = dict(year_contracts.FARS_YEAR_CONTRACTS)
    initial_contracts[2024] = first
    monkeypatch.setattr(year_contracts, "FARS_YEAR_CONTRACT_HISTORY", initial_history)
    monkeypatch.setattr(year_contracts, "FARS_YEAR_CONTRACTS", initial_contracts)
    second = replace(
        first,
        revision=2,
        predecessor_contract_sha256=year_contracts.fars_year_contract_sha256(first),
        transition_review_reference="reviewed-smaller-r2-transition",
        source_revision_id=f"reviewed-20260714-{hashlib.sha256(smaller_raw).hexdigest()[:12]}",
        raw_size_bytes=len(smaller_raw),
        raw_sha256=hashlib.sha256(smaller_raw).hexdigest(),
    )
    history = dict(initial_history)
    history[2024] = (first, second)
    contracts = dict(initial_contracts)
    contracts[2024] = second
    year_contracts.validate_fars_year_contract_registry(history)
    monkeypatch.setattr(year_contracts, "FARS_YEAR_CONTRACT_HISTORY", history)
    monkeypatch.setattr(year_contracts, "FARS_YEAR_CONTRACTS", contracts)
    monkeypatch.setattr(artifacts_v2, "FARS_YEAR_CONTRACT_HISTORY", history)
    monkeypatch.setattr(
        artifacts_v2,
        "_VALIDATOR",
        Draft202012Validator(artifacts_v2._schema(), format_checker=FormatChecker()),
    )
    larger_path = tmp_path / "larger-r1.zip"
    smaller_path = tmp_path / "smaller-r2.zip"
    larger_path.write_bytes(larger_raw)
    smaller_path.write_bytes(smaller_raw)
    private = tmp_path / "private"

    first_evidence = activation.activate_fars_year(
        root=private,
        repository_root=ROOT,
        raw_archive_path=larger_path,
        year=2024,
        contract_revision=1,
        attempt_id="larger-r1",
    )
    second_evidence = activation.activate_fars_year(
        root=private,
        repository_root=ROOT,
        raw_archive_path=smaller_path,
        year=2024,
        contract_revision=2,
        attempt_id="smaller-r2",
    )

    assert first_evidence.contract_revision == 1
    assert second_evidence.contract_revision == 2
    assert second_evidence.raw_sha256 == second.raw_sha256
    assert second_evidence.attempt_id == "smaller-r2"


@pytest.mark.parametrize("year", year_contracts.SUPPORTED_FARS_YEARS)
def test_each_supported_year_uses_its_distinct_source_store(tmp_path: Path, year: int) -> None:
    evidence = _activate(tmp_path, year=year, attempt_id=f"annual-{year}")

    assert evidence.dataset_year == year
    assert evidence.source_id == f"fars-joined-{year}"
    assert (tmp_path / "private" / f"fars-joined-{year}" / "normalized" / "current.json").is_file()


def test_unregistered_revision_fails_before_private_storage_or_archive_read(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="not registered"):
        activation.activate_fars_year(
            root=tmp_path / "private",
            repository_root=ROOT,
            raw_archive_path=tmp_path / "missing.zip",
            year=2024,
            contract_revision=3,
            attempt_id="must-not-run",
        )
    assert not (tmp_path / "private").exists()


def test_locked_post_activation_verification_failure_rolls_back_current(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = _activate(tmp_path, attempt_id="annual-good")
    current = tmp_path / "private" / first.source_id / "normalized" / "current.json"
    marker_before = current.read_bytes()

    def reject(*_args: object, **_kwargs: object) -> Any:
        raise VerificationError("test post-activation rejection")

    monkeypatch.setattr(verifier, "_verify_activated_fars_year_locked", reject)
    with pytest.raises(IngestionRunError):
        _activate(tmp_path, attempt_id="annual-rejected")
    assert current.read_bytes() == marker_before
    assert (
        verifier.verify_active_fars_year(
            tmp_path / "private", year=2024, contract_revision=1
        ).attempt_id
        == "annual-good"
    )


def test_receipt_capacity_is_rejected_before_fetch_or_new_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = _activate(tmp_path, attempt_id="annual-cap-first")
    source = tmp_path / "private" / first.source_id
    receipts = source / "receipts"
    before = {path.name: path.read_bytes() for path in receipts.iterdir()}
    monkeypatch.setattr(lineage, "_MAX_RECEIPTS", len(before))
    fetched = False

    def forbidden_fetch(*_args: object, **_kwargs: object) -> bytes:
        nonlocal fetched
        fetched = True
        raise AssertionError("receipt-cap preflight must run before archive fetch")

    monkeypatch.setattr(activation, "_read_raw_archive", forbidden_fetch)
    with pytest.raises(VerificationError, match="no capacity"):
        _activate(tmp_path, attempt_id="annual-cap-rejected")

    assert fetched is False
    assert {path.name: path.read_bytes() for path in receipts.iterdir()} == before
    assert not (source / ".ingestion.lock").exists()


def test_success_generation_capacity_is_reserved_before_fetch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = _activate(tmp_path, attempt_id="annual-success-cap-first")
    source = tmp_path / "private" / first.source_id
    receipts = source / "receipts"
    before = {path.name: path.read_bytes() for path in receipts.iterdir()}
    monkeypatch.setattr(lineage, "_MAX_SUCCESS_GENERATIONS", 1)
    fetched = False

    def forbidden_fetch(*_args: object, **_kwargs: object) -> bytes:
        nonlocal fetched
        fetched = True
        raise KeyboardInterrupt

    monkeypatch.setattr(activation, "_read_raw_archive", forbidden_fetch)
    with pytest.raises(VerificationError, match="successful history has no capacity"):
        _activate(tmp_path, attempt_id="annual-success-cap-rejected")

    assert fetched is False
    assert {path.name: path.read_bytes() for path in receipts.iterdir()} == before
    assert not (source / ".ingestion.lock").exists()
    assert (
        verifier.verify_active_fars_year(
            tmp_path / "private",
            year=2024,
            contract_revision=1,
        )
        == first
    )


def test_receipt_drift_cannot_poison_reserved_capacity_with_a_failure_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = _activate(tmp_path, attempt_id="annual-budget-first")
    source = tmp_path / "private" / first.source_id
    donor = tmp_path / "receipt-donor"

    def fail_fetch() -> bytes:
        raise ValueError("donor failure")

    with pytest.raises(IngestionRunError) as donor_failure:
        run_ingestion(
            root=donor,
            source_id=first.source_id,
            fetch=fail_fetch,
            normalize=lambda raw: raw,
            attempt_id="injected-after-preflight",
        )
    injected_payload = donor_failure.value.receipt_path.read_bytes()
    original_normalize = artifacts_v2.canonical_joined_outcome_artifact_v2_from_pinned_archive
    injected = False

    def inject_receipt_then_normalize(
        raw: bytes,
        *,
        year: int,
        contract_revision: int,
    ) -> bytes:
        nonlocal injected
        assert injected is False
        injected = True
        destination = source / "receipts" / "injected-after-preflight.json"
        destination.write_bytes(injected_payload)
        destination.chmod(0o400)
        return original_normalize(
            raw,
            year=year,
            contract_revision=contract_revision,
        )

    monkeypatch.setattr(lineage, "_MAX_RECEIPTS", 2)
    monkeypatch.setattr(
        activation,
        "canonical_joined_outcome_artifact_v2_from_pinned_archive",
        inject_receipt_then_normalize,
    )
    with pytest.raises(IngestionError, match="no failure receipt was written"):
        _activate(tmp_path, attempt_id="annual-budget-rejected")

    assert injected is True
    receipts = sorted((source / "receipts").glob("*.json"))
    assert [path.name for path in receipts] == [
        "annual-budget-first.json",
        "injected-after-preflight.json",
    ]
    assert not (source / ".ingestion.lock").exists()
    assert (
        verifier.verify_active_fars_year(
            tmp_path / "private",
            year=2024,
            contract_revision=1,
        )
        == first
    )


def test_lock_replacement_between_history_and_activation_cannot_return_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = _activate(tmp_path, attempt_id="annual-lock-first")
    source = tmp_path / "private" / first.source_id
    current = source / "normalized" / "current.json"
    marker_before = current.read_bytes()
    original = verifier._validate_fars_year_history_candidate_locked

    def replace_after_history(
        source_root: Path,
        candidate: bytes,
        *,
        year: int,
        contract_revision: int,
        started_at: str,
        expected_preflight: verifier._FarsYearIngestionPreflight,
    ) -> None:
        original(
            source_root,
            candidate,
            year=year,
            contract_revision=contract_revision,
            started_at=started_at,
            expected_preflight=expected_preflight,
        )
        replacement = source_root / ".replacement-lock"
        replacement.mkdir(mode=0o700)
        (source_root / ".ingestion.lock").rmdir()
        replacement.rename(source_root / ".ingestion.lock")

    monkeypatch.setattr(
        verifier,
        "_validate_fars_year_history_candidate_locked",
        replace_after_history,
    )
    with pytest.raises(IngestionError, match="no failure receipt was written"):
        _activate(tmp_path, attempt_id="annual-lock-rejected")

    assert current.read_bytes() == marker_before
    assert sorted(path.name for path in (source / "receipts").glob("*.json")) == [
        "annual-lock-first.json"
    ]
    stale_lock = source / ".ingestion.lock"
    assert stale_lock.is_dir()
    stale_lock.rmdir()
    assert (
        verifier.verify_active_fars_year(
            tmp_path / "private",
            year=2024,
            contract_revision=1,
        )
        == first
    )


def test_post_commit_public_replay_rejects_lock_replaced_after_locked_verification(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _activate(tmp_path, attempt_id="annual-postcommit-first")
    source = tmp_path / "private" / "fars-joined-2024"
    original_run = run_ingestion

    def relock_after_commit(**kwargs: Any) -> Any:
        result = original_run(**kwargs)
        (source / ".ingestion.lock").mkdir(mode=0o700)
        return result

    monkeypatch.setattr(activation, "run_ingestion", relock_after_commit)
    with pytest.raises(IngestionError, match="post-commit public verification"):
        _activate(tmp_path, attempt_id="annual-postcommit-unreported")

    stale_lock = source / ".ingestion.lock"
    assert stale_lock.is_dir()
    stale_lock.rmdir()
    assert (
        verifier.verify_active_fars_year(
            tmp_path / "private",
            year=2024,
            contract_revision=1,
        ).attempt_id
        == "annual-postcommit-unreported"
    )


def test_private_root_is_rejected_before_archive_or_repository_mutation(tmp_path: Path) -> None:
    repository_archive = ROOT / "must-not-be-read-fars.zip"
    with pytest.raises(ValueError, match="outside the repository"):
        activation.activate_fars_year(
            root=ROOT / "private",
            repository_root=ROOT,
            raw_archive_path=repository_archive,
            year=2024,
            contract_revision=1,
            attempt_id="must-not-run",
        )
    assert not (ROOT / "private").exists()

    assert (
        activation.require_private_fars_year_root(tmp_path / "private", ROOT)
        == (tmp_path / "private").resolve()
    )

    with pytest.raises(ValueError, match="activation root preflight failed"):
        activation.require_private_fars_year_root("bad\0root", ROOT)
    with pytest.raises(ValueError, match="repository root preflight failed"):
        activation.require_private_fars_year_root(tmp_path / "private", "bad\0repository")


def test_secure_raw_reader_rejects_symlinks_and_hardlinks(tmp_path: Path) -> None:
    contract = year_contracts.fars_year_contract(2024)
    archive = _write_archive(tmp_path)
    symlink = tmp_path / "fars-link.zip"
    symlink.symlink_to(archive)
    with pytest.raises(ValueError, match="safely readable"):
        activation._read_raw_archive(symlink, contract=contract)

    hardlink = tmp_path / "fars-hardlink.zip"
    os.link(archive, hardlink)
    with pytest.raises(ValueError, match="metadata"):
        activation._read_raw_archive(archive, contract=contract)


def test_activation_surface_has_no_latest_or_policy_escape_hatches() -> None:
    parameters = inspect.signature(activation.activate_fars_year).parameters
    assert tuple(parameters) == (
        "root",
        "repository_root",
        "raw_archive_path",
        "year",
        "contract_revision",
        "clock",
        "attempt_id",
    )
    assert parameters["year"].default is inspect.Parameter.empty
    assert parameters["contract_revision"].default is inspect.Parameter.empty
    assert not any("allow" in name or "override" in name for name in parameters)


def test_candidate_must_be_canonical_v2_for_the_selected_revision(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        activation,
        "canonical_joined_outcome_artifact_v2_from_pinned_archive",
        lambda *_args, **_kwargs: b'{"not":"v2"}\n',
    )
    with pytest.raises(IngestionRunError):
        _activate(tmp_path, attempt_id="annual-forged")
    source = tmp_path / "private" / "fars-joined-2024"
    assert not (source / "normalized" / "current.json").exists()
