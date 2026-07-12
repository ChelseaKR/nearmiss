"""City source registry and conservative national evidence-tier assessment."""

from __future__ import annotations

import dataclasses
import datetime as dt
import json
from pathlib import Path

import pytest

from nearmiss.__main__ import main
from nearmiss.adapters.fars import FarsAdapter, read_export_bytes
from nearmiss.config import load_config
from nearmiss.coverage import DataSource, SourceRegistry, assess_coverage, load_source_registry
from nearmiss.errors import ConfigError
from nearmiss.ingestion import run_ingestion
from nearmiss.outcome_artifacts import build_outcome_artifact, canonical_outcome_artifact_bytes
from nearmiss.verified_outcomes import VerifiedOutcomeEvidence, verify_active_fars

ROOT = Path(__file__).resolve().parents[1]
DAVIS_CONFIG = ROOT / "config" / "davis-demo.toml"
DAVIS_REGISTRY = ROOT / "config" / "sources" / "davis-demo.toml"
FARS_FIXTURE = ROOT / "tests" / "fixtures" / "fars" / "accident.csv"
FARS_URL = "https://static.nhtsa.gov/nhtsa/downloads/FARS/2023/National/FARS2023NationalCSV.zip"


def _real_sources(*, exposure_updated: str = "2026-05-01") -> tuple[DataSource, ...]:
    return (
        DataSource("streets", "streets", "Street network", "ODbL", "2026-05-01", "Test"),
        DataSource("reports", "incidents", "Reports", "CC-BY", "2026-05-01", "Test"),
        DataSource(
            "counts", "exposure", "Counts", "CC0", exposure_updated, "Test", stale_after_days=365
        ),
    )


def _fars_source() -> DataSource:
    return DataSource(
        "fars",
        "official_outcomes",
        "FARS fatal crash census",
        "U.S. Government Work",
        "2025-01-01",
        "United States",
        stale_after_days=730,
    )


def _verified_fars(tmp_path: Path) -> VerifiedOutcomeEvidence:
    raw = FARS_FIXTURE.read_bytes()
    outcomes, provenance = FarsAdapter().parse(read_export_bytes(raw), release_status="final")
    artifact = build_outcome_artifact(
        outcomes,
        provenance,
        expected_year=2023,
        distribution_url=FARS_URL,
        max_invalid_fraction=0.34,
    )
    root = tmp_path / "verified-evidence"
    run_ingestion(
        root=root,
        source_id="fars",
        fetch=lambda: raw,
        normalize=lambda _raw: canonical_outcome_artifact_bytes(artifact),
        attempt_id="coverage-test",
    )
    return verify_active_fars(root)


def test_demo_registry_can_never_be_promoted_by_observed_fixture_rows() -> None:
    config = load_config(DAVIS_CONFIG)
    registry = load_source_registry(DAVIS_REGISTRY)
    assessment = assess_coverage(config, registry)
    assert assessment.evidence_tier == "demonstration"
    assert assessment.observed_exposure_coverage == 0.0667
    assert len(assessment.registry_sha256) == 64
    assert assessment.sources[0].id == "davis-demo-streets"
    assert "official_outcome_triangulation" not in assessment.capabilities
    assert "contextual_screening" not in assessment.capabilities


def test_measured_and_partner_tiers_require_coverage_and_explicit_review() -> None:
    config = load_config(DAVIS_CONFIG)
    measured = SourceRegistry(city="Davis", sources=_real_sources(), measured_min_coverage=0.05)
    assert assess_coverage(config, measured).evidence_tier == "measured_city"

    partner = dataclasses.replace(
        measured,
        partner_organization="Davis Streets Coalition",
        partner_review_ref="review-2026-07-12",
    )
    assessment = assess_coverage(config, partner)
    assert assessment.evidence_tier == "partner_city"
    assert assessment.partner_review_ref == "review-2026-07-12"


def test_stale_observed_exposure_downgrades_to_modeled_city() -> None:
    config = load_config(DAVIS_CONFIG)
    registry = SourceRegistry(city="Davis", sources=_real_sources(exposure_updated="2020-01-01"))
    assessment = assess_coverage(config, registry, as_of=dt.date(2026, 7, 12))
    assert assessment.evidence_tier == "modeled_city"
    assert assessment.stale_source_ids == ("counts",)
    assert "refresh stale sources" in assessment.unlocks


def test_any_stale_core_source_prevents_measured_promotion() -> None:
    config = load_config(DAVIS_CONFIG)
    sources = tuple(
        dataclasses.replace(source, updated_at="2020-01-01") if source.kind == "streets" else source
        for source in _real_sources()
    )
    registry = SourceRegistry(city="Davis", sources=sources, measured_min_coverage=0.05)
    assessment = assess_coverage(config, registry, as_of=dt.date(2026, 7, 12))
    assert assessment.evidence_tier == "modeled_city"
    assert assessment.stale_source_ids == ("streets",)


