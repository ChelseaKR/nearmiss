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


def _with_stability(
    bundle: AnalysisBundle,
    *,
    survives: bool,
    coarse_rank: int | None,
    still_significant: bool,
) -> AnalysisBundle:
    """The bundle with its MAUP result replaced, to render one branch of the note."""
    stability = bundle.result.rank_stability
    assert stability is not None
    replaced = dataclasses.replace(
        stability,
        top_hotspot_survives=survives,
        top_hotspot_coarse_rank=coarse_rank,
        top_hotspot_still_significant=still_significant,
    )
    return dataclasses.replace(
        bundle,
        result=dataclasses.replace(bundle.result, rank_stability=replaced),
    )


def test_maup_note_says_the_rank_fell_when_the_rank_fell(
    bundle: AnalysisBundle, config: Config
) -> None:
    """`top_hotspot_survives` is false for two different reasons, and the brief
    must not report the wrong one.

    `rank_stability` sets it only when the top-rate unit is *both* still rank 1
    and still a significant Gi\\* cluster, so "did not survive" covers a hotspot
    that held rank 1 and lost significance and one whose rank fell. Telling a
    reader the hotspot "stays the highest-rate unit" when it dropped to rank 4 is
    an overstatement in the direction that flatters the finding.
    `figures._stability_note` already distinguishes the two; the brief did not.
    """
    fell = _with_stability(bundle, survives=False, coarse_rank=4, still_significant=False)
    text = render_brief(fell, config, "en")
    assert "stays the highest-rate unit" not in text
    assert "falls to rank 4" in text

    # The other branch keeps its own wording: rank held, significance did not.
    held = _with_stability(bundle, survives=False, coarse_rank=1, still_significant=False)
    held_text = render_brief(held, config, "en")
    assert "stays the highest-rate unit" in held_text
    assert "falls to rank" not in held_text


def test_maup_rank_fell_branch_is_localized(bundle: AnalysisBundle, config: Config) -> None:
    """Every branch of the robustness note is translated, not just the happy ones."""
    fell = _with_stability(bundle, survives=False, coarse_rank=4, still_significant=False)
    spanish = render_brief(fell, config, "es")
    assert "cae al puesto 4" in spanish
    assert "sigue siendo la unidad de mayor tasa" not in spanish
    assert "falls to rank" not in spanish  # no English leaks through the new branch
