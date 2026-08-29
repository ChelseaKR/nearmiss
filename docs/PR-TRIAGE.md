# Pull-request triage

Snapshot of the open pull-request queue, taken 2026-08-28 against `main` at
`9baca50`. Every merge state, CI result, and conflict claim below was checked
locally against the fetched refs rather than read off the GitHub page, because a
pull request's mergeability badge and its check results are computed at different
times and can disagree.

There are **nine** open pull requests, all based on `main`.

## How to read the CI column

`main` is protected by the `protect-main` ruleset. Ten checks are required:

```
security (pip-audit + gitleaks + CodeQL)      test (pytest, known-answer fixtures) (3.11)
accessibility (structural WCAG gate + axe)    test (pytest, known-answer fixtures) (3.12)
reproducibility (make reproduce + diff)       i18n (gettext catalog gate)
zizmor (GitHub Actions workflow SAST)         type (mypy --strict)
teaching (execute EXP-12 heat-map notebooks)  lint (ruff)
```

`dco`, `claims`, `qgis-plugin`, and `build minimal public artifact` run on every
pull request but are **not** required. That distinction is the whole explanation
for why one pull request here reports `UNSTABLE` rather than `BLOCKED`.

The ruleset sets `strict_required_status_checks_policy: false`, so a branch does
not have to be current with `main` to merge. A green tick therefore only means
"green against `main` as it stood when the job ran". All six Dependabot branches
below are **three commits behind `main`**, cut at `7bd6d8c` (#191), before #209,
#210 and #211 landed, and their checks ran on 2026-08-24.

Because that staleness could hide a changed answer, the lock gates were re-run
locally against **today's** `main` with each bump applied. The results below are
reproduced, not inherited.

## Summary

| PR | Base | Real merge state | CI reality | Recommendation |
| --- | --- | --- | --- | --- |
| #214 | `main` | Merges clean, current with `main` | Only `dco` red, and `dco` is not required | `needs work` |
| #213 | `main` | Conflicting, but a rebase clears it | Never ran, starved by the conflict | `merge after rebase` |
| #212 | `main` | Conflicting, but a rebase clears it | Never ran, starved by the conflict | `merge after rebase` |
| #207 | `main` | Clean | All required checks green | `merge` |
| #206 | `main` | Blocked | `lint` red, born red, not its fault | `needs work` |
| #205 | `main` | Blocked | `lint` and both `test` jobs red, born red | `needs work` |
| #204 | `main` | Blocked | `lint` red, born red, not its fault | `needs work` |
| #203 | `main` | Blocked | `lint` red, born red, not its fault | `needs work` |
| #202 | `main` | Clean | All required checks green | `merge` |

Group counts: 2 ready to merge, 2 mergeable after a rebase, 5 needing a commit
that does not exist yet. Nothing here is a duplicate and nothing is superseded.

## The stack

#212 and #213 are a real stack, not two independent branches.

```
origin/main (9baca50)
  |
  |  ... the branches were cut at 4991ad9 (#209), before #210 and #211
  |      were squash-merged onto main
  |
  +-- #212  feat/dependence-robust-fdr
  |     eeaee62  (already on main as fa6a6a6, PR #210)
  |     7bd1e3b  (already on main as 9baca50, PR #211)
  |     de66e02  <- the only genuinely new commit
  |
  +-- #213  feat/empirical-bayes-stability   (contains all of #212)
        eeaee62  (already on main)
        7bd1e3b  (already on main)
        de66e02  <- #212's commit
        6a63fd0  <- new
        29c2a31  <- new
```

`git merge-base --is-ancestor origin/feat/dependence-robust-fdr
origin/feat/empirical-bayes-stability` returns true, so **#213 is a strict
superset of #212**.

Two consequences that matter for sequencing:

1. **Merging #213 first would silently deliver #212.** Because this repository
   squash-merges, #212 would then **not** auto-close. It would sit open, still
   showing a diff, while every line of it was already on `main`. Merge #212
   first so that each pull request closes on its own merge.
2. **Neither pull request would auto-close if the other's branch were merged and
   deleted**, for the same squash-merge reason. No pull request in this queue
   auto-closes as a side effect of another.

### Why they are `DIRTY`, and why it is not a real conflict

`git merge-tree --write-tree` reports fifteen conflicting files for both
branches, including `CHANGELOG.md`, `src/nearmiss/publish.py`,
`src/nearmiss/brief.py`, `src/nearmiss/figures.py`,
`src/nearmiss/stats/__init__.py`, `schema/dataset.schema.md`,
`docs/DOCUMENTATION-AUDIT.md`, `docs/STATISTICAL-INTEGRITY-PROGRAM.md`
(add/add), `data/published/davis-ranked.md`,
`data/published/riverside-ranked.md`, and the six gettext catalogue files under
`src/nearmiss/locales/`.

None of that is a genuine disagreement about content. The branches still carry
the pre-squash commits for #210 and #211, which `main` already has in squashed
form. `git cherry origin/main` marks both with `-`, meaning patch-equivalent.
The conflict is the same change meeting itself.

Verified by doing it: rebasing each branch onto `origin/main` succeeds with no
conflicts and drops the duplicates automatically.

- `#212` rebases to **one** commit, 23 files, +921/-12.
- `#213` rebases to **three** commits; after #212 lands it rebases to **two**
  commits, 23 files, +1160/-28.

### Why they have no CI at all

`gh pr checks` reports `no checks reported on the branch` for both. This is not
a starved queue or a cancelled run. Workflows here trigger on `pull_request`,
which runs against the `refs/pull/N/merge` ref, and GitHub cannot construct that
ref while the merge conflicts. The conflict is the reason the checks never ran,
so **both pull requests are untested through no fault of their own**, and both
become testable the moment they are rebased.

## Per pull request

### #214 Gates that could not fire, and documents that claimed gates which did not exist

- **Base:** `main`. Head `fix/gates-that-could-not-fire`, 12 commits, 42 files,
  +2853/-46.
- **Real merge state:** mergeable and already current with `main` (zero commits
  behind). `git merge-tree` confirms a clean merge.
- **CI reality:** sixteen checks ran. Fifteen pass or skip. The single red one is
  `dco (Signed-off-by on every commit)`, and it is failing on **all twelve
  commits**, not one. `dco` is **not** in the required-checks list, which is
  exactly why this pull request reports `UNSTABLE` rather than `BLOCKED`, and why
  GitHub would let it merge today. Every required check is green.
- **What it changes:** twelve fixes to gates that could pass while the thing they
  guard was broken, plus the documents that described those gates. It bundles
  work from several earlier pull requests (#155, #156, #157, #182, #183) whose
  content is **not** on `main`. `git cherry` marks all twelve commits as new, so
  this is not a cumulative snapshot of anything already merged.
- **Correctness:** the code changes hold up. The full suite on this branch is
  **2013 passed, 1 skipped**, and the one skip is itself evidence a fix landed:
  its reason now reads ``PyPI's `build` distribution is not installed (a
  `build/` directory is not it)``, where `main` said only ``the `build` package is
  not installed``. That is commit `6de0d1f`, the skip guard the repository's own
  `build/` directory used to satisfy.

  Spot-checking the headline fix `9562d65`: `make conformance` previously ran
  over two hard-coded demo paths and then echoed that all published datasets
  pass HR1 to HR5, while eight of the ten artifacts went unaudited. The
  replacement enumerates `data/published/` and fails on any file it cannot
  classify, and it explicitly guards the two ways an enumerating gate goes
  vacuous: a family whose glob matches nothing fails, and a sweep that audits
  zero artifacts fails. That is the right shape, and it anticipates the exact
  defect class the pull request is named for.

  One defect, described below, is in a comment this pull request adds.

**The defect: a measured claim that is not true.** The pull request adds a block
to `.github/dependabot.yml` stating:

> Measured 2026-08-24: #202 (hatchling), #203 (ruff), #204 (mypy), #205
> (packaging) and #206 (pre-commit) all failed on exactly that step.

**#202 did not fail on that step.** Its `lint` job passed in 19 seconds, every
required check is green, and its merge state is `CLEAN`. The claim is falsifiable
from the run history it cites, and it is false for one of its five cases.

It is also structurally impossible for #202 to fail that gate. #202 edits only
`[build-system].requires`. `hatchling` does not appear in `uv.lock` at all, and
`tools/check_lock_drift.py` reads only `project.dependencies` and the `dev`
extra. Neither lock gate can see a build-backend bump. Applying #202's one-line
change to today's `main` and running the gate directly gives
`Resolved 111 packages`, no error. The sentence describes a gate firing on a pull
request that gate cannot reach, which is precisely the failure mode this pull
request's own title is about.

**Recommendation: `needs work`.** Two things, both small:

1. Correct the `.github/dependabot.yml` comment to say #203, #204, #205 and #206,
   and to record that #202 is unaffected because a `[build-system].requires` bump
   is outside both lock gates. Do not ship the sentence as written.
2. Re-sign the twelve commits, for example `git rebase --signoff origin/main`,
   then force-push. `dco` is advisory here, but CONTRIBUTING.md requires a
   sign-off on every commit, and merging twelve unsigned ones would make the
   policy untrue rather than merely unenforced.

### #213 feat(stats): report whether the ranking survives borrowing strength across segments

- **Base:** `main`. Head `feat/empirical-bayes-stability`, 5 commits, 2 behind.
  Against `main`: 27 files, +2072/-31.
- **Real merge state:** `DIRTY`, for the duplicate-commit reason above. Rebases
  clean.
- **CI reality:** no checks ever ran, starved by the conflict. Not a failure.
- **What it changes:** adds `src/nearmiss/stats/shrinkage.py` and
  `honest_rates.rates.empirical_bayes_rates`, an empirical-Bayes shrinkage pass
  that re-ranks segments and reports whether the published order survives, plus
  ADR 0020, a METHODOLOGY section, a schema section, and the published sidecars.
- **Correctness:** the tests genuinely exercise the bound. I looked specifically
  for a statistical assertion made with data too far from the threshold to
  discriminate, and it is not present.
  `test_a_lucky_sparse_segment_is_reported_as_fragile` constructs a case that
  actually flips the verdict to `FRAGILE` and asserts the top segment moves rank,
  and `test_the_published_rates_and_order_are_not_changed_by_the_pass` asserts
  `baseline_top_weight < 0.7` explicitly so that the no-write check is proved
  against data the adjustment really would move. The refusal paths
  (`not_evaluated` for fewer than three rated segments, and for zero
  between-segment variance) are covered and asserted to be distinct from
  `stable`.
- **Recommendation: `merge after rebase`.** Rebase onto `main` after #212 lands;
  the duplicate commit drops itself.

### #212 feat(stats): measure how much of the published significance rests on independence

- **Base:** `main`. Head `feat/dependence-robust-fdr`, 3 commits, 2 behind.
  Against `main`: 23 files, +921/-12.
- **Real merge state:** `DIRTY`, same duplicate-commit cause. Rebases to a single
  commit with no conflicts.
- **CI reality:** no checks ever ran, starved by the conflict. Not a failure.
- **What it changes:** adds `src/nearmiss/stats/multiplicity.py` and
  Benjamini-Yekutieli to `honest_rates.hotspot`, publishing how much of the
  Benjamini-Hochberg significance survives an arbitrary-dependence correction,
  plus ADR 0019 and the matching METHODOLOGY, schema, and sidecar entries.
- **Correctness:** verified by hand as well as by running it.
  `harmonic(12) = 3.103210678210678` is correct. The p-value set in
  `test_yekutieli_rejects_a_subset_of_hochberg` genuinely separates the two
  procedures: Benjamini-Hochberg rejects four of the seven hypotheses and
  Benjamini-Yekutieli rejects one, and the test asserts `by != bh` explicitly
  rather than only `by <= bh`. That assertion is the guard against the exact
  defect shape where a bound is asserted with data that could never violate it.
  The module is careful not to claim it implements Caldas de Castro and Singer
  (2006), and a test enforces that disclaimer.
- **Recommendation: `merge after rebase`.** Merge this one **before** #213.

### #207 ci(deps): bump the actions-version-updates group with 5 updates

- **Base:** `main`. Head `dependabot/github_actions/actions-version-updates-db1565d3de`,
  3 files, +5/-5.
- **Real merge state:** `CLEAN`, confirmed by `git merge-tree`.
- **CI reality:** all ten required checks green. Genuinely green, not born red.
- **What it changes:** five SHA-pinned GitHub Actions digests move forward:
  `astral-sh/setup-uv` to v10.0.1, `github/codeql-action` init/analyze/upload-sarif
  to v4.37.7, and `trufflesecurity/trufflehog` to v3.97.0. Each keeps its full
  commit SHA with the `# vN` comment, matching the repository's pinning
  convention, and `zizmor` passes.
- **Why it is green when #203 to #206 are not:** it is the `github-actions`
  ecosystem. It never touches `pyproject.toml`, so neither lock gate is engaged.
- **Staleness:** its checks ran 2026-08-24 against a `main` five commits older.
  The change is confined to workflow files that none of those five commits
  touched, so the stale green is low risk.
- **Recommendation: `merge`.**

### #206 chore(deps-dev): update pre-commit requirement from >=4.6.1 to >=4.6.2

- **Base:** `main`. One line of `pyproject.toml`.
- **Real merge state:** `BLOCKED`. The tree merges clean; it is blocked by the
  required `lint` check, not by a conflict.
- **CI reality: born red, not its fault.** `lint` fails at its very first step,
  `make lock-check`, with `error: The lockfile at uv.lock needs to be updated,
  but --check was provided`. Every other check, including both `test` jobs,
  passes.
- **Root cause:** `uv.lock` records the dependency specifiers themselves, so
  editing a specifier in `pyproject.toml` drifts the lock by construction. The
  `pip` ecosystem does not know `uv.lock` exists.
- **Recommendation: `needs work`.** Add one commit to the branch: `uv lock`, then
  commit `uv.lock`. `make lock-dev` is **not** needed here, because
  `requirements-dev.lock` already pins `pre-commit==4.6.2`, which satisfies the
  new floor.

### #205 chore(deps-dev): update packaging requirement from >=24.0 to >=26.3

- **Base:** `main`. One line of `pyproject.toml`.
- **Real merge state:** `BLOCKED`. Merges clean; blocked by three failing
  required checks.
- **CI reality: born red, not its fault, and it is the one that is red twice.**
  `lint` fails on `uv lock --check` like its siblings, and **both** `test` jobs
  additionally fail on a second, independent gate:

  ```
  FAILED tests/test_lock_drift.py::test_the_committed_lock_has_no_drift
  AssertionError: packaging: pyproject.toml requires >=26.3,
  requirements-dev.lock pins 26.2 -- does not satisfy it
  ```

- **Why this one differs from #203, #204 and #206:** those three bump packages
  whose pins in `requirements-dev.lock` already satisfy the new floor
  (`ruff==0.16.4`, `mypy==2.3.1`, `pre-commit==4.6.2`). `packaging` is pinned at
  `26.2`, below the requested `>=26.3`, so the second gate fires too.
- **Recommendation: `needs work`.** This one needs **both** regeneration steps:
  `uv lock` and `make lock-dev`, committing `uv.lock` and
  `requirements-dev.lock`. `make lock-dev` is a real network re-resolution, so it
  cannot be done offline.

### #204 chore(deps-dev): update mypy requirement from >=2.3.0 to >=2.3.1

- **Base:** `main`. One line of `pyproject.toml`.
- **Real merge state:** `BLOCKED` by the required `lint` check. Tree merges clean.
- **CI reality: born red, not its fault.** `lint` fails on `uv lock --check`.
  Everything else, both `test` jobs included, passes.
- **Recommendation: `needs work`.** One commit: `uv lock`, commit `uv.lock`.
  `requirements-dev.lock` already pins `mypy==2.3.1`, so `make lock-dev` is not
  required.

### #203 chore(deps-dev): update ruff requirement from >=0.16.2 to >=0.16.3

- **Base:** `main`. One line of `pyproject.toml`.
- **Real merge state:** `BLOCKED` by the required `lint` check. Tree merges clean.
- **CI reality: born red, not its fault.** Same `uv lock --check` failure.
- **Recommendation: `needs work`.** One commit: `uv lock`, commit `uv.lock`.
  `requirements-dev.lock` already pins `ruff==0.16.4`, so `make lock-dev` is not
  required.

### #202 chore(deps-dev): update hatchling requirement from >=1.31.0 to >=1.32.0

- **Base:** `main`. One line of `pyproject.toml`, in `[build-system].requires`.
- **Real merge state:** `CLEAN`, confirmed by `git merge-tree`.
- **CI reality:** all ten required checks green, `lint` included. **This pull
  request is not born red**, contrary to the comment #214 proposes adding to
  `.github/dependabot.yml`.
- **Why it escapes both lock gates:** `hatchling` is a build backend, not a
  project or `dev` dependency. It appears nowhere in `uv.lock`, and
  `tools/check_lock_drift.py` reads only `project.dependencies` and the `dev`
  extra. Neither gate has it in scope.
- **Staleness:** three commits behind `main`, checks ran 2026-08-24. Re-running
  both lock gates locally with this change applied to today's `main` passes, so
  the stale green is not hiding a changed answer here.
- **Recommendation: `merge`.**

## The false-green shape: still closed

This repository was once burned by `make verify` being piped through `tail`, so
the pipeline's exit status was read instead of make's. That shape is **closed on
`main` and no open pull request reintroduces it**:

- `Makefile` line 24 sets `.SHELLFLAGS := -eu -o pipefail -c`, so every recipe
  line in every target already fails on the first failing stage of a pipe.
- `release.yml` and `ci.yml` set `set -euo pipefail` in their multi-line shell
  steps.
- No gate in `Makefile` or any workflow pipes into `tail`, `head`, or `tee`.

Two `|| true` occurrences remain, and both are deliberate rather than accidental:
`mutation.yml` line 58 (`make mutation || true`), where the job is documented as
advisory, and `ci.yml` line 818, inside a manifest lookup rather than a gate.
Neither swallows a merge-blocking result.

None of the nine open pull requests adds a pipe, a `|| true`, or a `tail` to any
gate. #207 touches workflows but only changes `uses:` digests.

## Order of operations

Two pull requests need a regeneration step that cannot be skipped, and one file
makes the ordering matter more than it looks.

### The file that forces sequencing

`docs/DOCUMENTATION-AUDIT.md` is **generated** by `tools/doc_audit.py`, and
`make docs-audit-check` plus `tests/test_doc_audit.py` fail the build when the
committed block no longer describes the tree. Its numbers are absolute counts
over the whole repository, and **#212, #213 and #214 all rewrite the same lines
with different values**:

| | link check | hand-authored docs | test files |
| --- | --- | --- | --- |
| `main` | 480 links / 95 files | 99 | 110 |
| #212 and #213 | 491 links / 97 files | 101 | 112 |
| #214 | 483 links / 96 files | 100 | 115 |

Whichever of these merges second and third will carry a **stale** audit block.
Each pull request is individually correct against `main` as it stands today, so
this does not show up as a red check now. It shows up after the first merge.
Regenerate between merges.

`docs/CLAIMS.md` is also touched by both #213 and #214, but they insert in
different regions of the table, so it merges cleanly into a valid table. No
action needed there.

### Suggested order

1. **#202** (`merge`). No regeneration. Independent of everything else.
2. **#207** (`merge`). No regeneration. Independent of everything else.
3. **#203, #204, #206** (`needs work` first). On each branch, one commit:
   `uv lock` and commit `uv.lock`. They then go green and can merge in any order.
   Do them one at a time: each merge invalidates the next branch's `uv.lock`
   against the new `pyproject.toml`, so re-run `uv lock` on the branch that is
   still open after each merge.
4. **#205** (`needs work` first). Same, plus `make lock-dev` and a commit of
   `requirements-dev.lock`, because `packaging` needs a real re-resolution to
   26.3. Requires network.
5. **#212** (`merge after rebase`). `git rebase origin/main` clears the conflict
   and drops the two duplicate commits, leaving one. Let CI run for the first
   time, then merge.
6. **#213** (`merge after rebase`). Rebase onto the new `main`. #212's commit
   drops itself as patch-equivalent, leaving two commits. **Then run
   `make docs-audit` and commit the regenerated
   `docs/DOCUMENTATION-AUDIT.md`**, because #212's merge changed the tree counts
   this branch also edits.
7. **#214** (`needs work` first). Fix the `.github/dependabot.yml` sentence, then
   `git rebase --signoff origin/main` and force-push. After #212 and #213 have
   landed, **run `make docs-audit` and commit the result** before merging, for
   the same reason.

Steps 1 and 2 can happen immediately and in either order. Steps 5, 6 and 7 must
keep their relative order.

## Verified versus taken on trust

### Verified locally

- Every merge state, by `git merge-tree --write-tree origin/main origin/<head>`
  against freshly fetched refs, independently of GitHub's badge.
- The #212/#213 stack relationship, by `git merge-base --is-ancestor` and by
  `git cherry origin/main`, which marks the two duplicated commits `-`.
- That neither #212 nor #213 is already contained in `main`: both two-dot diffs
  are non-empty.
- That rebasing #212 and #213 onto `main` resolves every one of the fifteen
  reported conflicts with no manual resolution, done in a throwaway worktree.
- That after a simulated squash-merge of #212, rebasing #213 is still clean and
  drops the duplicate commit automatically, leaving two commits and 23 files.
- The full test suite on the rebased #212 plus #213 stack: **1951 passed, 1
  skipped**, the skip being `test_packaged_schema.py` where the `build` package
  is absent.
- `harmonic(12) = 3.103210678210678`, and that the Benjamini-Hochberg and
  Benjamini-Yekutieli rejection sets for the test's p-value vector are four and
  one respectively, so the test data really does separate the two procedures.
- That #202 cannot fail either lock gate: `hatchling` appears nowhere in
  `uv.lock`, and `tools/check_lock_drift.py` reads only `project.dependencies`
  and the `dev` extra.
- The `requirements-dev.lock` pins that explain the #203/#204/#206 versus #205
  split: `ruff==0.16.4`, `mypy==2.3.1`, `pre-commit==4.6.2`, `packaging==26.2`.
- **The whole #202 to #206 story, reproduced against today's `main`** rather than
  inherited from 2026-08-24 runs. Applying each bump to a clean checkout of
  `9baca50` and running the gates directly:

  | bump | `uv lock --check` | `check_lock_drift.py` |
  | --- | --- | --- |
  | hatchling (#202) | passes, `Resolved 111 packages` | passes |
  | ruff (#203) | fails, lockfile needs updating | passes |
  | packaging (#205) | fails, lockfile needs updating | fails on `packaging` |

  This also retires most of the staleness worry for #202: it is green against
  current `main`, not only against the `main` of five days ago.
- That all six Dependabot branches sit three commits behind `main`, merge-base
  `7bd6d8c` (#191).
- The full test suite on #214: **2013 passed, 1 skipped**.
- The required-checks list and `strict_required_status_checks_policy: false`,
  read from the `protect-main` ruleset.
- The exact failing annotations, read from the job logs rather than inferred from
  a red tick: `uv lock --check` for #203/#204/#205/#206, `test_lock_drift` for
  #205, and twelve `missing a Signed-off-by trailer` errors for #214.
- That `.SHELLFLAGS := -eu -o pipefail -c` is set on `main`, and that no gate
  pipes into `tail`, `head`, or `tee`.
- That `docs/DOCUMENTATION-AUDIT.md` drifts on any added Markdown file under
  `docs/`, by adding one in a scratch worktree and watching
  `tools/doc_audit.py --check` fail.
- That the CHANGELOG hunks for #212 and #213 both land at line 58, immediately
  under `## [Unreleased]` at line 57, and therefore **not** inside the released
  `## [0.4.0]` section that begins at line 317.

### Taken on trust

- That the **non-lock** checks recorded on #202 and #207 would still pass against
  today's `main`. They ran 2026-08-24 and the ruleset does not require branches
  to be current. The lock gates were re-run locally and pass, and neither change
  touches Python source, so the residual risk is small, but the remaining eight
  required jobs were not re-run.
- That #212 and #213 will pass CI once rebased. The full suite passes locally,
  but `accessibility`, `i18n`, `reproducibility`, `teaching`, `security`, and
  `zizmor` are workflow jobs that were never exercised for these branches and are
  not covered by `pytest` alone.
- That `make lock-dev` for #205 will actually resolve `packaging==26.3` with
  hashes. That requires a network re-resolution and was not attempted.
- That the twelve commits bundled into #214 correspond to pull requests that were
  closed rather than merged. `main` contains no commit with those subjects and
  `git cherry` marks all twelve as new, which is consistent, but the closure
  reasons were not read.
- The correctness of the statistical *methods* as methods. The arithmetic,
  the invariants, and the test coverage were checked. Whether
  Benjamini-Yekutieli and Marshall-style empirical-Bayes shrinkage are the right
  choices for this data is a review question, not a triage question.

## A note on this file

`docs/PR-TRIAGE.md` is itself a new Markdown file under `docs/`, so it changes
the counts in `docs/DOCUMENTATION-AUDIT.md` and will fail `make docs-audit-check`
until that file is regenerated. This was confirmed rather than assumed. The
triage branch deliberately commits only `docs/PR-TRIAGE.md`, so **this pull
request is born red on exactly the gate it documents**. Run `make docs-audit` and
commit the result to clear it.
