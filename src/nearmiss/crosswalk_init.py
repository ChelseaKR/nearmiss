# SPDX-License-Identifier: Apache-2.0
"""Build a spreadsheet crosswalk manifest from a group's own CSV export.

``nearmiss crosswalk init --from reports.csv`` inspects the header row,
proposes which column carries which intake field, collects the source metadata
and the eight bias answers the framework already enforces, and writes a
crosswalk TOML that :mod:`nearmiss.adapters.spreadsheet` can read.

Inference is a *suggestion*, never a decision. Three things make this refuse
rather than guess:

* a required intake field no column matches (``mode``, ``hazard_type``,
  ``severity``, ``occurred_at``) and no answer supplies;
* two columns matching one intake field, or one column matching two, with
  nothing to break the tie;
* a mode, hazard or severity value the answers do not map — for ``mode`` that
  is fatal at import time by design, so it is named here instead of discovered
  later as a row count that quietly fell.

Whatever is written is loaded straight back through
:func:`~nearmiss.adapters.base.load_crosswalk_file` and
:func:`~nearmiss.adapters.spreadsheet.load_field_map` before this returns, so a
generated manifest passes exactly the checks a hand-written one does. A blank
bias answer is rejected by the same code path that rejects it in
``crosswalks/bikemaps.toml``; there is no generator-only lane.
"""

from __future__ import annotations

import csv
import tomllib
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .adapters.base import BIAS_AXES, PUBLICATION_STATUSES, load_crosswalk_file
from .adapters.spreadsheet import (
    MAPPABLE_COLUMNS,
    REQUIRED_COLUMNS,
    SpreadsheetCrosswalkError,
    load_field_map,
)

#: Header spellings that suggest an intake field, normalized (lower-cased, with
#: spaces, hyphens and underscores removed) before comparison. Kept small and
#: literal on purpose: a fuzzy matcher that is right most of the time is worse
#: than an exact one that says "I do not know" out loud, because the failure it
#: produces is a silently mis-mapped column rather than a refusal.
COLUMN_SYNONYMS: dict[str, tuple[str, ...]] = {
    "occurred_at": (
        "occurredat",
        "occurred",
        "date",
        "datetime",
        "datetimeoccurred",
        "when",
        "whenithappened",
        "timestamp",
        "incidentdate",
        "dateoccurred",
        "eventtime",
    ),
    "mode": (
        "mode",
        "travelmode",
        "modeoftravel",
        "travellingby",
        "travelingby",
        "howwereyoutravelling",
        "howwereyoutraveling",
        "transportmode",
        "roaduser",
    ),
    "hazard_type": (
        "hazardtype",
        "hazard",
        "type",
        "incidenttype",
        "whathappened",
        "category",
        "conflicttype",
        "kind",
    ),
    "severity": ("severity", "outcome", "injury", "howbad", "result", "harm"),
    "lat": ("lat", "latitude", "ycoord", "y"),
    "lon": ("lon", "lng", "long", "longitude", "xcoord", "x"),
    "address": ("address", "streetaddress", "intersection", "street", "where", "place"),
    "note": ("note", "notes", "description", "details", "comment", "comments", "narrative"),
    "language": ("language", "lang"),
}

#: Fields whose *values* need a source-vocabulary mapping. ``mode`` has no
#: default anywhere in this system, so an unmapped value costs the row.
VALUE_MAPPED_FIELDS: tuple[str, ...] = ("mode", "hazard_type", "severity")


class CrosswalkInitError(ValueError):
    """The answers and the spreadsheet cannot produce a usable crosswalk."""


@dataclass(frozen=True)
class ColumnProposal:
    """What inference concluded about one spreadsheet's header row."""

    #: intake field -> the single header that matched it.
    matched: dict[str, str]
    #: intake field -> the several headers that matched it, none chosen.
    ambiguous: dict[str, tuple[str, ...]]
    #: header -> the several intake fields it matched, none chosen.
    contested: dict[str, tuple[str, ...]]
    #: headers no intake field claimed.
    unmatched: tuple[str, ...]


def normalize_header(header: str) -> str:
    return "".join(ch for ch in header.strip().casefold() if ch.isalnum())


def read_headers(path: Path) -> tuple[str, ...]:
    """The CSV's header row, in file order."""
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        try:
            row = next(reader)
        except StopIteration:
            raise CrosswalkInitError(
                f"{path} is empty: there is no header row to inspect"
            ) from None
    headers = [cell.strip() for cell in row if cell.strip()]
    if not headers:
        raise CrosswalkInitError(f"{path}'s header row holds no named columns")
    return tuple(headers)


