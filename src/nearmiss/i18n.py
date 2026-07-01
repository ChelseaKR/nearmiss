"""Gettext localization seam for nearmiss's one end-user-facing surface.

The advocacy brief (:mod:`nearmiss.brief`) is the only place nearmiss emits
end-user-facing, natural-language text, and it renders in English or Spanish.
This module is the single migration seam onto GNU gettext catalogs
(INTERNATIONALIZATION-STANDARD §3): the *source string is the English text
itself*, extracted by ``pybabel`` into ``locales/messages.pot`` and translated
in ``locales/<lang>/LC_MESSAGES/messages.po``.

Operator-facing text is deliberately English-only and is NOT routed through this
module: the CLI (:mod:`nearmiss.__main__`), the moderation output, the read-only
server's HTTP status/JSON bodies (:mod:`nearmiss.server`), and every structured
log line (:mod:`nearmiss.obs`). The standard scopes i18n to end-user text, not
operator logs, so translating those would be noise, not access.
"""

from __future__ import annotations

import gettext
from pathlib import Path

#: gettext domain — the ``messages`` in ``messages.po`` / ``messages.mo``.
DOMAIN = "messages"

#: Compiled catalogs live beside this module (inside the package) so a checkout
#: or an installed wheel resolves them with no separate install step. See
#: docs/I18N.md for the decision to commit the compiled ``.mo`` files.
LOCALEDIR = Path(__file__).resolve().parent / "locales"

#: BCP 47 tags nearmiss ships a catalog for. English is the source language and
#: the fallback for any unsupported request.
SUPPORTED_LANGUAGES: tuple[str, ...] = ("en", "es")
DEFAULT_LANGUAGE = "en"


def get_translation(lang: str) -> gettext.NullTranslations:
    """Return the gettext catalog for ``lang``, falling back to English text.

    ``fallback=True`` means an unknown tag (or a missing ``.mo``) yields a
    :class:`gettext.NullTranslations` whose ``gettext``/``ngettext`` return the
    English source msgid unchanged — never an exception, never a blank string.
    """
    return gettext.translation(DOMAIN, localedir=str(LOCALEDIR), languages=[lang], fallback=True)


def negotiate_lang(accept_language: str | None) -> str:
    """Resolve a supported language from an RFC 9110 ``Accept-Language`` value.

    The brief is CLI-driven today (``nearmiss brief --lang``), so no live HTTP
    request context reaches it; this helper exists so a future negotiated
    surface reuses one fallback chain — ``<requested> → <primary subtag> → en``
    (INTERNATIONALIZATION-STANDARD §6). Quality weights (``;q=``) are honored;
    an empty, malformed, or unmatched header falls back to English.
    """
    if not accept_language:
        return DEFAULT_LANGUAGE
    ranked: list[tuple[float, int, str]] = []
    for index, part in enumerate(accept_language.split(",")):
        token = part.strip()
        if not token:
            continue
        tag_part, _sep, params = token.partition(";")
        tag = tag_part.strip().lower()
        if not tag:
            continue
        weight = 1.0
        params = params.strip()
        if params.startswith("q="):
            try:
                weight = float(params[2:])
            except ValueError:
                weight = 0.0
        # index breaks q ties in source order (earlier = higher priority).
        ranked.append((weight, -index, tag))
    for weight, _neg_index, tag in sorted(ranked, reverse=True):
        if weight <= 0.0:
            continue
        if tag == "*" or tag in SUPPORTED_LANGUAGES:
            return DEFAULT_LANGUAGE if tag == "*" else tag
        primary = tag.split("-", 1)[0]
        if primary in SUPPORTED_LANGUAGES:
            return primary
    return DEFAULT_LANGUAGE


def confidence_label(translation: gettext.NullTranslations, key: str) -> str:
    """Localized name for a segment's confidence bucket."""
    _ = translation.gettext
    labels: dict[str, str] = {
        "certain": _("certain"),
        "uncertain": _("uncertain"),
        "exposure_unknown": _("exposure unknown"),
    }
    return labels.get(key, key.replace("_", " "))


def part_of_day_label(translation: gettext.NullTranslations, key: str) -> str:
    """Localized name for a time-of-day bucket."""
    _ = translation.gettext
    labels: dict[str, str] = {
        "overnight": _("overnight (00–06)"),
        "am_peak": _("morning commute (06–10)"),
        "midday": _("midday (10–16)"),
        "pm_peak": _("evening commute (16–20)"),
        "evening": _("evening (20–24)"),
    }
    return labels.get(key, key)


def weekday_label(translation: gettext.NullTranslations, key: str) -> str:
    """Localized weekday name from its three-letter English code (Mon…Sun)."""
    _ = translation.gettext
    labels: dict[str, str] = {
        "Mon": _("Monday"),
        "Tue": _("Tuesday"),
        "Wed": _("Wednesday"),
        "Thu": _("Thursday"),
        "Fri": _("Friday"),
        "Sat": _("Saturday"),
        "Sun": _("Sunday"),
    }
    return labels.get(key, key)
