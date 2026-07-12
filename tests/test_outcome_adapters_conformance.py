"""Conformance checks for sibling official-outcome adapters."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from nearmiss.adapters import FarsAdapter, registry
from nearmiss.adapters.outcomes import OfficialOutcomeAdapter, OutcomeProvenance

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "fars" / "accident.csv"
SCHEMA = json.loads((ROOT / "schema" / "official-outcome.schema.json").read_text())


def test_fars_satisfies_official_outcome_protocol() -> None:
    adapter = FarsAdapter()
    assert isinstance(adapter, OfficialOutcomeAdapter)
    assert adapter.source_id not in registry
    outcomes, provenance = adapter.parse(FIXTURE)
    Draft202012Validator.check_schema(SCHEMA)
    validator = Draft202012Validator(SCHEMA, format_checker=FormatChecker())
    assert outcomes
    for outcome in outcomes:
        assert not list(validator.iter_errors(outcome))
    assert isinstance(provenance, OutcomeProvenance)
    assert provenance.source_id == adapter.source_id
    assert provenance.limitations
    assert provenance.as_dict()["records_accepted"] == len(outcomes)


def test_schema_rejects_positive_fatalities_with_nonfatal_maximum_severity() -> None:
    outcome = {
        "schema_version": "1.0.0",
        "id": str(uuid.uuid4()),
        "source_record_id": "example",
        "occurred_on": "2024-01-01",
        "location": {"lat": 38.5, "lon": -121.7},
        "outcome_type": "motor_vehicle_traffic_crash",
        "maximum_injury_severity": "suspected_serious_injury",
        "fatality_count": 1,
    }
    validator = Draft202012Validator(SCHEMA, format_checker=FormatChecker())
    assert list(validator.iter_errors(outcome))
