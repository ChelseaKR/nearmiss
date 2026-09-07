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
from babel.messages.catalog import Catalog
from babel.messages.pofile import read_po
from tools import check_catalog_parity

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


# --- G5 untranslated-source: a Spanish msgstr may not be verbatim English ------
#
# Key-parity, completeness and placeholder parity are ALL satisfied by a Spanish
# msgstr that is a verbatim copy of its English msgid, so before this check the
# gate was green on an untranslated catalog. The design problem is false
# positives: proper nouns, acronyms, URLs, bare numbers and pure-placeholder
# strings are legitimately identical, and a gate that fires on `CSV` gets turned
# off. These tests pin both halves — it fires on a sentence, it does not fire on
# the identical-by-right strings.


def _catalogs(entries: dict[str, tuple[str, str]]) -> tuple[Catalog, Catalog]:
    """Build an (en, es) catalog pair from ``{msgid: (en_msgstr, es_msgstr)}``."""
    en, es = Catalog(locale="en"), Catalog(locale="es")
    for msgid, (en_string, es_string) in entries.items():
        en.add(msgid, en_string)
        es.add(msgid, es_string)
    return en, es


IDENTICAL_BY_RIGHT = [
    "CSV",
    "GeoJSON",
    "OK",
    "nearmiss",
    "BikeMaps",
    "Riverside",
    "OpenStreetMap",
    "n",
    "z",
    "—",
    "2026",
    "95%",
    "{published} / {total}",
    "{year} · {mode}",
    "https://bikemaps.org/",
    "`--lang es`",
]


@pytest.mark.parametrize("source", IDENTICAL_BY_RIGHT)
def test_identical_translation_is_allowed_when_nothing_is_translatable(source: str) -> None:
    """The positive control: the gate must NOT fire on a string with no words to translate."""
    assert not check_catalog_parity._is_translatable(source), source
    en, es = _catalogs({source: (source, source)})
    assert check_catalog_parity._check_untranslated("es", es, en, {}) == []


UNTRANSLATED_SENTENCES = [
    "No segment reaches statistical significance at this sample size.",
    "Those intervals have already been widened accordingly (quasi-Poisson).",
    "Export the ranked corridors as CSV",
    "Reported near misses per 1000 riders",
]


@pytest.mark.parametrize("source", UNTRANSLATED_SENTENCES)
def test_verbatim_english_spanish_msgstr_fails(source: str) -> None:
    """The negative control: a Spanish msgstr copied verbatim from English is a defect."""
    en, es = _catalogs({source: (source, source)})
    errors = check_catalog_parity._check_untranslated("es", es, en, {})
    assert len(errors) == 1, errors
    assert "byte-identical to the English source" in errors[0]


def test_translated_spanish_msgstr_passes() -> None:
    source = "No segment reaches statistical significance at this sample size."
    en, es = _catalogs(
        {source: (source, "Ningún segmento alcanza significancia con este tamaño de muestra.")}
    )
    assert check_catalog_parity._check_untranslated("es", es, en, {}) == []


def test_web_key_compares_the_english_translation_not_the_msgid() -> None:
    """``web.*`` msgids are opaque keys, so the English *msgstr* is the source text."""
    en, es = _catalogs(
        {"web.app.export": ("Download the ranked corridors", "Download the ranked corridors")}
    )
    errors = check_catalog_parity._check_untranslated("es", es, en, {})
    assert len(errors) == 1, errors
    assert "web.app.export" in errors[0]

    en, es = _catalogs(
        {"web.app.export": ("Download the ranked corridors", "Descargar los corredores")}
    )
    assert check_catalog_parity._check_untranslated("es", es, en, {}) == []


def test_source_locale_identity_rows_are_not_flagged() -> None:
    """``en`` msgstr == msgid is the identity row the catalog is *supposed* to have.

    Almost every row of the real English catalog is byte-identical to its msgid,
    so if the rule were applied to the source locale the gate could never pass.
    That the gate does pass (the subprocess test above) is the proof it is skipped;
    this pins the premise — that the English catalog really is identity rows.
    """
    assert check_catalog_parity.SOURCE_LOCALE == "en"
    en_po = REPO_ROOT / "src" / "nearmiss" / "locales" / "en" / "LC_MESSAGES" / "messages.po"
    with en_po.open("rb") as handle:
        english = read_po(handle, locale="en")
    identity = [
        message
        for message in english
        if message.id
        and isinstance(message.id, str)
        and not message.id.startswith("web.")
        and message.string == message.id
    ]
    assert len(identity) > 100, "expected the English catalog to be mostly identity rows"


