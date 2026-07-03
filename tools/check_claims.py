#!/usr/bin/env python3
"""Claims-parity drift gate (merge-blocking).

Enforces the accuracy-claims manifest ``docs/CLAIMS.md`` against the docs and the
tree, in both directions, so a doc claim can never drift away from the code that
backs it (or from the honest "planned, not implemented" wording it stands in for):

* **Manifest -> docs** — every claim ID in the manifest table appears as a
  *matched* ``<!-- claim:ID -->`` … ``<!-- /claim:ID -->`` comment pair in the
  doc file named in its anchor column.
* **Manifest -> tree** — every witness path exists; a ``path::test_name`` witness
  names a function (``def test_name``) that exists in that file.
* **Docs -> manifest** — every ``<!-- claim:… -->`` tag found in any scanned doc
  (README, METHODOLOGY, CHANGELOG, plus every doc referenced by the manifest) is
  listed in the manifest. A tagged claim missing from the table fails the build,
  as does an unmatched open/close tag.

Pure standard library; no network, deterministic. Style mirrors
``tools/check_catalog_parity.py``.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "docs" / "CLAIMS.md"

# Docs always scanned for tags (Docs -> manifest drift), on top of every doc the
# manifest itself references.
DEFAULT_DOCS = ("README.md", "docs/METHODOLOGY.md", "CHANGELOG.md")

_OPEN = re.compile(r"<!--\s*claim:([A-Za-z0-9._-]+)\s*-->")
_CLOSE = re.compile(r"<!--\s*/claim:([A-Za-z0-9._-]+)\s*-->")
_BACKTICK = re.compile(r"`([^`]+)`")


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


def _tag_pairs(text: str, where: str) -> tuple[set[str], list[str]]:
    """Matched claim IDs in a doc; errors for any unmatched open/close tag."""
    errors: list[str] = []
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


def main() -> int:
    errors: list[str] = []

    if not MANIFEST.exists():
        print(f"claims parity FAILED: manifest missing: {MANIFEST}", file=sys.stderr)
        return 1

    rows, parse_errors = _parse_manifest(MANIFEST.read_text(encoding="utf-8"))
    errors.extend(parse_errors)

    if not rows and not parse_errors:
        errors.append("docs/CLAIMS.md: no claim rows found in the manifest table")

    # Duplicate claim IDs in the manifest.
    seen: set[str] = set()
    for row in rows:
        cid = row["claim"]
        if cid in seen:
            errors.append(f"docs/CLAIMS.md: claim {cid!r} listed more than once")
        seen.add(cid)
    manifest_ids = seen

    # Which doc files to scan for tags: the defaults plus everything the manifest
    # points at.
    doc_rel = sorted({*DEFAULT_DOCS, *(row["doc"] for row in rows)})
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

    # Manifest -> docs: each claim's tag pair must live in its named doc.
    for row in rows:
        cid, rel = row["claim"], row["doc"]
        if cid not in doc_tags.get(rel, set()):
            errors.append(
                f"docs/CLAIMS.md: claim {cid!r} is not a matched <!-- claim:{cid} --> pair in {rel}"
            )
        # Manifest -> tree: witness must be real.
        wit_err = _witness_ok(row["witness"])
        if wit_err:
            errors.append(f"docs/CLAIMS.md: claim {cid!r}: {wit_err}")

    # Docs -> manifest: every tagged claim in any scanned doc must be listed.
    for rel, tags in doc_tags.items():
        for cid in sorted(tags - manifest_ids):
            errors.append(
                f"{rel}: claim {cid!r} is tagged in the doc but missing from docs/CLAIMS.md"
            )

    if errors:
        print("claims parity FAILED:", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1
    print(
        f"claims parity OK: {len(rows)} claims, manifest<->docs<->tree parity holds "
        f"(scanned {len(doc_rel)} docs)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
