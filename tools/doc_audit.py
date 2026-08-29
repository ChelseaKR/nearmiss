#!/usr/bin/env python3
"""Documentation-inventory and link audit, generated from the tree (never typed).

``docs/DOCUMENTATION-AUDIT.md`` used to be a hand-written table of `pass` verdicts
backed by counted evidence. The verdicts stayed; the counts stopped describing this
repository — "32 test files" against 100, "4 workflow files" against 6, "5
architecture and interface docs" against 14 ADRs alone. Nothing generated or checked
the file, so a document whose entire purpose was to show that the project's process
claims are real was itself a validation surface reporting success about records it no
longer inspected. That is the failure pattern this repository polices everywhere else.

This tool removes the possibility. It regenerates the machine-derived block of that
document between its ``BEGIN GENERATED`` / ``END GENERATED`` markers, so every count is
read off the tree at the commit that ships it:

    make docs-audit          # rewrite the generated block
    make docs-audit-check    # fail if the committed block has drifted

Two deliberate choices about honesty:

* **`pass` is reserved for a real predicate.** Presence checks (does `README.md`
  exist?) and the link check (does every relative link resolve?) can pass or fail. An
  inventory count cannot — "100 test files" is not a verdict — so counts are reported
  as ``info``. The old table's standing ``pass`` on "Validation surface | 32 test
  files" is exactly the kind of borrowed authority that reads as a conformance result.
* **No generated timestamp.** A date in the output would drift every day and make the
  drift check meaningless, and the git history already dates the file. The dated
  narrative of the original 2026-07-08 sweep is kept *outside* the generated block, as
  history, where it cannot masquerade as a current verdict.

Pure standard library; no network; deterministic (identical tree, identical bytes).
Style mirrors ``tools/check_catalog_parity.py``.

Porting this to another repository
----------------------------------

This has been ported once, to ``davis-bike-hazard-map`` (as ``scripts/doc_audit.py``),
which is enough of a sample to say where the seam actually is. Copy the file; do **not**
turn it into a shared package. It is ~450 lines of standard library with no dependencies,
and a vendored copy that each repo can edit is worth more than a dependency that has to
grow options for every repo's layout. The two ports have already diverged in ways a shared
version would have had to configure rather than express.

What travelled unchanged, and is the actual reusable content:

* the BEGIN/END splice plus ``--check`` drift gate — regenerate into a marked block, fail
  if the committed bytes differ, wire both into ``make`` and into a test so a stale audit
  is a red build rather than a stale document;
* ``_exists_case_sensitively`` — the defect worth copying. ``Path.exists()`` is
  case-insensitive on macOS and case-sensitive on Linux runners and on github.com, so a
  mis-cased relative link passes on a laptop and 404s for every reader. Walking each path
  component against the real directory listing is what makes the link check agree with
  github.com instead of with whichever filesystem it happened to run on;
* ``_link_targets`` with its fenced-code stripping and its skip rule for absolute URLs,
  ``mailto:``, and pure anchors;
* the honesty split — ``pass`` only for a real predicate, counts reported as inventory —
  and the refusal to stamp a generated timestamp, which would make the drift check
  meaningless.

What had to change per repository, i.e. everything a port must review:

* ``BEGIN`` (it names the tool's own path, which differed) and ``AUDIT``;
* ``EXCLUDED_DIR_NAMES``, plus an ``EXCLUDED_FILES`` set if the repo has generated files
  inside otherwise-authored directories;
* ``EXCLUDED_PATH_PREFIXES`` — every gitignored directory a repo's own tooling writes
  Markdown into. This is the one exclusion a port is most likely to get wrong, because
  the symptom appears only on the machine that ran the tooling: the audit describes that
  checkout instead of the repository, the drift gate fails on an unmodified tree, and
  regenerating commits a local, ignored path into a public document. Cross-check the set
  against the repo's ``.gitignore`` rather than against the directories you remember;
  ``test_no_gitignored_markdown_reaches_the_inventory`` does that automatically and is
  the more valuable half of this item to copy;
* ``GROUPED_DIRS``, ``CATEGORY_RULES``, ``ENTRY_AND_PROCESS``, and the ``ROOT_*`` tuples —
  all of them are this repository's documentation taxonomy and none of it generalises;
* the inventory collectors: ``_test_files``, ``_workflows``, ``_npm_scripts``, and
  ``_requires_python`` are Python-plus-npm shaped. The davis port replaced the test
  collector with a Vitest/Playwright declaration regex, because "test file" is not the
  same countable thing in every stack;
* whether a link that escapes the tree is resolved or merely counted. This one is a real
  fork, not a preference: a repo whose README links a sibling checkout (``../STANDARDS/``)
  would have a gate that passes on a laptop and fails on CI, so those links are counted
  separately there and resolved here.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tomllib
from collections.abc import Iterable
from pathlib import Path
from typing import cast

ROOT = Path(__file__).resolve().parent.parent
AUDIT = ROOT / "docs" / "DOCUMENTATION-AUDIT.md"

BEGIN = "<!-- BEGIN GENERATED: doc-audit (tools/doc_audit.py) -->"
END = "<!-- END GENERATED: doc-audit -->"

#: Facts about the HAND-AUTHORED half of the audit -- everything outside the markers --
#: recorded where regeneration cannot reach them. See `_narrative_facts` for why.
NARRATIVE_PIN = ROOT / "docs" / "DOCUMENTATION-AUDIT.narrative.json"

# Directories that hold generated, vendored, or third-party Markdown. They are
# counted as a content group so they stay visible without swamping the inventory.
GROUPED_DIRS = ("docs/standards",)

# Directory names with no hand-authored documentation to audit, excluded wherever
# they appear. Matching on the name rather than a root-relative prefix matters: the
# audit has to produce the same numbers whether or not `npm ci` has created
# `web/node_modules`, or `make verify` has created `build/`, in this checkout.
EXCLUDED_DIR_NAMES = frozenset(
    {
        ".git",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".smoke-venv",
        ".venv",
        "__pycache__",
        "build",
        "dist",
        "htmlcov",
        "node_modules",
        "site",
    }
)

# Root-relative directory prefixes holding a contributor's local working data rather
# than repository content. `.gitignore` excludes `data/raw/`, `data/pending/`, and
# `data/real/` under HR4 — only aggregated, published artifacts are ever committed — so
# any Markdown beneath them belongs to one checkout and not to the repository.
#
# Counting it is not cosmetic. `make real` writes a generated brief under
# `data/real/<city>/`, after which `make docs-audit-check` and `make test` fail on a
# checkout with no changes in it at all, and the fix those failures ask for
# (`make docs-audit`) writes the ignored path — city name included — into a public,
# committed document. `data/published/` is deliberately absent: it *is* committed, and
# its briefs are part of the inventory.
#
# These need a root-relative prefix where `EXCLUDED_DIR_NAMES` above needs a bare name.
# "raw", "real", and "pending" are ordinary words a genuine docs directory could use,
# and excluding them wherever they appear would silently drop authored documentation.
EXCLUDED_PATH_PREFIXES = (
    "data/pending/",
    "data/raw/",
    "data/real/",
)

ROOT_PROCESS_DOCS = ("CONTRIBUTING.md", "SECURITY.md", "CHANGELOG.md")
ROOT_LEGAL_DOCS = ("LICENSE", "NOTICE", "CITATION.cff", "CODE_OF_CONDUCT.md")
ROOT_TEMPLATES = (".github/PULL_REQUEST_TEMPLATE.md", ".github/CODEOWNERS")

# Category rules, in order: the first prefix/name that matches wins. Written as data
# so the categorization is reviewable rather than buried in branches.
CATEGORY_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "safety, privacy, accessibility, and audits",
        (
            "docs/ACCESSIBILITY.md",
            "docs/DPIA.md",
            "docs/DOCUMENTATION-AUDIT.md",
            "docs/INTAKE-AND-ABUSE.md",
            "docs/RE-IDENTIFICATION.md",
            "docs/RESPONSIBLE-TECH-AUDITS.md",
            "docs/THREAT-MODEL.md",
            "docs/accessibility/",
            "docs/audits/",
            "docs/privacy/",
        ),
    ),
    ("architecture and interfaces", ("docs/adr/", "schema/")),
    (
        "planning and research",
        (
            "docs/ideation/",
            "docs/preregistration/",
            "docs/research/",
            "docs/ROADMAP.md",
            "docs/RESEARCH-ROADMAP.md",
        ),
    ),
    ("examples and guides", ("docs/teaching/", "notebooks/")),
)
ENTRY_AND_PROCESS = (
    ".github/CODEOWNERS",
    ".github/PULL_REQUEST_TEMPLATE.md",
    "CHANGELOG.md",
    "CITATION.cff",
    "CODE_OF_CONDUCT.md",
    "CONTRIBUTING.md",
    "DEFINITION_OF_DONE.md",
    "LICENSE",
    "NOTICE",
    "README.md",
    "SECURITY.md",
)
OTHER = "other docs"

# Representative files shown per category. The complete list is printed below the
# tables, so the table stays readable without hiding anything.
_SAMPLE = 5

# A relative Markdown link: [text](target). Absolute URLs, mailto: and pure anchors
# are out of scope — this check is about links that must resolve inside the tree.
_LINK = re.compile(r"\[[^\]]*\]\(\s*(<[^>]+>|[^)\s]+)")
_SKIP_LINK = re.compile(r"^(?:[a-z][a-z0-9+.-]*:|//|#)")
_CODE_FENCE = re.compile(r"(?ms)^```.*?^```\s*?$")


def _relative(path: Path) -> str:
    # Falls back to the absolute path rather than raising: the tests point AUDIT and
    # NARRATIVE_PIN at copies under tmp_path, and a failure message that raises while
    # being formatted is a gate that cannot report.
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def _excluded(rel: str) -> bool:
    if rel.startswith(EXCLUDED_PATH_PREFIXES):
        return True
    return any(part in EXCLUDED_DIR_NAMES for part in rel.split("/")[:-1])


def _grouped(rel: str) -> bool:
    return any(rel.startswith(f"{d}/") for d in GROUPED_DIRS)


def _authored_docs() -> list[str]:
    """Every hand-authored Markdown file, plus the non-Markdown root process files."""
    found: set[str] = set()
    for path in ROOT.rglob("*.md"):
        rel = _relative(path)
        if _excluded(rel) or _grouped(rel):
            continue
        found.add(rel)
    for rel in (*ROOT_LEGAL_DOCS, *ROOT_TEMPLATES):
        if (ROOT / rel).is_file():
            found.add(rel)
    return sorted(found)


def _grouped_counts() -> list[tuple[str, int]]:
    counts = []
    for directory in GROUPED_DIRS:
        base = ROOT / directory
        n = len(list(base.rglob("*.md"))) if base.is_dir() else 0
        counts.append((f"{directory}/", n))
    return counts


def _category(rel: str) -> str:
    for name, prefixes in CATEGORY_RULES:
        if any(rel == prefix or rel.startswith(prefix) for prefix in prefixes):
            return name
    if rel in ENTRY_AND_PROCESS:
        return "entry points and repo process"
    return OTHER


def _test_files() -> list[str]:
    return sorted(_relative(p) for p in (ROOT / "tests").glob("test_*.py"))


def _workflows() -> list[str]:
    workflows = ROOT / ".github" / "workflows"
    if not workflows.is_dir():
        return []
    return sorted(_relative(p) for p in (*workflows.glob("*.yml"), *workflows.glob("*.yaml")))


def _npm_scripts() -> list[str]:
    package = ROOT / "web" / "package.json"
    if not package.is_file():
        return []
    return sorted(json.loads(package.read_text(encoding="utf-8")).get("scripts", {}))


def _requires_python() -> str:
    cfg = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    requires: str = cfg["project"].get("requires-python", "unspecified")
    return requires


def _link_targets(text: str) -> Iterable[str]:
    for raw in _LINK.findall(_CODE_FENCE.sub("", text)):
        target = raw.strip()
        if target.startswith("<") and target.endswith(">"):
            target = target[1:-1]
        target = target.split(" ")[0].split("#")[0].strip()
        if not target or _SKIP_LINK.match(target):
            continue
        yield target


def _exists_case_sensitively(target: Path) -> bool:
    """Does this path exist with *exactly* this spelling?

    ``Path.exists()`` is case-insensitive on macOS (APFS) and case-sensitive on the
    Linux hosts CI runs on and on github.com, so a link whose case is wrong passes on
    a laptop and 404s for every reader. That is not hypothetical here: it is how
    `docs/README.md`'s duplicate `accessibility.md` entry survived a link check that
    reported "0 unresolved". Each component is matched against the real directory
    listing so this gate agrees with github.com rather than with the filesystem it
    happens to run on.
    """
    try:
        relative = target.relative_to(ROOT)
    except ValueError:
        # A link that escapes the repository: out of scope for a repo-local check.
        return target.exists()
    cursor = ROOT
    for part in relative.parts:
        try:
            entries = {entry.name for entry in cursor.iterdir()}
        except OSError:
            return False
        if part not in entries:
            return False
        cursor = cursor / part
    return True


def _check_links(docs: Iterable[str]) -> tuple[int, list[str]]:
    """(links checked, unresolved 'doc -> target' strings)."""
    checked = 0
    unresolved: list[str] = []
    for rel in docs:
        path = ROOT / rel
        if path.suffix != ".md":
            continue
        for target in _link_targets(path.read_text(encoding="utf-8")):
            checked += 1
            # Textual normalisation only: realpath would fold `..` *and*, on some
            # platforms, the case this check exists to catch.
            resolved = Path(os.path.normpath(path.parent / target))
            if not _exists_case_sensitively(resolved):
                unresolved.append(f"{rel} -> {target}")
    return checked, unresolved


def _present(paths: Iterable[str]) -> tuple[list[str], list[str]]:
    present = [p for p in paths if (ROOT / p).exists()]
    missing = [p for p in paths if not (ROOT / p).exists()]
    return present, missing


def _verdict(missing: list[str]) -> str:
    return "pass" if not missing else "fail"


def _bullets(items: Iterable[str]) -> str:
    return "\n".join(f"- `{item}`" for item in items)


def _render() -> str:
    docs = _authored_docs()
    tests = _test_files()
    workflows = _workflows()
    checked, unresolved = _check_links(docs)

    _, missing_process = _present(ROOT_PROCESS_DOCS)
    _, missing_legal = _present(ROOT_LEGAL_DOCS)
    _, missing_templates = _present(ROOT_TEMPLATES)
    readme_missing = [] if (ROOT / "README.md").is_file() else ["README.md"]

    categories: dict[str, list[str]] = {}
    for rel in docs:
        categories.setdefault(_category(rel), []).append(rel)

    grouped = _grouped_counts()
    grouped_total = sum(n for _, n in grouped)

    lines: list[str] = [BEGIN, ""]
    lines += [
        "_Everything between these markers is generated by `tools/doc_audit.py` from the tree "
        "at this commit. Do not edit it by hand: run `make docs-audit`. `make docs-audit-check` "
        "(and `tests/test_doc_audit.py`) fail if it has drifted._",
        "",
        "## Presence and link checks",
        "",
        "These are real predicates, so they can pass or fail.",
        "",
        "| Check | Result | Evidence |",
        "| --- | --- | --- |",
        f"| Entry doc | {_verdict(readme_missing)} | `README.md`"
        f"{'' if not readme_missing else ' missing'} |",
        f"| Root process docs | {_verdict(missing_process)} | "
        f"{', '.join(f'`{p}`' for p in ROOT_PROCESS_DOCS)} |",
        f"| Root legal, citation, and conduct docs | {_verdict(missing_legal)} | "
        f"{', '.join(f'`{p}`' for p in ROOT_LEGAL_DOCS)} |",
        f"| Root-adjacent GitHub templates | {_verdict(missing_templates)} | "
        f"{', '.join(f'`{p}`' for p in ROOT_TEMPLATES)} |",
        f"| Local doc links resolve | {_verdict(unresolved)} | {checked} relative links checked "
        f"in {len([d for d in docs if d.endswith('.md')])} Markdown files; {len(unresolved)} "
        "unresolved |",
        "",
        "## Inventory",
        "",
        "Counts, not verdicts. A count cannot pass or fail; it can only be current, which is "
        "what generating it from the tree buys.",
        "",
        "| Surface | Count | Evidence |",
        "| --- | ---: | --- |",
        f"| Hand-authored docs | {len(docs)} | Markdown at the repository root and under "
        "`docs/`, `data/`, `infra/`, `notebooks/`, `schema/`, `src/`, `tests/`, `web/`, plus the "
        "root legal and template files |",
        f"| Test files | {len(tests)} | `tests/test_*.py` |",
        f"| Workflow files | {len(workflows)} | `.github/workflows/*.yml` |",
        f"| Grouped/vendored doc content | {grouped_total} | "
        f"{', '.join(f'`{name}` ({n})' for name, n in grouped)} |",
        "",
        "### By category",
        "",
        f"Up to {_SAMPLE} representative files per category; the complete list follows below.",
        "",
        "| Category | Count | Representative files |",
        "| --- | ---: | --- |",
    ]
    for name in sorted(categories):
        members = sorted(categories[name])
        shown = ", ".join(f"`{m}`" for m in members[:_SAMPLE])
        extra = len(members) - _SAMPLE
        sample = shown + (f", plus {extra} more" if extra > 0 else "")
        lines.append(f"| {name} | {len(members)} | {sample} |")

    lines += [
        "",
        "## Workflow files checked",
        "",
        _bullets(workflows) or "- none found",
        "",
        "## Package and workspace metadata",
        "",
        f"- Node workspace `web/package.json` (scripts: {', '.join(_npm_scripts()) or 'none'}).",
        f"- Python package `nearmiss` ({_requires_python()}).",
        "",
        "## Full hand-authored doc inventory",
        "",
        _bullets(docs),
        "",
    ]
    if unresolved:
        lines += ["## Unresolved links", "", _bullets(unresolved), ""]
    lines.append(END)
    return "\n".join(lines) + "\n"


def _narrative(document: str) -> str:
    """Everything outside the generated markers: the prose a person wrote."""
    start = document.find(BEGIN)
    end = document.find(END)
    if start == -1 or end == -1:
        raise SystemExit(
            f"docs/DOCUMENTATION-AUDIT.md is missing the generated-block markers ({BEGIN} … {END})"
        )
    return document[:start] + document[end + len(END) + 1 :]


def _narrative_facts(text: str) -> dict[str, object]:
    """Size, shape and digest of the hand-authored region.

    A generated file with hand-authored regions is a distinct hazard, and this repository
    ported this tool to a project where the hazard fired. In `davis-bike-hazard-map` a bad
    conflict resolution deleted two paragraphs from the prose *outside* the markers; the
    only thing that noticed was the generated link count, which fell 96 to 95; and the
    documented repair for a failing count is `make docs-audit`, which rewrote the count to
    agree with the damage. Green gate, real content loss.

    The same thing happens here. The preamble of `docs/DOCUMENTATION-AUDIT.md` carries two
    relative links, so deleting the paragraph that holds them moves "494 relative links
    checked" to 492 and `make docs-audit` makes the file self-consistent again. Deleting a
    paragraph with no link in it is not even that visible: the drift check passes
    unchanged, because `_splice` copies the prose through untouched and compares only what
    it generated.

    So the prose is pinned separately, in a file the regeneration path never writes. The
    digest is what fails; the counts beside it are there to say, in the failure message,
    whether the region grew or shrank, because "shrank" is the case worth reading twice.
    """
    return {
        "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "bytes": len(text.encode("utf-8")),
        "lines": len(text.splitlines()),
        "words": len(text.split()),
        "relative_links": len(list(_link_targets(text))),
    }


def _load_pin() -> dict[str, object] | None:
    if not NARRATIVE_PIN.is_file():
        return None
    loaded: dict[str, object] = json.loads(NARRATIVE_PIN.read_text(encoding="utf-8"))
    return loaded


def _pin_deltas(pinned: dict[str, object], current: dict[str, object]) -> list[str]:
    """One line per counted fact that moved, saying which way it moved."""
    lines = []
    for key in ("bytes", "lines", "words", "relative_links"):
        before = int(cast(int, pinned.get(key, 0)))
        after = int(cast(int, current[key]))
        if before != after:
            direction = "removed" if after < before else "added"
            lines.append(f"    {key}: {before} -> {after} ({direction} {abs(after - before)})")
    return lines


def _narrative_problem(document: str) -> list[str] | None:
    """The failure message when the prose no longer matches its pin, or None."""
    current = _narrative_facts(_narrative(document))
    pinned = _load_pin()
    if pinned is None:
        return [
            f"{_relative(NARRATIVE_PIN)} is missing, so nothing records what the "
            "hand-authored half of the audit is supposed to contain.",
            "  Review the prose, then run `make docs-audit-accept-narrative`.",
        ]
    if pinned.get("sha256") == current["sha256"]:
        return None
    deltas = _pin_deltas(pinned, current)
    shrank = int(cast(int, current["bytes"])) < int(cast(int, pinned.get("bytes", 0)))
    return [
        "the hand-authored prose in docs/DOCUMENTATION-AUDIT.md is not what "
        f"{_relative(NARRATIVE_PIN)} records.",
        *deltas,
        (
            "  The region got SMALLER. Prose was deleted. Read the diff before accepting it: "
            "regenerating the block would move the counts to agree with the deletion, which "
            "is how this exact failure shipped once already."
            if shrank
            else "  If the edit is intended, run `make docs-audit-accept-narrative`."
        ),
    ]


def _splice(document: str, generated: str) -> str:
    start = document.find(BEGIN)
    end = document.find(END)
    if start == -1 or end == -1:
        raise SystemExit(
            f"docs/DOCUMENTATION-AUDIT.md is missing the generated-block markers ({BEGIN} … {END})"
        )
    return document[:start] + generated + document[end + len(END) + 1 :]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail if the committed generated block differs from the tree",
    )
    parser.add_argument(
        "--accept-narrative",
        action="store_true",
        help="record the hand-authored prose as it now stands (a deliberate, reviewed act)",
    )
    args = parser.parse_args(argv)

    document = AUDIT.read_text(encoding="utf-8")
    updated = _splice(document, _render())
    narrative_problem = _narrative_problem(document)

    if args.accept_narrative:
        current = _narrative_facts(_narrative(document))
        pinned = _load_pin()
        if pinned is not None:
            for line in _pin_deltas(pinned, current):
                print(line.strip())
        NARRATIVE_PIN.write_text(
            json.dumps(current, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print(f"doc audit: recorded the hand-authored prose in {_relative(NARRATIVE_PIN)}.")
        return 0

    if args.check:
        problems: list[str] = []
        if updated != document:
            problems.append(
                "docs/DOCUMENTATION-AUDIT.md no longer describes this tree.\n"
                "  Run `make docs-audit` and commit the result."
            )
        if narrative_problem is not None:
            problems.append("\n".join(narrative_problem))
        if problems:
            for problem in problems:
                print(f"doc audit FAILED: {problem}", file=sys.stderr)
            return 1
        print(
            "doc audit OK: the committed inventory, counts, and link check match the tree, "
            "and the hand-authored prose is what its pin records."
        )
        return 0

    # Regeneration is the documented repair for a failing drift check, which makes it the
    # step that would otherwise launder a deletion: rewrite the counts, and the file agrees
    # with the damage. It refuses while the prose is unaccounted for, so the person has to
    # look at what changed before anything gets rewritten around it.
    if narrative_problem is not None:
        print("doc audit REFUSED to regenerate: " + "\n".join(narrative_problem), file=sys.stderr)
        print(
            "  Regenerating now would rewrite the counts to agree with the edited prose. "
            "Review it first; then `make docs-audit-accept-narrative` and re-run.",
            file=sys.stderr,
        )
        return 1

    AUDIT.write_text(updated, encoding="utf-8")
    print(f"doc audit: regenerated the generated block in {_relative(AUDIT)}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
