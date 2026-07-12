"""City source registry and conservative national evidence-tier assessment."""

from __future__ import annotations

import dataclasses
import datetime as dt
import json
from pathlib import Path

import pytest

from nearmiss.__main__ import main
from nearmiss.config import load_config
from nearmiss.coverage import DataSource, SourceRegistry, assess_coverage, load_source_registry
from nearmiss.errors import ConfigError

ROOT = Path(__file__).resolve().parents[1]
DAVIS_CONFIG = ROOT / "config" / "davis-demo.toml"
DAVIS_REGISTRY = ROOT / "config" / "sources" / "davis-demo.toml"


def _real_sources(*, exposure_updated: str = "2026-05-01") -> tuple[DataSource, ...]:
    return (
        DataSource("streets", "streets", "Street network", "ODbL", "2026-05-01", "Test"),
        DataSource("reports", "incidents", "Reports", "CC-BY", "2026-05-01", "Test"),
        DataSource(
            "counts", "exposure", "Counts", "CC0", exposure_updated, "Test", stale_after_days=365
        ),
    )


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
