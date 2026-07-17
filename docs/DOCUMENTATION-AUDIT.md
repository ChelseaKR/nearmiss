# Documentation Audit

Last reviewed: 2026-07-08. Base branch: `main`.

This audit records the documentation sweep and remediation loop for this repository. It checks the docs as a system: entry points, root-level process and legal files, project scope, setup and validation notes, safety and privacy posture, architecture and planning docs, local links, and the places where code, tests, workflows, and docs meet.

## Audit Results

| Area | Result | Evidence |
| --- | --- | --- |
| Entry docs | pass | `README.md` present |
| Security/process docs | pass | CONTRIBUTING.md, SECURITY.md, CHANGELOG.md |
| Architecture/planning docs | pass | 5 architecture/interface docs; 4 planning/research docs |
| Safety/privacy/audit docs | pass | 7 safety/privacy/accessibility/audit docs |
| Validation surface | pass | 32 test files; 4 workflow files |
| Local doc links | pass | 431 authored-doc links checked; 0 unresolved |

## Root-Level Documentation Audit

This section covers hand-authored documentation at the repository root and root-adjacent GitHub templates. It is separate from the `docs/` inventory so README, process, legal, release, and project-specific root files do not get hidden inside the larger docs tree.

| Surface | Result | Evidence |
| --- | --- | --- |
| Root README | pass | Present: `README.md` |
| Root process docs | pass | Present: `CONTRIBUTING.md`, `SECURITY.md`, `CHANGELOG.md` |
| Root legal, citation, and conduct docs | pass | Present: `LICENSE`, `NOTICE`, `CITATION.cff`, `CODE_OF_CONDUCT.md` |
| Other root project docs | info | None found. |
| Root-adjacent GitHub templates | pass | `.github/PULL_REQUEST_TEMPLATE.md`, `.github/CODEOWNERS` |
| Root/template doc links | pass | 169 root-level/template links checked; 0 unresolved |

Root-level files checked:

- `CHANGELOG.md`
- `CITATION.cff`
- `CODE_OF_CONDUCT.md`
- `CONTRIBUTING.md`
- `LICENSE`
- `NOTICE`
- `README.md`
- `SECURITY.md`

Root-adjacent template files checked:

- `.github/PULL_REQUEST_TEMPLATE.md`
- `.github/CODEOWNERS`

## Remediation In This PR

- Added missing root-level remediation docs found by the audit loop, including legal, conduct, contribution, or security files where absent.
- Added `docs/PROJECT-SCOPE.md` as the plain-language project and boundary map.
- Added this audit record so future doc changes have a dated baseline.
- Added or refreshed the docs index so scope, audit, and primary docs are easy to find.
- Fixed or added root/doc remediation files: `docs/standards/README.md`.

## Repo Surfaces Checked

Package and workspace metadata:

- Node workspace `web/package.json` named `nearmiss-web` (scripts: axe).
- Python package `nearmiss` (>=3.11).

Source and operations surfaces seen at the repo root:

- `config/`
- `data/`
- `infra/`
- `Makefile`
- `pyproject.toml`
- `src/`
- `tests/`
- `tools/`
- `uv.lock`
- `web/`

Workflow files checked:

- `.github/workflows/ci.yml`
- `.github/workflows/mutation.yml`
- `.github/workflows/scorecard.yml`
- `.github/workflows/secret-scan-scheduled.yml`

## Documentation Inventory

