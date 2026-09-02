"""CQ-34's bare-marker gate has to be a gate, not a claim.

`docs/standards/CODE-QUALITY-STANDARD.md` declares CQ-34 an AUTO-GATE — "bare markers fail
CI" — and until `tools/check_debt_markers.py` there was no implementation of it anywhere:
not in `make verify`, not in a workflow, not in pre-commit, and not in ruff's select set.
The repository was conformant by assertion. It happened to be true (the source tree really
was clean), which is the worst version of the problem: an unimplemented AUTO-GATE is
invisible to the conformance table precisely because nothing is failing.

Two directions are tested here, because a gate that has never been observed to fail is the
green tick this file exists to prevent:

* the real tree passes, so the gate is not merely dormant; and
* a planted bare marker fails, and the same marker with an issue reference passes, so the
  rule being enforced is the one the standard states.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from tools import check_debt_markers

ROOT = Path(__file__).resolve().parents[1]

# This file has to talk about the exact words the gate forbids, and it is NOT exempted
# from the gate — only `tools/check_debt_markers.py` is. Typing the literals here would
# mean either a red gate or an allowlist entry, and an allowlist entry in the test file
# would be a hole in the check this file exists to exercise. So the words are imported
# from the gate's own definition, which also keeps the cases below from drifting away
# from the rule they claim to test.
_TODO, _FIXME, _HACK, _XXX = check_debt_markers.MARKER_WORDS


def test_the_tree_has_no_bare_debt_markers(capsys: pytest.CaptureFixture[str]) -> None:
    """`make markers`, as a merge gate."""
    assert check_debt_markers.main([]) == 0, (
        "A debt marker in the scanned tree carries no issue reference. Add one "
        "(`# marker(#142): ...`) or resolve the marker.\n" + capsys.readouterr().err
    )


def test_the_only_marker_the_repo_ships_is_linked() -> None:
    """CITATION.cff's DOI marker is the repository's one real marker; it must stay linked.

    It is not an incidental example. It is the marker the standard's own `src/`-scoped
    example regex would have missed, which is why this gate scans root metadata too.
    """
    citation = (ROOT / "CITATION.cff").read_text(encoding="utf-8")
    marker_lines = [line for line in citation.splitlines() if _TODO in line]
    assert marker_lines, "CITATION.cff no longer carries the DOI marker; update this test."
    for line in marker_lines:
        assert check_debt_markers._LINKED.search(line), (
            f"bare marker in CITATION.cff: {line.strip()}"
        )


def test_the_doi_marker_and_the_documents_name_the_same_issue() -> None:
    """The marker's issue number must be the one README and ROADMAP say tracks the DOI.

    CQ-34 is offline by design: it proves a marker *carries* an issue reference, never
    that the issue exists, is open, or is about the marker. That blind spot was live —
    the marker read `TODO(#184)` and passed while #184 was closed and about stale tag
    claims, so the DOI was tracked by nothing and the gate was green.

    Issue state still cannot be checked here without a network call the gate refuses to
    make. What *can* be checked offline is agreement: the number in the marker, the
    number README calls the DOI's tracking issue, and the number ROADMAP calls it must
    all be the same one. Repointing the marker without moving the prose — or the reverse
    — is how the previous state would be re-entered, and this fails on it.
    """
    citation = (ROOT / "CITATION.cff").read_text(encoding="utf-8")
    marker_line = next(line for line in citation.splitlines() if _TODO in line and "doi" in line)
    match = check_debt_markers._LINKED.search(marker_line)
    assert match is not None, f"the DOI marker carries no issue reference: {marker_line.strip()}"
    marker_issue = re.search(r"#(\d+)", match.group(0))
    assert marker_issue is not None, f"no issue number in {match.group(0)!r}"
    number = marker_issue.group(1)

    for document in ("README.md", "docs/ROADMAP.md"):
        text = (ROOT / document).read_text(encoding="utf-8")
        doi_sentences = [
            line
            for line in text.splitlines()
            if "CITATION.cff" in line and f"#{number}" in line and "DOI" in line
        ]
        assert doi_sentences, (
            f"{document} does not name #{number} as the issue tracking the DOI, but "
            f"CITATION.cff's marker points there. One of the two moved without the other."
        )


@pytest.mark.parametrize(
    ("line", "is_violation"),
    [
        (f"# {_TODO}: wire this up", True),
        (f"# {_FIXME} rounding is wrong here", True),
        (f"// {_HACK} around the parser", True),
        (f"# {_XXX} revisit", True),
        (f"# {_TODO}(#142): wire this up", False),
        (f"# {_FIXME}: see https://github.com/ChelseaKR/nearmiss/issues/142", False),
        ("a comment mentioning todos in lower case", False),
        (f"{_TODO}S_REMAINING = 0", False),
    ],
)
def test_the_rule_is_the_one_the_standard_states(line: str, is_violation: bool) -> None:
    """Bare marker fails; the same marker with an issue reference passes."""
    matched = bool(check_debt_markers._MARKER.search(line))
    linked = bool(check_debt_markers._LINKED.search(line))
    assert (matched and not linked) is is_violation


def test_the_gate_actually_fails_on_a_planted_marker(tmp_path: Path) -> None:
    """A check that cannot be shown to fail is not a check.

    The scanner is pointed at a temporary tree rather than the real one so the assertion
    is about the detector, not about whatever happens to be committed today.
    """
    planted = tmp_path / "src" / "planted.py"
    planted.parent.mkdir(parents=True)
    planted.write_text(f"x = 1  # {_TODO}: unlinked\n", encoding="utf-8")

    original_root = check_debt_markers.ROOT
    try:
        check_debt_markers.ROOT = tmp_path
        violations = check_debt_markers.find_bare_markers()
    finally:
        check_debt_markers.ROOT = original_root

    assert [(rel, number) for rel, number, _ in violations] == [("src/planted.py", 1)]


def test_docs_are_out_of_scope_so_the_standard_does_not_fail_itself(tmp_path: Path) -> None:
    """`docs/standards/CODE-QUALITY-STANDARD.md` contains the word this gate looks for.

    A naive repo-wide grep matches the document that *defines* the rule. Debt markers are
    a code-hygiene control, so `docs/` is not scanned — this pins that decision.
    """
    doc = tmp_path / "docs" / "standards" / "CODE-QUALITY-STANDARD.md"
    doc.parent.mkdir(parents=True)
    rule = f"| No `{_TODO}`/`{_FIXME}`/`{_HACK}` without a linked issue | AUTO-GATE |\n"
    doc.write_text(rule, encoding="utf-8")

    original_root = check_debt_markers.ROOT
    try:
        check_debt_markers.ROOT = tmp_path
        violations = check_debt_markers.find_bare_markers()
    finally:
        check_debt_markers.ROOT = original_root

    assert violations == []
