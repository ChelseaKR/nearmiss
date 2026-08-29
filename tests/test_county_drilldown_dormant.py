"""The county drill-down is declared dormant, and the declaration has to stay true.

Issue #182. Seven modules under `src/nearmiss/` (3,809 lines), three build tools, eight
test modules, a 57 KB implementation plan, three published contract documents and ADR
0014 are fully implemented, contracted and tested — and nothing runs them. No `make`
target, no CI job, no entry in `tools/build_site.py`'s published-file allowlist, and no
county artifact under `data/published/`. The blocker is a human step: the manual review
in `docs/PRIVATE-COUNTY-CROSSWALK-REVIEW.md`, where an unresolved `pending-review` row
blocks county projection.

That left the repository's largest single body of code in a state a reader could not
classify: not a stub, not shipped, not declared. `docs/ROADMAP.md` now declares it, under
the `county-drilldown-dormant` claim, and this file is that claim's witness.

A dormancy notice is exactly the kind of statement that rots: the day someone wires a
`make` target, the doc keeps saying "reaches nothing" and the claims gate keeps passing,
because the gate only checks that the witness exists and passes. So the witness is a
predicate on the tree, and it fails in **both** directions — if the modules go missing, and
if they become reachable. Landing the pilot is supposed to break this test; when it does,
the fix is to retire the claim, not to loosen the assertion.
"""

from __future__ import annotations

import ast
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

#: The dormant modules, by file name under `src/nearmiss/`.
COUNTY_MODULES = (
    "fars_county_boundary_publication.py",
    "fars_county_crosswalk.py",
    "fars_county_crosswalk_review.py",
    "fars_county_feasibility.py",
    "fars_county_projection.py",
    "fars_county_public_index.py",
    "fars_county_publication.py",
)

#: The build tools in the same position: implemented, tested, invoked by nothing.
COUNTY_TOOLS = (
    "build_fars_county_crosswalk.py",
    "build_fars_county_public_index.py",
    "build_us_county_boundaries.py",
)


def declared_console_script_paths(root: Path = ROOT) -> tuple[Path, ...]:
    """Resolve every console script `pyproject.toml` declares to the file it names.

    A hand-maintained candidate list is what let this witness go blind. It named the
    Makefile, the workflow files and `tools/build_site.py`, and omitted
    `src/nearmiss/__main__.py` — the 1,516-line, 28-subcommand CLI that
    `[project.scripts]` installs as `nearmiss`, and therefore the one place in the
    repository that would actually *run* a county module. Wiring one in as a
    subcommand left this file's assertions untouched and green. A second literal list
    would go blind the same way the first did, so the console scripts are read from
    the packaging declaration rather than remembered here.

    Every failure mode is a failure, never an empty result: a missing or unparseable
    `pyproject.toml`, an absent or empty script table, a target naming no module, or a
    module resolving to no file on disk. A derivation that quietly returned `()` would
    restore exactly the blindness it exists to remove — the gate would pass by having
    nothing to look at.
    """
    pyproject = root / "pyproject.toml"
    if not pyproject.is_file():
        raise AssertionError(
            f"{pyproject} does not exist, so the declared entry points cannot be derived. "
            "This witness scans entry points; with none derived it would assert nothing."
        )
    try:
        declaration = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise AssertionError(
            f"{pyproject} does not parse as TOML, so the declared entry points cannot be "
            f"derived: {exc}"
        ) from exc

    project = declaration.get("project", {})
    targets: dict[str, str] = {}
    for table in ("scripts", "gui-scripts"):
        targets.update(project.get(table, {}))
    if not targets:
        raise AssertionError(
            f"{pyproject} declares no [project.scripts] or [project.gui-scripts] entry, so "
            "this witness would scan no command-line surface at all. If the package really "
            "ships no console script, rewrite this derivation deliberately rather than "
            "letting it return nothing."
        )

    resolved: list[Path] = []
    for name, target in sorted(targets.items()):
        module = str(target).split(":", 1)[0].strip()
        if not module:
            raise AssertionError(
                f"the console script {name!r} declares the target {target!r}, which names no "
                "module, so the file it runs cannot be scanned."
            )
        base = root / "src" / Path(*module.split("."))
        for candidate in (base.with_suffix(".py"), base / "__init__.py"):
            if candidate.is_file():
                resolved.append(candidate)
                break
        else:
            raise AssertionError(
                f"the console script {name!r} declares the target {target!r}, whose module "
                f"{module!r} resolves to no file under {root / 'src'}. An entry point that "
                "cannot be located cannot be scanned, and skipping it would be a silent hole."
            )
    return tuple(resolved)


#: Where a wired capability would necessarily show up. The Makefile, the workflows and
#: the site builder are the *build* surfaces; the console scripts, derived rather than
#: remembered, are the *run* surface that this tuple used to be missing entirely.
ENTRY_POINTS = (
    ROOT / "Makefile",
    *sorted((ROOT / ".github" / "workflows").glob("*.yml")),
    *sorted((ROOT / ".github" / "workflows").glob("*.yaml")),
    ROOT / "tools" / "build_site.py",
    *declared_console_script_paths(),
)

CLAIM = "county-drilldown-dormant"
ROADMAP = ROOT / "docs" / "ROADMAP.md"
CLAIMS = ROOT / "docs" / "CLAIMS.md"
PUBLISHED = ROOT / "data" / "published"


def test_the_dormant_modules_still_exist() -> None:
    """Direction one: the claim describes files. If they are gone, it is stale."""
    missing = [name for name in COUNTY_MODULES if not (ROOT / "src" / "nearmiss" / name).exists()]
    assert missing == [], (
        f"docs/ROADMAP.md's {CLAIM} claim names modules that no longer exist: {missing}. "
        "Retire or rewrite the claim rather than leaving it describing a tree that changed."
    )
    missing_tools = [name for name in COUNTY_TOOLS if not (ROOT / "tools" / name).exists()]
    assert missing_tools == []


