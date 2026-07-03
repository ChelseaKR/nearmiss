#!/usr/bin/env python3
"""G6 EN/ES key-parity + G5 completeness/placeholder gate (merge-blocking).

Enforces, over ``src/nearmiss/locales``:

* **G6 key-parity** — the msgid set of ``en`` and ``es`` is identical (empty
  symmetric difference), and both cover every msgid in ``messages.pot``. A key
  present in one catalog but not the other fails the build.
* **G5 completeness** — every msgstr (each plural form) is non-empty. nearmiss's
  Spanish is real, pre-existing human translation migrated from the retired
  bespoke ``_ES`` dict, so completeness is enforced as a hard gate here rather
  than deferred: there is no untranslated-ES backlog to wave through.
* **G5 placeholder parity** — the set of ``{...}`` fields is identical between
  each msgid and its translation (so a rename or dropped ``{name}`` cannot ship).

* **Web domain** — every ``web.*`` msgid (the web-UI strings registered in
  :mod:`nearmiss.web_i18n`, single-sourced into ``web/locales/*.json`` by
  :mod:`tools.po2json`) is present and non-empty in both en and es, the two
  translations share an identical ``{...}`` field set, and the committed
  ``web/locales/<lang>.json`` keys exactly match the ``web.*`` msgid inventory —
  so a web string that bypasses the catalog fails the build. (The ``web.*``
  msgids are keys, not English source text, so they are exempt from the
  msgid-vs-translation placeholder check above and gated here instead.)

Pure standard library + Babel's PO reader; no network, deterministic.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from babel.messages.catalog import Catalog, Message
from babel.messages.pofile import read_po

ROOT = Path(__file__).resolve().parent.parent
LOCALES = ROOT / "src" / "nearmiss" / "locales"
WEB_LOCALES = ROOT / "web" / "locales"
POT = LOCALES / "messages.pot"
CATALOGS = {"en", "es"}
WEB_PREFIX = "web."

_FIELD = re.compile(r"\{[^{}]*\}")


def _load(path: Path, locale: str | None) -> Catalog:
    with path.open("rb") as fh:
        return read_po(fh, locale=locale)


def _key(message: Message) -> str:
    """A hashable identity for a message (the singular msgid for plurals)."""
    return message.id[0] if isinstance(message.id, (tuple, list)) else message.id


def _ids(catalog: Catalog) -> set[str]:
    return {_key(m) for m in catalog if m.id}


def _fields(text: str) -> set[str]:
    return set(_FIELD.findall(text))


def _check_key_parity(en_ids: set[str], es_ids: set[str]) -> list[str]:
    """G6: EN/ES key-parity — the symmetric difference of msgid sets must be empty."""
    errors: list[str] = []
    only_en = en_ids - es_ids
    only_es = es_ids - en_ids
    if only_en:
        errors.append(f"G6: msgids in en but not es: {sorted(only_en)}")
    if only_es:
        errors.append(f"G6: msgids in es but not en: {sorted(only_es)}")
    return errors


def _check_pot_coverage(pot_ids: set[str], en_ids: set[str], es_ids: set[str]) -> list[str]:
    """Structural completeness: every template msgid must be present in each catalog."""
    errors: list[str] = []
    for name, ids in (("en", en_ids), ("es", es_ids)):
        missing = pot_ids - ids
        if missing:
            errors.append(
                f"G5: {name} is missing msgids present in the template: {sorted(missing)}"
            )
    return errors


def _check_plural_message(name: str, message: Message, src_fields: set[str]) -> list[str]:
    """G5 for a plural message: every form non-empty, placeholders match the source."""
    errors: list[str] = []
    forms = message.string if isinstance(message.string, (tuple, list)) else ()
    if not forms or any(not s for s in forms):
        errors.append(f"G5: {name} has an empty plural form for {_key(message)!r}")
        return errors
    for form in forms:
        if _fields(form) != src_fields:
            errors.append(
                f"G5: {name} placeholder mismatch in plural {_key(message)!r}: "
                f"{_fields(form)} != {src_fields}"
            )
    return errors


def _check_singular_message(name: str, message: Message, src_fields: set[str]) -> list[str]:
    """G5 for a singular message: msgstr non-empty, placeholders match the source."""
    errors: list[str] = []
    target = message.string
    if not target:
        errors.append(f"G5: {name} has an empty msgstr for {message.id!r}")
        return errors
    if _fields(target) != src_fields:
        errors.append(
            f"G5: {name} placeholder mismatch in {message.id!r}: {_fields(target)} != {src_fields}"
        )
    return errors


def _check_message(name: str, message: Message) -> list[str]:
    """G5: every msgstr (each plural form) non-empty, with placeholders preserved.

    ``web.*`` msgids are keys, not English text (their braces live only in the
    translations), so they are gated by _check_web, not here.
    """
    if not message.id:
        return []
    if _key(message).startswith(WEB_PREFIX):
        return []
    src_fields = _fields(_key(message))
    if isinstance(message.id, (tuple, list)):
        src_fields |= _fields(message.id[1])
        return _check_plural_message(name, message, src_fields)
    return _check_singular_message(name, message, src_fields)


def _string(catalog: Catalog, msgid: str) -> str:
    message = catalog.get(msgid)
    return message.string if message and isinstance(message.string, str) else ""


def _check_web(pot_ids: set[str], en: Catalog, es: Catalog) -> list[str]:
    """Gate the web domain: catalog completeness, EN/ES field parity, JSON match."""
    errors: list[str] = []
    web_ids = {mid for mid in pot_ids if mid.startswith(WEB_PREFIX)}
    if not web_ids:
        return ["web: no web.* msgids in the template (expected the web-UI strings)"]

    # Every web.* id present and non-empty in both catalogs, with matching fields.
    for name, catalog in (("en", en), ("es", es)):
        for mid in sorted(web_ids):
            if not _string(catalog, mid):
                errors.append(f"web: {name} is missing or empty for {mid!r}")
    for mid in sorted(web_ids):
        en_fields, es_fields = _fields(_string(en, mid)), _fields(_string(es, mid))
        if en_fields != es_fields:
            errors.append(f"web: en/es placeholder mismatch in {mid!r}: {en_fields} != {es_fields}")

    # web/locales/<lang>.json keys must exactly equal the web.* inventory, so a
    # string that bypasses the catalog (added only to the JSON, or dropped) fails.
    for lang in sorted(CATALOGS):
        path = WEB_LOCALES / f"{lang}.json"
        if not path.exists():
            errors.append(f"web: {path} is missing (run `make i18n-compile`)")
            continue
        try:
            keys = set(json.loads(path.read_text(encoding="utf-8")))
        except (ValueError, OSError) as exc:
            errors.append(f"web: could not read {path}: {exc}")
            continue
        if keys != web_ids:
            missing, extra = web_ids - keys, keys - web_ids
            if missing:
                errors.append(f"web: {lang}.json missing web ids: {sorted(missing)}")
            if extra:
                errors.append(f"web: {lang}.json has non-catalog ids: {sorted(extra)}")
    return errors


def main() -> int:
    errors: list[str] = []

    pot = _load(POT, None)
    en = _load(LOCALES / "en" / "LC_MESSAGES" / "messages.po", "en")
    es = _load(LOCALES / "es" / "LC_MESSAGES" / "messages.po", "es")

    pot_ids, en_ids, es_ids = _ids(pot), _ids(en), _ids(es)

    errors.extend(_check_key_parity(en_ids, es_ids))
    errors.extend(_check_pot_coverage(pot_ids, en_ids, es_ids))
    for name, catalog in (("en", en), ("es", es)):
        for message in catalog:
            errors.extend(_check_message(name, message))

    errors.extend(_check_web(pot_ids, en, es))

    if errors:
        print("catalog parity FAILED:", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1
    web_count = sum(1 for mid in pot_ids if mid.startswith(WEB_PREFIX))
    print(
        f"catalog parity OK: {len(pot_ids)} msgids ({web_count} web.*), en/es key-parity + "
        "completeness + placeholder parity + web JSON match hold."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
