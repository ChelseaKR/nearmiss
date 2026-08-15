"""The documentation audit has to describe *this* tree, not the one it was typed against.

`docs/DOCUMENTATION-AUDIT.md` published a table of `pass` verdicts backed by counted
evidence: "32 test files", "4 workflow files", "5 architecture and interface docs". The
verdicts stayed; the counts drifted about 3x, and the workflow list omitted the daily
live-site sentinel and the signed release pipeline — the two an outside reviewer would
most want to see audited. Nothing in the repository generated or checked the file, so
the numbers looked machine-produced with no machine behind them.

That is the same failure the project polices elsewhere: a validation surface reporting
success about records it no longer inspects. These gates close it from both directions.

* The committed block must equal what `tools/doc_audit.py` derives from the tree, so a
  new test file or workflow makes the audit stale for at most one pull request.
* The drift check must actually fail on drift — a check that cannot be shown to fail is
  the green tick this file exists to prevent.
* Counts are reported as inventory, never as `pass`. "100 test files" is not a verdict,
  and the old table's standing `pass` on that row borrowed authority the number never
  had.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

import pytest
from tools import doc_audit

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "docs" / "DOCUMENTATION-AUDIT.md"

# Numbers the hand-typed audit asserted, each wrong by the time it was read.
STALE_CLAIMS = (
    "32 test files",
    "4 workflow files",
    "| architecture and interfaces | 5 |",
    "431 authored-doc links",
)


def _generated_block() -> str:
    text = AUDIT.read_text(encoding="utf-8")
    start = text.index(doc_audit.BEGIN)
    end = text.index(doc_audit.END)
    return text[start:end]


def test_the_committed_audit_still_describes_this_tree(capsys: pytest.CaptureFixture[str]) -> None:
    """`make docs-audit-check`, as a merge gate: the counts cannot outlive the tree."""
    assert doc_audit.main(["--check"]) == 0, (
        "docs/DOCUMENTATION-AUDIT.md no longer matches the repository. "
        "Run `make docs-audit` and commit the result.\n" + capsys.readouterr().err
    )


def test_the_drift_check_actually_fails_on_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Tamper with one number in a copy and require the check to catch it."""
    tampered = tmp_path / "DOCUMENTATION-AUDIT.md"
    shutil.copy2(AUDIT, tampered)
    text = tampered.read_text(encoding="utf-8")
    edited = re.sub(r"\| Test files \| \d+ \|", "| Test files | 32 |", text, count=1)
    assert edited != text, "the generated block no longer carries a test-file count"
    tampered.write_text(edited, encoding="utf-8")

    monkeypatch.setattr(doc_audit, "AUDIT", tampered)
    assert doc_audit.main(["--check"]) == 1


def test_the_stated_counts_equal_the_tree(tmp_path: Path) -> None:
    """Each count is re-derived here independently of the generator that wrote it."""
    block = _generated_block()

    tests = len(list((ROOT / "tests").glob("test_*.py")))
    workflows = sorted(p.name for p in (ROOT / ".github" / "workflows").glob("*.yml"))

    assert f"| Test files | {tests} |" in block, (
        f"the audit does not state the real test-file count ({tests})"
    )
    assert f"| Workflow files | {len(workflows)} |" in block, (
        f"the audit does not state the real workflow count ({len(workflows)})"
    )
    for name in workflows:
        assert f".github/workflows/{name}" in block, (
            f"{name} is a workflow in this repository and the audit does not list it"
        )


def test_no_stale_hand_typed_count_survives() -> None:
    """The absence assertion: the specific wrong numbers must be gone, not just corrected."""
    text = AUDIT.read_text(encoding="utf-8")
    surviving = [claim for claim in STALE_CLAIMS if claim in text]
    assert not surviving, f"hand-typed counts are still asserted: {surviving}"


def test_a_count_is_never_reported_as_a_pass() -> None:
    """`pass` belongs to predicates. An inventory row cannot pass or fail."""
    block = _generated_block()
    inventory = block[block.index("## Inventory") :]
    offenders = [
        line
        for line in inventory.splitlines()
        if line.startswith("|") and re.search(r"\|\s*(pass|fail)\s*\|", line)
    ]
    assert not offenders, (
        "the inventory tables report a count as a pass/fail verdict:\n  - "
        + "\n  - ".join(offenders)
    )


def test_the_link_check_resolves_every_relative_link() -> None:
    """The claim the old audit reported as passing, re-derived rather than trusted."""
    checked, unresolved = doc_audit._check_links(doc_audit._authored_docs())
    assert checked > 0, "the link check found no links — it would pass vacuously"
    assert not unresolved, f"unresolved relative links: {unresolved}"


def test_the_link_check_is_case_sensitive_on_a_case_insensitive_filesystem() -> None:
    """macOS said `docs/accessibility.md` existed. github.com returns 404 for it.

    The old audit reported "0 unresolved" while `docs/README.md` shipped a dead
    lowercase link on the first page of the docs index, because `Path.exists()` folds
    case on APFS. A link check that agrees with the maintainer's laptop instead of the
    host every reader uses is a check that certifies 404s.
    """
    wrong_case = ROOT / "docs" / "accessibility.md"
    real = ROOT / "docs" / "ACCESSIBILITY.md"
    assert real.is_file(), "the accessibility statement moved; update this gate"
    assert not doc_audit._exists_case_sensitively(wrong_case), (
        "the link check resolves a path whose case is wrong — it would keep passing on "
        "macOS while shipping 404s to everyone else"
    )
    assert doc_audit._exists_case_sensitively(real)


def test_the_audit_is_deterministic() -> None:
    """Same tree, same bytes — otherwise the drift check is noise, not a gate."""
    assert doc_audit._render() == doc_audit._render()
    assert "Last reviewed" not in _generated_block(), (
        "a generated date would drift daily and make the drift check meaningless"
    )


def test_generated_artifacts_do_not_change_the_inventory(tmp_path: Path) -> None:
    """`npm ci` and `make verify` leave directories behind; the audit must ignore them."""
    for polluted in ("web/node_modules/pkg/README.md", "build/pseudolocale/NOTES.md"):
        assert doc_audit._excluded(polluted), f"{polluted} would be counted as authored docs"
