"""A schema's ``format`` is documentation until something enforces it.

Two independent ways a `"format"` in this repository can be inert, and both have
already been found live here:

1. **No ``format_checker``.** JSON Schema treats ``format`` as an *annotation*
   unless the validator was built with one, so ``Draft202012Validator(schema)``
   reads every ``format`` and enforces none. That was the published dataset's
   ``exposure_date`` (fixed; ``tests/test_dataset_schema.py`` pins it).
2. **A ``FormatChecker`` with no checker for that format.** A stock install carries
   ``date``, ``email``, ``idn-email``, ``idn-hostname``, ``ipv4``, ``ipv6``,
   ``regex``, ``time`` and ``uuid`` — and **not** ``date-time`` or ``uri``, which
   need optional packages. A ``FormatChecker`` **silently skips** a format it has
   no checker for, so adding one *looks* like a fix and enforces nothing. That is
   why ``occurred_at``'s contract had to be re-implemented in code
   (``validation._occurred_at_problem``, #273).

Both facts were true and written down — once in a docstring and once in a test
comment, each about one field. This module makes them machine-checked across
**every** schema and **every** module-level validator in the package, so the next
``"format": "uri"`` cannot be added in the belief that it validates. The rule is
deliberately not "every format must be enforced": it is "every declared format is
either live **and demonstrably able to reject**, or written down here with the
reason and with where the constraint really lives".

The registry is self-limiting. An entry for a format nothing declares, for a format
this environment *can* enforce, or with no written reason, fails until it is
deleted — otherwise it stops describing the schemas and starts describing history.
"""

from __future__ import annotations

import importlib
import json
import pkgutil
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator, FormatChecker

import nearmiss

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = ROOT / "schema"

#: The formats jsonschema can actually check in the environment the gates run in.
LIVE_CHECKERS = frozenset(FormatChecker().checkers)

#: Declared in this repository's schemas and NOT enforceable here. Each value says
#: why, and where the constraint really lives if it lives anywhere. Deleting a key
#: is the correct move the day the environment gains that checker; the test below
#: fails until someone does.
UNENFORCED_FORMATS: dict[str, str] = {
    "date-time": (
        "jsonschema has no built-in date-time checker; it needs the optional "
        "rfc3339-validator package, which this project does not depend on (the merge "
        "gate installs from a hashed, offline lockfile, so adding one is a dependency "
        "decision rather than a test fixture). The one date-time field a stranger can "
        "supply — a report's occurred_at — is enforced in code instead: "
        "validation._occurred_at_problem rejects an unparseable value AND one with no "
        "timezone offset, neither of which format alone would have caught. The "
        "date-time fields on ingestion and verified-outcome receipts are written by "
        "this project, from datetime.now(UTC).isoformat(), never parsed from input."
    ),
    "uri": (
        "jsonschema has no built-in uri checker; it needs the optional rfc3987 (or "
        "rfc3986-validator) package. Every uri-shaped field in these schemas is a "
        "distribution or source URL this project records from its own configuration "
        "rather than from an untrusted submission, and each is additionally constrained "
        "by minLength and by the surrounding contract. Recorded here rather than left "
        "to read as validated."
    ),
}

#: A value each live checker must REJECT. A checker that cannot fail reads exactly
#: like a checker that passed, so presence in `LIVE_CHECKERS` is not enough.
KNOWN_BAD: dict[str, str] = {
    "date": "sometime in 2026",
    "uuid": "not-a-uuid",
    "email": "not an email",
    "ipv4": "999.1.1.1",
    "ipv6": "not::an::address::",
    "regex": "[unclosed",
    "time": "half past three",
    "idn-email": "not an email",
    "idn-hostname": "-leading-dash-",
}


def _formats_in(node: Any, out: set[str]) -> None:
    """Every ``"format"`` string anywhere in a schema document."""
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "format" and isinstance(value, str):
                out.add(value)
            else:
                _formats_in(value, out)
    elif isinstance(node, list):
        for value in node:
            _formats_in(value, out)


def _module_validators() -> dict[str, Draft202012Validator]:
    """Every module-level ``Draft202012Validator`` in the package, discovered.

    Discovered rather than listed: a hand-maintained list of validators is exactly
    the thing that goes stale the moment someone adds the fifteenth one, and the
    fifteenth one is the one most likely to carry the mistake.
    """
    found: dict[str, Draft202012Validator] = {}
    for info in pkgutil.walk_packages(nearmiss.__path__, "nearmiss."):
        module = importlib.import_module(info.name)
        for name, obj in vars(module).items():
            if isinstance(obj, Draft202012Validator):
                found[f"{info.name}.{name}"] = obj
    return found


VALIDATORS = _module_validators()
SCHEMA_FILES = sorted(SCHEMA_DIR.glob("*.json"))


def _declared_formats() -> dict[str, list[str]]:
    """format -> the schemas and validators that declare it."""
    declared: dict[str, list[str]] = {}
    for path in SCHEMA_FILES:
        found: set[str] = set()
        _formats_in(json.loads(path.read_text(encoding="utf-8")), found)
        for fmt in found:
            declared.setdefault(fmt, []).append(f"schema/{path.name}")
    for name, validator in VALIDATORS.items():
        found = set()
        _formats_in(validator.schema, found)
        for fmt in found:
            declared.setdefault(fmt, []).append(name)
    return declared


