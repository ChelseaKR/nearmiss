"""Adapter conformance: every registered SourceAdapter round-trips through
validation.validate_report and carries a real Provenance block (EXP-04).

This is the "adding a new source touches no pipeline code" bar from
docs/ideation/03-expansions.md EXP-04: a new adapter only has to pass this
suite (plus its own source-specific fixture tests, e.g. test_fetch_simra.py)
to be a first-class citizen of the intake pipeline.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from nearmiss.adapters import Provenance, SourceAdapter, registry
from nearmiss.adapters.base import load_crosswalk
from nearmiss.validation import validate_report

# One tiny fixture payload per registered source, exercised through parse()
# only (never fetch()) so this suite needs no network, mirroring every
# adapter's own --from-file / --dir offline path.
_FIXTURE_KWARGS: dict[str, dict[str, object]] = {
    "bikemaps": {
        "raw": {
            "nearmiss": [
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [-123.365, 48.428]},
                    "properties": {
                        "pk": 1,
                        "date": "2023-05-01T17:30:00Z",
                        "incident_with": "Vehicle, passing",
                    },
                }
            ]
        },
        "bbox": None,
        "utc_offset": "+00:00",
    },
    "simra": {
        "raw": Path(__file__).resolve().parent / "fixtures" / "simra",
        "bbox": None,
    },
}


@pytest.mark.parametrize("source_id", sorted(registry))
def test_every_registered_source_id_matches_key(source_id: str) -> None:
    assert registry[source_id].source_id == source_id


@pytest.mark.parametrize("source_id", sorted(registry))
def test_adapter_satisfies_protocol(source_id: str) -> None:
    assert isinstance(registry[source_id], SourceAdapter)


@pytest.mark.parametrize("source_id", sorted(registry))
def test_crosswalk_loads_and_validates_against_intake_schema(source_id: str) -> None:
    # load_crosswalk() itself raises ValueError if a mapped value falls outside
    # the intake schema's closed hazard_type/severity enums; loading it here is
    # the "validated against ... schema" check from the EXP-04 shape.
    crosswalk = load_crosswalk(source_id)
    assert crosswalk.source_id == source_id
    assert crosswalk.bias_label  # every source must name its own bias, not hide it


@pytest.mark.parametrize("source_id", sorted(_FIXTURE_KWARGS))
def test_parse_round_trips_through_validate_report(source_id: str) -> None:
    adapter = registry[source_id]
    kwargs = dict(_FIXTURE_KWARGS[source_id])
    raw = kwargs.pop("raw")
    reports, provenance = adapter.parse(raw, **kwargs)

    assert reports, f"{source_id} fixture produced no reports"
    for report in reports:
        problems = validate_report(report)
        assert not problems, f"{source_id} report failed schema validation: {problems}"

    assert isinstance(provenance, Provenance)
    assert provenance.source_id == source_id
    assert provenance.bias_label
    assert provenance.bias_notes
    assert provenance.as_dict()["source_id"] == source_id
