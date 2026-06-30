"""Schema location, the env override, and the raise-on-invalid helper.

Complements test_validation.py (which exercises the accept/reject rules) by
covering how the validator finds its schema and how :func:`require_valid` turns a
list of problems into a typed :class:`ValidationError`.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from nearmiss import validation
from nearmiss.errors import ValidationError
from nearmiss.validation import (
    _ENV_OVERRIDE,
    find_report_schema,
    require_valid,
    validate_report,
)


def test_env_override_is_honored_by_find_report_schema(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(_ENV_OVERRIDE, "/some/where/report.schema.json")
    assert find_report_schema() == Path("/some/where/report.schema.json")


def test_find_report_schema_walks_up_to_the_repo_schema(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(_ENV_OVERRIDE, raising=False)
    found = find_report_schema()
    assert found.is_file()
    assert found.name == "report.schema.json"


def test_missing_schema_raises_validation_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # No env override, and the module's location is moved under a temp tree whose
    # ancestors contain no schema/report.schema.json -> the walk-up fails loudly.
    monkeypatch.delenv(_ENV_OVERRIDE, raising=False)
    monkeypatch.setattr(validation, "__file__", str(tmp_path / "pkg" / "validation.py"))
    with pytest.raises(ValidationError, match="could not locate schema"):
        find_report_schema()


def test_env_override_schema_is_actually_used_for_validation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, a_valid_report: dict[str, object]
) -> None:
    # Point the override at a stricter schema (no location/address requirement,
    # an extra mandatory field) and confirm validate_report routes through it.
    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "required": ["must_have_me"],
    }
    schema_path = tmp_path / "override.schema.json"
    schema_path.write_text(json.dumps(schema), encoding="utf-8")
    monkeypatch.setenv(_ENV_OVERRIDE, str(schema_path))

    problems = validate_report(copy.deepcopy(a_valid_report))
    assert problems  # rejected: the override requires a field the report lacks
    assert any("must_have_me" in p for p in problems)


def test_require_valid_accepts_a_valid_report(a_valid_report: dict[str, object]) -> None:
    require_valid(a_valid_report)  # contract: returns normally (no raise) when valid


def test_require_valid_raises_with_id_and_problems(a_valid_report: dict[str, object]) -> None:
    bad = copy.deepcopy(a_valid_report)
    bad["severity"] = "catastrophic"  # not in the closed vocabulary
    with pytest.raises(ValidationError) as excinfo:
        require_valid(bad)
    err = excinfo.value
    assert repr(bad["id"]) in str(err)  # the report id is named in the message
    assert err.problems  # every concrete problem is carried for the operator
