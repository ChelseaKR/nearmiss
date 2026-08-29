#!/usr/bin/env python3
"""CQ-34: no bare `TODO`/`FIXME`/`HACK`/`XXX` — every marker carries a linked issue.

`docs/standards/CODE-QUALITY-STANDARD.md` declares CQ-34 an **AUTO-GATE** ("bare markers
fail CI") and ships a drop-in regex for it. Until this file, nothing in this repository
implemented it: `make verify` did not grep for markers, no CI job did, pre-commit did not,
and ruff's select set carries neither `FIX` nor `TD`. A declared AUTO-GATE with no
implementation is the one kind of conformance gap the conformance table cannot see,
because there is nothing failing — which is exactly why it is worth closing in a repository
whose posture is that its gates are real.

**Scope is deliberate, and wider than the standard's example.** The example regex scans
`src/` only. The single real marker in this repository lives in `CITATION.cff`, so scanning
`src/` alone would have shipped a green gate over a live violation. This tool scans the
code and configuration a maintainer actually edits, plus the root metadata files, and
excludes three things on purpose:

* `docs/` — including `docs/standards/`, whose *prose defines this rule* and would match a
  naive repo-wide grep. Debt markers are a code-hygiene control; a design doc that says the
  word "TODO" is not debt.
* Lockfiles and generated trees (`node_modules/`, `build/`, `dist/`, caches, `.venv/`),
  where a match belongs to somebody else's source.
* Binary files, skipped by decode failure rather than by extension guesswork.

A marker is satisfied by an issue reference on the same line: `(#142)` or a full issue URL.
That is the standard's own wording, and it is the whole point — the marker is allowed to
exist as long as the work behind it is tracked somewhere a reader can open.

**What this gate cannot confirm, stated rather than left implicit.** It is offline by
design, so it checks that a marker *carries* an issue reference — never that the issue
exists, is open, or is about the marker. The repository's one live marker is the current
example: `CITATION.cff:68` reads `TODO(#184)` and passes, but #184 was closed on
2026-08-23 and was about the README and ROADMAP's stale tag claims, not about minting a
DOI. So the DOI is presently tracked by no open issue while the gate is green. That is a
real blind spot, and closing it would mean a network call from a gate whose whole value
is that it is fast, local, and identical in CI — a trade this tool declines. The
disposition is recorded in `docs/ROADMAP.md` under "Open review and owner actions" so the
gap is visible where a reader will meet it, rather than inferred from a green tick.

CQ-35 (no `type: ignore` / `# noqa` without a code *and* an issue reference) is the same
grep shape and is **not** implemented here. This repository has roughly two dozen such
suppressions, all of which already carry a rule code and most a written justification, so
turning CQ-35 on is a decision about whether a code plus a reason satisfies it or whether
every suppression must also carry an issue link. That is a judgment call for the owner, not
something to smuggle in behind a CQ-34 fix.

Pure standard library; no network; deterministic. Style mirrors `tools/doc_audit.py`.

    make markers        # run the gate (also runs inside `make verify`)
"""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Iterator
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Trees whose contents are this project's own code and configuration.
SCANNED_DIRS = (
    "benchmarks",
    "config",
    "infra",
    "integrations",
    "schema",
    "src",
    "tests",
    "tools",
    "web",
    ".github",
)

# Individual root files that are hand-maintained project metadata. CITATION.cff is in
# this list because that is where the repository's only real marker lives; a gate scoped
# to `src/` would have passed over it.
SCANNED_FILES = (
    ".pre-commit-config.yaml",
    "CITATION.cff",
    "Makefile",
    "babel.cfg",
    "pyproject.toml",
    "renovate.json",
)

# Directory names skipped wherever they appear. Matching on the name rather than a
# root-relative prefix keeps the result identical whether or not `npm ci`, `make verify`,
# or a mutation run has populated this checkout.
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
        "mutants",
        "node_modules",
        "site",
    }
)

# Generated or vendored files whose markers are not this project's debt.
EXCLUDED_SUFFIXES = (".lock", ".mo", ".png", ".svg", ".ico", ".woff", ".woff2")
EXCLUDED_NAMES = frozenset({"package-lock.json", "uv.lock"})

# The word list is public so `tests/test_debt_markers.py` can build its cases from it
# instead of typing the literals. That test is not exempt from this gate (only this file
# is), and a test file full of bare markers would either fail the gate or force an
# allowlist entry — a hole in the very check it exercises. Importing the words keeps the
# rule and its tests on one definition.
MARKER_WORDS: tuple[str, ...] = ("TODO", "FIXME", "HACK", "XXX")
_MARKER = re.compile(r"\b(" + "|".join(MARKER_WORDS) + r")\b")
# An issue reference on the same line: a bare (#142), or a full issue URL.
_LINKED = re.compile(r"\(#\d+\)|https?://\S+/issues/\d+")

# This file is the one exemption, and it is unavoidable rather than convenient: the
# detector's own pattern and docstring necessarily spell out the words it forbids, so
# scanning itself would make the gate permanently red. It is exempted by resolved path,
# not by name, so moving or copying it does not silently widen the hole — and
# `tests/test_debt_markers.py`, which also needs those words, gets none: it assembles them
# from fragments instead. One exemption, in the file that defines the rule.
_SELF = Path(__file__).resolve()


def _relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def _skip(path: Path) -> bool:
    rel = _relative(path)
    if any(part in EXCLUDED_DIR_NAMES for part in rel.split("/")[:-1]):
        return True
    if path.name in EXCLUDED_NAMES:
        return True
    return path.suffix in EXCLUDED_SUFFIXES


def _scanned_paths() -> Iterator[Path]:
    for name in SCANNED_FILES:
        path = ROOT / name
        if path.is_file():
            yield path
    for directory in SCANNED_DIRS:
        base = ROOT / directory
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if path.is_file() and not _skip(path):
                yield path


def find_bare_markers() -> list[tuple[str, int, str]]:
    """Every (path, line number, line) whose marker carries no issue reference."""
    violations: list[tuple[str, int, str]] = []
    for path in _scanned_paths():
        if path.resolve() == _SELF:
            continue
        rel = _relative(path)
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            # Binary, or unreadable: nothing a human wrote a marker into.
            continue
        for number, line in enumerate(text.splitlines(), start=1):
            if _MARKER.search(line) and not _LINKED.search(line):
                violations.append((rel, number, line.strip()))
    return violations


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args(argv)

    violations = find_bare_markers()
    if violations:
        print(
            "CQ-34 FAILED: debt markers without a linked issue.\n"
            "  Every TODO/FIXME/HACK/XXX must carry an issue reference on the same line,\n"
            "  e.g. `# TODO(#142): ...` or a full .../issues/142 URL. File the issue, or\n"
            "  resolve the marker.\n",
            file=sys.stderr,
        )
        for rel, number, line in violations:
            print(f"  {rel}:{number}: {line}", file=sys.stderr)
        return 1

    print("CQ-34 OK: every debt marker in the scanned tree carries a linked issue.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
