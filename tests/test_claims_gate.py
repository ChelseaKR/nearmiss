"""The claims gate has to prove the witness *passes*, and has to read the docs a reader reads.

`tools/check_claims.py` is what this project offers in place of "trust us": a manifest
of load-bearing sentences, each with a witness a reviewer can open. Two structural
holes made that guarantee narrower than the one a reader would infer.

* A witness only had to **exist**. `_witness_ok` checked `path.exists()` and regex-matched
  `def <name>(`. A witness that was skipped, xfailed, or sitting where pytest never
  collects it satisfied the gate exactly as well as a passing one — the confirming half
  of "the thing a reviewer can open to confirm the sentence is not an overclaim" was on
  the honour system.
* Only **three docs** were ever scanned. Everything else could carry a tagged claim with
  no gate in either direction, including `docs/ACCESSIBILITY.md`,
  `docs/DECISION-DOSSIER-TEMPLATE.md` and `docs/PRODUCT-EXPANSION-PLAN.md` — the docs a
  stranger opens from the live site.

Each scenario below builds a miniature repository, drops the real tool into it, and runs
it. Asserting on a synthetic repo is what lets these tests assert the *failure* modes: a
gate that cannot be shown to fail is the green check this file exists to prevent.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from tools import check_claims

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "check_claims.py"

MANIFEST_HEADER = (
    "# Claims manifest\n\n"
    "| Claim ID | Doc anchor (file + section) | Witness (test or file) |\n"
    "| --- | --- | --- |\n"
)

PASSING_WITNESS = """
def test_witness() -> None:
    assert True
"""

SKIPPED_WITNESS = """
import pytest


@pytest.mark.skip(reason="not implemented yet")
def test_witness() -> None:
    assert True
"""

XFAIL_WITNESS = """
import pytest


@pytest.mark.xfail(reason="known broken")
def test_witness() -> None:
    raise AssertionError("the claim is not actually backed")
"""

FAILING_WITNESS = """
def test_witness() -> None:
    raise AssertionError("the claim is not actually backed")
"""

# `def test_witness(` is right there in the file, and pytest never runs it: a class
# that is not named Test* is not collected.
UNCOLLECTED_WITNESS = """
class Helpers:
    def test_witness(self) -> None:
        assert True
