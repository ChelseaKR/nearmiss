"""The gettext seam: catalog loading, label helpers, and Accept-Language logic.

These guard nearmiss's migration from bespoke EN/ES dicts to gettext catalogs
(INTERNATIONALIZATION-STANDARD §3): a loaded catalog returns real translations,
an unknown tag falls back to English text, and ``negotiate_lang`` implements the
``<requested> → <primary subtag> → en`` fallback chain (§6).
"""

from __future__ import annotations

import pytest

from nearmiss.i18n import (
    DEFAULT_LANGUAGE,
    SUPPORTED_LANGUAGES,
    confidence_label,
    get_translation,
    negotiate_lang,
    part_of_day_label,
    weekday_label,
)


def test_get_translation_loads_spanish_catalog() -> None:
    assert get_translation("es").gettext("Rank") == "Rango"


def test_get_translation_english_is_source_text() -> None:
    assert get_translation("en").gettext("Rank") == "Rank"


def test_get_translation_unknown_tag_falls_back_to_source() -> None:
    # fallback=True → NullTranslations returns the English msgid unchanged.
    assert get_translation("xx").gettext("Rank") == "Rank"


def test_ngettext_plural_selection_spanish() -> None:
    es = get_translation("es")
    one = es.ngettext("- **{part}**: {n} report ({pct}%)", "- **{part}**: {n} reports ({pct}%)", 1)
    many = es.ngettext("- **{part}**: {n} report ({pct}%)", "- **{part}**: {n} reports ({pct}%)", 3)
    assert one == "- **{part}**: {n} reporte ({pct}%)"
    assert many == "- **{part}**: {n} reportes ({pct}%)"


@pytest.mark.parametrize(
    ("lang", "key", "expected"),
    [
        ("es", "certain", "cierto"),
        ("es", "uncertain", "incierto"),
        ("es", "exposure_unknown", "exposición desconocida"),
        ("en", "certain", "certain"),
        ("en", "made_up_bucket", "made up bucket"),  # fallback: humanized key
    ],
)
def test_confidence_label(lang: str, key: str, expected: str) -> None:
    assert confidence_label(get_translation(lang), key) == expected


@pytest.mark.parametrize(
    ("lang", "key", "expected"),
    [
        ("es", "am_peak", "hora pico matutina (06–10)"),
        ("es", "overnight", "madrugada (00–06)"),
        ("en", "midday", "midday (10–16)"),
        ("en", "not_a_part", "not_a_part"),  # fallback: raw key
    ],
)
def test_part_of_day_label(lang: str, key: str, expected: str) -> None:
    assert part_of_day_label(get_translation(lang), key) == expected


@pytest.mark.parametrize(
    ("lang", "key", "expected"),
    [
        ("es", "Mon", "lunes"),
        ("es", "Sun", "domingo"),
        ("en", "Fri", "Friday"),
        ("en", "Xyz", "Xyz"),  # fallback: raw code
    ],
)
def test_weekday_label(lang: str, key: str, expected: str) -> None:
    assert weekday_label(get_translation(lang), key) == expected


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        (None, "en"),
        ("", "en"),
        ("   ", "en"),
        ("es", "es"),
        ("ES", "es"),
        ("es-MX", "es"),  # primary-subtag fallback
        ("fr", "en"),  # unsupported → default
        ("*", "en"),  # wildcard → default
        ("en-US,es;q=0.9", "en"),  # highest-q primary matches en
        ("fr;q=0.2, es;q=0.8", "es"),  # q-weighted selection
        ("de-DE, es", "es"),  # first unsupported, tie broken by order to es
        ("es;q=0", "en"),  # q=0 means "not acceptable"
        ("es;q=notanumber", "en"),  # malformed q → dropped
        (";q=0.5, es", "es"),  # empty tag skipped
    ],
)
def test_negotiate_lang(header: str | None, expected: str) -> None:
    assert negotiate_lang(header) == expected


def test_default_language_is_supported() -> None:
    assert DEFAULT_LANGUAGE in SUPPORTED_LANGUAGES