def distinct_values(path: Path, column: str, limit: int = 200) -> tuple[str, ...]:
    """The distinct non-blank values in one column, in first-appearance order."""
    seen: dict[str, None] = {}
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            value = (row.get(column) or "").strip()
            if value and value not in seen:
                seen[value] = None
                if len(seen) >= limit:
                    break
    return tuple(seen)


def propose_columns(headers: Iterable[str]) -> ColumnProposal:
    """Match headers to intake fields, reporting every tie rather than breaking it."""
    headers = tuple(headers)
    by_field: dict[str, list[str]] = {}
    by_header: dict[str, list[str]] = {}
    for header in headers:
        normalized = normalize_header(header)
        for intake_field, synonyms in COLUMN_SYNONYMS.items():
            if normalized in synonyms:
                by_field.setdefault(intake_field, []).append(header)
                by_header.setdefault(header, []).append(intake_field)

    matched = {f: hs[0] for f, hs in by_field.items() if len(hs) == 1}
    ambiguous = {f: tuple(hs) for f, hs in by_field.items() if len(hs) > 1}
    contested = {h: tuple(fs) for h, fs in by_header.items() if len(fs) > 1}
    # A header claimed by two fields decides neither of them.
    for header, fields in contested.items():
        for intake_field in fields:
            if matched.get(intake_field) == header:
                del matched[intake_field]
    return ColumnProposal(
        matched=matched,
        ambiguous=ambiguous,
        contested=contested,
        unmatched=tuple(h for h in headers if h not in by_header),
    )


def _toml_string(value: str) -> str:
    """One TOML basic string, escaped."""
    escaped = (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\t", "\\t")
    )
    return f'"{escaped}"'


def _rules_block(field_name: str, rules: list[dict[str, str]], key: str) -> list[str]:
    lines: list[str] = []
    for rule in rules:
        lines.append(f"[[{field_name}.rules]]")
        lines.append(f"{key} = {_toml_string(str(rule[key]))}")
        lines.append(f"value = {_toml_string(str(rule['value']))}")
        lines.append(f"rationale = {_toml_string(str(rule.get('rationale', '')))}")
        lines.append("")
    return lines


def render_crosswalk(answers: dict[str, Any], columns: dict[str, str]) -> str:
    """Render the crosswalk TOML. Validation happens in :func:`init_crosswalk`."""
    source = answers["source"]
    lines = [
        "# SPDX-License-Identifier: Apache-2.0",
        "# Spreadsheet crosswalk, generated by `nearmiss crosswalk init`.",
        "#",
        "# Edit it: this is a starting point, not an authority. The [field_map]",
        "# columns were proposed from the header row and confirmed by the answers",
        "# file; every value rule below came from the answers, never from a guess.",
        "# An unmapped mode value costs its row at import time, by design.",
        "",
        "[source]",
    ]
    for key in (
        "id",
        "name",
        "url",
        "license",
        "publication_status",
        "publication_note",
        "bias_label",
    ):
        lines.append(f"{key} = {_toml_string(str(source[key]))}")
    lines += ["", "# --- bias profile ---", "[source.bias_profile]"]
    for axis in BIAS_AXES:
        lines.append(f"{axis} = {_toml_string(str(source['bias_profile'][axis]))}")

    lines += ["", "# --- which column carries which intake field ---", "[field_map]"]
    for intake_field in MAPPABLE_COLUMNS:
        if intake_field in columns:
            lines.append(f"{intake_field} = {_toml_string(columns[intake_field])}")
    offset = answers.get("field_map", {}).get("timezone_offset")
    if offset:
        lines.append(f"timezone_offset = {_toml_string(str(offset))}")
    else:
        lines.append("# timezone_offset is unset: a timestamp with no offset of its own is")
        lines.append("# excluded and counted rather than given an invented hour.")

    lines += ["", "# --- travel mode: no default, ever ---"]
    lines += _rules_block("mode", list(answers.get("mode", {}).get("rules", [])), "when")

    hazard = answers.get("hazard_type", {})
    lines += [
        "# --- hazard type ---",
        "[hazard_type]",
        f"default = {_toml_string(str(hazard.get('default', 'other')))}",
        "",
    ]
    lines += _rules_block("hazard_type", list(hazard.get("rules", [])), "when")

    severity = answers.get("severity", {})
    lines += [
        "# --- severity ---",
        "[severity]",
        f"default = {_toml_string(str(severity.get('default', 'near_miss')))}",
        "",
    ]
    lines += _rules_block("severity", list(severity.get("rules", [])), "contains")
    return "\n".join(lines).rstrip("\n") + "\n"


