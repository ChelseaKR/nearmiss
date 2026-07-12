"""The published dataset conforms to its machine-readable contract (FIX-10).

`schema/dataset.schema.json` is the authoritative, validator-runnable form of the
prose contract in `schema/dataset.schema.md`. These tests are the CI gate for it:

* every committed ``data/published/*.geojson`` validates against the JSON Schema;
* a mutated dataset (renamed property, missing metadata member, bad enum) is
  rejected, so the schema actually constrains and is not vacuously true;
* the schema's pinned ``schema_version`` matches what ``publish.py`` writes; and
* the JSON Schema's feature-property vocabulary and the prose field tables do not
  drift apart (the schema/prose-drift risk called out in the FIX-10 review).
"""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any

import pytest
from jsonschema.protocols import Validator
from jsonschema.validators import validator_for

from nearmiss.errors import ValidationError
from nearmiss.publish import assert_conforms_to_schema

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_JSON = ROOT / "schema" / "dataset.schema.json"
SCHEMA_MD = ROOT / "schema" / "dataset.schema.md"
PUBLISHED = ROOT / "data" / "published"
PUBLISHED_GEOJSON = sorted(PUBLISHED.glob("*.geojson"))


def _load_schema() -> Any:
    return json.loads(SCHEMA_JSON.read_text(encoding="utf-8"))


def _validator() -> Validator:
    schema = _load_schema()
    cls = validator_for(schema)
    cls.check_schema(schema)
    return cls(schema)


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def test_schema_is_itself_a_valid_json_schema() -> None:
    schema = _load_schema()
    cls = validator_for(schema)
    cls.check_schema(schema)  # raises if the schema document is malformed


def test_committed_geojson_files_exist() -> None:
    # Guard against the glob silently matching nothing (which would make the
    # parametrized validation test vacuously pass).
    assert PUBLISHED_GEOJSON, f"no published *.geojson found under {PUBLISHED}"


@pytest.mark.parametrize("path", PUBLISHED_GEOJSON, ids=lambda p: p.name)
def test_published_geojson_validates(path: Path) -> None:
    validator = _validator()
    errors = sorted(validator.iter_errors(_load(path)), key=lambda e: list(e.path))
    assert not errors, "\n".join(
        f"{'/'.join(str(p) for p in e.path) or '<root>'}: {e.message}" for e in errors[:10]
    )


def _davis() -> Any:
    davis = PUBLISHED / "davis.geojson"
    assert davis.exists(), "davis.geojson fixture missing"
    return _load(davis)


def _has_errors(data: Any) -> bool:
    return bool(list(_validator().iter_errors(data)))


def test_renamed_property_fails_validation() -> None:
    data = _davis()
    props = data["features"][0]["properties"]
    # Rename a required property: additionalProperties is permissive, but the
    # required list must still bite when the canonical name disappears.
    props["raite"] = props.pop("rate")
    assert _has_errors(data), "renaming 'rate' should fail validation"


def test_removed_metadata_member_fails_validation() -> None:
    data = _davis()
    del data["metadata"]["schema_version"]
    assert _has_errors(data), "dropping metadata.schema_version should fail"


def test_bad_enum_value_fails_validation() -> None:
    data = _davis()
    data["features"][0]["properties"]["confidence_label"] = "definitely"
    assert _has_errors(data), "an unknown confidence_label should fail"


def test_removed_required_feature_property_fails_validation() -> None:
    data = _davis()
    del data["features"][0]["properties"]["hazard_breakdown"]
    assert _has_errors(data), "dropping a required feature property should fail"


def test_publish_time_gate_accepts_valid_and_rejects_invalid() -> None:
    # The self-check publish.py runs before writing: a valid document passes, a
    # schema-violating one raises rather than shipping (HR5 contract gate).
    assert_conforms_to_schema(_davis())
    bad = _davis()
    del bad["features"][0]["properties"]["rate"]
    with pytest.raises(ValidationError) as exc:
        assert_conforms_to_schema(bad)
    assert "dataset.schema.json" in str(exc.value)
    assert exc.value.problems  # each schema error surfaced for debugging


def test_pristine_copy_still_validates() -> None:
    # Sanity: the deep-copy/mutation machinery above starts from a valid document,
    # so the negative tests are meaningfully negative.
    assert not _has_errors(copy.deepcopy(_davis()))


def test_schema_version_matches_published() -> None:
    schema = _load_schema()
    const = schema["$defs"]["metadata"]["properties"]["schema_version"]["const"]
    assert const == "1.0.0", f"schema pins schema_version {const!r}"
    # And it must equal what publish.py actually wrote into the committed files.
    for path in PUBLISHED_GEOJSON:
        meta = _load(path)["metadata"]
        assert meta["schema_version"] == const, (
            f"{path.name} metadata.schema_version {meta['schema_version']!r} "
            f"!= schema const {const!r}"
        )


# --- schema / prose drift guard -------------------------------------------------

_MD_PROPERTY_TABLE_HEADER = re.compile(r"^\|\s*Property\s*\|")
_MD_ROW = re.compile(r"^\|\s*`([a-z0-9_]+)`\s*\|")


def _md_property_names() -> set[str]:
    """Extract feature-property names from the ``| Property | ... |`` tables of the
    prose schema doc (sections 4.x). Deliberately ignores the metadata (``| Field |``)
    and vocabulary (``| Flag |``) tables so only the feature-property vocabulary is
    compared against the JSON Schema."""
    names: set[str] = set()
    in_property_table = False
    for raw in SCHEMA_MD.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if _MD_PROPERTY_TABLE_HEADER.match(line):
            in_property_table = True
            continue
        if in_property_table:
            if not line.startswith("|"):
                in_property_table = False
                continue
            m = _MD_ROW.match(line)
            if m:
                names.add(m.group(1))
    return names


def _schema_property_names() -> set[str]:
    schema = _load_schema()
    return set(schema["$defs"]["properties"]["properties"].keys())


def test_prose_and_schema_feature_properties_do_not_drift() -> None:
    md_names = _md_property_names()
    schema_names = _schema_property_names()
    assert md_names, "extracted no property names from the prose field tables"
    missing_from_schema = md_names - schema_names
    missing_from_prose = schema_names - md_names
    assert not missing_from_schema, (
        f"documented in dataset.schema.md but absent from dataset.schema.json: "
        f"{sorted(missing_from_schema)}"
    )
    assert not missing_from_prose, (
        f"in dataset.schema.json but not documented in the dataset.schema.md field tables: "
        f"{sorted(missing_from_prose)}"
    )


def test_all_documented_properties_are_required() -> None:
    # publish.py emits every feature property for every feature, so each documented
    # property is required (not merely permitted) in the schema.
    schema = _load_schema()
    required = set(schema["$defs"]["properties"]["required"])
    assert _md_property_names() == required
