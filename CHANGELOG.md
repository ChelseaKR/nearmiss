# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Scope and conventions

This file tracks the **software** version of the `nearmiss` repository (the version in
`pyproject.toml` and the git release tag). The two data contracts the project ships are versioned
**independently** of the software and of each other, and each has a dedicated subsection under every
release so a schema change is never buried in a code change:

- **Intake report schema** — `schema/report.schema.json`, currently `1.0.0`. The intake contract for
  precise, pre-aggregation reports. Carried per payload in the `schema_version` field.
- **Published dataset schema** — `schema/dataset.schema.md` (and its mirroring JSON Schema validated
  in CI), currently `1.0.0`. The contract for the open `data/published/nearmiss.geojson` artifact.
  Carried per file in `metadata.schema_version`.

Both schemas follow the **versioning and deprecation policy** in
[`schema/dataset.schema.md`](schema/dataset.schema.md#7-versioning-and-deprecation-policy), summarized
under [Schema-versioning policy](#schema-versioning-policy) at the foot of this file. In short: PATCH =
clarifications, MINOR = backward-compatible additive changes (flag and hazard vocabularies are additive,
never silently repurposed), MAJOR = a breaking change. Breaking changes are announced at least one MINOR
release ahead with a deprecation window and a stated migration path; published artifacts are immutable
and hashed and are never rewritten in place.

Released versions are signed; conventional-commit history backs every entry.

## [Unreleased]

Nothing released yet beyond `0.1.0`. Changes land here first.

### Intake report schema (`schema/report.schema.json`)

- No changes since `1.0.0`.

### Published dataset schema (`schema/dataset.schema.md`)

- No changes since `1.0.0`.

## [0.1.0] - 2026-06-16

First beta. The end-to-end pipeline runs from a raw report to a published, open, statistically honest
dataset, and `make reproduce` regenerates every figure, table, and published artifact from inputs. The
project ships as a **dataset and analysis**, not an app; the web view is a read-only window onto the
published data. This release is labeled **beta**: the schemas are stable enough to build against under
the deprecation policy, but rate magnitudes, exposure sources, and bias adjustments are still being
calibrated against real corridors and may move between `0.x` releases.

### Added — schema and intake

- **Intake report schema** `schema/report.schema.json` (`report.schema.json` version `1.0.0`,
  JSON Schema draft 2020-12). Defines a single incoming road-hazard / near-miss report with required
  `schema_version`, `id` (UUID, not derived from reporter identity), `occurred_at` (RFC 3339 with
  explicit offset), `location`, `mode`, `hazard_type` (close-pass, door-zone, blind-corner, pothole,
  and related categories), and `severity`. The intake contract intentionally accepts full submitted
  coordinate precision and an optional pseudonymous reporter token; such precise reports are **private
  and gitignored** under `data/raw/` and are never published as-is (**HR4**).
- **`intake.py`** — validates each submission against the report schema before it lands in the private
  raw store, routing by `schema_version` so future schema revisions get the correct validation and
  migration path. Intake attaches no denominators, rates, or intervals; those are computed downstream
  and never claimed at intake.

### Added — pipeline

- **`pipeline/`** — pure, recorded transforms with plain, inspectable data between stages:
  - **dedupe** — collapses duplicate and near-duplicate submissions of the same event.
  - **geocode** — resolves locations to coordinates against a documented, versioned reference.
  - **snap-to-segment** — snaps each report to a street segment, the unit of aggregation and exposure.
  - **classify** — normalizes `hazard_type` and `mode` into the analysis vocabulary.
  - **quality-flag** — annotates reports with quality signals (e.g. low location accuracy, ambiguous
    snap) that carry through to per-feature `quality_flags` in the published dataset.

### Added — exposure and statistics

- **`exposure.py`** — attaches an exposure denominator to each segment from documented, versioned
  sources (observed bike/ped counts, a demand model, or an imported exposure layer), recording the
  `exposure_source` identifier and `exposure_date` **per feature** so a stale or swapped layer is
  visible, not silent. Segments with no available denominator are carried as `exposure_unknown`, not
  silently dropped (**HR1**).
- **`stats/rates.py`** — computes every risk figure as a **rate normalized by exposure**, never a raw
  count, and attaches a **confidence interval and an `n`** to every published rate, ranking, and
  comparison. Small-sample segments are flagged `low_sample` and shown as uncertain rather than ranked
  as certain (**HR1**, **HR2**).
- **`stats/bias.py`** — characterizes **reporting bias** as a first-class output: who is over- and
  under-represented by route choice, demographics, app access, and language, and what that does to the
  conclusions. The characterization is stated plainly, not hidden (**HR3**).
- **`stats/kde.py`** — kernel density estimation for a continuous report/risk surface, with the
  bandwidth and the smoothed quantity documented; a KDE of raw counts is labeled **report volume**,
  never **danger**.
- **`stats/getis_ord.py`** — Getis-Ord Gi\* to identify **statistically significant** hot and cold
  spots, with the significance level and multiple-comparison correction stated, so "hotspot" means a
  tested cluster rather than a bright patch on a heat map.

### Added — publishing and briefs

- **`publish.py`** — emits the open artifacts:
  - **`data/published/nearmiss.geojson`** — aggregated to street segments with a minimum reports per
    feature, coordinates fuzzed and jittered, conforming to the published dataset schema `1.0.0`
    (WGS84 / EPSG:4326 per RFC 7946). Every feature carries its rate, CI, `n`, `quality_flags`, and
    per-feature exposure provenance.
  - **data card** — a `Datasheets for Datasets`-style card (`docs/DATA-CARD.md`, with a per-release
    `data/published/datacard.json` sidecar) covering provenance, known reporting biases, a schema
    crosswalk, and explicit out-of-scope and discouraged uses.
  - **provenance** — each file pins `metadata.schema_version`, `metadata.content_hash`, and
    `metadata.rng_seed`, making every published build immutable, verifiable, and reproducible (**HR5**).
  - **privacy guarantees** — no per-report records, raw or sub-jitter coordinates, reporter tokens,
    verbatim notes, or per-contributor sequences ever appear in the published artifact; a CI privacy
    check enforces the "guaranteed absent" list (**HR4**).
- **`brief.py`** — generates advocacy briefs from the published dataset, carrying intervals and the
  bias caveats through to the prose so a brief cannot quietly overclaim.

### Added — accessible web view

- **`server.py`** plus a framework-free `web/` build — a **read-only** accessible map of the published
  dataset with an **equivalent sortable list/table view** of the same data, targeting **WCAG 2.2 AA**
  and **Section 508 (Revised, 36 CFR Part 1194)**. Maps show modeled/uncertain segments as such; the
  table exposes rate, CI, `n`, and flags as sortable columns so no information is map-only.

### Added — documentation

- `README.md`, `CONTRIBUTING.md`, `SECURITY.md`, `NOTICE`, and an Apache-2.0 `LICENSE`.
- `docs/METHODOLOGY.md` (exposure, rates, intervals, bias, KDE, Getis-Ord Gi\*),
  `docs/DATA-CARD.md`, `docs/THREAT-MODEL.md`, and `docs/ACCESSIBILITY.md`.
- `docs/accessibility/ACR.md` — a committed **VPAT 2.5 (Rev 508)** Accessibility Conformance Report.
- `docs/adr/` — Architecture Decision Records, including
  `0001-record-architecture-decisions.md` and `0002-exposure-normalization-and-confidence-intervals.md`.
- `docs/audits/` — the committed audit log directory.
- `schema/dataset.schema.md` — the human-readable published-dataset contract, including the versioning
  and deprecation policy.

### Added — CI, security, and supply chain

- GitHub Actions CI (`.github/workflows/ci.yml`) gating every change on:
  - **lint** — `ruff` (lint, import order, format check).
  - **type** — `mypy --strict`.
  - **test** — `pytest` against **synthetic fixtures with known answers** (planted hotspots are
    recovered by Getis-Ord Gi\*; interval coverage is checked against the planted truth).
  - **accessibility** — automated `axe` on the built map, table, report form, legends, and charts;
    manual NVDA/VoiceOver passes are required per `docs/ACCESSIBILITY.md` and tracked outside CI.
  - **security** — `pip-audit`, `gitleaks`, and `CodeQL`.
  - **reproducibility** — `make reproduce` must rebuild `data/published` from inputs with no drift.
- **Pinned and hashed** dependencies (`pip install --require-hashes`), `Dependabot`
  (`.github/dependabot.yml`), `.github/CODEOWNERS`, conventional commits, semantic versioning, and
  **signed releases**.

### Security

- Established the supply-chain and secret-scanning baseline above (pinned+hashed deps, Dependabot,
  `pip-audit`, `gitleaks`, `CodeQL`) and the disclosure process in `SECURITY.md`.
- Privacy-by-construction enforced in CI: precise reports stay private and gitignored, and the
  published-artifact privacy check fails the build if any identifying field appears (**HR4**).

### Intake report schema (`schema/report.schema.json`)

- **`1.0.0`** — initial published intake contract. Establishes the required fields, the
  full-precision-private / aggregated-public split, and the additive vocabularies for `hazard_type`,
  `mode`, and `severity`.

### Published dataset schema (`schema/dataset.schema.md`)

- **`1.0.0`** — initial published dataset contract. Establishes the `FeatureCollection` with versioned
  `metadata`, per-feature rate / CI / `n`, per-feature exposure provenance, the additive `quality_flags`
  vocabulary, the WGS84 / RFC 7946 geometry conventions, and the "guaranteed absent" privacy list.

## Schema-versioning policy

The two schemas are versioned independently of the software and of each other; the canonical statement
lives in [`schema/dataset.schema.md`](schema/dataset.schema.md#7-versioning-and-deprecation-policy).
Summary:

- **PATCH** — clarifications, doc fixes, added examples, non-semantic corrections. No consumer action.
- **MINOR** — backward-compatible **additions** only: a new optional property, a new `quality_flags`
  value, a new `exposure_source` identifier, a new permitted `hazard_breakdown` key. Existing properties
  keep their name, type, and meaning; flag and hazard vocabularies are **additive and never silently
  repurposed**. A consumer written for an earlier `1.x` keeps working and should ignore anything it does
  not recognize.
- **MAJOR** — a **breaking change**: removing or renaming a property, changing a type or unit, changing
  the meaning of a field, changing the default CI level or the significance / correction method in a way
  that alters how published numbers read, or changing the geometry/CRS conventions.

**Deprecation.** A field slated for removal or change is marked deprecated in the schema doc and the
data card, with the target removal version and migration path, **at least one MINOR release** before the
breaking MAJOR; where feasible the deprecated field is kept alongside its replacement during the window.
Every schema change is recorded under the schema subsections above with version, date, and rationale,
and triggers a review of the threat model and data card. Published files are immutable, hashed, and
signed; older artifacts are never rewritten in place, so a consumer can always verify exactly which
schema version and which build a file conforms to.

[Unreleased]: https://github.com/ChelseaKR/nearmiss/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/ChelseaKR/nearmiss/releases/tag/v0.1.0
