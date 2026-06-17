# Verification audit — 2026-06-16

Audit-as-artifact record for the first implemented build (v0.1.0). This captures
what was run and what passed, so the claim "it works" is backed by evidence, not
assertion. Regenerate and re-commit on each release.

**Commit context:** implementation of the analysis engine, fixtures, tests, the
accessible web view, and the published Davis demo dataset.

## Gates run

| Gate | Command | Result |
| --- | --- | --- |
| Tests | `make test` (`pytest`) | **27 passed** |
| Lint | `make lint` (`ruff check` + `ruff format --check`) | **clean** |
| Types | `make type` (`mypy --strict`) | **no issues in 35 source files** |
| Accessibility (structural) | `make accessibility` (`tools/a11y_check.py web/index.html`) | **pass** |
| Secrets | `gitleaks detect` | **no leaks (15 commits scanned)** |
| Demo | `make demo` | **recovers planted hotspot seg-06** |
| Reproducibility | `make reproduce` | **byte-for-byte; `git diff` clean on `data/published/`** |

## Known-answer checks (the point of the fixtures)

- Exposure normalization ranks **seg-06** (low exposure, rate 20.0 per 1000)
  first, while **seg-03** — which has the **most raw reports** (n=20) — ranks
  6th at rate 2.5. Volume is not danger.
- **Getis-Ord Gi\*** flags **only seg-06** as significant (z = 3.26 > 1.96),
  the planted cluster centre.
- The published GeoJSON for Davis hashes to
  `033aa7f764cd1b3dda61ca4d599cfa0afaa41114dcfdcb619281d2fb2805f955`
  and the privacy invariant (`assert_published_clean`) holds: no per-report
  coordinate, time, reporter token, mode, severity, or note is present, and
  small-n (n < 5) hazard breakdowns are suppressed.

## Not run here (run in CI / pending)

- **`pip-audit`** and **CodeQL** require network access and run in CI, not in
  this local audit.
- The **deeper accessibility audit** — an `axe` automated run plus manual NVDA
  and VoiceOver review — is still pending; the local gate above is structural
  only. See `docs/accessibility/ACR.md`, which remains a conformance target for
  the manual criteria.
- A committed, hashed `requirements.lock` (via `make lock`) is not yet present.
