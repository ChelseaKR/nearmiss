#!/usr/bin/env python3
"""G9 pseudo-locale generator — a build-only ``xx`` catalog for the locale gate.

Pseudolocalization is a *machine* transform of the source msgids that keeps every
string legible as English while making three classes of i18n defect impossible to
miss without any human translator:

* **Untranslated / hardcoded strings** — a string that bypasses gettext renders as
  plain, unaccented English and is *not* wrapped in the ``[!! … !!]`` sentinels, so
  it jumps out of a pseudo-rendered brief (this is what
  :mod:`tests.test_pseudolocale` asserts).
* **Truncation / clipping** — each string is expanded ~30% (localized text is
  routinely longer than English), surfacing layouts that assume English width.
* **Placeholder / format corruption** — ``{brace}`` fields and ``printf`` tokens are
  held out of the transform verbatim, so a rendered pseudo string still carries its
  real data; a test can assert the placeholders survived.

The catalog is **build-only** and is written to a temp/build directory the caller
chooses (default ``build/pseudolocale``). It is *never* written under
``src/nearmiss/locales`` — ``xx`` is not a shipped locale and must not land in the
package or the wheel (see docs/I18N.md). The module refuses to do so.

Usage::

    python tools/make_pseudolocale.py                 # -> build/pseudolocale/xx/…
    python tools/make_pseudolocale.py --out /tmp/foo   # explicit build dir

Only the standard library + Babel (already a dev dependency) are used; no ``msgfmt``
binary is required, so the pseudo catalog compiles anywhere ``pybabel`` runs.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from babel.messages.catalog import Catalog
from babel.messages.mofile import write_mo
from babel.messages.pofile import read_po, write_po

#: Repo root (…/nearmiss) — this file lives in ``tools/``.
ROOT = Path(__file__).resolve().parent.parent
#: The shipped extraction template we pseudo-localize.
DEFAULT_POT = ROOT / "src" / "nearmiss" / "locales" / "messages.pot"
#: Default build-only output dir (gitignored ``build/``); NEVER under the package.
DEFAULT_OUT = ROOT / "build" / "pseudolocale"
#: The pseudo-locale tag. Deliberately not a real BCP 47 tag and never registered
#: in ``SUPPORTED_LANGUAGES`` — it exists only for this gate.
PSEUDO_LANG = "xx"

#: Sentinel markers wrapping every transformed string. A user-facing string that
#: renders *without* these went around gettext.
OPEN, CLOSE = "[!! ", " !!]"

#: ASCII letter -> visually-accented look-alike. Keeps the text readable as English
#: while proving the string round-tripped through the catalog.
_ACCENTS = {
    "a": "á",
    "b": "ƀ",
    "c": "ç",
    "d": "ð",
    "e": "é",
    "f": "ƒ",
    "g": "ĝ",
    "h": "ĥ",
    "i": "í",
    "j": "ĵ",
    "k": "ķ",
    "l": "ļ",
    "m": "ɱ",
    "n": "ñ",
    "o": "ó",
    "p": "þ",
    "q": "ɋ",
    "r": "ŕ",
    "s": "š",
    "t": "ţ",
    "u": "ú",
    "v": "ṽ",
    "w": "ŵ",
    "x": "ẋ",
    "y": "ý",
    "z": "ž",
    "A": "Á",
    "B": "Ɓ",
    "C": "Ç",
    "D": "Ð",
    "E": "É",
    "F": "Ƒ",
    "G": "Ĝ",
    "H": "Ĥ",
    "I": "Í",
    "J": "Ĵ",
    "K": "Ķ",
    "L": "Ļ",
    "M": "Ṁ",
    "N": "Ñ",
    "O": "Ó",
    "P": "Þ",
    "Q": "Ǫ",
    "R": "Ŕ",
    "S": "Š",
    "T": "Ţ",
    "U": "Ú",
    "V": "Ṽ",
    "W": "Ŵ",
    "X": "Ẋ",
    "Y": "Ý",
    "Z": "Ž",
}
_ACCENT_TABLE = str.maketrans(_ACCENTS)
#: Accented vowels cycled to pad each string to ~30% over its source length.
_PAD_CYCLE = "áéíóúåøœæ"

# Held-out tokens that must survive verbatim: ``{brace}`` fields and printf
# conversions (``%s``, ``%d``, ``%(name)s``, ``%%``, ``%5.2f``, …). A bare ``%``
# not followed by a conversion (e.g. ``95%``, ``{pct}%``) is left as literal text.
_TOKEN = re.compile(
    r"""(?P<brace>\{[^{}]*\})
      | (?P<named>%\([^)]+\)[-+ #0]*\d*(?:\.\d+)?[sdiouxXeEfFgGrc%])
      | (?P<printf>%[-+ #0]*\d*(?:\.\d+)?[sdiouxXeEfFgGrc%])
    """,
    re.VERBOSE,
)


def pseudo(text: str) -> str:
    """Return the pseudo-localized form of ``text``.

    Letters are accented, the string is wrapped in ``[!! … !!]`` and padded to
    roughly 130% of its source length, while every ``{brace}`` placeholder and
    ``printf`` token is copied through untouched (byte-for-byte).
    """
    pieces: list[str] = []
    letters = 0
    cursor = 0
    for match in _TOKEN.finditer(text):
        literal = text[cursor : match.start()]
        pieces.append(literal.translate(_ACCENT_TABLE))
        letters += sum(ch.isalpha() for ch in literal)
        pieces.append(match.group(0))  # protected token, verbatim
        cursor = match.end()
    tail = text[cursor:]
    pieces.append(tail.translate(_ACCENT_TABLE))
    letters += sum(ch.isalpha() for ch in tail)

    core = "".join(pieces)
    pad_len = max(1, round(letters * 0.3))
    pad = "".join(_PAD_CYCLE[i % len(_PAD_CYCLE)] for i in range(pad_len))
    return f"{OPEN}{core} {pad}{CLOSE}"


def _pseudo_string(msgid: object) -> object:
    """Pseudo-localize a msgid that may be a plural tuple."""
    if isinstance(msgid, (tuple, list)):
        return tuple(pseudo(form) for form in msgid)
    return pseudo(str(msgid))


def build_pseudo_catalog(pot_path: Path = DEFAULT_POT, out_dir: Path = DEFAULT_OUT) -> Path:
    """Generate the ``xx`` pseudo catalog under ``out_dir`` and return its localedir.

    Writes ``<out_dir>/xx/LC_MESSAGES/messages.{po,mo}``. Returns ``out_dir`` (the
    gettext *localedir*), so a caller can do ``gettext.translation(..., localedir,
    languages=["xx"])``. Refuses to write anywhere under the shipped package
    ``locales`` tree.
    """
    out_dir = out_dir.resolve()
    package_locales = (ROOT / "src" / "nearmiss" / "locales").resolve()
    if out_dir == package_locales or package_locales in out_dir.parents:
        raise ValueError(
            f"refusing to write the build-only pseudo catalog under the shipped "
            f"package locales ({package_locales}); xx must never ship."
        )

    with Path(pot_path).open("rb") as handle:
        template = read_po(handle)

    # 'xx' is not a CLDR locale, so we cannot hand it to Babel. Build the catalog
    # as 'en' purely to borrow English's public 2-form Germanic plural rule
    # (nplurals=2; plural=(n != 1)), so ngettext resolves both pseudo plural forms
    # in the .mo. The Language header is irrelevant at load time — gettext selects
    # this catalog by its 'xx' *directory*, never by the header — and this catalog
    # is build-only regardless.
    catalog = Catalog(
        locale="en",
        domain=template.domain or "messages",
        charset="utf-8",
        project=template.project,
        version=template.version,
    )

    for message in template:
        if not message.id:
            continue  # the header; Catalog synthesizes its own.
        catalog.add(
            message.id,
            string=_pseudo_string(message.id),
            flags=message.flags,
            auto_comments=message.auto_comments,
            context=message.context,
        )

    lc_messages = out_dir / PSEUDO_LANG / "LC_MESSAGES"
    lc_messages.mkdir(parents=True, exist_ok=True)
    with (lc_messages / "messages.po").open("wb") as handle:
        write_po(handle, catalog)
    with (lc_messages / "messages.mo").open("wb") as handle:
        write_mo(handle, catalog)
    return out_dir


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pot", type=Path, default=DEFAULT_POT, help="source .pot")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="build dir")
    args = parser.parse_args()
    localedir = build_pseudo_catalog(args.pot, args.out)
    target = localedir / PSEUDO_LANG / "LC_MESSAGES" / "messages.mo"
    print(f"pseudolocale: wrote build-only {PSEUDO_LANG} catalog -> {target}")
    print("pseudolocale: (build-only; never commit under src/nearmiss/locales).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
