#!/usr/bin/env python3
"""Claims-parity drift gate (merge-blocking).

Enforces the accuracy-claims manifest ``docs/CLAIMS.md`` against the docs and the
tree, in both directions, so a doc claim can never drift away from the code that
backs it (or from the honest "planned, not implemented" wording it stands in for):

* **Manifest -> docs** — every claim ID in the manifest table appears as a
  *matched* ``<!-- claim:ID -->`` … ``<!-- /claim:ID -->`` comment pair in the
  doc file named in its anchor column.
* **Manifest -> tree** — every witness path exists; a ``path::test_name`` witness
  names a function (``def test_name``) that exists in that file **and that test is
  collected and passes**.
* **Docs -> manifest** — every ``<!-- claim:… -->`` tag found in any scanned doc
  is listed in the manifest. A tagged claim missing from the table fails the build,
  as does an unmatched open/close tag.

Two properties this gate used to *imply* and now actually enforces:

**The witness runs.** It used to be enough for ``def test_name`` to exist somewhere
in the named file. A witness that was ``@pytest.mark.skip``\\ ped, ``xfail``\\ ed,
emptied out, or sitting in a file pytest never collects satisfied the gate exactly as
well as a passing one — "the thing a reviewer can open" without the confirming half.
The witnesses are now executed with ``pytest --junitxml`` and each one has to be
collected and to *pass*; a skip, an xfail, or a missing collection is a failure, not a
pass. Only a witness that names a test can be run this way. A witness that names a
plain file (a lockfile, a schema, a module whose *absence* of a feature is the point)
is still checked for existence only, and that limit is printed rather than papered
over — an unrunnable witness is reported as unrun, not as green.

**The scan reaches the docs a reader actually reads.** The scan used to cover three
files. It now covers every ``*.md`` at the repository root and every ``docs/**/*.md``,
plus every doc the shipped HTML links to — the atlas footer links
``docs/ACCESSIBILITY.md``; the gateway and the dossier link
``docs/DECISION-DOSSIER-TEMPLATE.md`` and ``docs/PRODUCT-EXPANSION-PLAN.md``. Those are
the sentences a stranger reads with the live site open in the next tab, and a link from
the site to a doc that does not exist is itself an error here.

Widening costs nothing until someone tags a claim: this is a drift gate for *tagged*
sentences, so a wider scan only removes blind spots.

Standard library only; no network, deterministic apart from the pytest subprocess it
runs. Style mirrors ``tools/check_catalog_parity.py``.
"""

from __future__ import annotations

import re
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ElementTree
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "docs" / "CLAIMS.md"

# Every HTML document in the repository's web sources. A superset of the deployed
# allowlist in tools/build_site.py, deliberately: a doc linked from a page that is
# not deployed today is still a doc this gate should read.
SITE_HTML_GLOBS = ("*.html", "web/*.html")

_OPEN = re.compile(r"<!--\s*claim:([A-Za-z0-9._-]+)\s*-->")
_CLOSE = re.compile(r"<!--\s*/claim:([A-Za-z0-9._-]+)\s*-->")
_BACKTICK = re.compile(r"`([^`]+)`")
# A repo-relative docs/… Markdown path, linked either relatively (`docs/X.md`) or
# through a forge URL (`https://github.com/<owner>/<repo>/blob/<ref>/docs/X.md`).
# The atlas footer and the gateway use the URL form, which is exactly the form a
# single relative-path pattern would miss.
_DOC_LINKS = (
    re.compile(r"https?://[^\s\"'<>]*?/blob/[^/\s\"'<>]+/(docs/[A-Za-z0-9._/-]+\.md)"),
    re.compile(r"(?<![\w./-])(docs/[A-Za-z0-9._/-]+\.md)"),
)
_TEST_MODULE = re.compile(r"(?:^|/)test_[A-Za-z0-9_]+\.py$")


def _first_backtick(cell: str) -> str | None:
    """The first `code-span` in a table cell, unwrapped, or None."""
    m = _BACKTICK.search(cell)
    return m.group(1).strip() if m else None


