"""The `mypy --strict` gate must actually cover the scripts the README says it covers.

The README carries a "Types: mypy strict" badge and says "mypy strict in CI". For most of
this repository's life that was true of `src/` and `tests/` and false of `tools/`: the
`[tool.mypy] files` list named two of the three trees, so all 31 scripts under `tools/`
— every gate the project runs on itself, `verify_dataset.py` and `conformance_sweep.py`
included — were outside it. PR #214 measured the cost of closing it (97 errors across 21
files) and recorded it as the largest remaining gap rather than fixing it there.

That gap was invisible for the usual reason: nothing failed. The type job was green, and
green over a narrower scope than advertised looks exactly like green over the advertised
one. So this file is the witness — the same treatment `tests/test_accessibility_claims.py`
gives the structural a11y gate's file list.

It checks two things, because the scope can be lost in two different ways:

1. **`files` names every first-party tree.** Drop `"tools"` and the gate silently stops
   checking a third of the project's Python.
2. **The packages `tools/` imports ship `py.typed`.** Without those markers mypy treats
   `import nearmiss...` from outside the package as untyped, hands back `Any` for every
   call, and a script can be inside `files` while nothing in it is really checked. That is
   the more dangerous of the two, because `files` still reads correctly.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[1]
PYPROJECT = REPOSITORY / "pyproject.toml"

#: Every top-level tree holding first-party Python that a merge gate executes.
FIRST_PARTY_TREES = ("src", "tests", "tools")

#: Distributions under `src/` that `tools/` and `tests/` import across a package
#: boundary, and that therefore need an inline-types marker to be checked at all.
TYPED_DISTRIBUTIONS = ("nearmiss", "honest_rates")


def _mypy_config() -> dict[str, object]:
    config = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    mypy = config["tool"]["mypy"]
    assert isinstance(mypy, dict)
    return mypy


def test_the_type_gate_covers_every_first_party_tree() -> None:
    """`[tool.mypy] files` names src, tests AND tools — not two of the three."""
    files = _mypy_config()["files"]
    assert isinstance(files, list), "[tool.mypy] files must be a list of trees"
    missing = [tree for tree in FIRST_PARTY_TREES if tree not in files]
    assert not missing, (
        f"mypy's scope omits {missing}, so the README's 'mypy strict' badge covers less "
        f"than it claims. Declared scope: {files}"
    )


def test_the_type_gate_is_still_strict() -> None:
    """A wider scope is worthless if the strictness that gives it meaning is relaxed."""
    mypy = _mypy_config()
    for setting in ("strict", "warn_unreachable", "disallow_any_generics"):
        assert mypy.get(setting) is True, f"[tool.mypy] {setting} must stay enabled"


def test_every_tool_script_is_inside_the_declared_scope() -> None:
    """No script under `tools/` is carved back out by an exclude."""
    mypy = _mypy_config()
    excluded = mypy.get("exclude", [])
    patterns: list[object]
    if isinstance(excluded, str):
        patterns = [excluded]
    elif isinstance(excluded, list):
        patterns = list(excluded)
    else:  # a scalar of some other type: still has to be inspected, not skipped
        patterns = [excluded]
    offenders = [pattern for pattern in patterns if "tools" in str(pattern)]
    assert not offenders, f"[tool.mypy] exclude carves scripts back out of the gate: {offenders}"
    scripts = sorted(p.name for p in (REPOSITORY / "tools").glob("*.py"))
    assert scripts, "tools/ holds no Python; this witness would pass vacuously"


def test_the_packages_tools_import_ship_inline_type_markers() -> None:
    """Without `py.typed`, a checked script still gets `Any` from every package call."""
    for distribution in TYPED_DISTRIBUTIONS:
        marker = REPOSITORY / "src" / distribution / "py.typed"
        assert marker.is_file(), (
            f"src/{distribution}/py.typed is missing, so mypy treats "
            f"`import {distribution}` from tools/ as untyped and every value it returns "
            f"as Any — the scripts would be in scope and unchecked at the same time"
        )


def test_the_typed_marker_is_declared_to_the_world_as_well() -> None:
    """PEP 561 markers only mean something if the wheel ships them and the metadata says so."""
    config = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    classifiers = config["project"]["classifiers"]
    assert "Typing :: Typed" in classifiers, (
        "the project claims inline types; the Typing :: Typed classifier must say so"
    )
    packages = config["tool"]["hatch"]["build"]["targets"]["wheel"]["packages"]
    for distribution in TYPED_DISTRIBUTIONS:
        assert f"src/{distribution}" in packages, (
            f"src/{distribution} is not in the wheel, so its py.typed cannot ship"
        )