def test_the_entry_points_include_every_declared_console_script() -> None:
    """The scan's blind spot was the CLI, and it must not become the blind spot again.

    `[project.scripts]` is the packaging declaration of what a user can actually run.
    Anything it names has to be in the scanned set, or the reachability assertion below
    is checking build files while the run surface goes unread.
    """
    declared = declared_console_script_paths()
    assert declared, "no console script was derived, so the run surface would go unscanned"
    unscanned = sorted(str(path.relative_to(ROOT)) for path in declared if path not in ENTRY_POINTS)
    assert unscanned == [], (
        "pyproject.toml declares console scripts that this witness does not scan, so a county "
        f"module wired into one of them would not be noticed: {unscanned}"
    )
    assert ROOT / "src" / "nearmiss" / "__main__.py" in ENTRY_POINTS, (
        "the nearmiss CLI is not in the scanned set. It is the entry point a county module "
        "would actually be run from; omitting it is the defect this derivation exists to fix."
    )


@pytest.mark.parametrize(
    "pyproject",
    [
        None,
        "[project\nscripts = ",
        "[tool.ruff]\nline-length = 100\n",
        '[project]\nname = "nearmiss"\n',
        '[project]\nname = "nearmiss"\n\n[project.scripts]\n',
        '[project]\nname = "nearmiss"\n\n[project.scripts]\nnearmiss = ":main"\n',
        '[project]\nname = "nearmiss"\n\n[project.scripts]\nnearmiss = "absent.cli:main"\n',
    ],
    ids=[
        "no-pyproject",
        "unparseable-toml",
        "no-project-table",
        "no-script-table",
        "empty-script-table",
        "target-names-no-module",
        "module-resolves-to-no-file",
    ],
)
def test_the_entry_point_derivation_fails_closed(pyproject: str | None, tmp_path: Path) -> None:
    """A derivation that cannot find the entry points must fail, not scan nothing.

    Returning `()` on a broken declaration is the same defect as the literal list that
    forgot the CLI, only harder to see: the reachability test would pass by having no
    candidates rather than by finding no county code.
    """
    (tmp_path / "src").mkdir()
    if pyproject is not None:
        (tmp_path / "pyproject.toml").write_text(pyproject, encoding="utf-8")
    with pytest.raises(AssertionError):
        declared_console_script_paths(tmp_path)


def test_no_county_module_is_reachable_from_a_pipeline_entry_point() -> None:
    """Direction two: the moment something runs it, the dormancy claim is false."""
    reachable: list[str] = []
    for entry in ENTRY_POINTS:
        assert entry.is_file(), (
            f"{entry.relative_to(ROOT)} is listed as an entry point but does not exist, so "
            "this witness would silently stop looking at it. Fix the path or remove it "
            "deliberately; do not let a missing candidate read as a clean scan."
        )
        text = entry.read_text(encoding="utf-8")
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("#") or stripped.startswith("//"):
                continue
            if "county" in stripped.lower():
                reachable.append(f"{entry.relative_to(ROOT)}: {stripped}")
    assert reachable == [], (
        "the county drill-down is reachable from a pipeline entry point, so "
        f"docs/ROADMAP.md's {CLAIM} claim is no longer true. Retire the claim and the "
        "DORMANT docstrings; do not relax this test:\n  " + "\n  ".join(reachable)
    )


def test_no_county_artifact_is_published() -> None:
    published = sorted(path.name for path in PUBLISHED.rglob("*") if "county" in path.name.lower())
    assert published == [], (
        f"county artifacts are published, so the {CLAIM} claim is no longer true: {published}"
    )


@pytest.mark.parametrize("name", COUNTY_MODULES)
def test_each_dormant_module_says_so_in_its_own_docstring(name: str) -> None:
    """A reader opening the file must not have to find `docs/ROADMAP.md` first."""
    docstring = ast.get_docstring(
        ast.parse((ROOT / "src" / "nearmiss" / name).read_text(encoding="utf-8"))
    )
    assert docstring is not None, f"{name} has no module docstring"
    assert "DORMANT:" in docstring, (
        f"{name} is declared dormant in docs/ROADMAP.md but does not say so itself"
    )
    assert "#182" in docstring


@pytest.mark.parametrize("name", COUNTY_TOOLS)
def test_each_dormant_tool_says_so_in_its_own_docstring(name: str) -> None:
    docstring = ast.get_docstring(ast.parse((ROOT / "tools" / name).read_text(encoding="utf-8")))
    assert docstring is not None, f"{name} has no module docstring"
    assert "DORMANT:" in docstring


def test_the_claim_is_tagged_and_listed() -> None:
    """The claims gate checks this too; asserted here so the witness is self-contained."""
    roadmap = ROADMAP.read_text(encoding="utf-8")
    assert f"<!-- claim:{CLAIM} -->" in roadmap
    assert f"<!-- /claim:{CLAIM} -->" in roadmap
    assert f"`{CLAIM}`" in CLAIMS.read_text(encoding="utf-8")


def test_the_claim_names_the_human_blocker_rather_than_a_missing_feature() -> None:
    roadmap = ROADMAP.read_text(encoding="utf-8")
    body = roadmap.split(f"<!-- claim:{CLAIM} -->")[1].split(f"<!-- /claim:{CLAIM} -->")[0]
    assert "PRIVATE-COUNTY-CROSSWALK-REVIEW.md" in body
    assert "pending-review" in body
    for module in COUNTY_MODULES:
        assert module.removesuffix(".py") in body, (
            f"the dormancy claim does not name {module}, so a reader cannot tell which "
            "code it covers"
        )