def _parse_manifest(text: str) -> tuple[list[dict[str, str]], list[str]]:
    """Rows of {claim, doc, witness} from the first Markdown table; plus errors."""
    errors: list[str] = []
    rows: list[dict[str, str]] = []
    in_table = False
    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line.startswith("|"):
            in_table = False
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        # Header row (contains "Claim ID") starts the table; the separator row
        # (dashes only) is skipped.
        if any("claim id" in c.lower() for c in cells):
            in_table = True
            continue
        if not in_table:
            continue
        if all(set(c) <= {"-", ":", " "} for c in cells):
            continue
        if len(cells) < 3:
            errors.append(f"docs/CLAIMS.md:{lineno}: table row has < 3 columns: {raw!r}")
            continue
        claim = _first_backtick(cells[0])
        doc = _first_backtick(cells[1])
        witness = _first_backtick(cells[2])
        if not claim:
            errors.append(f"docs/CLAIMS.md:{lineno}: no `claim-id` in first column: {raw!r}")
            continue
        if not doc:
            errors.append(f"docs/CLAIMS.md:{lineno}: no `doc/path` in anchor column for {claim!r}")
            continue
        if not witness:
            errors.append(f"docs/CLAIMS.md:{lineno}: no `witness` for {claim!r}")
            continue
        rows.append({"claim": claim, "doc": doc, "witness": witness})
    return rows, errors


def _strip_code(text: str) -> str:
    """Drop fenced blocks and inline code spans.

    A doc that *documents* the convention — ``docs/CLAIMS.md`` itself writes
    ``` `<!-- claim:ID --> … <!-- /claim:ID -->` ``` — is describing a tag, not making
    a claim. Scanning the example would have made the widened scan fail on the manifest
    that defines it.
    """
    without_fences = re.sub(r"(?ms)^```.*?^```\s*?$", "", text)
    return re.sub(r"`[^`\n]*`", "", without_fences)


def _tag_pairs(text: str, where: str) -> tuple[set[str], list[str]]:
    """Matched claim IDs in a doc; errors for any unmatched open/close tag."""
    errors: list[str] = []
    text = _strip_code(text)
    opens = _OPEN.findall(text)
    closes = _CLOSE.findall(text)
    open_set, close_set = set(opens), set(closes)
    for cid in sorted(open_set - close_set):
        errors.append(
            f"{where}: claim {cid!r} has an opening tag with no matching <!-- /claim:{cid} -->"
        )
    for cid in sorted(close_set - open_set):
        errors.append(
            f"{where}: claim {cid!r} has a closing tag with no matching <!-- claim:{cid} -->"
        )
    for cid in sorted(open_set):
        if opens.count(cid) > 1 or closes.count(cid) > 1:
            errors.append(f"{where}: claim {cid!r} tag appears more than once")
    return (open_set & close_set), errors


def _witness_ok(witness: str) -> str | None:
    """Return an error string if the witness path/function is missing, else None."""
    path_part, _, func = witness.partition("::")
    path = ROOT / path_part
    if not path.exists():
        return f"witness path does not exist: {path_part}"
    if func:
        if not path_part.endswith(".py"):
            return f"witness {witness!r} names ::{func} but {path_part} is not a .py file"
        src = path.read_text(encoding="utf-8")
        if not re.search(rf"^\s*def {re.escape(func)}\s*\(", src, re.MULTILINE):
            return f"witness {witness!r}: function def {func}(...) not found in {path_part}"
    return None


def _node_id(witness: str) -> str | None:
    """The pytest node id for a runnable witness, or None if it names no test.

    ``tests/test_rates.py::test_wilson_ci_bounds`` runs that one test;
    ``tests/test_network.py`` runs the whole module. A witness that names a
    lockfile or a source module has no test to run, and says so by returning None.
    """
    path_part, _, func = witness.partition("::")
    if func:
        return f"{path_part}::{func}" if path_part.endswith(".py") else None
    return path_part if _TEST_MODULE.search(path_part) else None


