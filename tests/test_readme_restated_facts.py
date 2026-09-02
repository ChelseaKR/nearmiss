"""README sentences that restate a fact living somewhere else in the tree.

A restated fact is a copy, and a copy drifts. Four of them had:

* **Supported versions.** `README.md` § Security said "the latest released `0.1.x` minor
  line". `SECURITY.md`'s table is generic -- ``Latest released `MINOR` (e.g. `0.1.x`)`` --
  so the README had promoted the *example* to the *fact*, and then v0.2.0, v0.3.0, v0.3.1
  and v0.4.0 shipped (`git tag --sort=-v:refname`; `pyproject.toml` `version = "0.4.0"`).
  The fix is not to type `0.4.x`, which resets the same clock: the sentence now names no
  version at all and points at `SECURITY.md`, and this module holds it to that.
* **"the other ten standards."** The standards-conformance table has fifteen rows, so the
  cross-reference under § Observability was off by four. The count is derived here from
  the table itself.
* **A "planned" hashed lockfile.** § Install (claim `lockfile-committed-hashed`) said both
  locks are committed and hashed; the resilience paragraph 200 lines later still called
  `requirements.lock` "planned". Both files are committed and carry `--hash=sha256:` pins.
* **"four blocking CI gates"** for i18n, where `make i18n` runs six. An undercount is the
  rarer direction and just as wrong; the count is derived here from the Makefile recipe,
  and a seventh gate added to that recipe fails this module until the README names it.

Same shape as `tests/test_lock_drift.py` and `tests/test_doc_audit.py`: the committed state
must pass, and each check must be one that can actually fail -- a figure nothing recomputes
is a figure nobody is checking.

Every claim here is tagged in the doc with a matched ``<!-- claim:ID -->`` pair and listed
in `docs/CLAIMS.md`, so `make claims` runs these tests as the witnesses.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
SECURITY = ROOT / "SECURITY.md"
MAKEFILE = ROOT / "Makefile"
CI_WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"

#: Spelled-out cardinals, for prose that counts something the tree defines. Wide enough
#: that adding a standard or a gate changes the expected word rather than exhausting the map.
CARDINALS = {
    1: "one",
    2: "two",
    3: "three",
    4: "four",
    5: "five",
    6: "six",
    7: "seven",
    8: "eight",
    9: "nine",
    10: "ten",
    11: "eleven",
    12: "twelve",
    13: "thirteen",
    14: "fourteen",
    15: "fifteen",
    16: "sixteen",
    17: "seventeen",
    18: "eighteen",
    19: "nineteen",
    20: "twenty",
}

#: `0.4.0`, `0.1.x`, `v1.2.3` -- any pinned release line written into prose.
VERSION_LITERAL = re.compile(r"\bv?[0-9]+\.[0-9]+\.(?:[0-9]+|x)\b")

#: The two committed lockfiles, named the way prose names them.
LOCKFILES = ("requirements.lock", "requirements-dev.lock")

#: Wording that describes a lockfile as not-yet-real. The defect this catches shipped as
#: "with a generated hashed `requirements.lock` planned".
STALE_LOCK_WORDING = re.compile(
    r"\b(planned|not committed|not yet committed|generated but not committed|"
    r"is not yet present|remains? planned)\b",
    re.IGNORECASE,
)


def claim_region(text: str, claim_id: str) -> str:
    """The text between a matched ``<!-- claim:ID --> … <!-- /claim:ID -->`` pair.

    `tools/check_claims.py` only checks that the pair *exists*; what it wraps is for a
    human. These tests read the region, so the tag also delimits the sentence under test.
    """
    pattern = re.compile(
        rf"<!--\s*claim:{re.escape(claim_id)}\s*-->(.*?)<!--\s*/claim:{re.escape(claim_id)}\s*-->",
        re.DOTALL,
    )
    match = pattern.search(text)
    assert match is not None, f"no matched <!-- claim:{claim_id} --> pair found"
    return match.group(1)


def standards_table_rows(text: str) -> list[str]:
    """The data rows of the first Markdown table under `## Standards conformance`."""
    lines = text.splitlines()
    start = next(
        i for i, line in enumerate(lines) if line.strip().lower() == "## standards conformance"
    )
    rows: list[str] = []
    in_table = False
    for line in lines[start + 1 :]:
        stripped = line.strip()
        if stripped.startswith("|"):
            in_table = True
            cells = [c.strip() for c in stripped.strip("|").split("|")]
            if any(c.lower() == "standard" for c in cells):
                continue  # header
            if all(set(c) <= {"-", ":", " "} for c in cells):
                continue  # separator
            rows.append(stripped)
        elif in_table:
            break
    return rows


def recipe_lines(makefile_text: str, target: str) -> list[str]:
    """One target's recipe commands, continuations joined, comments and `@echo` dropped.

    `@echo` is a report, not a check: it cannot fail the gate, so it is not one of the
    gates the README counts.
    """
    lines = makefile_text.splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith(f"{target}:"))
    commands: list[str] = []
    pending: list[str] = []
    for raw in lines[start + 1 :]:
        if not raw.startswith("\t"):
            if raw.strip() == "":
                continue
            break
        command = raw[1:].strip()
        if command.endswith("\\"):
            pending.append(command[:-1].strip())
            continue
        pending.append(command)
        commands.append(" ".join(pending))
        pending = []
    return [c for c in commands if not c.startswith("#") and not c.startswith("@echo")]


#: Each merge-blocking gate `make i18n` runs: the README's name for it, and the recipe
#: commands that implement it. Several commands can make up one gate (the POT gate is an
#: extract, a normalize and a `git diff --exit-code`; `msgfmt` runs once per catalog), so
#: this maps commands to gates rather than counting command lines.
I18N_GATES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "POT drift",
        (r"babel\.messages\.frontend extract", r"i18n_normalize_pot\.py", r"git diff --exit-code"),
    ),
    ("`msgfmt --check`", (r"\bmsgfmt --check\b",)),
    ("EN/ES parity", (r"tools/check_catalog_parity\.py",)),
    ("web-JSON drift", (r"tools/po2json\.py --check",)),
    ("BCP-47 validity", (r"tools/check_bcp47\.py",)),
    ("pseudo-locale no-bypass gate", (r"\$\(MAKE\) i18n-pseudo",)),
)


def i18n_gates_in_the_recipe() -> tuple[list[str], list[str]]:
    """(gates `make i18n` actually runs, recipe commands no known gate accounts for)."""
    commands = recipe_lines(MAKEFILE.read_text(encoding="utf-8"), "i18n")
    seen: list[str] = []
    unaccounted: list[str] = []
    for command in commands:
        matched = [
            name for name, patterns in I18N_GATES if any(re.search(p, command) for p in patterns)
        ]
        if not matched:
            unaccounted.append(command)
            continue
        for name in matched:
            if name not in seen:
                seen.append(name)
    return seen, unaccounted


# ---------------------------------------------------------------------------
# Guard the guards: an empty parse would make every assertion below vacuous.
# ---------------------------------------------------------------------------


def test_the_parsers_actually_read_this_repositorys_files() -> None:
    rows = standards_table_rows(README.read_text(encoding="utf-8"))
    assert len(rows) > 5, f"only {len(rows)} standards rows parsed out of README.md"
    assert any("Internationalization" in row for row in rows)

    commands = recipe_lines(MAKEFILE.read_text(encoding="utf-8"), "i18n")
    assert len(commands) > 3, f"only {len(commands)} recipe commands parsed out of `make i18n`"
    assert any("check_bcp47.py" in command for command in commands)


# ---------------------------------------------------------------------------
# The claims
# ---------------------------------------------------------------------------


def test_the_supported_version_line_is_not_restated_as_a_literal() -> None:
    """Witness for `supported-versions-not-restated`.

    `SECURITY.md` is the policy and states the supported channel by shape; the README
    points at it. A concrete version written back into this sentence is the defect,
    whatever the number is -- `0.4.x` typed today is stale at 0.5.0.
    """
    region = claim_region(README.read_text(encoding="utf-8"), "supported-versions-not-restated")

    found = VERSION_LITERAL.findall(region)
    assert found == [], (
        "README.md § Security names a specific version line "
        f"({', '.join(found)}); that number goes stale at the next minor release, which is "
        "how it came to read `0.1.x` at v0.4.0. State the policy by shape and point at "
        "SECURITY.md instead."
    )
    assert "SECURITY.md#supported-versions" in region, (
        "the sentence has to point somewhere, or removing the number just removes the answer"
    )
    assert "## Supported versions" in SECURITY.read_text(encoding="utf-8"), (
        "README.md links SECURITY.md#supported-versions, which no longer exists"
    )


def test_the_standards_cross_reference_counts_the_standards_table() -> None:
    """Witness for `standards-table-cross-reference`.

    § Observability points at the standards table for "the other N standards". N is the
    table's row count minus the Observability row itself, so it moves whenever a standard
    is added, and this recomputes it rather than trusting the prose.
    """
    text = README.read_text(encoding="utf-8")
    others = len(standards_table_rows(text)) - 1  # every row but Observability's own
    expected = f"the other {CARDINALS[others]} standards"

    region = claim_region(text, "standards-table-cross-reference")
    assert expected in " ".join(region.split()), (
        f"the standards table has {others + 1} rows, so § Observability should say "
        f"{expected!r}; it says: {' '.join(region.split())!r}"
    )


def test_the_readme_never_calls_the_committed_hashed_lock_planned() -> None:
    """Witness for `vuln-management-hashed-locks`.

    Both locks are committed and hashed, and § Install (claim `lockfile-committed-hashed`)
    says so. The resilience paragraph said the opposite about the same file. One README
    cannot hold both, so no sentence in it may describe a committed lock as planned.
    """
    for name in LOCKFILES:
        path = ROOT / name
        assert path.is_file(), f"{name} is not committed, but the README says it is"
        assert "--hash=sha256:" in path.read_text(encoding="utf-8"), (
            f"{name} carries no `--hash=sha256:` pins, so it is not a hashed lock"
        )

    text = README.read_text(encoding="utf-8")
    sentences = re.split(r"(?<=[.:])\s", " ".join(text.split()))
    offenders = [
        sentence
        for sentence in sentences
        if any(lock in sentence for lock in LOCKFILES) and STALE_LOCK_WORDING.search(sentence)
    ]
    assert offenders == [], (
        "README.md describes a committed, hashed lockfile as not yet real:\n  "
        + "\n  ".join(offenders)
    )

    region = claim_region(text, "vuln-management-hashed-locks")
    assert "--require-hashes" in region
    hashed_install = "python -m pip install --require-hashes -r requirements-dev.lock"
    assert hashed_install in CI_WORKFLOW.read_text(encoding="utf-8"), (
        "the README claims CI installs with --require-hashes; ci.yml no longer does"
    )


def test_the_i18n_gate_count_matches_what_make_i18n_runs() -> None:
    """Witness for `i18n-gate-count`.

    The standards table named four gates where the recipe runs six -- an undercount, which
    understates the work but is drift all the same. Both halves are checked: the README
    names every gate the recipe runs, and the recipe runs no gate the README does not name.
    """
    seen, unaccounted = i18n_gates_in_the_recipe()
    assert unaccounted == [], (
        "`make i18n` runs a check this test does not know about, so the README's gate list "
        "cannot be trusted to be complete. Add it to I18N_GATES and name it in README.md "
        "§ Standards conformance:\n  " + "\n  ".join(unaccounted)
    )
    missing_from_recipe = [name for name, _ in I18N_GATES if name not in seen]
    assert missing_from_recipe == [], (
        "the README names a gate `make i18n` no longer runs: " + ", ".join(missing_from_recipe)
    )

    region = " ".join(claim_region(README.read_text(encoding="utf-8"), "i18n-gate-count").split())
    expected = f"{CARDINALS[len(seen)]} merge-blocking gates"
    assert expected in region, (
        f"`make i18n` runs {len(seen)} merge-blocking gates, so the README should say "
        f"{expected!r}; it says: {region!r}"
    )
    for name, _ in I18N_GATES:
        assert name in region, f"README.md does not name the {name!r} gate that `make i18n` runs"