| Category | Count | Representative files |
| --- | ---: | --- |
| architecture and interfaces | 5 | `docs/adr/0000-record-architecture-decisions.md`, `docs/adr/0002-exposure-normalization-and-confidence-intervals.md`, `docs/adr/0003-pure-python-statistics-and-planar-geometry.md`, `docs/adr/0004-standards-applicability.md`, `schema/dataset.schema.md` |
| entry points and repo process | 10 | `.github/CODEOWNERS`, `.github/PULL_REQUEST_TEMPLATE.md`, `CHANGELOG.md`, `CITATION.cff`, `CODE_OF_CONDUCT.md`, `CONTRIBUTING.md`, `LICENSE`, `NOTICE`, plus 2 more |
| examples and guides | 2 | `docs/teaching/FACILITATOR-GUIDE.es.md`, `docs/teaching/FACILITATOR-GUIDE.md` |
| other docs | 22 | `data/README.md`, `data/published/davis-ranked.md`, `data/published/riverside-ranked.md`, `docs/ADAPTING.md`, `docs/DATA-CARD.md`, `docs/DPIA.md`, `docs/I18N.md`, `docs/INTAKE-AND-ABUSE.md`, plus 14 more |
| planning and research | 4 | `docs/ideation/02-large-scale-fixes.md`, `docs/ideation/03-expansions.md`, `docs/research/2026-06-17-bug-review-and-user-research.md`, `docs/research/2026-06-20-synthetic-user-interviews.md` |
| safety, privacy, accessibility, and audits | 7 | `docs/ACCESSIBILITY.md`, `docs/DOCUMENTATION-AUDIT.md`, `docs/RESPONSIBLE-TECH-AUDITS.md`, `docs/THREAT-MODEL.md`, `docs/accessibility/ACR.md`, `docs/audits/2026-06-16-verification.md`, `docs/audits/README.md` |
| grouped generated/source content | 12 | `docs/standards/` counted as a content group, not listed file by file |

Full hand-authored doc inventory checked by this pass:

- `.github/CODEOWNERS`
- `.github/PULL_REQUEST_TEMPLATE.md`
- `CHANGELOG.md`
- `CITATION.cff`
- `CODE_OF_CONDUCT.md`
- `CONTRIBUTING.md`
- `LICENSE`
- `NOTICE`
- `README.md`
- `SECURITY.md`
- `data/README.md`
- `data/published/davis-ranked.md`
- `data/published/riverside-ranked.md`
- `docs/ACCESSIBILITY.md`
- `docs/ADAPTING.md`
- `docs/DATA-CARD.md`
- `docs/DOCUMENTATION-AUDIT.md`
- `docs/DPIA.md`
- `docs/I18N.md`
- `docs/INTAKE-AND-ABUSE.md`
- `docs/LIMITATIONS.md`
- `docs/METHODOLOGY.md`
- `docs/MUTATION-TESTING.md`
- `docs/PERFORMANCE.md`
- `docs/PROJECT-SCOPE.md`
- `docs/README.md`
- `docs/REAL-DATA.md`
- `docs/RESPONSIBLE-TECH-AUDITS.md`
- `docs/SUBMISSIONS.md`
- `docs/THREAT-MODEL.md`
- `docs/accessibility/ACR.md`
- `docs/adr/0000-record-architecture-decisions.md`
- `docs/adr/0002-exposure-normalization-and-confidence-intervals.md`
- `docs/adr/0003-pure-python-statistics-and-planar-geometry.md`
- `docs/adr/0004-standards-applicability.md`
- `docs/audits/2026-06-16-verification.md`
- `docs/audits/README.md`
- `docs/ideation/02-large-scale-fixes.md`
- `docs/ideation/03-expansions.md`
- `docs/research/2026-06-17-bug-review-and-user-research.md`
- `docs/research/2026-06-20-synthetic-user-interviews.md`
- `docs/teaching/FACILITATOR-GUIDE.es.md`
- `docs/teaching/FACILITATOR-GUIDE.md`
- `infra/README.md`
- `notebooks/README.md`
- `notebooks/teaching/README.md`
- `schema/dataset.schema.md`
- `src/nearmiss/README.md`
- `tests/README.md`
- `web/README.md`

Grouped content counts:

- `docs/standards/`: 12 files

## Link Check

- Checked 431 local links in authored Markdown and MDX docs.
- Unresolved authored-doc links after remediation: 0.
- Root-level/template unresolved links after remediation: 0.

Audit scope notes:

- Generated sites, deployed app routes, raw third-party HTML captures, and golden fixture websites were inventoried as product or data surfaces but excluded from authored-doc link failure counts.
- Grouped content directories are counted so they stay visible without making the audit readable without hiding them.

## Validation Notes

- The audit was generated from a clean worktree based on `origin/main` for this PR branch.
- Ran a local relative-link check over hand-authored Markdown and MDX docs.
- Ran an explicit root-level documentation presence and link check for README, process, legal, project, and template docs.
- Ran `git diff --check` across the PR worktrees after remediation.
- Product test suites remain the authority for runtime behavior; this PR changes documentation only.