"""


def _make_repo(
    tmp_path: Path,
    *,
    witness_source: str = PASSING_WITNESS,
    witness: str = "tests/test_witness.py::test_witness",
    doc: str = "README.md",
    tagged_docs: dict[str, str] | None = None,
    listed: bool = True,
    html: dict[str, str] | None = None,
) -> Path:
    """A miniature repository with the real gate installed in it."""
    repo = tmp_path / "repo"
    (repo / "tools").mkdir(parents=True)
    (repo / "docs").mkdir(parents=True)
    (repo / "tests").mkdir(parents=True)
    shutil.copy2(TOOL, repo / "tools" / "check_claims.py")
    (repo / "tools" / "__init__.py").write_text("", encoding="utf-8")
    (repo / "tests" / "test_witness.py").write_text(witness_source, encoding="utf-8")

    rows = f"| `demo-claim` | `{doc}` — § Demo | `{witness}` |\n" if listed else ""
    (repo / "docs" / "CLAIMS.md").write_text(MANIFEST_HEADER + rows, encoding="utf-8")

    docs = tagged_docs if tagged_docs is not None else {doc: "demo-claim"}
    for rel, claim_id in docs.items():
        path = repo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            f"# Doc\n\n<!-- claim:{claim_id} -->\nA load-bearing sentence.\n"
            f"<!-- /claim:{claim_id} -->\n",
            encoding="utf-8",
        )

    for rel, body in (html or {}).items():
        page = repo / rel
        page.parent.mkdir(parents=True, exist_ok=True)
        page.write_text(body, encoding="utf-8")
    return repo


def _run(repo: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "tools/check_claims.py"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )


def test_a_passing_witness_is_accepted(tmp_path: Path) -> None:
    """The control: without this, every failure assertion below proves nothing."""
    result = _run(_make_repo(tmp_path))
    assert result.returncode == 0, result.stdout + result.stderr
    assert "ran 1 witness tests, all passed" in result.stdout


def test_a_skipped_witness_is_not_a_passing_witness(tmp_path: Path) -> None:
    """`@pytest.mark.skip` used to satisfy the gate exactly as well as a green test."""
    result = _run(_make_repo(tmp_path, witness_source=SKIPPED_WITNESS))
    assert result.returncode == 1, result.stdout
    assert "does not pass" in result.stderr
    assert "skipped" in result.stderr


def test_an_xfailed_witness_is_not_a_passing_witness(tmp_path: Path) -> None:
    """An xfail records that the claim is *not* backed. It cannot be the evidence for it."""
    result = _run(_make_repo(tmp_path, witness_source=XFAIL_WITNESS))
    assert result.returncode == 1, result.stdout
    assert "does not pass" in result.stderr


def test_a_failing_witness_fails_the_gate(tmp_path: Path) -> None:
    result = _run(_make_repo(tmp_path, witness_source=FAILING_WITNESS))
    assert result.returncode == 1, result.stdout
    assert "does not pass" in result.stderr


def test_a_witness_pytest_never_collects_fails_the_gate(tmp_path: Path) -> None:
    """`def test_witness(` exists in the named file and nothing ever runs it."""
    result = _run(_make_repo(tmp_path, witness_source=UNCOLLECTED_WITNESS))
    assert result.returncode == 1, result.stdout
    assert "was not collected by pytest" in result.stderr


def test_a_witness_naming_no_test_is_reported_as_unrun_not_as_green(tmp_path: Path) -> None:
    """A lockfile witness cannot be executed; the gate publishes that limit."""
    repo = _make_repo(tmp_path, witness="requirements.lock")
    (repo / "requirements.lock").write_text("pinned==1.0\n", encoding="utf-8")
    result = _run(repo)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "checked for existence only — existence is not a pass" in result.stdout
    assert "requirements.lock" in result.stdout


def test_a_tag_outside_the_three_original_docs_is_still_gated(tmp_path: Path) -> None:
    """`docs/**/*.md` was a blind spot: an unlisted tag there used to pass silently."""
    repo = _make_repo(
        tmp_path,
        doc="docs/ANYWHERE.md",
        tagged_docs={"docs/ANYWHERE.md": "demo-claim", "docs/UNLISTED.md": "not-in-manifest"},
    )
    result = _run(repo)
    assert result.returncode == 1, result.stdout
    assert "docs/UNLISTED.md" in result.stderr
    assert "missing from docs/CLAIMS.md" in result.stderr


def test_a_doc_the_site_links_to_is_scanned(tmp_path: Path) -> None:
    """The atlas footer and gateway link docs through full forge URLs, not relative paths."""
    repo = _make_repo(
        tmp_path,
        tagged_docs={"README.md": "demo-claim", "docs/LINKED.md": "linked-but-unlisted"},
        html={
            "web/us-coverage.html": (
                '<a href="https://github.com/ChelseaKR/nearmiss/blob/main/docs/LINKED.md">docs</a>'
            )
        },
    )
    result = _run(repo)
    assert result.returncode == 1, result.stdout
    assert "docs/LINKED.md" in result.stderr
    assert "missing from docs/CLAIMS.md" in result.stderr


def test_a_site_link_to_a_missing_doc_is_an_error(tmp_path: Path) -> None:
    """A published page pointing at a doc that does not exist is a broken public promise."""
    repo = _make_repo(
        tmp_path,
        html={"index.html": '<a href="docs/GONE.md">read the plan</a>'},
    )
    result = _run(repo)
    assert result.returncode == 1, result.stdout
    assert "docs/GONE.md" in result.stderr
    assert "does not exist in this repository" in result.stderr


def test_a_documented_example_tag_is_not_a_claim(tmp_path: Path) -> None:
    """A doc explaining the convention inside a code span is describing, not claiming."""
    repo = _make_repo(tmp_path)
    (repo / "docs" / "HOWTO.md").write_text(
        "Wrap the sentence in `<!-- claim:ID -->` … `<!-- /claim:ID -->` tags.\n\n"
        "```markdown\n<!-- claim:example -->\nprose\n<!-- /claim:example -->\n```\n",
        encoding="utf-8",
    )
    result = _run(repo)
    assert result.returncode == 0, result.stdout + result.stderr


def test_this_repository_scans_the_docs_its_own_site_links_to() -> None:
    """Not a synthetic repo: the real gate, against the real shipped HTML."""
    linked, errors = check_claims._site_linked_docs()
    assert not errors, errors
    for expected in (
        "docs/ACCESSIBILITY.md",
        "docs/DECISION-DOSSIER-TEMPLATE.md",
        "docs/PRODUCT-EXPANSION-PLAN.md",
    ):
        assert expected in linked, f"{expected} is linked from the shipped HTML but not scanned"
    assert len(check_claims._default_docs()) > 3, (
        "the scan is back to a handful of docs; the blind spot has returned"
    )