DECLARED = _declared_formats()


# --------------------------------------------------------------------------- #
# Floors — a check that examined nothing prints the same green line as one that
# examined everything and found nothing.
# --------------------------------------------------------------------------- #


def test_the_discovery_actually_found_the_schemas_and_the_validators() -> None:
    assert len(SCHEMA_FILES) >= 8, f"only {len(SCHEMA_FILES)} schema files found"
    assert len(VALIDATORS) >= 10, f"only {len(VALIDATORS)} module-level validators found"
    assert DECLARED, "no schema in this repository declares a format — the walk is broken"
    assert any(_has_format(v.schema) for v in VALIDATORS.values()), (
        "no validator's schema declares a format; the rule below would be vacuous"
    )


def _has_format(schema: Any) -> bool:
    found: set[str] = set()
    _formats_in(schema, found)
    return bool(found)


# --------------------------------------------------------------------------- #
# The two ways a format goes inert
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("name", sorted(VALIDATORS))
def test_a_validator_declaring_a_format_was_built_with_a_checker(name: str) -> None:
    """Rule 1: `Draft202012Validator(schema)` reads `format` and enforces none of it."""
    validator = VALIDATORS[name]
    if not _has_format(validator.schema):
        pytest.skip("this validator's schema declares no format")
    assert validator.format_checker is not None, (
        f"{name} declares a format and was built without a FormatChecker, so every "
        "format constraint in its schema is documentation the validator never reads"
    )


@pytest.mark.parametrize("fmt", sorted(DECLARED))
def test_every_declared_format_is_live_or_written_down(fmt: str) -> None:
    """Rule 2: a FormatChecker skips, silently, any format it has no checker for."""
    if fmt in LIVE_CHECKERS:
        return
    assert fmt in UNENFORCED_FORMATS, (
        f'"{fmt}" is declared by {", ".join(sorted(DECLARED[fmt]))} and jsonschema has '
        "no checker for it in this environment, so nothing enforces it. Either install a "
        "checker for it, enforce the rule in code, or record it in UNENFORCED_FORMATS "
        "with the reason and with where the constraint really lives."
    )


@pytest.mark.parametrize("fmt", sorted(f for f in DECLARED if f in LIVE_CHECKERS))
def test_a_live_checker_can_actually_reject(fmt: str) -> None:
    """Presence is not enforcement — a checker that never fails reads like a pass."""
    assert fmt in KNOWN_BAD, f'no known-bad sample for the live format "{fmt}"'
    checker = FormatChecker()
    assert not checker.conforms(KNOWN_BAD[fmt], fmt), (
        f'the "{fmt}" checker accepted {KNOWN_BAD[fmt]!r}; a checker that cannot reject '
        "is indistinguishable from an absent one"
    )


def test_the_date_checker_is_rfc3339_strict_not_fromisoformat() -> None:
    """The two rules disagree, and the disagreement is a shipping hazard.

    ``datetime.date.fromisoformat`` has accepted the basic form (``20260501``) and
    ISO week dates since 3.11; RFC 3339 ``full-date`` accepts neither. A loader that
    validates with ``fromisoformat`` and a publisher that gates on ``"format": "date"``
    would then disagree about the same string. Measured here rather than assumed,
    because which rule this environment's checker implements is a property of the
    installed package, not of the standard.
    """
    checker = FormatChecker()
    assert checker.conforms("2026-05-01", "date")
    for basic in ("20260501", "2026-W01-1", ""):
        assert not checker.conforms(basic, "date"), (
            f"the date checker accepted {basic!r}; it is following fromisoformat rather "
            "than RFC 3339, so a value can pass a loader and fail at publish time"
        )


# --------------------------------------------------------------------------- #
# The registry is gated too, or it becomes the drawer
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("fmt", sorted(UNENFORCED_FORMATS))
def test_the_unenforced_registry_is_self_limiting(fmt: str) -> None:
    assert fmt in DECLARED, (
        f'UNENFORCED_FORMATS names "{fmt}", which no schema or validator in this '
        "repository declares any more — delete the entry"
    )
    assert fmt not in LIVE_CHECKERS, (
        f'UNENFORCED_FORMATS names "{fmt}", but this environment CAN check it now — '
        "delete the entry so the constraint is enforced rather than excused"
    )
    reason = UNENFORCED_FORMATS[fmt]
    assert len(reason.strip()) >= 40, f'"{fmt}" needs a written reason, not a placeholder'


def test_the_registry_is_not_a_blanket_waiver() -> None:
    """Every format this repository declares that IS enforceable must be enforced."""
    excused = set(UNENFORCED_FORMATS)
    assert not (excused & LIVE_CHECKERS), (
        f"an enforceable format is listed as unenforced: {sorted(excused & LIVE_CHECKERS)}"
    )
    enforced = sorted(set(DECLARED) & LIVE_CHECKERS)
    assert enforced, "no declared format is enforced at all — check the discovery walk"