def test_modeled_exposure_is_not_called_measured(tmp_path: Path) -> None:
    config = load_config(DAVIS_CONFIG)
    exposure = json.loads(config.exposure_path.read_text(encoding="utf-8"))
    for row in exposure["segments"]:
        row["tier"] = "modeled"
    modeled_path = tmp_path / "exposure.json"
    modeled_path.write_text(json.dumps(exposure), encoding="utf-8")
    modeled_config = dataclasses.replace(config, exposure_path=modeled_path)
    assessment = assess_coverage(
        modeled_config,
        SourceRegistry(city="Davis", sources=_real_sources()),
    )
    assert assessment.evidence_tier == "modeled_city"
    assert assessment.usable_exposure_coverage == 0.0667
    assert assessment.observed_exposure_coverage == 0.0


def test_registry_rejects_half_declared_partner(tmp_path: Path) -> None:
    path = tmp_path / "sources.toml"
    path.write_text(
        'version = 1\ncity = "Test"\n[partner]\norganization = "Org"\n',
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="organization and review_ref"):
        load_source_registry(path)


def test_registry_rejects_duplicate_source_ids(tmp_path: Path) -> None:
    source = (
        '[[sources]]\nid = "same"\nkind = "streets"\nname = "N"\n'
        'license = "L"\nupdated_at = "2026-01-01"\ngeography = "G"\n'
    )
    path = tmp_path / "sources.toml"
    path.write_text(f'version = 1\ncity = "Test"\n{source}{source}', encoding="utf-8")
    with pytest.raises(ConfigError, match="duplicate source id"):
        load_source_registry(path)


def test_undeclared_exposure_does_not_unlock_rate_capability() -> None:
    config = load_config(DAVIS_CONFIG)
    registry = SourceRegistry(city="Davis", sources=_real_sources()[:2])
    assessment = assess_coverage(config, registry)
    assert assessment.evidence_tier == "national_baseline"
    assert "exposure_normalized_segment_rates" not in assessment.capabilities


def test_outcome_declaration_and_verification_are_distinct_from_triangulation(
    tmp_path: Path,
) -> None:
    config = load_config(DAVIS_CONFIG)
    declared = SourceRegistry(city="Davis", sources=(*_real_sources(), _fars_source()))
    verified = _verified_fars(tmp_path)

    declaration_only = assess_coverage(config, declared)
    assert "verified_official_outcomes" not in declaration_only.capabilities
    assert "official_outcome_triangulation" not in declaration_only.capabilities
    assert declaration_only.official_outcomes.verification_status == "not_requested"
    assert declaration_only.official_outcomes.declared_source_ids == ("fars",)
    assert "verify the active FARS receipt/artifact chain with --fars-root" in (
        declaration_only.unlocks
    )

    verified_but_undeclared = assess_coverage(
        config,
        SourceRegistry(city="Davis", sources=_real_sources()),
        verified_outcomes=verified,
    )
    assert "verified_official_outcomes" not in verified_but_undeclared.capabilities
    assert "declare source 'fars' with kind official_outcomes" in verified_but_undeclared.unlocks

    matched = assess_coverage(config, declared, verified_outcomes=verified)
    assert "verified_official_outcomes" in matched.capabilities
    assert "official_outcome_triangulation" not in matched.capabilities
    assert matched.official_outcomes.verification_status == "verified"
    assert matched.official_outcomes.verified == verified
    assert "join verified outcomes to modes, segments, and time windows" in matched.unlocks


def test_unloaded_context_and_intervention_declarations_grant_no_capability() -> None:
    config = load_config(DAVIS_CONFIG)
    declared_only = (
        DataSource("context", "context", "Context", "CC0", "2026-05-01", "Test"),
        DataSource(
            "interventions",
            "interventions",
            "Projects",
            "CC0",
            "2026-05-01",
            "Test",
        ),
    )
    assessment = assess_coverage(
        config,
        SourceRegistry(city="Davis", sources=(*_real_sources(), *declared_only)),
    )

    assert "contextual_screening" not in assessment.capabilities
    assert "before_after_evaluation_inputs" not in assessment.capabilities
    assert "connect and validate declared intervention-history records" in assessment.unlocks


