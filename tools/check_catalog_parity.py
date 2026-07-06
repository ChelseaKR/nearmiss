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

Pure standard library + Babel's PO reader; no network, deterministic.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from babel.messages.catalog import Catalog, Message
from babel.messages.pofile import read_po

LOCALES = Path(__file__).resolve().parent.parent / "src" / "nearmiss" / "locales"
POT = LOCALES / "messages.pot"
CATALOGS = {"en", "es"}

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
    """G5: every msgstr (each plural form) non-empty, with placeholders preserved."""
    if not message.id:
        return []
    src_fields = _fields(_key(message))
    if isinstance(message.id, (tuple, list)):
        src_fields |= _fields(message.id[1])
        return _check_plural_message(name, message, src_fields)
    return _check_singular_message(name, message, src_fields)


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

    if errors:
        print("catalog parity FAILED:", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1
    print(
        f"catalog parity OK: {len(pot_ids)} msgids, en/es key-parity + completeness + "
        "placeholder parity hold."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