# --- the reasoned exemption file, and why it is a file --------------------------
#
# docs/I18N.md promises a contributor adding a locale never edits Python, so the
# escape hatch for a legitimately identical string cannot live in this tool. It is
# self-limiting on purpose: an entry with no reason, for an unchecked locale, for a
# msgid the template dropped, or for a row that has since been translated, all fail
# the gate. A list that only grows stops describing the catalogs and starts
# describing the project's history.

SOURCE_SENTENCE = "Reported near misses per 1000 riders"


def _write_exemptions(tmp_path: Path, entries: list[dict[str, str]]) -> Path:
    path = tmp_path / "identical_by_design.json"
    path.write_text(json.dumps({"identical_by_design": entries}), encoding="utf-8")
    return path


def test_an_exemption_with_a_reason_allows_the_identical_row(tmp_path: Path) -> None:
    en, es = _catalogs({SOURCE_SENTENCE: (SOURCE_SENTENCE, SOURCE_SENTENCE)})
    assert check_catalog_parity._check_untranslated("es", es, en, {}) != []
    exemptions, errors = check_catalog_parity.load_exemptions(
        _write_exemptions(
            tmp_path,
            [{"locale": "es", "msgid": SOURCE_SENTENCE, "reason": "identical by decision (test)"}],
        )
    )
    assert errors == []
    assert check_catalog_parity._check_untranslated("es", es, en, exemptions) == []


def test_an_exemption_without_a_reason_is_refused(tmp_path: Path) -> None:
    exemptions, errors = check_catalog_parity.load_exemptions(
        _write_exemptions(tmp_path, [{"locale": "es", "msgid": SOURCE_SENTENCE, "reason": "  "}])
    )
    assert exemptions == {}
    assert any("no reason" in e for e in errors), errors


def test_a_malformed_exemption_file_fails_rather_than_reading_as_empty(tmp_path: Path) -> None:
    path = tmp_path / "identical_by_design.json"
    path.write_text("{ not json", encoding="utf-8")
    exemptions, errors = check_catalog_parity.load_exemptions(path)
    assert exemptions == {}
    assert errors, "a file that cannot be read must fail, not read as no exemptions"


def test_a_missing_exemption_file_simply_means_none(tmp_path: Path) -> None:
    assert check_catalog_parity.load_exemptions(tmp_path / "absent.json") == ({}, [])


def test_an_exemption_that_has_stopped_applying_must_be_deleted() -> None:
    en, es = _catalogs({SOURCE_SENTENCE: (SOURCE_SENTENCE, "Cuasi-accidentes por cada 1000")})
    errors = check_catalog_parity._check_stale_exemptions(
        {"en": en, "es": es}, en, {SOURCE_SENTENCE}, {("es", SOURCE_SENTENCE): "was identical"}
    )
    assert any("now translated" in e for e in errors), errors


def test_an_exemption_for_a_msgid_the_template_dropped_must_be_deleted() -> None:
    en, es = _catalogs({SOURCE_SENTENCE: (SOURCE_SENTENCE, SOURCE_SENTENCE)})
    errors = check_catalog_parity._check_stale_exemptions(
        {"en": en, "es": es}, en, set(), {("es", SOURCE_SENTENCE): "identical by decision"}
    )
    assert any("no longer declares" in e for e in errors), errors


@pytest.mark.parametrize(
    ("locale", "needle"),
    [("fr", "not a checked catalog"), ("en", "source locale")],
)
def test_an_exemption_for_a_locale_that_cannot_use_it_is_refused(locale: str, needle: str) -> None:
    en, es = _catalogs({SOURCE_SENTENCE: (SOURCE_SENTENCE, SOURCE_SENTENCE)})
    errors = check_catalog_parity._check_stale_exemptions(
        {"en": en, "es": es}, en, {SOURCE_SENTENCE}, {(locale, SOURCE_SENTENCE): "a reason"}
    )
    assert any(needle in e for e in errors), errors