def _require_answers_shape(answers: dict[str, Any]) -> None:
    source = answers.get("source")
    if not isinstance(source, dict):
        raise CrosswalkInitError(
            "the answers file needs a [source] table (id, name, url, license, "
            "publication_status, publication_note, bias_label)"
        )
    missing = [
        key
        for key in (
            "id",
            "name",
            "url",
            "license",
            "publication_status",
            "publication_note",
            "bias_label",
        )
        if not str(source.get(key, "")).strip()
    ]
    if missing:
        raise CrosswalkInitError(f"[source] is missing {missing}")
    if source["publication_status"] not in PUBLICATION_STATUSES:
        raise CrosswalkInitError(
            f"[source] publication_status must be one of {list(PUBLICATION_STATUSES)}; "
            f"a source whose redistribution terms nobody has established here is "
            f"'undetermined', not omitted"
        )
    profile = source.get("bias_profile")
    if not isinstance(profile, dict):
        raise CrosswalkInitError(
            f"[source.bias_profile] must answer every axis in {list(BIAS_AXES)}"
        )


def resolve_columns(
    headers: tuple[str, ...], proposal: ColumnProposal, overrides: dict[str, Any]
) -> dict[str, str]:
    """Inferred columns with the answers file's overrides applied, or a refusal."""
    columns = dict(proposal.matched)
    for intake_field, header in overrides.items():
        if intake_field == "timezone_offset":
            continue
        if intake_field not in MAPPABLE_COLUMNS:
            raise CrosswalkInitError(
                f"[field_map] names {intake_field!r}, which is not an intake field; "
                f"the mappable fields are {list(MAPPABLE_COLUMNS)}"
            )
        if header == "":
            columns.pop(intake_field, None)
            continue
        if header not in headers:
            raise CrosswalkInitError(
                f"[field_map] maps {intake_field} to column {header!r}, which the "
                f"spreadsheet does not have. Its columns are {list(headers)}."
            )
        columns[intake_field] = str(header)

    unresolved_ties = {
        f: hs
        for f, hs in proposal.ambiguous.items()
        if f not in overrides and f in REQUIRED_COLUMNS
    }
    if unresolved_ties:
        detail = "; ".join(f"{f}: {list(hs)}" for f, hs in sorted(unresolved_ties.items()))
        raise CrosswalkInitError(
            f"more than one column matches a required intake field ({detail}). Name the "
            f"one you mean in the answers file's [field_map]; picking for you would be a "
            f"guess about your data."
        )
    missing = [f for f in REQUIRED_COLUMNS if f not in columns]
    if missing:
        raise CrosswalkInitError(
            f"no column carries required intake field(s) {missing}, and the answers file "
            f"does not name one. The spreadsheet's columns are {list(headers)}. These "
            f"fields are never defaulted: a report whose mode nobody wrote down is not a "
            f"report about anybody."
        )
    return columns


def unmapped_mode_values(path: Path, column: str, rules: list[dict[str, str]]) -> tuple[str, ...]:
    """Distinct mode values in the export that the answers do not map."""
    mapped = {str(rule.get("when", "")).casefold() for rule in rules}
    return tuple(v for v in distinct_values(path, column) if v.casefold() not in mapped)


def init_crosswalk(csv_path: Path, answers: dict[str, Any], out_path: Path) -> Path:
    """Write a validated crosswalk for ``csv_path`` at ``out_path``.

    Raises :class:`CrosswalkInitError` (or the loaders' own errors) rather than
    writing a manifest that would not load.
    """
    _require_answers_shape(answers)
    headers = read_headers(csv_path)
    proposal = propose_columns(headers)
    columns = resolve_columns(headers, proposal, dict(answers.get("field_map", {})))

    mode_rules = list(answers.get("mode", {}).get("rules", []))
    if not mode_rules:
        raise CrosswalkInitError(
            "the answers file maps no travel modes. [[mode.rules]] must map every value "
            "the mode column uses onto the intake enum; there is no default to fall back on."
        )
    unmapped = unmapped_mode_values(csv_path, columns["mode"], mode_rules)
    if unmapped:
        raise CrosswalkInitError(
            f"the mode column {columns['mode']!r} holds value(s) {list(unmapped)} that "
            f"[[mode.rules]] does not map. Every one of those rows would be excluded at "
            f"import; map them or say in the data card why they are out of scope."
        )

    text = render_crosswalk(answers, columns)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    scratch = out_path.with_name(out_path.name + ".partial")
    scratch.write_text(text, encoding="utf-8")
    try:
        load_crosswalk_file(scratch, name=str(answers["source"]["id"]))
        load_field_map(scratch, name=str(answers["source"]["id"]))
    except (ValueError, SpreadsheetCrosswalkError):
        scratch.unlink(missing_ok=True)
        raise
    scratch.replace(out_path)
    return out_path


