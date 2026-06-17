"""The brief is comprehensible and bilingual (guards the i18n / --lang path)."""

from __future__ import annotations

from nearmiss.brief import render_brief
from nearmiss.config import Config
from nearmiss.engine import AnalysisBundle


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
    assert "Anderson Rd" not in text  # seg-11 is withheld (n=1)


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