@pytest.mark.parametrize(
    "registry",
    [
        SourceRegistry(
            city="Davis",
            sources=tuple(
                dataclasses.replace(source, synthetic=True) for source in _real_sources()
            ),
        ),
        SourceRegistry(city="Davis", sources=_real_sources()[:2]),
        SourceRegistry(city="Davis", sources=_real_sources()),
        SourceRegistry(city="Davis", sources=_real_sources(), measured_min_coverage=0.05),
        SourceRegistry(
            city="Davis",
            sources=_real_sources(),
            measured_min_coverage=0.05,
            partner_organization="Davis Streets Coalition",
            partner_review_ref="review-2026-07-12",
        ),
    ],
    ids=["demonstration", "national", "modeled", "measured", "partner"],
)
def test_verified_outcomes_never_change_tier_or_core_metrics(
    registry: SourceRegistry, tmp_path: Path
) -> None:
    config = load_config(DAVIS_CONFIG)
    with_fars = dataclasses.replace(registry, sources=(*registry.sources, _fars_source()))
    before = assess_coverage(config, with_fars)
    after = assess_coverage(config, with_fars, verified_outcomes=_verified_fars(tmp_path))

    assert after.evidence_tier == before.evidence_tier
    assert after.segments_total == before.segments_total
    assert after.reports_total == before.reports_total
    assert after.usable_exposure_coverage == before.usable_exposure_coverage
    assert after.observed_exposure_coverage == before.observed_exposure_coverage
    assert after.missing_core_source_kinds == before.missing_core_source_kinds


def test_coverage_cli_redacts_failed_private_fars_verification(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    secret_root = tmp_path / "private-secret-38.123,-121.456"
    assert (
        main(
            [
                "coverage",
                "--config",
                str(DAVIS_CONFIG),
                "--fars-root",
                str(secret_root),
            ]
        )
        == 2
    )

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "active FARS verification failed" in captured.err
    assert str(secret_root) not in captured.err
    assert "38.123" not in captured.err

    assert main(["coverage", "--config", str(DAVIS_CONFIG), "--fars-root", ""]) == 2
    empty = capsys.readouterr()
    assert empty.out == ""
    assert "active FARS verification failed" in empty.err

    unknown_user = "~nearmiss-user-that-does-not-exist-xyz/private-38.123,-121.456"
    assert (
        main(
            [
                "coverage",
                "--config",
                str(DAVIS_CONFIG),
                "--fars-root",
                unknown_user,
            ]
        )
        == 2
    )
    expanded = capsys.readouterr()
    assert expanded.out == ""
    assert "active FARS verification failed" in expanded.err
    assert "nearmiss-user-that-does-not-exist" not in expanded.err
    assert "38.123" not in expanded.err


def test_coverage_cli_reports_only_safe_verified_fars_context(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    private_root = tmp_path / "private"
    assert (
        main(
            [
                "ingest-fars",
                str(FARS_FIXTURE),
                "--root",
                str(private_root),
                "--year",
                "2023",
                "--release-status",
                "final",
                "--distribution-url",
                FARS_URL,
                "--max-invalid-fraction",
                "0.34",
            ]
        )
        == 0
    )
    capsys.readouterr()

    registry = tmp_path / "sources.toml"
    registry.write_text(
        DAVIS_REGISTRY.read_text(encoding="utf-8")
        + """

[[sources]]
id = "fars"
kind = "official_outcomes"
name = "FARS fatal crash census"
license = "U.S. Government Work"
updated_at = "2025-01-01"
geography = "United States"
stale_after_days = 730
""",
        encoding="utf-8",
    )

    assert (
        main(
            [
                "coverage",
                "--config",
                str(DAVIS_CONFIG),
                "--registry",
                str(registry),
                "--fars-root",
                str(private_root),
            ]
        )
        == 0
    )
    rendered = capsys.readouterr().out
    payload = json.loads(rendered)

    assert payload["evidence_tier"] == "demonstration"
    assert "verified_official_outcomes" in payload["capabilities"]
    assert "official_outcome_triangulation" not in payload["capabilities"]
    assert payload["official_outcomes"]["verification_status"] == "verified"
    assert payload["official_outcomes"]["verified"]["dataset_year"] == 2023
    assert payload["official_outcomes"]["verified"]["records_accepted"] == 2
    assert str(private_root) not in rendered
    assert "artifact_path" not in rendered
    assert "outcomes" not in payload["official_outcomes"]["verified"]
    assert "lat" not in payload["official_outcomes"]["verified"]
    assert "lon" not in payload["official_outcomes"]["verified"]


def test_coverage_cli_emits_machine_readable_assessment(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["coverage", "--config", str(DAVIS_CONFIG)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["city"] == "Davis"
    assert payload["evidence_tier"] == "demonstration"
    assert len(payload["registry_sha256"]) == 64
    assert payload["sources"][0]["license"] == "Apache-2.0"
    assert payload["capabilities"] == [
        "source_coverage_screening",
        "exposure_normalized_segment_rates",
    ]
