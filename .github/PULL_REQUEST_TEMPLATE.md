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
- [ ] **Accessibility gate** — for UI changes, `axe` passes **and** a manual NVDA/VoiceOver pass was
      done; risk and significance are conveyed in text and pattern, not color alone, and everything
      is reachable via the list/table equivalent. Manual result noted below.
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

<!-- Which screen reader and browser you tested, and the result. Write "n/a" if no UI change. -->

## Reviewer-facing notes

<!-- Anything a skeptical reviewer should check first: a tricky interval, a bias caveat, a snapping edge case. -->
