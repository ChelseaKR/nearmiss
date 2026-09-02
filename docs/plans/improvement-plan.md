# Improvement plan and running log

Working document for an audit-and-repair pass over `nearmiss`. Nothing in this pass is
committed: the owner withheld commit permission, so every change below lives in the
working tree only. This file is the durable record of what was done and why.

Read at local `main` = `4991ad9` (`origin/main` is 2 commits ahead: `fa6a6a6` #210 and
`9baca50` #211, both statistical-integrity work; HEAD is deliberately not moved).

## Governing rule for this pass

A check that cannot fail is worse than no check. Every guard touched here is broken on
purpose, watched to fail, restored, and watched to pass. Both directions are recorded.

## Status

| Phase | Item | State |
|---|---|---|
| 0 | Read 9 issues, 8 PRs, 2 CI failures | done |
| 1 | `make security` swallows gitleaks/zizmor failures | done |
| 2 | `make conformance` overclaims "all published datasets" (#156) | done |
| 3 | Atlas/Studio `<noscript>` degradation (#157) | done |
| 4 | Studio "Permitted claim" asserts an uncomputed rate (#155) | done |
| 5 | Dependabot pip PRs cannot pass the CQ-09 lock gate | done |
| 6 | Documentation and issue-hygiene corrections (#183, #186) | done |

## Log

(appended as work proceeds)

### Phase 1 — `make security` could not fail (done)

`Makefile` invoked both optional scanners as `command -v tool && tool ... || echo "not
found"`. A finding takes the `||` branch, so a non-zero scanner exit printed "not found"
and the recipe exited 0.

Measured before the fix, with stub scanners that exit 1:

```
STUB gitleaks: pretending to find a committed secret
security: gitleaks not found (it is a Go binary, not a pip dep); ...
STUB zizmor: pretending to find a high-severity workflow finding
security: zizmor not found (pip install zizmor, ...)
EXIT=0
```

After the fix, same stubs: `security: gitleaks FAILED (exit 1) — that is a finding, not
a missing tool.` and `EXIT=2`. With the real scanners installed: `EXIT=0`. With neither
on `PATH`: `EXIT=0` and two explicit `SKIPPED — not installed ... No secret scan ran
here` lines; with `SECURITY_REQUIRE_SCANNERS=1`, `EXIT` non-zero.

Guards added: `tests/test_gate_recipes.py` executes the real recipe lines from
the Makefile against stub scanners (8 tests when added; 6 fail against the pre-fix
Makefile), and
`tests/test_makefile_gates.py` gains a swallow detector plus its own witnesses.

### Phase 2 — `make conformance` audited 2 of 10 published artifacts (done, #156)

The target ran `verify_dataset.py` on two retired-demo paths and echoed "all published
datasets pass HR1-HR5". Unaudited: six FARS state-mode artifacts (the only real data
published) and two `<slug>.corridors.geojson` views carrying `rate`, `rate_ci_low/high`,
`n` and exposure provenance.

Added two artifact families to `tools/verify_dataset.py` and an enumerating
`tools/conformance_sweep.py` that fails on any published file it cannot classify.
Audited count: 2 -> 10.

Demonstrated: with one suppressed FARS cell restored at `crash_count=4` under a declared
`k=10`, the old recipe exits 0 and prints "all published datasets pass HR1-HR5"; the new
gate exits non-zero naming `AL/other_road_user`. Restored, both exit 0 and
`git status --porcelain data/published/` is empty.

### Phase 3 — the atlas said "Loading…" forever without JavaScript (done, #157)

Added a `<noscript>` stylesheet in `<head>` and a `<noscript>` fallback in `<main>` for
`web/us-coverage.html` and `web/studio.html`. The atlas fallback links every artifact the
current release index binds, plus the index and the correction ledger, and states the
`suppressed_or_zero` reading rule; the studio fallback says both tools run in the browser
and never upload the file, and its two forms are hidden rather than left inert.

`tests/test_noscript_degradation.py` derives the placeholders from the markup rather than
listing them: 7 failed against the pre-fix HTML, 9 pass after. Removing one selector from
the noscript stylesheet makes `test_every_atlas_loading_placeholder_is_hidden_without_script`
fail and name the two uncovered elements.

The issue's smaller ask — a distinct "unavailable" state on fetch failure — turned out to
be already implemented: `showError()` in `web/us-coverage.js` writes `load_error` into the
ledger body and `caption_error` into the caption. The real gap was only the static shell.

### Phase 4 — the Studio asserted an elevated rate nothing computed (done, #155)

Reproduced the issue's measurement exactly (ten rows all at 0,0, one shared date, two
ticked declarations):

```
BEFORE  CLAIM : The observed report rate at Main Street is elevated in the stated
                observation window.
AFTER   CLAIM : If the declared exposure denominator is temporally and spatially aligned
                with these reports, they can support a statement that the observed report
                rate at Main Street is elevated in the stated observation window — after
                the interval and sensitivity checks in docs/METHODOLOGY.md are run and pass.
        BASIS : Basis: 10 rows with a usable location and date, plus two unverified
                declarations on this page (an aligned exposure denominator, and a completed
                human data-quality review). No rate, denominator, interval, or comparison
                was computed here.
```

The basis now renders under the claim and leads the copied text. `web/workflow_check.mjs`
fails against the pre-fix `studio.js` ("tier 2 claim asserts a result this page never
computed") and passes after.

### Phase 5 — Dependabot's Python PRs cannot go green unaided (done)

Not a flake and not a repo bug: `versioning-strategy: increase` rewrites
`pyproject.toml`'s specifiers, and the `pip` ecosystem does not maintain `uv.lock` or
re-resolve `requirements-dev.lock`. Both gates then fire correctly — CQ-09
(`uv lock --check`) on #203/#204/#206, and additionally `tests/test_lock_drift.py` on
#205 ("packaging: pyproject.toml requires >=26.3, requirements-dev.lock pins 26.2").

`make lock-check` now explains the remediation on failure, reproduced by simulating the
ruff bump. The standing decision, including why `package-ecosystem: "uv"` is not taken
yet, is recorded in `.github/dependabot.yml`.

### Phase 6 — documentation defects (done, #186, #182, #183)

* `publication_status` / `publication_note` are now required, closed-vocabulary fields on
  every source crosswalk. SimRa is `research_only`, BikeMaps is `undetermined`.
  `docs/DATA-CARD.md` quotes the manifests and `tests/test_source_publication_status.py`
  fails on drift in either direction.
* `docs/ADAPTING.md` gains § 0: the binding constraint is sourcing, not adapter count.
* The county drill-down is declared dormant under the `county-drilldown-dormant` claim,
  with a `DORMANT:` paragraph in all seven modules and three tools, and a witness test
  that fails if any of them becomes reachable.
* CQ-34's blind spot is now stated in `tools/check_debt_markers.py`: it cannot tell that
  `TODO(#184)` points at a closed, unrelated issue. README and ROADMAP corrected.

### Phase 7 — two gates that could not fire (done, found during this pass)

* `tests/test_packaged_schema.py`'s skip guard was `pytest.importorskip("build")`, and
  this repository's own output directory is `build/`, which Python imports as a namespace
  package. `make verify` was green on a clean checkout and red on the next run of the same
  command, and the wheel-contents assertion had never actually run locally.
* `docs/ACCESSIBILITY.md` § 7 listed "a contrast regression" among the things that fail
  the build, while `color-contrast` is disabled in every axe run and nothing else computes
  it. § 6.1 of the same file said so correctly.

## Final state

`make verify PYTHON=.venv/bin/python < /dev/null; echo "EXIT=$?"` run twice in a row,
both `EXIT=0`. Second run matters: before the `build/` namespace-package fix, the second
consecutive run of the same command failed.

```
1988 passed, 1 skipped in 117.50s
Required test coverage of 90% reached. Total coverage: 90.21%
security: gitleaks ran over the committed history and reported nothing.
security: zizmor ran over .github/workflows/ and reported nothing at high severity.
claims parity OK: 14 claims, manifest<->docs<->tree parity holds
conformance: 10 published artifacts audited against HR1-HR5 across 3 families
verify: all merge gates green
```

Baseline for comparison: 1901 passed, coverage 90.19%, conformance auditing 2 artifacts.

`HEAD` is unmoved at `4991ad9`; every change is uncommitted working tree.
`git status --porcelain data/published/` is empty, so no published artifact was altered.

## Not done, and why

* **Landing the county pilot (#182, option one).** Blocked on a human step: the manual
  crosswalk review in `docs/PRIVATE-COUNTY-CROSSWALK-REVIEW.md` and private FARS data
  this environment does not have. Option two (declare it dormant) was executed instead.
* **Switching Dependabot to `package-ecosystem: "uv"`.** Would remove the follow-up
  commit on Python bumps, but it also stops maintaining `requirements-dev.lock`, and the
  change is only observable on the next scheduled Dependabot run. Recorded as a decision
  in `.github/dependabot.yml` rather than made blind.
* **Rebasing #212 and #213.** Both are `DIRTY` against `main` after #210 and #211 landed,
  and their descriptions still say they are stacked on branches that merged. Rebasing
  moves HEAD; out of scope for this pass.
* ~~**Opening a tracking issue for the DOI.**~~ **Closed.** #227 is open and about the
  DOI; `CITATION.cff:68` now reads `TODO(#227)`. README, ROADMAP and
  `tools/check_debt_markers.py`'s docstring are updated. The *class* of defect — a marker
  whose referenced issue is closed or unrelated — is still invisible to CQ-34, which is
  offline by design; that limit stays stated rather than fixed.
* **Putting the #186 sourcing text into the issue bodies of #161 and #162.** Same reason:
  it is a GitHub write. The text is in `docs/ADAPTING.md` § 0, which both issues link to.
* ~~**`mypy --strict` over `tools/`.**~~ **Closed.** `pyproject.toml` now sets
  `files = ["src", "tests", "tools"]`. Re-measured on the merged tree the cost was 97
  errors across 21 files, of which 39 were a single missing `src/nearmiss/py.typed`:
  without it every `tools/` script importing the package got `Any` back from every call,
  so the scripts could have been listed in `files` and still not really checked.
  (`src/honest_rates/py.typed` had shipped since EXP-08; `nearmiss`'s never did.) The
  remaining 58 were real: bare `dict`/`tuple`/`frozenset` generics, `Any` leaking out of
  `json.load` through a typed return, and — the ones worth the pass on their own —
  eighteen reported arithmetic/comparison errors at twelve places in
  `tools/verify_dataset.py` and `tools/diff_datasets.py` where a missing
  JSON field arrives as `None` and reaches `<`, `>` or `+`. Those raise `TypeError` inside
  the verifier whose job is to report the defect. `_is_number`/`_is_int` are now
  `TypeGuard`s, so the checker proves each comparison is reached only with a real number.
  `tests/test_type_gate_scope.py` is the witness: it fails if `tools` leaves `files`, if
  the strictness flags are relaxed, or if either `py.typed` marker goes missing.
