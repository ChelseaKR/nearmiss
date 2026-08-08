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
from nearmiss.adapters.base import (
    BIAS_AXES,
    CROSSWALK_DIR,
    _load_bias_profile,
    load_crosswalk,
)
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


@pytest.mark.parametrize("source_id", sorted(registry))
def test_crosswalk_answers_every_bias_axis(source_id: str) -> None:
    """Hard rule #3: bias is named, not hidden — axis by axis.

    The old check was ``assert crosswalk.bias_notes``, which a single word
    satisfied. A source's skew is only comparable across sources if each named
    axis is answered separately, so this asserts coverage rather than presence.
    """
    profile = load_crosswalk(source_id).bias_profile
    assert set(profile) == set(BIAS_AXES), (
        f"{source_id}: bias profile must answer exactly the axes {list(BIAS_AXES)}"
    )
    for axis, answer in profile.items():
        assert answer.strip(), f"{source_id}: bias axis {axis!r} is blank"


@pytest.mark.parametrize("source_id", sorted(registry))
def test_bias_axes_are_answered_distinctly(source_id: str) -> None:
    """One paragraph pasted into all eight axes is not a bias profile."""
    profile = load_crosswalk(source_id).bias_profile
    answers = [a.strip() for a in profile.values()]
    assert len(set(answers)) == len(answers), (
        f"{source_id}: at least two bias axes carry an identical answer; each axis asks a "
        f"different question and needs its own answer"
    )


def test_every_crosswalk_manifest_is_registered() -> None:
    """A manifest on disk that no adapter registers is a silent contract gap.

    Without this, someone can add ``crosswalks/foo.toml`` and never wire up an
    adapter, and no test would ever load (and therefore validate) that file.
    """
    on_disk = {p.stem for p in CROSSWALK_DIR.glob("*.toml")}
    assert on_disk == set(registry), (
        f"crosswalk manifests on disk {sorted(on_disk)} do not match the registry "
        f"{sorted(registry)}"
    )


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
    assert set(provenance.bias_profile) == set(BIAS_AXES)
    assert provenance.bias_notes  # derived view, one entry per axis
    emitted = provenance.as_dict()
    assert emitted["source_id"] == source_id
    assert set(emitted["bias_profile"]) == set(BIAS_AXES)


# --- the bias-profile gate itself -------------------------------------------
# These exercise the validator directly rather than through a manifest file, so
# a new source cannot quietly reach the registry with its skew undocumented.

_GOOD_ANSWER = (
    "A substantive, source-specific answer that is comfortably longer than the "
    "minimum length this validator enforces."
)


def _profile(**overrides: object) -> dict[str, object]:
    profile: dict[str, object] = {axis: f"{_GOOD_ANSWER} ({axis})" for axis in BIAS_AXES}
    profile.update(overrides)
    return profile


def test_bias_profile_accepts_a_complete_manifest() -> None:
    loaded = _load_bias_profile("fixture", {"bias_profile": _profile()})
    assert set(loaded) == set(BIAS_AXES)


def test_bias_profile_rejects_a_missing_table() -> None:
    with pytest.raises(ValueError, match="required"):
        _load_bias_profile("fixture", {})


def test_bias_profile_rejects_a_missing_axis() -> None:
    incomplete = _profile()
    del incomplete["language"]
    with pytest.raises(ValueError, match="language"):
        _load_bias_profile("fixture", {"bias_profile": incomplete})


def test_bias_profile_rejects_an_unknown_axis() -> None:
    with pytest.raises(ValueError, match="unrecognized"):
        _load_bias_profile("fixture", {"bias_profile": _profile(vibes=_GOOD_ANSWER)})


@pytest.mark.parametrize("placeholder", ["", "n/a", "N/A.", "none", "TBD", "unknown"])
def test_bias_profile_rejects_placeholder_answers(placeholder: str) -> None:
    """The regression this whole gate exists for: a non-answer used to pass."""
    with pytest.raises(ValueError, match="salience"):
        _load_bias_profile("fixture", {"bias_profile": _profile(salience=placeholder)})


def test_bias_profile_rejects_a_too_short_answer() -> None:
    with pytest.raises(ValueError, match="survivorship"):
        _load_bias_profile("fixture", {"bias_profile": _profile(survivorship="skewed")})


def test_bias_profile_rejects_a_non_string_answer() -> None:
    with pytest.raises(ValueError, match="must be a string"):
        _load_bias_profile("fixture", {"bias_profile": _profile(language=["a", "b"])})
