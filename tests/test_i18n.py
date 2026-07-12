"""The gettext seam: catalog loading, label helpers, and Accept-Language logic.

These guard nearmiss's migration from bespoke EN/ES dicts to gettext catalogs
(INTERNATIONALIZATION-STANDARD §3): a loaded catalog returns real translations,
an unknown tag falls back to English text, and ``negotiate_lang`` implements the
``<requested> → <primary subtag> → en`` fallback chain (§6).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

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


# --- Web domain: single-sourced web/locales/*.json from the PO catalogs -------
#
# The static web UI can't call gettext at runtime, so tools/po2json.py compiles
# the ``web.*`` msgids into committed JSON catalogs. These guard that the JSON
# stays in lockstep with the catalogs (FIX-13): a web string added to the UI but
# not the catalog, or a stale/untranslated JSON, must fail the suite.

REPO_ROOT = Path(__file__).resolve().parent.parent
POT_PATH = REPO_ROOT / "src" / "nearmiss" / "locales" / "messages.pot"
WEB_LOCALES = REPO_ROOT / "web" / "locales"
WEB_LANGS = ("en", "es")


def _pot_web_ids() -> set[str]:
    """The ``web.*`` msgid inventory as recorded in the extraction template."""
    ids: set[str] = set()
    for line in POT_PATH.read_text(encoding="utf-8").splitlines():
        if line.startswith('msgid "web.') and line.endswith('"'):
            ids.add(line[len('msgid "') : -1])
    return ids


def _web_catalog(lang: str) -> dict[str, str]:
    data: dict[str, str] = json.loads((WEB_LOCALES / f"{lang}.json").read_text(encoding="utf-8"))
    return data


@pytest.mark.parametrize("lang", WEB_LANGS)
def test_web_json_catalog_exists_and_is_complete(lang: str) -> None:
    path = WEB_LOCALES / f"{lang}.json"
    assert path.is_file(), f"missing committed web catalog {path}"
    data = _web_catalog(lang)
    assert data, "web catalog is empty"
    assert all(key.startswith("web.") for key in data), "non-web key in web catalog"
    assert all(value for value in data.values()), "web catalog has an empty translation"


@pytest.mark.parametrize("lang", WEB_LANGS)
def test_web_json_keys_match_pot_inventory(lang: str) -> None:
    web_ids = _pot_web_ids()
    assert web_ids, "no web.* msgids found in messages.pot"
    assert set(_web_catalog(lang)) == web_ids


def test_web_json_en_es_key_parity() -> None:
    assert set(_web_catalog("en")) == set(_web_catalog("es"))


def test_po2json_check_passes() -> None:
    result = subprocess.run(
        [sys.executable, "tools/po2json.py", "--check"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