def _module_path(node_id: str) -> str:
    """``tests/test_rates.py::test_x`` -> ``tests.test_rates`` (a junit classname)."""
    path_part = node_id.partition("::")[0]
    return path_part.removesuffix(".py").replace("/", ".")


def _parse_report(xml: str) -> list[tuple[str, str, str]]:
    """(classname, name, outcome) for every testcase in a pytest junit report.

    ``skipped`` covers both an actual skip and an xfail: pytest records both with a
    ``<skipped>`` child. Neither is evidence that a claim holds, so neither counts.
    """
    outcomes: list[tuple[str, str, str]] = []
    for case in ElementTree.fromstring(xml).iter("testcase"):
        outcome = "passed"
        for child in case:
            if child.tag in {"failure", "error", "skipped"}:
                outcome = child.tag
                break
        outcomes.append((case.get("classname", ""), case.get("name", ""), outcome))
    return outcomes


def _run_witnesses(node_ids: list[str]) -> list[str]:
    """Execute the witness tests; return one error per witness that did not pass."""
    if not node_ids:
        return []
    with tempfile.TemporaryDirectory() as tmp:
        report = Path(tmp) / "witnesses.xml"
        completed = subprocess.run(  # fixed argv, no shell, repo-local
            [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                "--no-header",
                "-p",
                "no:cacheprovider",
                f"--junitxml={report}",
                *node_ids,
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        if not report.is_file():
            tail = (completed.stdout + completed.stderr).strip().splitlines()[-10:]
            return [
                "could not run the witness tests — a witness that cannot be executed is "
                "not a witness. pytest exited "
                f"{completed.returncode}:\n      " + "\n      ".join(tail)
            ]
        outcomes = _parse_report(report.read_text(encoding="utf-8"))

    errors: list[str] = []
    for node_id in node_ids:
        module = _module_path(node_id)
        func = node_id.partition("::")[2]
        matched = [
            (name, outcome)
            for classname, name, outcome in outcomes
            if (classname == module or classname.startswith(f"{module}."))
            and (not func or name == func or name.startswith(f"{func}["))
        ]
        if not matched:
            errors.append(
                f"witness {node_id!r} was not collected by pytest — it exists in the file "
                "but nothing runs it"
            )
            continue
        for name, outcome in matched:
            if outcome != "passed":
                errors.append(
                    f"witness {node_id!r} does not pass: {module}::{name} {outcome}"
                    + (
                        " (a skipped or xfailed witness proves nothing)"
                        if outcome == "skipped"
                        else ""
                    )
                )
    return errors


def _default_docs() -> list[str]:
    """Every root-level and ``docs/`` Markdown file, as repo-relative POSIX paths."""
    found = {p.relative_to(ROOT).as_posix() for p in ROOT.glob("*.md")}
    found |= {p.relative_to(ROOT).as_posix() for p in (ROOT / "docs").rglob("*.md")}
    return sorted(found)


def _site_linked_docs() -> tuple[list[str], list[str]]:
    """Docs the shipped HTML links to, plus an error for any that does not resolve."""
    errors: list[str] = []
    linked: set[str] = set()
    for glob in SITE_HTML_GLOBS:
        for page in sorted(ROOT.glob(glob)):
            html = page.read_text(encoding="utf-8")
            for pattern in _DOC_LINKS:
                for rel in pattern.findall(html):
                    if (ROOT / rel).is_file():
                        linked.add(rel)
                    else:
                        errors.append(
                            f"{page.relative_to(ROOT).as_posix()}: links to {rel}, which does "
                            "not exist in this repository"
                        )
    return sorted(linked), errors


def _find_duplicates(rows: list[dict[str, str]]) -> list[str]:
    errors: list[str] = []
    seen: set[str] = set()
    for row in rows:
        cid = row["claim"]
        if cid in seen:
            errors.append(f"docs/CLAIMS.md: claim {cid!r} listed more than once")
        seen.add(cid)
    return errors


def _scan_docs(doc_rel: list[str]) -> tuple[dict[str, set[str]], list[str]]:
    """Matched claim tags per doc, scanning every doc in ``doc_rel``."""
    errors: list[str] = []
    doc_tags: dict[str, set[str]] = {}
    for rel in doc_rel:
        path = ROOT / rel
        if not path.exists():
            errors.append(f"docs/CLAIMS.md references a doc that does not exist: {rel}")
            doc_tags[rel] = set()
            continue
        matched, tag_errors = _tag_pairs(path.read_text(encoding="utf-8"), rel)
        errors.extend(tag_errors)
        doc_tags[rel] = matched
    return doc_tags, errors


def _cross_check(
    rows: list[dict[str, str]], doc_tags: dict[str, set[str]], manifest_ids: set[str]
) -> list[str]:
    """Manifest<->docs<->tree parity errors in both directions."""
    errors: list[str] = []

    # Manifest -> docs: each claim's tag pair must live in its named doc.
    # Manifest -> tree: witness must be real.
    for row in rows:
        cid, rel = row["claim"], row["doc"]
        if cid not in doc_tags.get(rel, set()):
            errors.append(
                f"docs/CLAIMS.md: claim {cid!r} is not a matched <!-- claim:{cid} --> pair in {rel}"
            )
        wit_err = _witness_ok(row["witness"])
        if wit_err:
            errors.append(f"docs/CLAIMS.md: claim {cid!r}: {wit_err}")

    # Docs -> manifest: every tagged claim in any scanned doc must be listed.
    for rel, tags in doc_tags.items():
        for cid in sorted(tags - manifest_ids):
            errors.append(
                f"{rel}: claim {cid!r} is tagged in the doc but missing from docs/CLAIMS.md"
            )

    return errors


def main() -> int:
    if not MANIFEST.exists():
        print(f"claims parity FAILED: manifest missing: {MANIFEST}", file=sys.stderr)
        return 1

    rows, errors = _parse_manifest(MANIFEST.read_text(encoding="utf-8"))

    if not rows and not errors:
        errors.append("docs/CLAIMS.md: no claim rows found in the manifest table")

    errors.extend(_find_duplicates(rows))
    manifest_ids = {row["claim"] for row in rows}

    # Which doc files to scan for tags: every root-level and docs/ Markdown file,
    # every doc the shipped HTML links to, and everything the manifest points at.
    linked, link_errors = _site_linked_docs()
    errors.extend(link_errors)
    doc_rel = sorted({*_default_docs(), *linked, *(row["doc"] for row in rows)})
    doc_tags, scan_errors = _scan_docs(doc_rel)
    errors.extend(scan_errors)

    # A doc the live site links to must be in the scanned set. This is structurally
    # true above; asserting it keeps a future refactor from quietly re-narrowing the
    # scan to the three files it used to read.
    for rel in linked:
        if rel not in doc_tags:
            errors.append(f"a doc the site links to is not scanned for claim tags: {rel}")

    errors.extend(_cross_check(rows, doc_tags, manifest_ids))

    # Run the witnesses. A witness that only exists is not a witness.
    node_ids = sorted({node for row in rows if (node := _node_id(row["witness"]))})
    errors.extend(_run_witnesses(node_ids))

    if errors:
        print("claims parity FAILED:", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1
    unrunnable = sorted({row["witness"] for row in rows if not _node_id(row["witness"])})
    print(
        f"claims parity OK: {len(rows)} claims, manifest<->docs<->tree parity holds "
        f"(scanned {len(doc_rel)} docs, {len(linked)} of them linked from the shipped HTML; "
        f"ran {len(node_ids)} witness tests, all passed)."
    )
    if unrunnable:
        # Stated, not hidden: these claims rest on a file existing, which is weaker
        # evidence than a passing test, and a reader of this gate should know which.
        print(
            f"claims parity NOTE: {len(unrunnable)} witness(es) name no test and were checked "
            "for existence only — existence is not a pass: " + ", ".join(unrunnable)
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
