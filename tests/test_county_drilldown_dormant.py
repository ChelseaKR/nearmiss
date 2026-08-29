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

#: Where a wired capability would necessarily show up.
ENTRY_POINTS = (
    ROOT / "Makefile",
    *sorted((ROOT / ".github" / "workflows").glob("*.yml")),
    ROOT / "tools" / "build_site.py",
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


def test_no_county_module_is_reachable_from_a_pipeline_entry_point() -> None:
    """Direction two: the moment something runs it, the dormancy claim is false."""
    reachable: list[str] = []
    for entry in ENTRY_POINTS:
        if not entry.exists():
            continue
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
