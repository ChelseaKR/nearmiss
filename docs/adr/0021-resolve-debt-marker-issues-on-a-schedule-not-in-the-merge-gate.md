# 21. Resolve debt-marker issues on a schedule, not in the merge gate

Date: 2026-09-05

## Status

Accepted

## Deciders

nearmiss maintainers

## Context

`docs/standards/CODE-QUALITY-STANDARD.md` declares CQ-34 an AUTO-GATE: no bare debt marker; each one
carries a linked issue. `tools/check_debt_markers.py` implements it offline, and offline is exactly
its limit — it proves a marker *carries* an issue reference and can never see whether that issue
exists, is open, or is about the marker.

That limit was not theoretical. `CITATION.cff:68` read a marker pointing at #184 while #184 had been
closed on 2026-08-23 and was about the README and ROADMAP's stale tag claims, not about minting a
DOI. The gate was green over tracking that did not exist. PR #228 repointed the marker at #227 and
said so plainly: repointing fixes the instance, not the class. #233 is the class.

Closing it needs the issue tracker, and the tracker is a network dependency. The merge gate's entire
value is that it is fast, local, and identical in CI; making a merge fail because api.github.com had
a bad minute would trade a real property for a new one. Adding a scheduled workflow also creates a
new explicit GitHub Actions `permissions:` boundary, which DOC-06 requires this ADR for.

## Decision

Add an **opt-in** `--resolve-issues` pass to `tools/check_debt_markers.py` and run it from a weekly,
manually dispatchable workflow. The default invocation — the one `make verify` and CI's merge gate
run — is unchanged: no flag, no network, same exit codes. `tests/test_debt_markers.py` pins that by
making any socket open during the offline gate an assertion failure, so the property is enforced
rather than asserted in prose.

The online pass decides only what is decidable, against the repository named by `pyproject.toml`'s
`[project.urls] Repository` rather than a hard-coded slug:

- the issue **exists** in this repository (a 404 fails);
- it is **open** (a closed issue fails — the #184 case);
- it is an **issue, not a pull request** (GitHub's issues endpoint answers for pull requests too, so
  a marker citing a merged PR number would otherwise read as tracked work).

**Relevance is not decided, and not faked.** Whether "mint a DOI" is what #227 is about is a reading.
A title-similarity score would be a number that looks like a verdict without being one — the defect
this repository names everywhere else. The pass instead prints each issue's live title beside the
marker text on one line, which is the form in which the #184 mismatch was obvious to a human, and
leaves the judgment to the reader of the run.

A lookup that could not be performed at all — rate limit, 5xx, dropped connection — exits `2` and is
reported as **UNDETERMINED**, distinct from both a clean run (`0`) and a real finding (`1`). It is
never folded into the pass.

The workflow is granted `contents: read` and `issues: read`. `GITHUB_TOKEN` is passed only to lift
the unauthenticated rate limit; the job has no write authority of any kind.

## Consequences

- A marker whose issue is closed, deleted, or a pull request becomes visible within a week instead of
  never, without any merge acquiring a network dependency.
- The offline gate's docstring no longer states an unclosed limit; it states which half is closed
  here and which half is deliberately left to a human.
- The scheduled job can go red for reasons that are not the repository's fault (GitHub outage, rate
  limit). That is why the undetermined outcome has its own exit code and its own annotation: a red
  run says which of the two happened rather than leaving a reader to guess.
- The pass's first run found a real instance: `tests/test_debt_markers.py`'s own docstring spelled a
  marker word beside `(#184)`, so a line of prose read as a live marker tracked by a closed issue.
  That file's convention is to assemble marker words from `MARKER_WORDS` and never type them; the
  convention had been broken once, and the offline gate could not see it. Fixed in the same change.
- CQ-35 (suppressions needing an issue reference) remains unimplemented and out of scope, as recorded
  in the tool's docstring.

## Alternatives considered

- **Put the resolution in `make verify`.** Rejected. It makes every merge depend on api.github.com
  and on a rate limit shared across a runner IP, to catch a class that changes on the scale of weeks.
- **Weaken the offline gate to a warning and rely on the online pass.** Rejected. The offline rule is
  a real AUTO-GATE that catches a real thing; the online pass is additive.
- **Score marker/issue title similarity and fail below a threshold.** Rejected. It would publish a
  number that reads as a relevance verdict and is not one, and a threshold nobody can defend is worse
  than a stated blind spot. The titles are printed instead.
- **Keep a committed marker → issue-title manifest and fail on drift.** Deferred. It would catch a
  repurposed issue, but it adds a hand-maintained file to the merge path, and a hand-maintained
  counter in a gated document is a known way to jam a queue. Revisit if this repository ever carries
  more than a handful of markers.
- **Fail closed on an unreachable tracker.** Rejected as the *only* outcome: it makes a platform
  outage indistinguishable from a fictional issue reference. Both fail the run; the exit code and the
  annotation say which.
