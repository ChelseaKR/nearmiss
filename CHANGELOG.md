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
<!-- claim:dataset-schema-prose -->
- **Published dataset schema** — `schema/dataset.schema.md`, currently `1.1.0`. The contract for the
  open per-city `data/published/<city-slug>.geojson` artifact (e.g. `davis.geojson`).
  Carried per file in `metadata.schema_version`. This contract is **prose only**
  (`schema/dataset.schema.md`); a machine-readable JSON Schema mirror validated in CI is **planned,
  not yet committed** (only `schema/report.schema.json`, the intake contract, is a JSON Schema today).
  [Correction: an earlier revision of this entry claimed a "mirroring JSON Schema validated in CI"
  for the dataset — that JSON Schema does not exist yet; the dataset contract is the prose file.]
<!-- /claim:dataset-schema-prose -->

Both schemas follow the **versioning and deprecation policy** in
[`schema/dataset.schema.md`](schema/dataset.schema.md#7-versioning-and-deprecation-policy), summarized
under [Schema-versioning policy](#schema-versioning-policy) at the foot of this file. In short: PATCH =
clarifications, MINOR = backward-compatible additive changes (flag and hazard vocabularies are additive,
never silently repurposed), MAJOR = a breaking change — including **adding a newly-required field**.
Breaking changes are announced at least one MINOR release ahead with a deprecation window and a stated
migration path; published artifacts are immutable and hashed and are never rewritten in place.

Releases will be tagged and signed (gitsign) starting with the first actual tagged release; conventional-commit history backs every entry.

> **Note (2026-07-05):** `git tag` is currently empty — **no version has ever been tagged, released, or
> signed.** The `[0.1.0]` entry below records a versioned, verified *milestone* on `main`, not a
> published release; see the note under its heading. This corrects a prior version of this file that
> incorrectly stated the release was signed. A tag-triggered release workflow (build, SBOM, keyless
> cosign signing, SLSA provenance, GitHub Release) that would make "released and signed" literally true
> does not exist yet and is the top open item toward a real `v0.1.0`.

## [Unreleased]

Changes land here first. The pipeline, statistics, publishing, briefs, accessible web view, and the
first published dataset specified for `0.1.0` are now **implemented and verified** and have been moved
into the `[0.1.0]` release below. The items that remain genuinely **not yet implemented** are tracked
under **Planned** within `0.1.0` (real geocoder adapters, more cities, the deeper axe + manual
NVDA/VoiceOver audit, reproducible notebooks, a committed hashed `requirements.lock`, and benchmarking);
each will move here under its own `### Added` entry as it lands.

### Added

- **Hashed CI installs.** `make lock-dev` compiles the dev toolchain (`.[dev]`: pytest, ruff, mypy,
  pip-audit, babel, ...) to a new committed, hashed `requirements-dev.lock`. Every CI job in
  `.github/workflows/ci.yml` now installs from it with `pip install --require-hashes`, then the local
  package `--no-deps -e .`, instead of resolving `pip install -e ".[dev]"` fresh on every run. Closes
  `audit-2026-07-05/nearmiss-REMEDIATION.md` P1-4.
- **Single-sourced version strings.** `publish.py`'s embedded and sidecar metadata now read
  `dataset_version` and `schema_version` from the new `src/nearmiss/versions.py`
  (`DATASET_VERSION`, `DATASET_SCHEMA_VERSION`), instead of hand-duplicated `"0.1.0"` / `"1.0.0"`
  literals; `models.Report.schema_version` reads the same module's `REPORT_SCHEMA_VERSION`. No
  version string now exists in more than one place in the source.
- **Tag-triggered release pipeline.** New `.github/workflows/release.yml`: on a `vX.Y.Z` tag, it
  re-checks version consistency (tag == `pyproject.toml` == installed `__version__`) and the CHANGELOG
  entry, re-runs `make verify` at the tagged commit, builds the sdist + wheel, generates a CycloneDX
  1.7 SBOM, Sigstore-signs (keyless, OIDC) the sdist, wheel, SBOM, **and every published city
  GeoJSON**, attaches SLSA build provenance, cuts a GitHub Release, and publishes to PyPI via Trusted
  Publishing (OIDC — no stored token). See "How to verify a release" in
  [`docs/DATA-CARD.md`](docs/DATA-CARD.md). **Not yet exercised**: no tag has been pushed and PyPI
  Trusted Publishing has not yet been registered for this repository — see the NOTE at the top of
  `release.yml`.

- **Moderation transparency report** (`nearmiss moderate stats`). Publishes an aggregate, privacy-floored
  view of the moderation queue: submission totals by status (pending/approved/rejected), review-flag
  frequencies, rejection-reason **category** counts, and the median review latency in hours
  (`received_at` → `decided_at`). Rejection free text is never emitted — a small fixed taxonomy
  (`duplicate`, `spam`, `identifier-leak`, `invalid-location`, `off-topic`, `other`) buckets it first.
  Every per-cell count passes through the same k-anonymity floor as the published map data
  (`min_publish_n`, default 3): a non-zero cell below the floor is withheld (`null`) and tallied under
  `withheld_cells`, so "how many did not make it" stays explicit without exposing a group too small to
  be anonymous. `--out PATH` writes a dated Markdown (`docs/audits/YYYY-MM-DD-moderation.md` style) or
  JSON artifact. Submissions now carry a `decided_at` timestamp (set on approve/reject; legacy queue
  entries without it load fine and are excluded from latency).

- **FIX-02: network-topology spatial weights for Getis-Ord Gi\*.** `stats/getis_ord.py` previously
  decided Gi\* neighbors with a straight-line (haversine) centroid distance band, contradicting
  METHODOLOGY §8.2's claim that neighbors are "defined on the street network ... not naive
  straight-line distance." A new `network.py` (`SegmentGraph`) builds a segment-adjacency graph from
  the same polylines the pipeline already snaps reports to (two segments are adjacent when they
  share an endpoint — a real intersection — within the new `gi_node_snap_m` threshold) and computes
  network-distance neighbors via a band-bounded Dijkstra; `getis_ord_star` now takes a precomputed
  neighbor map instead of centroids and a distance band. `tests/test_network.py` includes the barrier
  fixture (two parallel, unconnected streets close in straight-line terms) asserting the network and
  Euclidean answers disagree and the network answer is what is published. See
  `docs/ideation/02-large-scale-fixes.md` FIX-02.

### Changed

- This changes every published `getis_ord_z` / `getis_ord_significant` value (a dataset content
  change, not a schema change) — see the per-city `dataset_version` bump below.
- Pluggable `SourceAdapter` framework (`src/nearmiss/adapters/`) with declarative TOML field
  crosswalks (`src/nearmiss/adapters/crosswalks/`), validated at load time against the intake
  schema's closed enums. `tools/fetch_bikemaps.py` is migrated onto it, and the previously-orphaned
  SimRa (TU Berlin) adapter lands as its second implementation (`tools/fetch_simra.py`, `make simra`).
  Every adapter returns a per-source `Provenance` block (license, bias label, bias notes) alongside
  its reports; see `docs/REAL-DATA.md#source-adapters` and
  `docs/DATA-CARD.md#known-reporting-biases-who-is-over--and-under-represented`. Adapter conformance
  is covered by `tests/test_adapters_conformance.py`. (EXP-04)

### Intake report schema (`schema/report.schema.json`)

- No changes since `1.0.0`.

### Published dataset schema (`schema/dataset.schema.md`)

- **`1.1.0` (MINOR, backward-compatible additive)** — Exposure trust tiers, corroboration, an
  exposure floor, and a staleness flag (FIX-04, `docs/ideation/02-large-scale-fixes.md`).
  `models.Exposure` gained `tier` (`observed`/`modeled`/`proxy`/`unknown`) and optional
  corroborating `sources`; `loaders.load_exposure` accepts both, defaulting older exposure rows to
  `tier="unknown"` rather than silently promoting them. Published GeoJSON features gained
  `exposure_tier` and `exposure_disagreement` (null unless corroborated by 2+ sources); the
  `quality_flags` vocabulary gained `exposure_stale`, raised when a feature's `exposure_date` is
  more than a configured threshold (`exposure_stale_days`) from the reports its rate is built
  from. A new `exposure_floor` config threshold treats a denominator at or below the floor as
  `exposure_unknown` rather than a giant, meaningless rate. All additions are optional/nullable;
  no existing field changed name, type, or meaning. See `schema/dataset.schema.md` §4.2/§4.6 and
  `docs/DATA-CARD.md`.
  The same `1.1.0` version also carries the other backward-compatible feature-property additions
  that landed alongside it: `rates_by_type` (per-hazard-type rate layers, FIX-06) and
  `rate_sensitivity_delta` (quality-tier sensitivity split, FIX-07), both required, aggregate-only,
  and additive.
- `metadata.methods` gained two new keys (`getis_ord_neighbors`, `getis_ord_node_snap_m`) —
  additive to the free-form `methods` provenance object, not part of the versioned feature schema
  (FIX-02).

### Data (per-city `dataset_version`, in `data/published/`)

- `davis` and `riverside`: `0.1.0` -> `0.1.1`. Regenerated with FIX-02's network-topology Gi* weights
  (above); every feature's `getis_ord_z` / `getis_ord_significant` may have changed relative to the
  prior `0.1.0` release, though the known-answer fixtures still recover the same planted hotspots.

## [0.1.0] - 2026-06-16 (versioned milestone — not yet tagged or published)

> **Correction (2026-07-05):** despite the heading and the prose below reading like a shipped release,
> **this version has never been git-tagged, never had a GitHub Release cut, and nothing under it is
> signed.** `pyproject.toml` carries `version = "0.1.0"` and this section records that the work
> described below is implemented and verified on `main` as of 2026-06-16 — but "released" in this
> entry means "specified and verified," not "tagged and published." Treat every "release" below as
> "milestone" until a real `git tag -s v0.1.0` (or later `v0.1.x`) exists.

A **working analysis engine** plus its specification and contracts, verified on `main` at this date.
This milestone covers the architecture, the two data-contract schemas, the full documentation set,
governance and community-health files, the CI and quality-gate scaffolding, **and** the implemented and
verified pipeline, statistics, publishing tooling, advocacy brief, read-only server, accessible web data
view, known-answer test fixtures, and the first published Davis demo dataset. A small set of items
remains specified-but-pending and is listed under **Planned** below.

The project ships as a **dataset and analysis**, not an app; the web view is a read-only window onto
the published data. The repository is now **public** (this line previously said "private during
pre-1.0 development," which stopped being true once the repo was made public; see README's status
badge). This milestone is labeled **`0.1.0` / pre-1.0**: the schemas are stable enough to build against
under the deprecation policy, but
the engine has so far been exercised only against the **Davis demo** (synthetic known-answer fixtures
plus one published demo corridor set), not calibrated against a breadth of real corridors; rate
magnitudes, exposure sources, and bias adjustments may still move between `0.1.x` releases.

### Added — schema and intake contract

- **Intake report schema** `schema/report.schema.json` (`report.schema.json` version `1.0.0`,
  JSON Schema draft 2020-12). Defines a single incoming road-hazard / near-miss report with required
  `schema_version`, `id` (UUID, not derived from reporter identity), `occurred_at` (RFC 3339 with
  explicit offset), `location`, `mode` (e.g. `cyclist`), `hazard_type` (close-pass, door-zone,
  blind-corner, `surface_hazard`, and related categories), and `severity`. The intake contract is
  designed to accept full submitted coordinate precision and an optional pseudonymous reporter token;
  such precise reports are specified as **private and gitignored** under `data/raw/` and are never to
  be published as-is (**HR4**).
- **Published dataset schema** `schema/dataset.schema.md` — the human-readable published-dataset
  contract (mirrored by a JSON Schema validated in CI), including the versioning and deprecation policy.
  Establishes the `FeatureCollection` with versioned `metadata`, per-feature rate / CI / `n`,
  per-feature exposure provenance, the additive `quality_flags` vocabulary, the WGS84 / RFC 7946
  geometry conventions, and the "guaranteed absent" privacy list. Note that the published dataset
  intentionally carries **no per-report `mode` field** (a quasi-identifier withheld for privacy).

### Added — analysis engine, pipeline, and CLI

The pure-typed-Python package in `src/nearmiss/`. Its **only** runtime dependency is `jsonschema`; it
uses a local equirectangular projection and pure-Python statistics rather than `numpy`/`shapely`/
`pyproj` (recorded in [`docs/adr/0003`](docs/adr/)).

- **`intake.py`** — validates each submission against the report schema before it lands in the private
  raw store, routing by `schema_version`. Intake attaches no denominators, rates, or intervals; those
  are computed downstream and never claimed at intake.
- **`pipeline/`** — pure, recorded transforms with plain, inspectable data between stages
  (`dedupe`, `geocode`, `snap`, `classify`, `quality`):
  - **dedupe** — collapses duplicate and near-duplicate submissions of the same event.
  - **geocode** — resolves locations to coordinates. **Note:** today this stage is a **pass-through**
    for reports that already carry coordinates; real geocoder adapters for address-only imports are
    still **Planned** (below).
  - **snap-to-segment** — snaps each report to a street segment, the unit of aggregation and exposure.
  - **classify** — normalizes `hazard_type` and `mode` into the analysis vocabulary.
  - **quality-flag** — annotates reports with quality signals that carry through to per-feature
    `quality_flags` in the published dataset.
- **`exposure.py`** — attaches an exposure denominator to each segment from documented, versioned
  sources, recording `exposure_source` and `exposure_date` **per feature** so a stale or swapped layer
  is visible, not silent. Segments with no available denominator are carried as `exposure_unknown`,
  not silently dropped (**HR1**).
- **`stats/rates.py`** — computes every risk figure as a **rate normalized by exposure**, never a raw
  count, and attaches a confidence interval and an `n` to every published rate, ranking, and
  comparison: **Byar's Poisson confidence intervals** for rates and **Wilson intervals** for
  proportions. Small-sample segments are flagged `low_sample` and shown as uncertain rather than ranked
  as certain (**HR1**, **HR2**).
- **`stats/bias.py`** — characterizes **reporting bias** as a first-class output: who is over- and
  under-represented, and what that does to the conclusions, stated plainly rather than hidden (**HR3**).
- **`stats/kde.py`** — kernel density estimation for a continuous report/risk surface, with the
  bandwidth and the smoothed quantity documented; a KDE of raw counts is labeled **report volume**,
  never **danger**.
- **`stats/getis_ord.py`** — Getis-Ord Gi\* to identify **statistically significant** hot and cold
  spots, with the significance level and multiple-comparison correction stated, so "hotspot" means a
  tested cluster rather than a bright patch on a heat map.
- **`publish.py`** — emits the open artifacts: the aggregated open GeoJSON (full dataset-schema fields)
  with its `sha256`/methods/summary metadata sidecar, enforcing the privacy invariant described under
  **Added — published dataset** below (**HR4**, **HR5**).
- **`brief.py`** — generates advocacy briefs from the published dataset, carrying intervals and the
  bias caveats through to the prose so a brief cannot quietly overclaim.
- **`server.py`** — a **read-only** server over the published dataset.
- Supporting modules: `config.py`, `geometry.py`, `models.py`, `loaders.py`, `validation.py`,
  `engine.py`, `util.py`, and `errors.py`.
- **`__main__.py` argparse CLI** — `nearmiss intake|pipeline|analyze|publish|brief|run|serve|version
  --config <cfg>`. The `pipeline` subcommand accepts `--dump` to emit intermediate clean records for
  debuggability.
- **Config-as-data** — `config.py` loads `config/davis-demo.toml` (cities, paths, thresholds, jitter).

### Added — known-answer fixtures and tests

- **Synthetic known-answer fixtures** committed under `tests/fixtures/davis/` (generated by
  `tools/make_fixtures.py`): a planted hotspot `seg-06` (low exposure, rate `20.0`/1000, uniquely
  Getis-Ord-significant at `z=3.26`) and a busy **decoy** `seg-03` (the **most** raw reports, `n=20`,
  but a low rate of `2.5` that ranks 6th) — so the tests prove the engine recovers risk rate rather
  than report volume.
- **27 pytest tests pass**; `ruff` is clean; `mypy --strict` is clean across 35 files. `make demo`,
  `make verify` (lint + type + test + accessibility + security), `make reproduce` (byte-for-byte
  deterministic; asserts `git diff` is clean on `data/published/`), and `make publish` all run.

### Added — accessible web data view

- A framework-free accessible web build in `web/` (`index.html`, `app.js`, `style.css`): a
  **supplementary** SVG map alongside an **authoritative** sortable data table that is the non-visual
  equivalent of the map. Significance and confidence are stated in **text, not color**; the build has a
  skip link and semantic `<th scope>` headers. It passes the **structural** accessibility gate
  `tools/a11y_check.py`. The deeper axe + manual NVDA/VoiceOver audit remains **Planned** (below) and
  the ACR's manual criteria remain a conformance target.

### Added — published Davis demo dataset

- **`data/published/davis.geojson`** — the first published open dataset, 12 street segments with the
  full published-dataset-schema fields (rate, CI, `n`, `quality_flags`, and per-feature exposure
  provenance; WGS84 / EPSG:4326 per RFC 7946), accompanied by **`data/published/davis.metadata.json`**
  (`sha256`, methods, summary).
- **Privacy invariant enforced and tested** (**HR4**): the public artifact carries no per-report
  coordinate, time, reporter, mode, severity, or note, and small-`n` (n < 5) hazard breakdowns are
  suppressed.

### Added — verification and architecture record

- **`docs/audits/2026-06-16-verification.md`** — an audit artifact recording the verification of the
  engine, fixtures, gates, and published dataset on 2026-06-16.
- **`docs/adr/0003`** — the Architecture Decision Record for the pure-Python / planar-geometry decision
  (local equirectangular projection and pure-Python statistics; `jsonschema` as the only runtime
  dependency).

### Added — documentation

- `README.md`, `CONTRIBUTING.md`, `SECURITY.md`, `NOTICE`, and an Apache-2.0 `LICENSE`.
- `docs/METHODOLOGY.md` (the intended approach to exposure, rates, intervals, bias, KDE, and
  Getis-Ord Gi\*), `docs/DATA-CARD.md`, `docs/THREAT-MODEL.md`, and `docs/ACCESSIBILITY.md`.
- `docs/accessibility/ACR.md` — a committed **VPAT 2.5 (Rev 508)** Accessibility Conformance Report.
  Its manual-review criteria remain a conformance **target** pending the deeper audit (see **Planned**);
  the shipped web view passes the structural gate today.
- `docs/adr/` — Architecture Decision Records, including
  `0001-record-architecture-decisions.md`, `0002-exposure-normalization-and-confidence-intervals.md`,
  and `0003` (pure-Python / planar-geometry decision).
- `docs/audits/` — the audit log directory, holding the `2026-06-16-verification.md` verification record
  and established for further audits.

### Added — governance and community health

- Governance and community-health files: `CONTRIBUTING.md`, `SECURITY.md` (disclosure process),
  `.github/CODEOWNERS`, and the conventional-commit and signed-release conventions that back this
  changelog.

### Added — CI, tooling, and quality gates

- GitHub Actions CI (`.github/workflows/ci.yml`) **scaffolding** that is designed to gate every change
  on the following jobs. Actions are pinned by **version tag** (e.g. `@v4`) and kept current by
  Dependabot; pinning to commit SHAs is a hardening goal, not a current fact. The jobs install the
  project with `pip install -e ".[dev]"` and run:
  - **lint** — `ruff` (lint, import order, format check). **Clean** on the current tree.
  - **type** — `mypy --strict`. **Clean** across 35 files.
  - **test** — `pytest`. Runs against the committed **synthetic fixtures with known answers**
    (`tests/fixtures/davis/`): the planted hotspot is recovered by Getis-Ord Gi\* and the busy decoy is
    correctly demoted; **27 tests pass**.
  - **accessibility** — `tools/a11y_check.py` runs a **structural** gate on the web view today and
    passes. The deeper automated `axe` run and the manual NVDA/VoiceOver passes required per
    `docs/ACCESSIBILITY.md` are **Planned** (below) and tracked outside this structural gate.
  - **security** — `pip-audit --strict`, `gitleaks`, and `CodeQL`. `pip-audit` and `CodeQL` need
    network and run in CI; they are **not** yet exercised locally.
  - **reproducibility** — `make reproduce` rebuilds `data/published` from inputs **byte-for-byte
    deterministically** and asserts `git diff` is clean on `data/published/`.
- **`.pre-commit-config.yaml`** — the pre-commit configuration wiring the local lint/type/format hooks.
- **`Makefile`** — defines the project gates and developer entry points, including `make install`
  (`pip install -e ".[dev]"`, the working install today), `make demo`, `make verify`
  (lint + type + test + accessibility + security), `make publish`, `make reproduce` (byte-for-byte
  deterministic), and `make accessibility`; plus `make lock` (generates the reproducible
  `requirements.lock` via `pip-compile --generate-hashes`, whose output is **not committed yet**).
- Dependency and supply-chain conventions: the working install is `pip install -e ".[dev]"`. A hashed
  lockfile, `requirements.lock` (generated by `pip-compile --generate-hashes`), is the **planned**
  reproducible-install artifact and is **not committed yet**. `Dependabot` (`.github/dependabot.yml`),
  `.github/CODEOWNERS`, conventional commits, semantic versioning, and **signed releases** round out the
  baseline.

### Planned — specified, not yet implemented

These remain **specified, not yet implemented**. They are listed here so the design intent is recorded;
each will move to `[Unreleased]` (and then to a release) as it actually lands.

- **Real geocoder adapters** for address-only imports. The shipped `geocode` stage is a **pass-through**
  for reports that already carry coordinates; resolving bare addresses against a documented, versioned
  reference is still to come.
- **More cities beyond the Davis demo**, and broader **real exposure layers** (observed bike/ped counts
  or demand models for additional corridors) to replace the demo's exposure inputs.
- **The deeper accessibility audit** — an automated `axe` run plus a manual NVDA/VoiceOver review. The
  committed `tools/a11y_check.py` gate is **structural only**; the ACR's manual criteria remain a
  conformance target until this audit is done.
- **Reproducible analysis notebooks** — `notebooks/` is still documentation only.
- **A committed hashed `requirements.lock`** — generated via `make lock`
  (`pip-compile --generate-hashes`); **not committed yet**.
- **Performance benchmarking** — the engine is not yet benchmarked.

### Security

- Established the supply-chain and secret-scanning baseline above (`pip-audit --strict`, `gitleaks`,
  `CodeQL`, Dependabot, version-tag-pinned actions, signed releases) and the disclosure process in
  `SECURITY.md`. `pip-audit` and `CodeQL` need network and run in CI only; they are not yet exercised
  locally. The committed hashed lock artifact (`requirements.lock`) remains **Planned**, not yet active.
- **Privacy-by-construction is now enforced and tested.** Precise reports stay private and gitignored,
  and `publish.py`'s privacy invariant keeps the published artifact free of any per-report coordinate,
  time, reporter, mode, severity, or note, and suppresses small-`n` (n < 5) hazard breakdowns; tests
  assert the "guaranteed absent" list (**HR4**).

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
- **MAJOR** — a **breaking change**: removing or renaming a property, **adding a newly-required field**,
  changing a type or unit, changing the meaning of a field, changing the default CI level or the
  significance / correction method in a way that alters how published numbers read, or changing the
  geometry/CRS conventions.

**Deprecation.** A field slated for removal or change is marked deprecated in the schema doc and the
data card, with the target removal version and migration path, **at least one MINOR release** before the
breaking MAJOR; where feasible the deprecated field is kept alongside its replacement during the window.
Every schema change is recorded under the schema subsections above with version, date, and rationale,
and triggers a review of the threat model and data card. Published files are immutable, hashed, and
signed; older artifacts are never rewritten in place, so a consumer can always verify exactly which
schema version and which build a file conforms to.

[Unreleased]: https://github.com/ChelseaKR/nearmiss/commits/main
<!-- No [0.1.0] comparison/release link is published here: v0.1.0 has never been git-tagged and no
     GitHub Release exists (see the correction note above and under "## [0.1.0]"). The prior link
     (`.../releases/tag/v0.1.0`) pointed at a release page that does not exist. This link is restored,
     pointing at a real tag, once `v0.1.0` is actually cut. -->
