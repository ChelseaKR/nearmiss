<!--
Thanks for contributing to nearmiss. This is an open dataset and a statistically honest analysis for
safe-streets advocacy — the standard is "holds up when a skeptical traffic engineer pushes back."
Keep the PR small and focused: one coherent change reviews faster and breaks less.
-->

## Summary

<!-- What does this change do, and why? Link the issue or discussion it addresses. -->

Closes #

## Type of change

<!-- Match the Conventional Commit type of your primary commit. -->

- [ ] `feat` — new capability
- [ ] `fix` — bug fix
- [ ] `docs` — documentation only
- [ ] `refactor` / `perf` — no behavior change
- [ ] `test` — tests or fixtures only
- [ ] `build` / `ci` / `chore` — tooling, deps, pipeline
- [ ] Breaking change (`!`) — schema, dataset, or public API changes incompatibly

## Contributor checklist

<!-- Check every box that applies. Do not route around a gate by disabling it; we fix the gate. -->

- [ ] **No raw data committed** — nothing from `data/raw/`, no real locations, no identifying
      details in code, fixtures, tests, notebooks, commit messages, or this PR description.
- [ ] **Tests** pass (`make test`); new statistical or pipeline code ships with a **synthetic
      fixture whose answer is known** (planted hotspot, known exposure, or interval-coverage check).
- [ ] **Lint** passes (`make lint` — `ruff`).
- [ ] **Types** pass (`make type` — `mypy --strict`); no untyped or loosely typed code.
- [ ] **Accessibility gate** — for UI changes, every AUTO-GATE passes; risk and significance are
      conveyed in text and pattern, not color alone; and everything is reachable via the list/table
      equivalent. The REVIEW disposition below is either a completed manual NVDA/VoiceOver pass or a
      public-preview-only provisional owner attestation satisfying
      [`ADR 0012`](../docs/adr/0012-solo-maintainer-provisional-review-attestation.md). Synthetic
      evidence is not reported as a manual pass.
- [ ] **Security** passes (`make security` — `pip-audit`, `gitleaks`, CodeQL-equivalent); deps remain
      **pinned and hashed**, or changed only via the documented bump path (not a hand edit).
- [ ] **Conventional Commits** used and commits are **DCO signed off** (`git commit -s`).
- [ ] **Reproducible** — changes are deterministic and seeded; `make reproduce` regenerates any
      affected figures or tables.
- [ ] **Five hard rules honored** — rates carry a **denominator** with a dated source; estimates
      carry a **confidence interval** and an `n`; relevant **reporting bias** is named; nothing is
      published at identifying precision.
- [ ] **Docs updated** where behavior, methods, or assumptions changed (README, `docs/METHODOLOGY.md`,
      `docs/DATA-CARD.md`, `docs/audits/`, or an ADR as appropriate).

## If the schema changed

<!-- Leave unchecked / write "n/a" if this PR does not touch schema/report.schema.json or the dataset schema. -->

- [ ] Schema is **versioned** (`schema_version` bumped per semver).
- [ ] **CHANGELOG** updated under the new schema version: what changed, why, and whether it breaks.
- [ ] A **migration** plus its test (runs the migration on a fixture and checks the result) is included.
- [ ] An **ADR** is added under `docs/adr/` recording the decision.

## Accessibility note (UI changes only)

<!--
Write "n/a" only when there is no UI change. Otherwise complete every field. Do not list a planned or
synthetic check as performed.

REVIEW disposition: completed / provisional public preview / blocked
Manual checks actually performed (AT + browser + versions + result):
Synthetic/browser evidence (exact method/environment/result):
Checks not performed:
Residual risk and accountable-owner acceptance (name/date/source):
Preview scope and rollback procedure/triggers:
Expiry and earlier recheck triggers:
Conformance language: confirm that provisional evidence is not cited as WCAG/ACR/508 conformance
-->

## Reviewer-facing notes

<!-- Anything a skeptical reviewer should check first: a tricky interval, a bias caveat, a snapping edge case. -->
