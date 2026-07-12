# Project Scope

Last reviewed: 2026-07-08. Base branch: `main`.

This file is a plain-language map of the project as it exists on `main`. It does not replace the README, roadmap, audit docs, or source comments. It points to them so a reviewer can see the whole shape without reading every file first.

## What This Project Is

Nearmiss turns hazard and near-miss reports into an open, statistically careful dataset for safe-streets advocacy. The product is the data and analysis, with maps and briefs as outputs.

Package metadata checked in this pass:

- Python package `nearmiss` for Python `>=3.11`.

## Who It Serves

- Bike and pedestrian advocates collecting reports outside official crash records.
- Researchers and journalists who need reproducible safety data.
- Maintainers building privacy-preserving civic datasets and public briefs.

## What It Covers

- Report schema, intake, dedupe, geocode, snap, classify, exposure, and statistics steps.
- GeoJSON outputs, metadata sidecars, bilingual briefs, and accessible data views.
- Confidence intervals, hotspot methods, reporting-bias notes, and privacy floors.
- Docs for methodology, accessibility, threat modeling, audits, ADRs, and responsible-tech review.
- Tests and reproducibility commands for the analysis pipeline.

## How It Is Put Together

- src/ and tools/ hold the analysis pipeline and fixture builders.
- schema/ defines reports and published dataset shapes.
- docs/ explains methodology, access, audits, and design choices.
- tests/ includes pipeline, privacy, statistics, and output checks.
- public/report outputs and demo data show the analysis surface.

Observed source and operations surfaces:

- `Makefile`
- `config/`
- `infra/`
- `notebooks/`
- `pyproject.toml`
- `schema/`
- `src/`
- `tools/`
- `web/`

GitHub workflow files checked:

- `.github/workflows/ci.yml`
- `.github/workflows/mutation.yml`
- `.github/workflows/scorecard.yml`
- `.github/workflows/secret-scan-scheduled.yml`

## Trust Boundaries

- Raw counts are not treated as danger rates without exposure context.
- Small samples and reporting bias are surfaced instead of hidden.
- Precise raw reports are protected and public data is aggregated to reduce reidentification risk.

## Outside This Scope

- It is not a city 311 system or official crash registry.
- Findings depend on report coverage and exposure estimates.
- Manual screen-reader review and deeper localization remain outside the automated pipeline.

## Docs And Evidence Checked

This pass checked 46 hand-authored doc or metadata files, 41 test files, and 4 workflow files on `main`. The count excludes vendored provider licenses, dependency folders, generated cache files, and large generated artifact history.

Large content groups were counted rather than listed file by file:

- `docs/standards/`: 12 files

Primary docs checked:

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
- `docs/DPIA.md`
- `docs/I18N.md`
- `docs/INTAKE-AND-ABUSE.md`
- `docs/LIMITATIONS.md`
- `docs/METHODOLOGY.md`
- `docs/MUTATION-TESTING.md`
- `docs/PERFORMANCE.md`
- `docs/REAL-DATA.md`
- `docs/RESPONSIBLE-TECH-AUDITS.md`
- `docs/SUBMISSIONS.md`
- `docs/THREAT-MODEL.md`
- `docs/accessibility/ACR.md`
- `docs/adr/0001-record-architecture-decisions.md`
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

Representative test files checked:

- `tests/README.md`
- `tests/conftest.py`
- `tests/fixtures/davis/exposure.json`
- `tests/fixtures/davis/reports.json`
- `tests/fixtures/davis/streets.geojson`
- `tests/fixtures/davis/weather.json`
- `tests/fixtures/riverside/exposure.json`
- `tests/fixtures/riverside/reports.json`
- `tests/fixtures/riverside/streets.geojson`
- `tests/test_brief.py`
- `tests/test_build_exposure.py`
- `tests/test_cli.py`
- `tests/test_dedupe_differential.py`
- `tests/test_diff_datasets.py`
- `tests/test_fdr.py`
- `tests/test_fetch_bikemaps.py`
- `tests/test_fetch_osm_streets.py`
- `tests/test_figures.py`
- `tests/test_geocoder.py`
- `tests/test_geometry.py`
- `tests/test_getis_ord_differential.py`
- `tests/test_hotspot.py`
- `tests/test_i18n.py`
- `tests/test_intake.py`
- `tests/test_kde_differential.py`
- `tests/test_loaders.py`
- `tests/test_moderation.py`
- `tests/test_observability.py`
- `tests/test_pipeline.py`
- `tests/test_publish_privacy.py`
- `tests/test_rates.py`
- `tests/test_reproduce.py`
- `tests/test_riverside.py`
- `tests/test_robustness.py`
- `tests/test_server.py`
- `tests/test_snap_differential.py`
- `tests/test_spatial_index.py`
- `tests/test_stats_numerics.py`
- `tests/test_temporal.py`
- `tests/test_validation.py`
- `tests/test_validation_internals.py`

## Validation Notes

For this docs PR, validation means the scope file was generated from the clean `origin/main` worktree, reviewed against repo metadata and docs inventory, and checked with `git diff --check`. Project test suites are still the authority for code behavior, because this PR changes documentation only.
