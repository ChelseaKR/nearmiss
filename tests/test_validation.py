"""Intake validation rejects malformed reports at the boundary (data integrity)."""

from __future__ import annotations

import copy

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
