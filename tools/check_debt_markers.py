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
exists, is open, or is about the marker. The repository's one live marker was the
demonstration: `CITATION.cff:68` read `TODO(#184)` and passed this gate while #184 had
been closed on 2026-08-23 and was about the README and ROADMAP's stale tag claims, not
about minting a DOI — green over tracking that did not exist. The marker now reads
`TODO(#227)`, an open issue that is actually about the DOI, so the instance is fixed.

**The class is closed by `--resolve-issues`, and only where the network is acceptable
(#233).** The merge gate above is unchanged: no flag, no network, same bytes, same exit
code. `--resolve-issues` is a second pass that asks GitHub about every issue a marker
already links, and it runs from a scheduled workflow rather than from `make verify`,
because a merge gate whose value is that it is fast, local, and identical in CI must not
acquire a dependency on api.github.com being up.

What the online pass decides, and what it deliberately does not:

* **Exists, in this repository** — a 404 fails. `(#142)` naming somebody else's issue
  tracker, or a number that was never allocated here, is not tracking.
* **Open** — a closed issue fails. This is the #184 case, caught.
* **An issue, not a pull request** — GitHub's issues endpoint answers for pull requests
  too, so `(#228)` would resolve happily to a merged PR and read as tracked work. A
  reference that resolves to a pull request fails.
* **Relevant** — *not decided here, and not faked.* Whether "mint a DOI" is what #227 is
  about is a reading, and a title-similarity score would be a number that looks like a
  verdict and is not one — the exact defect this repository names everywhere else. So the
  pass prints the issue's live title beside the marker text on one line, which is the form
  in which the #184 mismatch was obvious to a human ("mint a DOI" against "stale tag
  claims"), and leaves the judgment where it belongs.

A lookup that could not be performed at all — network down, rate limit, 5xx — is reported
as **undetermined** and exits `2`. It is never folded into the pass: "the API did not
answer" must not print as "every marker checks out".

CQ-35 (no `type: ignore` / `# noqa` without a code *and* an issue reference) is the same
grep shape and is **not** implemented here. This repository has roughly two dozen such
suppressions, all of which already carry a rule code and most a written justification, so
turning CQ-35 on is a decision about whether a code plus a reason satisfies it or whether
every suppression must also carry an issue link. That is a judgment call for the owner, not
something to smuggle in behind a CQ-34 fix.

Pure standard library. Deterministic and offline by default; network only under
`--resolve-issues`. Style mirrors `tools/doc_audit.py`.

    make markers            # the merge gate (also runs inside `make verify`) — offline
    make markers-online     # the scheduled resolver (#233) — network, NOT in `verify`
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tomllib
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
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

# --- The online resolver (#233). Nothing below this line runs without --resolve-issues. ---

GITHUB_API_ROOT = "https://api.github.com"
_USER_AGENT = "nearmiss-check-debt-markers"


@dataclass(frozen=True)
class LinkedMarker:
    """A marker that passed the offline gate, and the issue number it points at."""

    path: str
    line_number: int
    text: str
    issue: int


@dataclass(frozen=True)
class IssueFacts:
    """What GitHub says about a referenced number. `title` is for a human, not a check."""

    number: int
    state: str
    title: str
    is_pull_request: bool


@dataclass(frozen=True)
class MarkerResolution:
    """One marker's verdict.

    `problem` is a decided failure. `undetermined` means the lookup could not be
    performed, which is reported as its own outcome rather than as a pass — publishing
    "could not read" as "fine" is the failure mode this repository keeps finding.
    """

    marker: LinkedMarker
    facts: IssueFacts | None
    problem: str | None
    undetermined: str | None


class IssueLookupError(RuntimeError):
    """The API could not be asked. Says nothing about the marker."""


IssueFetcher = Callable[[int], IssueFacts]


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


def _marker_lines() -> Iterator[tuple[str, int, str]]:
    """Every (path, line number, raw line) in scope that contains a marker word.

    The offline gate and the online resolver split this stream between them — bare lines
    to one, linked lines to the other — so the two can never disagree about which lines
    are markers or which files are in scope.
    """
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
            if _MARKER.search(line):
                yield rel, number, line


def find_bare_markers() -> list[tuple[str, int, str]]:
    """Every (path, line number, line) whose marker carries no issue reference."""
    return [
        (rel, number, line.strip())
        for rel, number, line in _marker_lines()
        if not _LINKED.search(line)
    ]


def find_linked_markers() -> list[LinkedMarker]:
    """Every marker that satisfies the offline gate, with the issue number it claims.

    These are exactly the lines `find_bare_markers` does *not* return: the offline gate
    has already accepted them, and the online pass asks whether that acceptance was
    warranted.
    """
    linked: list[LinkedMarker] = []
    for rel, number, line in _marker_lines():
        reference = _LINKED.search(line)
        if reference is None:
            continue
        digits = re.search(r"\d+", reference.group(0))
        if digits is None:  # pragma: no cover — _LINKED cannot match without digits.
            continue
        linked.append(LinkedMarker(rel, number, line.strip(), int(digits.group(0))))
    return linked


def repository_slug() -> str:
    """`owner/name`, read off `pyproject.toml` rather than hard-coded here.

    A literal would keep answering `ChelseaKR/nearmiss` in a fork, so the fork's markers
    would be resolved against this repository's issue numbers — a check that quietly
    grades the wrong tracker. `[project.urls].Repository` is the committed answer, and it
    is already the URL the package publishes.
    """
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    url = data.get("project", {}).get("urls", {}).get("Repository")
    if not isinstance(url, str):
        raise IssueLookupError("pyproject.toml has no [project.urls] Repository to resolve against")
    slug = urllib.parse.urlparse(url).path.strip("/").removesuffix(".git")
    if slug.count("/") != 1 or not all(slug.split("/")):
        raise IssueLookupError(f"[project.urls] Repository is not an owner/name URL: {url}")
    return slug


def facts_from_payload(number: int, payload: Mapping[str, object]) -> IssueFacts:
    """Turn one issues-API response into the three things that are actually decidable.

    A payload missing `state` is not defaulted to "open": an unreadable answer raises, so
    it lands in the undetermined bucket instead of passing.
    """
    state = payload.get("state")
    if not isinstance(state, str):
        raise IssueLookupError(f"issue #{number}: response carries no usable 'state'")
    title = payload.get("title")
    return IssueFacts(
        number=number,
        state=state,
        title=title if isinstance(title, str) else "",
        is_pull_request="pull_request" in payload,
    )


def github_issue_fetcher(slug: str, *, token: str | None, timeout: float) -> IssueFetcher:
    """Bounded, read-only GET of one issue. `GITHUB_TOKEN` only lifts the rate limit."""

    def fetch(number: int) -> IssueFacts:
        # Fixed https://api.github.com origin; only the issue number varies.
        request = urllib.request.Request(
            f"{GITHUB_API_ROOT}/repos/{slug}/issues/{number}",
            headers={
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": _USER_AGENT,
                **({"Authorization": f"Bearer {token}"} if token else {}),
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                # Decided, not undetermined: the API answered, and the answer is "no such
                # issue in this repository".
                return IssueFacts(number=number, state="absent", title="", is_pull_request=False)
            raise IssueLookupError(f"issue #{number}: HTTP {exc.code} from {slug}") from exc
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            raise IssueLookupError(f"issue #{number}: {exc}") from exc
        if not isinstance(payload, dict):
            raise IssueLookupError(f"issue #{number}: response was not a JSON object")
        return facts_from_payload(number, payload)

    return fetch


def _verdict(facts: IssueFacts) -> str | None:
    """The decidable part. Relevance is not here on purpose — see the module docstring."""
    if facts.state == "absent":
        return "no such issue in this repository"
    if facts.is_pull_request:
        return "resolves to a pull request, not a tracked issue"
    if facts.state != "open":
        return f"issue is {facts.state}"
    return None


def resolve_linked_markers(
    markers: list[LinkedMarker], fetch: IssueFetcher
) -> list[MarkerResolution]:
    """Ask about each distinct issue once, and attach the answer to every marker citing it."""
    seen: dict[int, IssueFacts | IssueLookupError] = {}
    resolutions: list[MarkerResolution] = []
    for marker in markers:
        if marker.issue not in seen:
            try:
                seen[marker.issue] = fetch(marker.issue)
            except IssueLookupError as exc:
                seen[marker.issue] = exc
        answer = seen[marker.issue]
        if isinstance(answer, IssueLookupError):
            resolutions.append(MarkerResolution(marker, None, None, str(answer)))
        else:
            resolutions.append(MarkerResolution(marker, answer, _verdict(answer), None))
    return resolutions


def _describe(resolution: MarkerResolution) -> str:
    """One line: where the marker is, what it says, and what its issue actually is.

    The marker text and the live issue title sit side by side because that juxtaposition
    is the whole relevance check — it is how "mint a DOI" against "stale tag claims" was
    obvious to a reader, and no similarity score is invented to pretend otherwise.
    """
    where = f"{resolution.marker.path}:{resolution.marker.line_number}"
    facts = resolution.facts
    if facts is None:
        answer = f"undetermined: {resolution.undetermined}"
    else:
        answer = f"#{facts.number} [{facts.state}] {facts.title or '(untitled)'}"
    return f"  {where}: {resolution.marker.text}\n      -> {answer}"


def resolve_issues(fetch: IssueFetcher) -> int:
    """The online pass. 0 = every linked marker checks out, 1 = a failure, 2 = undetermined."""
    resolutions = resolve_linked_markers(find_linked_markers(), fetch)
    if not resolutions:
        print("CQ-34 ONLINE OK: no linked debt markers to resolve.")
        return 0

    failed = [item for item in resolutions if item.problem is not None]
    unknown = [item for item in resolutions if item.undetermined is not None]

    print(f"CQ-34 online resolution of {len(resolutions)} linked marker(s):")
    for item in resolutions:
        print(_describe(item))
    print(
        "\nRelevance is not machine-checked. Read each marker against its issue title "
        "above:\n  a marker tracked by an open issue about something else is still "
        "untracked work."
    )

    for item in failed:
        print(
            f"CQ-34 ONLINE FAILED: {item.marker.path}:{item.marker.line_number} references "
            f"#{item.marker.issue} — {item.problem}.",
            file=sys.stderr,
        )
    for item in unknown:
        print(
            f"CQ-34 ONLINE UNDETERMINED: {item.marker.path}:{item.marker.line_number} — "
            f"{item.undetermined}. This is not a pass.",
            file=sys.stderr,
        )
    if failed:
        return 1
    if unknown:
        return 2
    print("CQ-34 ONLINE OK: every linked marker names an open issue in this repository.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--resolve-issues",
        action="store_true",
        help=(
            "after the offline gate, ask GitHub whether each linked issue exists, is open, "
            "and is an issue rather than a pull request (#233). Network; NOT part of "
            "`make verify`. Exit 2 means the lookup could not be performed."
        ),
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=10.0,
        help="per-request timeout for --resolve-issues (default: 10)",
    )
    args = parser.parse_args(argv)
    if not 1 <= args.timeout_seconds <= 60:
        parser.error("--timeout-seconds must be between 1 and 60")

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
    if not args.resolve_issues:
        return 0
    return resolve_issues(
        github_issue_fetcher(
            repository_slug(),
            token=os.environ.get("GITHUB_TOKEN"),
            timeout=args.timeout_seconds,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
