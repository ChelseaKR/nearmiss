"""The brief is comprehensible and bilingual (guards the i18n / --lang path)."""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

from nearmiss.brief import render_brief
from nearmiss.config import Config
from nearmiss.engine import AnalysisBundle
from nearmiss.publish import _slug
from nearmiss.stats.calibration import run_null_calibration


def test_english_brief_is_comprehensible(bundle: AnalysisBundle, config: Config) -> None:
    text = render_brief(bundle, config, "en")
    # Real street names, not placeholders.
    assert "5th St" in text and "seg-06" not in text
    # Plain-language glossary, a bottom-line, the exposure unit, and a bias counterweight.
    assert "What the numbers mean" in text
    assert "Bottom line" in text
    assert config.exposure_unit in text
    assert "does not mean nothing can be concluded" in text
    # Withheld (k-anonymity) segments are never named in a published brief.
    assert "A St (1st–2nd)" not in text  # seg-08 is withheld (n=1)
    # EXP-03: the corridor view is published alongside the block-level table.
    # Under the network-topology Gi* weights (FIX-02) the borderline 5th St
    # block clears the FDR bar too, so the planted corridor spans seg-05/06/07.
    assert "Corridor view" in text
    assert "5th St (B–E)" in text
    assert "MAUP transparency note" in text


def test_spanish_brief_renders_in_spanish(bundle: AnalysisBundle, config: Config) -> None:
    text = render_brief(bundle, config, "es")
    assert "Dónde está realmente el peligro" in text
    assert "En resumen:" in text  # the bottom-line, localized
    assert "Qué significan los números" in text  # the glossary heading, localized
    # The headline hotspot is still the planted one.
    assert "5th St (C–D)" in text
    # The bias note and confidence labels are localized too (no English leakage).
    assert "Las cuotas comparan" in text
    assert "cierto" in text  # localized confidence label
    assert "Shares compare where reports land" not in text


def test_unknown_language_falls_back_to_english(bundle: AnalysisBundle, config: Config) -> None:
    assert render_brief(bundle, config, "xx") == render_brief(bundle, config, "en")


def test_brief_states_the_configured_window(bundle: AnalysisBundle, config: Config) -> None:
    import dataclasses

    cfg = dataclasses.replace(config, window_start="2026-01-01", window_end="2026-12-31")
    text = render_brief(bundle, cfg, "en")
    assert "Analysis window" in text
    assert "2026-01-01 to 2026-12-31" in text


def test_brief_warns_when_no_window_configured(bundle: AnalysisBundle, config: Config) -> None:
    import dataclasses

    cfg = dataclasses.replace(config, window_start=None, window_end=None)
    text = render_brief(bundle, cfg, "en")
    assert "Analysis window" in text
    assert "no window configured" in text


def test_brief_omits_calibration_when_no_artifact_exists(
    bundle: AnalysisBundle, config: Config, tmp_path: Path
) -> None:
    cfg = dataclasses.replace(config, out_dir=tmp_path)  # empty: never calibrated
    assert "Null calibration" not in render_brief(bundle, cfg, "en")


def test_brief_links_calibration_artifact_when_present(
    bundle: AnalysisBundle, config: Config, tmp_path: Path
) -> None:
    cfg = dataclasses.replace(config, out_dir=tmp_path)
    result = run_null_calibration(
        bundle.result.segments, bundle.segments, cfg, n_shuffles=10, seed=1
    )
    cal_path = tmp_path / f"{_slug(cfg.city)}.calibration.json"
    cal_path.write_text(json.dumps(result.to_metadata()), encoding="utf-8")
    text = render_brief(bundle, cfg, "en")
    assert "Null calibration" in text
    assert cal_path.name in text
