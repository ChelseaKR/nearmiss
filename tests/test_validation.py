"""Intake validation rejects malformed reports at the boundary (data integrity)."""

from __future__ import annotations

import copy

import pytest
from jsonschema import FormatChecker

from nearmiss import validation
from nearmiss.validation import validate_report


def test_valid_report_passes(a_valid_report: dict[str, object]) -> None:
    assert validate_report(a_valid_report) == []


def test_missing_required_field_rejected(a_valid_report: dict[str, object]) -> None:
    bad = copy.deepcopy(a_valid_report)
    del bad["hazard_type"]
    assert validate_report(bad)


def test_out_of_range_latitude_rejected(a_valid_report: dict[str, object]) -> None:
    bad = copy.deepcopy(a_valid_report)
    loc = bad["location"]
    assert isinstance(loc, dict)
    loc["lat"] = 999.0
    assert validate_report(bad)


def test_unknown_enum_rejected(a_valid_report: dict[str, object]) -> None:
    bad = copy.deepcopy(a_valid_report)
    bad["hazard_type"] = "asteroid"
    assert validate_report(bad)


def test_additional_property_rejected(a_valid_report: dict[str, object]) -> None:
    bad = copy.deepcopy(a_valid_report)
    bad["evil"] = "payload"
    assert validate_report(bad)


def test_address_only_report_passes(a_valid_report: dict[str, object]) -> None:
    r = copy.deepcopy(a_valid_report)
    del r["location"]
    r["address"] = "B St & 3rd St, Davis CA"
    assert validate_report(r) == []


def test_report_with_neither_location_nor_address_rejected(
    a_valid_report: dict[str, object],
) -> None:
    r = copy.deepcopy(a_valid_report)
    del r["location"]
    assert validate_report(r)


# --- occurred_at: the contract the schema states and could not enforce ---------
#
# report.schema.json says occurred_at is "an ISO-8601 / RFC 3339 date-time with an
# explicit timezone offset (UTC 'Z' or +/-HH:MM)" and declares "format": "date-time".
# Nothing enforced it: `format` is annotation-only unless the validator is built
# with a FormatChecker, and even with one `date-time` is NOT among jsonschema's
# built-in checkers — it needs the optional `rfc3339-validator` package, and when
# that is absent a FormatChecker skips the constraint *silently*. So the rule lives
# in code, and these tests are what keep it honest.


@pytest.mark.parametrize(
    "occurred_at",
    [
        "2026-06-15T08:42:00-07:00",
        "2026-06-15T15:42:00Z",
        "2026-06-15T08:42:00.123456-07:00",
        "2026-06-15T08:42:00+00:00",
    ],
)
def test_rfc3339_timestamps_with_an_offset_pass(
    a_valid_report: dict[str, object], occurred_at: str
) -> None:
    r = copy.deepcopy(a_valid_report)
    r["occurred_at"] = occurred_at
    assert validate_report(r) == []


@pytest.mark.parametrize(
    "occurred_at",
    [
        "",
        "not a time",
        "yesterday",
        "2026-13-45T99:99:99Z",
        "2026-06-15",  # a date, not a date-time
        "2026-06-15T08:42:00",  # parseable, but no offset: an hour in an unstated zone
        "2026-06-15T08:42:00-7:00",  # malformed offset
    ],
)
def test_unreadable_or_offsetless_timestamps_are_rejected(
    a_valid_report: dict[str, object], occurred_at: str
) -> None:
    r = copy.deepcopy(a_valid_report)
    r["occurred_at"] = occurred_at
    problems = validate_report(r)
    assert problems, f"{occurred_at!r} should not validate"
    assert any("RFC 3339" in p for p in problems), problems


def test_the_format_annotation_alone_would_not_have_caught_it() -> None:
    """Pin *why* the timestamp rule is in code rather than left to ``"format"``.

    A ``FormatChecker`` has no ``date-time`` checker unless the optional
    ``rfc3339-validator`` package is installed, and for a format it does not know
    it answers ``conforms() is True`` — it does not raise, warn, or report. So
    "the validator has a format_checker" is not the same claim as "the schema's
    formats are enforced", and this test writes down which of the two holds here.
    """
    checker = FormatChecker()
    if "date-time" not in checker.checkers:
        # The state this repository ships in: garbage "conforms", silently.
        assert checker.conforms("not a time", "date-time") is True
    else:  # pragma: no cover - only when rfc3339-validator is installed
        assert checker.conforms("not a time", "date-time") is False
    # Either way, the code-level rule is the one that bites — and it is stricter
    # than "format": "date-time" would be, because it also requires the offset.
    assert validation._occurred_at_problem({"occurred_at": "2026-06-15T08:42:00"}) is not None
    assert validation._occurred_at_problem({"occurred_at": "2026-06-15T08:42:00Z"}) is None


def test_a_non_string_occurred_at_is_left_to_the_schema(
    a_valid_report: dict[str, object],
) -> None:
    # The timestamp rule must not mask or duplicate the schema's own type error.
    r = copy.deepcopy(a_valid_report)
    r["occurred_at"] = 1750000000
    problems = validate_report(r)
    assert problems
    assert not any("RFC 3339" in p for p in problems), problems
