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

The last block covers the opt-in online pass (#233), which resolves what the offline gate
cannot: whether a linked issue exists, is open, and is an issue rather than a pull request.
Its two safety properties are tested as directly as the rule itself — the merge gate still
opens no socket, and a lookup that could not be performed never reports as a pass.
"""

from __future__ import annotations

import re
import urllib.error
import urllib.request
from collections.abc import Callable, Iterator
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

    CQ-34's merge gate is offline by design: it proves a marker *carries* an issue
    reference, never that the issue exists, is open, or is about the marker. That blind
    spot was live — the marker pointed at #184 and passed while #184 was closed and about
    stale tag claims, so the DOI was tracked by nothing and the gate was green.

    Issue state is now checked by the opt-in online pass (#233), which is scheduled rather
    than merge-blocking, so it cannot be relied on *here*: this file must hold offline.
    What can be checked offline is agreement: the number in the marker, the number README
    calls the DOI's tracking issue, and the number ROADMAP calls it must all be the same
    one. Repointing the marker without moving the prose — or the reverse — is how the
    previous state would be re-entered, and this fails on it.

    The sentence above deliberately writes "pointed at #184" rather than spelling the
    marker word next to it. It used to spell it, and the online pass's first run flagged
    this docstring: a line of prose that looks exactly like a live marker tracked by a
    closed issue. The file's own convention — assemble marker words from
    `MARKER_WORDS`, never type them — had been broken once, here, and the offline gate
    could not see it because the line carried a reference. The check found its first
    finding in the test file that exercises it.
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


# ---------------------------------------------------------------------------
# The online resolver (#233). CQ-34's merge gate proves a marker *carries* an issue
# reference; it cannot see that the issue is closed, absent, or about something else.
# These exercise the opt-in pass that closes what is decidable — and pin the two
# properties that make it safe to add: the merge gate stays offline, and a lookup that
# could not be performed never prints as a pass.
# ---------------------------------------------------------------------------


@pytest.fixture
def marker_tree(tmp_path: Path) -> Iterator[Path]:
    """Point the scanner at a temporary tree, so assertions are about the code."""
    original_root = check_debt_markers.ROOT
    check_debt_markers.ROOT = tmp_path
    try:
        yield tmp_path
    finally:
        check_debt_markers.ROOT = original_root


def _plant(root: Path, line: str) -> None:
    planted = root / "src" / "planted.py"
    planted.parent.mkdir(parents=True, exist_ok=True)
    planted.write_text(f"x = 1  # {line}\n", encoding="utf-8")


def _facts(
    number: int,
    *,
    state: str = "open",
    title: str | None = None,
    is_pull_request: bool = False,
) -> check_debt_markers.IssueFacts:
    return check_debt_markers.IssueFacts(
        number=number,
        state=state,
        title=f"issue {number}" if title is None else title,
        is_pull_request=is_pull_request,
    )


def test_the_merge_gate_makes_no_network_call(monkeypatch: pytest.MonkeyPatch) -> None:
    """The load-bearing property of #233: adding an online pass must not move the gate.

    `make verify` runs `check_debt_markers.py` with no flags. If that path ever acquired
    a dependency on api.github.com, a merge would start failing because GitHub had a bad
    minute — the trade the tool's docstring refuses. Any attempt to open a socket here is
    an error, so this fails loudly rather than merely being slow.
    """

    def forbidden(*args: object, **kwargs: object) -> object:
        raise AssertionError("the offline debt-marker gate opened a network connection")

    monkeypatch.setattr(urllib.request, "urlopen", forbidden)
    assert check_debt_markers.main([]) == 0


def test_linked_markers_are_exactly_what_the_offline_gate_accepted(marker_tree: Path) -> None:
    """The two passes split one stream, so they cannot disagree about what a marker is."""
    _plant(marker_tree, f"{_TODO}(#142): tracked")
    bare_file = marker_tree / "src" / "bare.py"
    bare_file.write_text(f"y = 2  # {_FIXME}: untracked\n", encoding="utf-8")

    linked = check_debt_markers.find_linked_markers()
    bare = check_debt_markers.find_bare_markers()

    assert [(m.path, m.line_number, m.issue) for m in linked] == [("src/planted.py", 1, 142)]
    assert [(rel, number) for rel, number, _ in bare] == [("src/bare.py", 1)]


def test_a_full_issue_url_resolves_to_the_same_number_as_a_bare_reference(
    marker_tree: Path,
) -> None:
    """CQ-34 accepts both forms, so the resolver has to read both."""
    _plant(marker_tree, f"{_HACK}: see https://github.com/ChelseaKR/nearmiss/issues/142")
    assert [m.issue for m in check_debt_markers.find_linked_markers()] == [142]


@pytest.mark.parametrize(
    ("facts", "expected"),
    [
        (_facts(1), None),
        (_facts(2, state="closed"), "issue is closed"),
        (_facts(3, state="absent"), "no such issue in this repository"),
        (_facts(4, is_pull_request=True), "resolves to a pull request, not a tracked issue"),
    ],
)
def test_the_decidable_checks_are_exists_open_and_not_a_pull_request(
    facts: check_debt_markers.IssueFacts, expected: str | None
) -> None:
    """The #184 case is the second row. The fourth is why the PR field is read at all.

    GitHub's issues endpoint answers for pull requests too, so a marker citing a merged
    PR number would otherwise resolve to `state: closed` — or, while the PR was open, to
    a cheerful `open` over work that is not a tracked task at all.
    """
    assert check_debt_markers._verdict(facts) == expected


def test_relevance_is_reported_and_never_scored(marker_tree: Path) -> None:
    """The one thing the pass refuses to decide, it still puts in front of a reader.

    A title-similarity number would look like a verdict without being one. What the pass
    owes instead is the juxtaposition that made the #184 mismatch obvious to a human, so
    the marker text and the live issue title must appear together on one marker's report.
    """
    _plant(marker_tree, f"{_TODO}(#184): mint a DOI")
    resolutions = check_debt_markers.resolve_linked_markers(
        check_debt_markers.find_linked_markers(),
        lambda number: _facts(number, title="README and ROADMAP say no tag has been pushed"),
    )
    described = check_debt_markers._describe(resolutions[0])
    assert "mint a DOI" in described
    assert "README and ROADMAP say no tag has been pushed" in described


def test_each_issue_is_asked_about_once_however_many_markers_cite_it(
    marker_tree: Path,
) -> None:
    """A repository with many markers on one issue must not spend one request per line."""
    _plant(marker_tree, f"{_TODO}(#142): first")
    (marker_tree / "src" / "second.py").write_text(
        f"z = 3  # {_XXX}(#142): second\n", encoding="utf-8"
    )
    asked: list[int] = []

    def fetch(number: int) -> check_debt_markers.IssueFacts:
        asked.append(number)
        return _facts(number)

    resolutions = check_debt_markers.resolve_linked_markers(
        check_debt_markers.find_linked_markers(), fetch
    )
    assert asked == [142]
    assert len(resolutions) == 2
    assert all(item.problem is None for item in resolutions)


def test_a_lookup_that_could_not_be_performed_is_not_a_pass(
    marker_tree: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """An unanswered API must never print as "every marker checks out".

    This repository's recurring defect is absence rendered as a value. A rate limit, a
    5xx, or a dropped connection leaves the markers unverified, so the pass reports
    UNDETERMINED and exits 2 — distinct from both the clean run and a real finding.
    """
    _plant(marker_tree, f"{_TODO}(#142): tracked")

    def fetch(number: int) -> check_debt_markers.IssueFacts:
        raise check_debt_markers.IssueLookupError(f"issue #{number}: HTTP 502")

    assert check_debt_markers.resolve_issues(fetch) == 2
    captured = capsys.readouterr()
    assert "UNDETERMINED" in captured.err
    assert "ONLINE OK" not in captured.out


def test_a_closed_issue_fails_the_online_pass(
    marker_tree: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The exact state that was green: a marker linked to a closed, unrelated issue."""
    _plant(marker_tree, f"{_TODO}(#184): mint a DOI")

    assert check_debt_markers.resolve_issues(lambda n: _facts(n, state="closed")) == 1
    assert "ONLINE FAILED" in capsys.readouterr().err


def test_a_real_finding_outranks_an_undetermined_lookup(marker_tree: Path) -> None:
    """Both are reported; the exit code names the actionable one."""
    _plant(marker_tree, f"{_TODO}(#184): closed")
    (marker_tree / "src" / "second.py").write_text(
        f"z = 3  # {_XXX}(#999): unreachable\n", encoding="utf-8"
    )

    def fetch(number: int) -> check_debt_markers.IssueFacts:
        if number == 999:
            raise check_debt_markers.IssueLookupError("HTTP 502")
        return _facts(number, state="closed")

    assert check_debt_markers.resolve_issues(fetch) == 1


def test_a_tree_with_no_linked_markers_resolves_cleanly(marker_tree: Path) -> None:
    """Nothing to ask about is a pass, not a crash — and still makes no request."""

    def fetch(number: int) -> check_debt_markers.IssueFacts:
        raise AssertionError("nothing should have been fetched")

    assert check_debt_markers.resolve_issues(fetch) == 0


def test_a_response_without_a_state_is_undetermined_not_open() -> None:
    """A missing field must not default to the answer that passes."""
    with pytest.raises(check_debt_markers.IssueLookupError):
        check_debt_markers.facts_from_payload(142, {"title": "no state here"})


def test_a_payload_carrying_pull_request_is_recognised_as_one() -> None:
    """GitHub marks a pull request by the presence of the key, not by a boolean."""
    facts = check_debt_markers.facts_from_payload(
        228, {"state": "closed", "title": "a merged PR", "pull_request": {"url": "..."}}
    )
    assert facts.is_pull_request
    assert facts.title == "a merged PR"


def test_the_repository_is_read_off_pyproject_not_hard_coded() -> None:
    """A hard-coded slug would grade a fork's markers against this repository's numbers."""
    assert check_debt_markers.repository_slug() == "ChelseaKR/nearmiss"


def test_an_unusable_repository_url_refuses_rather_than_guessing(marker_tree: Path) -> None:
    """No slug means no lookup: guessing one would resolve against the wrong tracker."""
    (marker_tree / "pyproject.toml").write_text(
        '[project]\nname = "x"\n[project.urls]\nRepository = "https://example.invalid/"\n',
        encoding="utf-8",
    )
    with pytest.raises(check_debt_markers.IssueLookupError):
        check_debt_markers.repository_slug()


def test_a_404_is_a_verdict_and_a_500_is_not(monkeypatch: pytest.MonkeyPatch) -> None:
    """The API answering "no such issue" is decided; the API failing to answer is not."""

    def raise_http(code: int) -> Callable[..., object]:
        def opener(*args: object, **kwargs: object) -> object:
            raise urllib.error.HTTPError("https://api.github.com", code, "", {}, None)  # type: ignore[arg-type]

        return opener

    fetch = check_debt_markers.github_issue_fetcher("o/r", token=None, timeout=1.0)

    monkeypatch.setattr(urllib.request, "urlopen", raise_http(404))
    assert fetch(142).state == "absent"

    monkeypatch.setattr(urllib.request, "urlopen", raise_http(500))
    with pytest.raises(check_debt_markers.IssueLookupError):
        fetch(142)


def test_an_unreachable_api_raises_a_lookup_error_not_a_verdict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A dropped connection is undetermined, and must not surface as a marker finding."""

    def opener(*args: object, **kwargs: object) -> object:
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr(urllib.request, "urlopen", opener)
    fetch = check_debt_markers.github_issue_fetcher("o/r", token=None, timeout=1.0)
    with pytest.raises(check_debt_markers.IssueLookupError):
        fetch(142)
