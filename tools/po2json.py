#!/usr/bin/env python3
"""Compile the ``web.*`` subset of the gettext catalogs into web JSON catalogs.

The static web UI (:file:`web/app.js`, :file:`web/submit.js`) is served as flat
files from GitHub Pages and cannot call gettext at runtime, so its translations
are single-sourced from the *same* PO catalogs as the advocacy brief. This tool
selects every ``web.*`` msgid — the inventory registered in
:mod:`nearmiss.web_i18n` — from ``src/nearmiss/locales/<lang>/LC_MESSAGES/
messages.po`` and writes a committed, deterministic JSON catalog per locale to
``web/locales/<lang>.json`` (sorted keys, two-space indent, trailing newline),
mirroring the repo's committed-``.mo`` pattern (no build step at deploy time).

Run it from ``make i18n-compile`` to regenerate the JSON after editing a PO;
``--check`` re-derives the JSON and fails if a committed file has drifted or a
``web.*`` entry is missing, empty, or fuzzy — the drift gate wired into
``make i18n``. Pure standard library plus Babel's PO reader; no network.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from babel.messages.pofile import read_po

ROOT = Path(__file__).resolve().parent.parent
LOCALES = ROOT / "src" / "nearmiss" / "locales"
WEB_LOCALES = ROOT / "web" / "locales"
LANGS = ("en", "es")
PREFIX = "web."

# The authoritative ``web.*`` id inventory lives in the package, so the tool and
# the browser catalogs can never disagree about which ids exist. Import from the
# source tree without requiring an install.
sys.path.insert(0, str(ROOT / "src"))
from nearmiss.web_i18n import WEB_MESSAGE_IDS  # noqa: E402


def build(lang: str) -> tuple[dict[str, str], list[str]]:
    """Return ``(catalog, errors)`` for ``lang``'s ``web.*`` entries."""
    po_path = LOCALES / lang / "LC_MESSAGES" / "messages.po"
    with po_path.open("rb") as fh:
        catalog = read_po(fh, locale=lang)

    expected = set(WEB_MESSAGE_IDS)
    web: dict[str, str] = {}
    errors: list[str] = []
    for message in catalog:
        mid = message.id
        if not isinstance(mid, str) or not mid.startswith(PREFIX):
            continue
        if "fuzzy" in message.flags:
            errors.append(f"{lang}: {mid!r} is fuzzy (an unreviewed machine guess)")
            continue
        if not message.string:
            errors.append(f"{lang}: {mid!r} has an empty translation")
            continue
        web[mid] = message.string

    missing = expected - set(web)
    if missing:
        errors.append(f"{lang}: missing web entries: {sorted(missing)}")
    extra = set(web) - expected
    if extra:
        errors.append(f"{lang}: web entries not registered in nearmiss.web_i18n: {sorted(extra)}")
    return web, errors


def render(web: dict[str, str]) -> str:
    """Deterministic JSON: sorted keys, two-space indent, trailing newline."""
    return json.dumps(web, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify committed web/locales/*.json match the catalogs (drift gate)",
    )
    args = parser.parse_args(argv)

    outputs: dict[str, str] = {}
    errors: list[str] = []
    for lang in LANGS:
        web, lang_errors = build(lang)
        errors.extend(lang_errors)
        outputs[lang] = render(web)

    if errors:
        print("po2json FAILED:", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1

    WEB_LOCALES.mkdir(parents=True, exist_ok=True)
    drift = False
    for lang, text in outputs.items():
        path = WEB_LOCALES / f"{lang}.json"
        if args.check:
            current = path.read_text(encoding="utf-8") if path.exists() else None
            if current != text:
                print(
                    f"po2json --check: web/locales/{lang}.json is stale "
                    "— run `make i18n-compile` and commit the result.",
                    file=sys.stderr,
                )
                drift = True
        else:
            path.write_text(text, encoding="utf-8")

    if args.check:
        if drift:
            return 1
        print(f"po2json --check OK: {len(LANGS)} web JSON catalogs match the PO catalogs.")
    else:
        print(f"po2json: wrote web/locales/{{{','.join(LANGS)}}}.json from the PO catalogs.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
