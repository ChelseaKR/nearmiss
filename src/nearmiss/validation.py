"""Schema validation at intake.

A report is validated against ``schema/report.schema.json`` (JSON Schema draft
2020-12) before it is allowed anywhere near the dataset. A malformed or
malicious report is rejected here, never silently corrupting downstream results
(dependability / data integrity / safety).
"""

from __future__ import annotations

import functools
import json
import os
from pathlib import Path

from jsonschema import Draft202012Validator

from .errors import ValidationError

_ENV_OVERRIDE = "NEARMISS_REPORT_SCHEMA"


def find_report_schema() -> Path:
    """Locate report.schema.json via env override or by walking up the tree."""
    override = os.environ.get(_ENV_OVERRIDE)
    if override:
        return Path(override)
    here = Path(__file__).resolve()
    for parent in [here.parent, *here.parents]:
        candidate = parent / "schema" / "report.schema.json"
        if candidate.is_file():
            return candidate
    raise ValidationError(
        f"could not locate schema/report.schema.json; set {_ENV_OVERRIDE} to its path"
    )


@functools.lru_cache(maxsize=1)
def _validator() -> Draft202012Validator:
    schema = json.loads(find_report_schema().read_text(encoding="utf-8"))
    return Draft202012Validator(schema)


def validate_report(report: dict[str, object]) -> list[str]:
    """Return a list of human-readable problems; empty means valid."""
    problems: list[str] = []
    for err in sorted(_validator().iter_errors(report), key=lambda e: list(e.path)):
        location = "/".join(str(p) for p in err.path) or "(root)"
        problems.append(f"{location}: {err.message}")
    return problems


def require_valid(report: dict[str, object]) -> None:
    """Raise :class:`ValidationError` if the report is invalid."""
    problems = validate_report(report)
    if problems:
        rid = report.get("id", "<no id>")
        raise ValidationError(f"report {rid!r} failed validation", problems)