def load_answers(path: Path) -> dict[str, Any]:
    with path.open("rb") as handle:
        return tomllib.load(handle)


# --- interactive path --------------------------------------------------------

_INTAKE_MODES = ("cyclist", "pedestrian", "wheelchair", "scooter", "other")
_INTAKE_HAZARDS = (
    "close_pass",
    "dooring",
    "surface_hazard",
    "sightline",
    "signal",
    "debris",
    "other",
)
_INTAKE_SEVERITIES = ("near_miss", "minor", "serious")


def prompt_answers(
    csv_path: Path,
    ask: Callable[[str], str],
    say: Callable[[str], None],
) -> dict[str, Any]:
    """Collect the same answers interactively that ``--answers`` supplies.

    ``ask``/``say`` are injected so the whole flow is testable without a
    terminal; ``nearmiss crosswalk init`` passes :func:`input` and a printer.
    """
    headers = read_headers(csv_path)
    proposal = propose_columns(headers)
    say(f"Columns found: {', '.join(headers)}")

    source: dict[str, Any] = {}
    for key, question in (
        ("id", "Short source id (lowercase, no spaces)"),
        ("name", "Source name, as you would cite it"),
        ("url", "URL for the source, or a description of where it lives"),
        ("license", "Licence or rights basis for these records"),
        ("publication_note", "On what basis was that status reached? Name the clause or document"),
        ("bias_label", "One line naming this source's skew"),
    ):
        source[key] = ask(f"{question}: ").strip()
        if key == "license":
            say(f"publication_status must be one of: {', '.join(PUBLICATION_STATUSES)}")
            source["publication_status"] = ask("publication_status: ").strip()
    say("Now the eight bias axes. Each needs a substantive answer in your own terms;")
    say("'n/a' is rejected, and an axis that does not apply must say why.")
    source["bias_profile"] = {axis: ask(f"  {axis}: ").strip() for axis in BIAS_AXES}

    field_map: dict[str, Any] = {}
    for intake_field in MAPPABLE_COLUMNS:
        suggestion = proposal.matched.get(intake_field, "")
        hint = f" [{suggestion}]" if suggestion else ""
        required = " (required)" if intake_field in REQUIRED_COLUMNS else ""
        answer = ask(f"Column for {intake_field}{required}{hint}: ").strip()
        if answer:
            field_map[intake_field] = answer
        elif suggestion:
            field_map[intake_field] = suggestion
    offset = ask("Fixed UTC offset for naive timestamps (e.g. -07:00, blank for none): ").strip()
    if offset:
        field_map["timezone_offset"] = offset

    answers: dict[str, Any] = {"source": source, "field_map": field_map}

    mode_column = field_map.get("mode")
    if mode_column:
        say(f"Map each value in {mode_column!r} onto one of: {', '.join(_INTAKE_MODES)}")
        say("There is no default. A value left blank costs every row that carries it.")
        answers["mode"] = {"rules": _prompt_value_rules(csv_path, mode_column, "when", ask)}

    # hazard_type and severity do have defaults, and an unmapped value lands on
    # them rather than costing the row. That makes the default a claim, so it is
    # asked for rather than assumed, and every distinct value gets its own turn.
    for intake_field, key, enum_hint, fallback in (
        ("hazard_type", "when", _INTAKE_HAZARDS, "other"),
        ("severity", "contains", _INTAKE_SEVERITIES, "near_miss"),
    ):
        column = field_map.get(intake_field)
        if not column:
            continue
        say(f"Map each value in {column!r} onto one of: {', '.join(enum_hint)}")
        rules = _prompt_value_rules(csv_path, column, key, ask)
        default = ask(f"Default {intake_field} for a value you did not map [{fallback}]: ").strip()
        answers[intake_field] = {"default": default or fallback, "rules": rules}
    return answers


def _prompt_value_rules(
    csv_path: Path, column: str, key: str, ask: Callable[[str], str]
) -> list[dict[str, str]]:
    """One rule per distinct value in ``column`` that the author chooses to map."""
    rules: list[dict[str, str]] = []
    for value in distinct_values(csv_path, column):
        mapped = ask(f"  {value!r} -> ").strip()
        if mapped:
            rules.append({key: value, "value": mapped, "rationale": "mapped by the author"})
    return rules