def test_the_committed_exemption_file_is_readable_and_currently_empty() -> None:
    exemptions, errors = check_catalog_parity.load_exemptions(check_catalog_parity.EXEMPTIONS)
    assert errors == []
    assert exemptions == {}, f"unexpected exemptions in {check_catalog_parity.EXEMPTIONS}"


# --- the source catalog is an identity map, and must stay one -------------------


def test_an_english_msgstr_that_drifts_from_its_msgid_fails() -> None:
    en, _ = _catalogs({SOURCE_SENTENCE: ("Reported near misses per 1000 RIDERS", SOURCE_SENTENCE)})
    errors = check_catalog_parity._check_source_identity(en)
    assert len(errors) == 1, errors
    assert "identity map by construction" in errors[0]


def test_a_web_key_is_exempt_from_the_source_identity_rule() -> None:
    # web.* msgids are opaque keys; their `en` msgstr is the English string and is
    # SUPPOSED to differ from the key. Requiring identity there would be nonsense.
    en, _ = _catalogs({"web.app.title": ("Where the danger actually is", "Donde está el peligro")})
    assert check_catalog_parity._check_source_identity(en) == []


def test_the_committed_english_catalog_is_an_identity_map() -> None:
    en_po = REPO_ROOT / "src" / "nearmiss" / "locales" / "en" / "LC_MESSAGES" / "messages.po"
    with en_po.open("rb") as handle:
        english = read_po(handle, locale="en")
    assert check_catalog_parity._check_source_identity(english) == []


def test_catalog_parity_gate_passes_on_the_committed_catalogs() -> None:
    result = subprocess.run(
        [sys.executable, "tools/check_catalog_parity.py"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


# --- where fare-policy-assistant's sibling rule does not transfer ---------------
#
# fare-policy-assistant landed the same gate (its PR #234) with two mechanical
# exemptions: no alphabetic content once {placeholders} are stripped, or a single
# ALL-CAPS token / bare URL. That is right for its catalogs and measurably wrong
# for these, in two ways, which is why nearmiss's rule is not a copy:
#
#   1. `n` — the sample-size symbol, and a real msgid here whose `es` msgstr is
#      `n`. It has alphabetic content and is not upper case, so FPA's rule fires
#      on it: one false positive on a green catalog, on day one.
#   2. 348 of these 479 msgids are `web.*` KEYS, not English text. FPA compares
#      msgstr against msgid, which for an opaque key can never be equal, so its
#      rule is vacuous over 73% of this catalog. nearmiss resolves a web id's
#      source to its `en` msgstr instead — that is what makes the check bite.


def test_a_single_letter_is_a_symbol_not_a_word() -> None:
    # `n` is a real msgid here and its es msgstr is `n`. A rule that requires
    # upper case for a single-token exemption fires on it.
    assert not check_catalog_parity._is_translatable("n")
    assert not check_catalog_parity._is_translatable("z")
    assert check_catalog_parity._translatable_words("n") == []


@pytest.mark.parametrize("source", ["Rank", "Corridor", "Segment", "Help", "Fares", "Senior"])
def test_an_ordinary_word_is_not_exempt_just_for_being_short(source: str) -> None:
    # The exemption is about the source having nothing to translate, never about
    # a string being brief. Each of these is one word and every one is gated.
    assert check_catalog_parity._is_translatable(source), source
    en, es = _catalogs({source: (source, source)})
    assert check_catalog_parity._check_untranslated("es", es, en, {}) != []


def test_a_web_key_is_compared_against_its_english_string_not_its_key() -> None:
    # The half FPA's rule cannot reach: an untranslated web string is identical to
    # the ENGLISH MSGSTR, never to the opaque msgid, so comparing against the msgid
    # would report nothing for 348 of this catalog's 479 ids.
    en, es = _catalogs({"web.app.summary": ("Reports per 1000 riders", "Reports per 1000 riders")})
    errors = check_catalog_parity._check_untranslated("es", es, en, {})
    assert len(errors) == 1, errors
    assert "web.app.summary" in errors[0]


def test_the_rule_refuses_to_run_against_no_target_locale() -> None:
    en, _ = _catalogs({"Rank": ("Rank", "Rango")})
    assert check_catalog_parity._check_target_locales({"en": en}) != []
    assert check_catalog_parity._check_target_locales({"en": en, "es": en}) == []
