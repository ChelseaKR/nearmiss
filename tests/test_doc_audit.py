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

import json
import re
import shutil
import subprocess
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


def test_local_data_runs_do_not_change_the_inventory() -> None:
    """`make real` writes Markdown into a gitignored tree; the audit must ignore it.

    The failure this pins was not hypothetical. A real-city run left a generated brief at
    `data/real/berlin/published-potsdam/potsdam-brief.md`, and from then on
    `make docs-audit-check` and `make test` failed on a checkout with no changes in it —
    while the remedy they printed, `make docs-audit`, wanted to commit that ignored path
    into a public document, city name and all.
    """
    for local in (
        "data/real/berlin/published-potsdam/potsdam-brief.md",
        "data/raw/victoria/NOTES.md",
        "data/pending/queue/README.md",
    ):
        assert doc_audit._excluded(local), f"{local} is gitignored but would be counted"


def test_published_artifacts_are_still_counted() -> None:
    """`data/published/` is committed, so excluding local data must not swallow it."""
    for published in ("data/published/davis-ranked.md", "data/published/riverside-ranked.md"):
        assert not doc_audit._excluded(published), f"{published} is committed and must count"
        assert published in doc_audit._authored_docs()


def test_no_gitignored_markdown_reaches_the_inventory() -> None:
    """The audit describes the repository, not whatever this checkout happens to hold.

    Asserted against git's own ignore rules rather than a second copy of the exclusion
    list, so a future ignored directory that grows a Markdown file fails here instead of
    silently entering a committed document.
    """
    if shutil.which("git") is None or not (ROOT / ".git").exists():
        pytest.skip("no git checkout available to read ignore rules from")

    docs = doc_audit._authored_docs()
    result = subprocess.run(
        ["git", "check-ignore", "--stdin"],
        input="\n".join(docs),
        capture_output=True,
        text=True,
        cwd=ROOT,
        check=False,
    )
    if result.returncode not in (0, 1):  # 0 = some ignored, 1 = none ignored
        pytest.skip(f"git check-ignore unavailable: {result.stderr.strip()}")

    ignored = sorted(line for line in result.stdout.splitlines() if line)
    assert not ignored, (
        "the audit counted gitignored paths as authored documentation, so its numbers "
        f"describe this checkout rather than the repository: {ignored}"
    )


# ---------------------------------------------------------------------------
# The half of the file the generator does not write.
#
# `_splice` copies everything outside the markers through untouched, so the drift
# check has never had an opinion about the prose. That is the hazard a generated
# file with hand-authored regions always carries, and it fired in this tool's other
# port: in `davis-bike-hazard-map` a bad conflict resolution deleted two paragraphs
# from outside the markers, the only witness was a generated link count falling 96
# to 95, and the documented repair for a failing count — regenerate — rewrote the
# count to agree with the deletion. Green gate, real content loss.
#
# Reproduced here before it was fixed: deleting the preamble paragraph that carries
# this file's two relative links moved "494 relative links checked" to 492 and
# `make docs-audit` made the file self-consistent again; deleting a paragraph with
# no link in it did not even fail the check.
# ---------------------------------------------------------------------------


def _prose_and_pin(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    """A working copy of the audit and its pin, so nothing here touches the real files."""
    audit = tmp_path / "DOCUMENTATION-AUDIT.md"
    pin = tmp_path / "DOCUMENTATION-AUDIT.narrative.json"
    shutil.copy2(AUDIT, audit)
    shutil.copy2(doc_audit.NARRATIVE_PIN, pin)
    monkeypatch.setattr(doc_audit, "AUDIT", audit)
    monkeypatch.setattr(doc_audit, "NARRATIVE_PIN", pin)
    return audit, pin


def _delete_a_paragraph(audit: Path, marker: str) -> None:
    text = audit.read_text(encoding="utf-8")
    start = text.index(marker)
    end = text.index("\n\n", start) + 2
    assert start < text.index(doc_audit.BEGIN), "that paragraph is inside the generated block"
    audit.write_text(text[:start] + text[end:], encoding="utf-8")


def test_the_committed_prose_matches_its_pin() -> None:
    """`make docs-audit-check`, on the half of the file the generator never writes."""
    assert doc_audit._narrative_problem(AUDIT.read_text(encoding="utf-8")) is None


def test_deleting_prose_with_no_link_in_it_is_caught(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The invisible case. Before the pin this passed, unchanged, with the prose gone."""
    audit, _ = _prose_and_pin(tmp_path, monkeypatch)
    _delete_a_paragraph(audit, "## Scope notes")
    assert doc_audit.main(["--check"]) == 1


def test_the_failure_says_the_region_shrank(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A reader has to be told which way it moved: 'smaller' is the case worth re-reading."""
    audit, _ = _prose_and_pin(tmp_path, monkeypatch)
    _delete_a_paragraph(audit, "## Scope notes")
    doc_audit.main(["--check"])
    error = capsys.readouterr().err
    assert "got SMALLER" in error
    assert "Prose was deleted" in error


def test_regeneration_refuses_to_launder_a_deletion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The davis failure, exactly: the repair for a failing count must not accept the damage.

    Deleting the paragraph that carries this file's two relative links makes the generated
    link count wrong, so the drift check fails and tells the reader to regenerate. If
    regeneration then wrote a smaller count, the deletion would be committed as correct.
    """
    audit, _ = _prose_and_pin(tmp_path, monkeypatch)
    before = audit.read_text(encoding="utf-8")
    _delete_a_paragraph(audit, "**Everything below the marker is generated")
    damaged = audit.read_text(encoding="utf-8")

    assert doc_audit.main([]) == 1, "regeneration accepted an unreviewed prose deletion"
    assert audit.read_text(encoding="utf-8") == damaged, "it rewrote the file anyway"
    assert "REFUSED to regenerate" in capsys.readouterr().err
    assert before != damaged


def test_accepting_the_prose_is_a_separate_deliberate_step(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An intended edit is not blocked forever; it is recorded where a reviewer sees it."""
    audit, pin = _prose_and_pin(tmp_path, monkeypatch)
    _delete_a_paragraph(audit, "## Scope notes")
    assert doc_audit.main(["--check"]) == 1

    recorded_before = json.loads(pin.read_text(encoding="utf-8"))
    assert doc_audit.main(["--accept-narrative"]) == 0
    recorded_after = json.loads(pin.read_text(encoding="utf-8"))

    assert recorded_after["sha256"] != recorded_before["sha256"], "the pin was not updated"
    assert recorded_after["bytes"] < recorded_before["bytes"], "the deletion is not recorded"
    assert doc_audit.main(["--check"]) == 0


def test_a_missing_pin_is_a_failure_not_a_pass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Deleting the pin must not be a way to make the prose check disappear."""
    _, pin = _prose_and_pin(tmp_path, monkeypatch)
    pin.unlink()
    assert doc_audit.main(["--check"]) == 1
