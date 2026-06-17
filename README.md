<div align="center">

# nearmiss

**An open dataset and statistically honest analysis of road hazards and near misses, for safe-streets advocacy.**

[![CI](https://github.com/ChelseaKR/nearmiss/actions/workflows/ci.yml/badge.svg)](https://github.com/ChelseaKR/nearmiss/actions/workflows/ci.yml)
[![License: Apache-2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![Status: beta](https://img.shields.io/badge/status-beta-orange.svg)](#roadmap)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](pyproject.toml)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-261230.svg)](https://docs.astral.sh/ruff/)
[![Types: mypy strict](https://img.shields.io/badge/types-mypy%20strict-blue.svg)](https://mypy-lang.org/)
[![WCAG 2.2 AA](https://img.shields.io/badge/accessibility-WCAG%202.2%20AA-success.svg)](docs/ACCESSIBILITY.md)
[![Conventional Commits](https://img.shields.io/badge/commits-conventional-fe5196.svg)](https://www.conventionalcommits.org/)
[![Cite this](https://img.shields.io/badge/cite-CITATION.cff-informational.svg)](CITATION.cff)

</div>

> Turns the hazard reports cyclists and pedestrians already make — the close pass, the door zone,
> the blind corner, the pothole that nearly threw someone — into a rigorous, open, reusable dataset
> and a statistically honest analysis of where the danger actually is. Report intake, a documented
> pipeline, and analysis that refuses to lie with a heat map: it normalizes by exposure, reports
> confidence intervals, and uses real spatial-hotspot statistics instead of mistaking "where people
> bothered to report" for "where it is dangerous." Outputs are advocacy-ready and reproducible.
> **The dataset and the analysis are the product, not an app.**

**Status:** beta · independent personal open-source project · Apache-2.0 · unaffiliated with any
employer or client; contains no proprietary or client material. Owned by cyclists and advocates, not
by a city. This is not a 311 queue and not a complaint inbox for a public works department; it is a
community-owned evidence base.

> **Where this is right now (read first):** the analysis engine is implemented and verified. The
> intake, the dedupe/geocode/snap/classify/quality pipeline, the exposure normalization and statistics
> (Poisson/Wilson confidence intervals, bias, KDE, Getis-Ord Gi\*), publishing, the accessible web data
> view, the CLI, the known-answer test suite, and a published Davis demo dataset all exist and pass the
> gates: `make demo`, `make verify`, and `make reproduce` run, 27 tests pass, and ruff + mypy `--strict`
> are clean. What remains is the still-pending list — real geocoder adapters, more cities, the deeper
> axe-plus-manual screen-reader accessibility audit, reproducible notebooks, a committed hashed
> lockfile, and benchmarking (see [Roadmap](#roadmap)). The repository is still private during pre-1.0
> development.

---

## Table of contents

- [Why this exists](#why-this-exists)
- [What it does](#what-it-does)
- [Hard rules (enforced, not aspirational)](#hard-rules-enforced-not-aspirational)
- [Quick start](#quick-start)
- [Install](#install)
- [Usage](#usage)
- [Architecture](#architecture)
- [The analysis engine (the actual product)](#the-analysis-engine-the-actual-product)
- [Quality attributes (engineered for, not assumed)](#quality-attributes-engineered-for-not-assumed)
- [Accessibility and Section 508 conformance](#accessibility-and-section-508-conformance)
- [Data, privacy, and ethics](#data-privacy-and-ethics)
- [Repository layout](#repository-layout)
- [Roadmap](#roadmap)
- [Contributing](#contributing)
- [Security](#security)
- [Governance and independence](#governance-and-independence)
- [License and citation](#license-and-citation)
- [Acknowledgements and related work](#acknowledgements-and-related-work)

---

## Why this exists

Vulnerable road users absorb most of the risk on streets and produce almost none of the official
data, because near misses leave no police report and most collisions involving people on bikes and on
foot are undercounted even when they do. Advocates are then told "show us the data" by the same
agencies whose data does not capture the problem. The honest answer is to collect it carefully and
analyze it without cheating.

The hard part is not the map. The hard part is that report counts are biased by who reports, where
they ride, and which streets are even traveled, and a naive heat map will confidently point at the
busiest bike route and call it the most dangerous one. nearmiss exists to do the harder, correct
thing and to make the dataset open so others can check it. It is a sibling to
[`davis-bike-hazard-map`](#acknowledgements-and-related-work); there the product is the map, here it
is the data and the statistics under it.

## What it does

- **Intakes** a hazard or near-miss report — location, time, mode, type (close pass, dooring, surface
  hazard, sightline, signal, debris), severity, and an optional note — through a simple form, an
  import path, or a documented JSON submission, validated against a
  [published schema](schema/report.schema.json).
- **Pipelines** raw reports into a clean, versioned dataset: deduplication, geocoding to coordinates,
  snapping to a street segment, classification, and quality flags, with every transform recorded so a
  result traces back to its inputs.
- **Normalizes by exposure.** Counts are turned into rates against a denominator (bike and pedestrian
  volume from counts, Strava/StreetLight-style exposure layers, or modeled demand), because three
  reports on a quiet street can mean more than thirty on the city's busiest route.
- **Quantifies uncertainty.** Every rate and comparison carries a **confidence interval**;
  small-sample segments are shown as uncertain, not as bold claims. Reporting bias is modeled and
  stated, never ignored.
- **Finds real hotspots.** Spatial-hotspot statistics (**kernel density estimation** for surfaces,
  **Getis-Ord Gi\*** for statistically significant clusters) identify where danger concentrates
  beyond what chance and exposure explain.
- **Publishes** open data (**GeoJSON** aligned to a [documented near-miss/collision
  schema](schema/dataset.schema.md)), reproducible analysis notebooks, and advocacy-ready outputs:
  ranked locations with intervals, plain-language briefs, and maps with honest legends and a
  non-visual table equivalent.

## Hard rules (enforced, not aspirational)

1. **No rate without a denominator.** A raw count is never published or mapped as if it were risk.
   Every risk claim is a rate normalized by an exposure estimate, and the exposure source and its
   date are stated alongside it. A map of raw counts is labeled as report volume, never as danger.
2. **No estimate without an interval.** Every published rate, ranking, and comparison carries a
   confidence interval and an n. A segment with too few reports to say anything is shown as uncertain,
   not ranked as if it were certain.
3. **Reporting bias is named, not hidden.** The analysis states who is likely over- and
   under-represented (route choice, demographics, app access, language) and what that does to the
   conclusions. A finding that could be an artifact of where people report is flagged as such.
4. **Contributor privacy is protected.** Reports are pseudonymous; exact home-end coordinates are
   fuzzed before publication; no report is published at a precision that could identify a specific
   person's routine. The open dataset is aggregated and jittered; raw precise reports stay private.
5. **Open and reproducible end to end.** The schema, the pipeline, the notebooks, and the published
   GeoJSON are all open, and `make reproduce` regenerates every figure and table in the briefs from
   raw inputs. A claim no one can reproduce is not published.

These five are encoded in tests, CI gates, and the publish path. See
[`docs/adr/0002-exposure-normalization-and-confidence-intervals.md`](docs/adr/0002-exposure-normalization-and-confidence-intervals.md)
for why rules 1 and 2 are non-negotiable, and [`docs/THREAT-MODEL.md`](docs/THREAT-MODEL.md) for how
rule 4 is defended.

## Quick start

```bash
# 1. Clone
git clone https://github.com/ChelseaKR/nearmiss.git
cd nearmiss

# 2. Install (editable, with dev tooling and pre-commit hooks)
make install

# 3. See it work end to end on synthetic fixtures with known answers —
#    runs the full pipeline and renders a sample advocacy brief.
make demo

# 4. Run the full merge gate locally (lint, types, tests, accessibility, security)
make verify
```

`make demo` uses the planted-hotspot fixtures in `tests/fixtures/`, so it needs no real data, no API
keys, and no cloud account. If `make demo` recovers the planted hotspots and `make verify` is green,
your environment is good. Run `make help` to list every target.

## Install

Requires **Python 3.11+** and a standard geospatial toolchain (installed via the package extras). No
database and no always-on service are required to run the analysis; intake can run serverless and
scale to zero.

```bash
# From a clone (the working install today, recommended for contributors)
make install                 # pip install -e ".[dev]" + pre-commit install

# As a tool, isolated (the packaging/release goal once published)
pipx install nearmiss

# Planned reproducible path: a generated, hashed lock
python -m pip install --require-hashes -r requirements.lock
# requirements.lock is produced by `make lock` (pip-compile --generate-hashes); it is a generated
# artifact and is not committed yet — `pip install -e ".[dev]"` is the install that works today.
```

A container image and a one-command serverless intake deploy are described in
[`infra/`](infra/). Configuration — cities, exposure sources, thresholds, and jitter — lives in
versioned files under [`src/nearmiss/config.py`](src/nearmiss) and city config, never in code.

## Usage

```bash
# Validate and intake reports (form export, import file, or documented JSON)
nearmiss intake path/to/reports.json        # validated against schema/report.schema.json

# Run the documented pipeline: dedupe -> geocode -> snap -> classify -> quality-flag
nearmiss pipeline --city davis

# Attach exposure denominators and compute exposure-normalized rates with intervals
nearmiss analyze --city davis               # rates + CIs + bias report + KDE + Getis-Ord Gi*

# Publish the open GeoJSON and the aggregated, jittered public dataset + data card
make publish

# Regenerate every figure and table in the briefs from raw inputs (the reproducibility proof)
make reproduce

# Serve the accessible map with its equivalent sortable list/table view (read-only)
nearmiss serve                              # WCAG 2.2 AA; data view is the non-visual equivalent

# Dump intermediate datasets at any stage for inspection/debugging
nearmiss pipeline --city davis --dump
```

Every published number can be traced from a brief figure back through a notebook cell, a statistic, a
cleaned record, and finally a raw report — see [Traceability](#statistical-correctness-and-result-quality)
and [`docs/METHODOLOGY.md`](docs/METHODOLOGY.md).

## Architecture

```text
nearmiss/
├── README.md
├── LICENSE  ·  NOTICE  ·  CHANGELOG.md  ·  CITATION.cff
├── CONTRIBUTING.md  ·  CODE_OF_CONDUCT.md  ·  SECURITY.md
├── Makefile                       # help, install, verify, reproduce, demo, publish, …
├── schema/
│   ├── report.schema.json         # incoming report schema (validated at intake)
│   └── dataset.schema.md          # published GeoJSON schema; alignment to near-miss/collision standard
├── src/nearmiss/
│   ├── intake.py                  # form/import/JSON intake → validate → raw store
│   ├── pipeline/                  # dedupe.py, geocode.py, snap.py, classify.py, quality.py
│   ├── exposure.py                # denominator layers: counts, demand model, exposure imports
│   ├── stats/                     # rates.py (CIs), bias.py, kde.py, getis_ord.py
│   ├── publish.py                 # build open GeoJSON + aggregated, jittered public dataset
│   ├── brief.py                   # generate advocacy briefs (ranked locations, intervals, prose)
│   ├── server.py                  # accessible map + equivalent data table; read-only
│   └── config.py                  # cities, exposure sources, thresholds as versioned files
├── notebooks/                     # reproducible analysis: hotspots, trends, exposure sensitivity
├── web/                           # framework-free WCAG 2.2 AA map UI (map + list/table view)
├── data/
│   ├── raw/                       # private precise reports (gitignored — never committed)
│   └── published/                 # committed open GeoJSON + dataset card
├── infra/                         # optional serverless intake + scheduled rebuild; scale-to-zero
├── tests/
│   └── fixtures/                  # synthetic report sets with known hotspots and known answers
├── docs/                          # METHODOLOGY, DATA-CARD, THREAT-MODEL, ACCESSIBILITY, ADRs, audits/, accessibility/
└── .github/                       # CI, CodeQL, Dependabot, issue/PR templates, CODEOWNERS
```

Reports enter through `intake.py`, validated against `report.schema.json`, and land in a private raw
store. The pipeline is a sequence of pure, recorded transforms (dedupe, geocode, snap to segment,
classify, quality-flag) producing a clean internal dataset. The statistics layer is where the value
is: `exposure.py` attaches denominators, `rates.py` computes rates with confidence intervals,
`bias.py` characterizes and reports the reporting bias, and `kde.py`/`getis_ord.py` produce the
hotspot surfaces and significant clusters. `publish.py` emits the open GeoJSON and an aggregated,
jittered public dataset; `brief.py` turns the results into advocacy outputs. The map server reads only
published artifacts and always ships an equivalent table. Nothing in the public path exposes a precise
raw report.

## The analysis engine (the actual product)

The deliverable is a dataset and an analysis that hold up when a skeptical traffic engineer pushes
back. That standard drives every statistical choice. The full treatment is in
[`docs/METHODOLOGY.md`](docs/METHODOLOGY.md); the summary:

**From counts to rates.** Reports are counts, and counts confound danger with traffic. `exposure.py`
attaches a denominator per segment — observed bike/pedestrian volume where counts exist, a demand
model or an exposure layer where they do not — and records which source and date were used. `rates.py`
computes the rate and a **confidence interval** appropriate to the count model (small-count methods for
sparse segments), so a segment is never ranked above another on a difference the data cannot support.

**Naming the bias.** `bias.py` makes the reporting bias explicit: it compares the reporter pool and
the geographic spread of reports against ridership and demographic baselines, and reports where the
dataset likely over- or under-represents. A conclusion that could be an artifact of who reports is
labeled, and the briefs say so in plain language rather than burying it.

**Honest hotspots.** A raw kernel density surface looks authoritative and is easy to misread, so it is
always exposure-aware and labeled as report intensity unless normalized. `getis_ord.py` computes
**Getis-Ord Gi\*** to find clusters that are statistically significant given spatial structure and
exposure, not merely places with more reports. The output distinguishes "hot because dangerous" from
"hot because busy."

**Reproducibility as the proof.** Every figure and number in a brief is produced by a notebook from
the raw inputs; `make reproduce` runs them end to end. The fixture suite includes synthetic report
sets with planted hotspots and known correct answers, so the pipeline and statistics are tested
against ground truth, and the published dataset carries a [data card](docs/DATA-CARD.md) stating
sources, methods, limits, and the exposure assumptions behind every rate.

## Quality attributes (engineered for, not assumed)

This section works through the full system-quality-attribute list and ties each to a concrete
decision. Grouped for readability; **every attribute is named and bold**. An advocacy dataset lives or
dies on statistical honesty, reproducibility, and trust, so those clusters carry weight.

### Statistical correctness and result quality

**Correctness** and **accuracy** — rates are computed against exposure, not raw counts, and tested
against synthetic fixtures with known answers. **Precision** and **fidelity** — every rate carries an
n and an interval; coordinates and segments are preserved without lossy rounding before the deliberate
publish-time jitter. **Determinability** and **predictability** — seeded pipelines and analyses yield
the same dataset and figures every run. **Repeatability** and **reproducibility** — `make reproduce`
regenerates every brief figure and table from raw inputs; notebooks are deterministic. **Provability**
— each published number records its method, exposure source, and threshold. **Traceability** — a
mapped hotspot traces from figure → notebook → statistic → cleaned dataset → raw reports.
**Relevance** — findings are exposure-normalized so they reflect risk, not traffic. **Effectiveness**
— the test design (planted-hotspot fixtures, interval-coverage checks) is documented in
[`tests/README.md`](tests/README.md), and the committed fixtures validate it: the tests recover the
planted hotspot `seg-06` and its unique Getis-Ord Gi\* significance (z = 3.26) while the busy decoy
`seg-03` — the most-reported segment — correctly ranks low on exposure-normalized rate.
**Accountability** — the data card and methodology doc state what the numbers do and do not support.

### Standards, interoperability, openness

**Standards compliance** — GeoJSON output aligned to a documented near-miss/collision schema; SPDX
headers; semver; conventional commits. **Interoperability** — published GeoJSON loads in QGIS,
Leaflet, and any GIS; the report schema is documented JSON. **Interchangeability** — exposure sources
(counts, demand model, imports) swap behind one interface. **Compatibility** — CI tests Python 3.11 and
3.12 per [`ci.yml`](.github/workflows/ci.yml); the package is pure-typed-Python with a single runtime
dependency (`jsonschema`), using a local equirectangular projection and pure-Python statistics instead
of numpy/shapely/pyproj per [`docs/adr/0003-pure-python-statistics-and-planar-geometry.md`](docs/adr/0003-pure-python-statistics-and-planar-geometry.md).
**Composability** and **inspectability** — every stage
emits plain, inspectable data others can pipe and check. **Portability** and **distributability** —
the dataset and pipeline move to any city by config, and the published GeoJSON is a single file anyone
can mirror, fork, or redistribute; nothing is bound to one locale or host.

### Privacy, security, accountability

**Confidentiality** — precise raw reports stay private; the public dataset is aggregated and jittered;
home-end coordinates are fuzzed. **Securability** — secrets via env, never committed; intake validates
and rate-limits to resist spam and poisoning. **Integrity** (data) — schema validation at intake and
hashed published artifacts make tampering detectable. **Safety** — no report is published at a
precision that could expose a person's routine; this is tested against the published dataset.
**Autonomy** — the dataset is community-owned and openly licensed, so advocates are not dependent on a
city's data portal. **Vulnerability** management — pip-audit, gitleaks, CodeQL configured in CI;
dependencies installed via `pip install -e ".[dev]"`, with a generated hashed `requirements.lock`
planned. **Auditability** — the audit policy and naming convention are committed in
[`docs/audits/README.md`](docs/audits/README.md), and the first dated audit artifact is committed at
[`docs/audits/2026-06-16-verification.md`](docs/audits/2026-06-16-verification.md); the pipeline records
every transform; the [CHANGELOG](CHANGELOG.md) records every schema change.

### Credibility and transparency

**Credibility** and **transparency** — reporting bias is named in every brief; methodology and limits
are documented; the data card is honest about exposure assumptions. **Demonstrability** — the test
design (planted-hotspot fixtures, interval-coverage checks) is documented in
[`tests/README.md`](tests/README.md), and `make demo` runs the full pipeline over the committed Davis
fixtures and renders a sample brief. **Understandability** — briefs explain the statistics in
plain language for a city-council audience.

### Usability, learnability, reach

**Accessibility** — a structural accessibility gate ([`tools/a11y_check.py`](tools/a11y_check.py)) runs
in `make verify` and the web view ships an authoritative sortable data table carrying the same ranked
locations and intervals as the supplementary map; the deeper axe-plus-manual-screen-reader audit is
still a conformance target.
**Usability** and **convenience** — reporting is a short form; the dataset is one download.
**Learnability**, **familiarity**, **intuitiveness** — the map and table read the way people expect;
the report form asks plain questions. **Interactivity** and **responsiveness** — the map filters and
the table sort quickly on published data. **Discoverability** — the data card, schema, and notebooks
are linked from the first screen. **Seamlessness** — map and table are two views of one published
artifact. **Localizability** — interface and form strings in per-language bundles; the report form is
bilingual where the community is. **Mobility** and **ubiquity** — mobile-first reporting, because
hazards are reported from the roadside.

### Performance, scale, cost

**Efficiency** — an architectural target: an incremental pipeline with spatial statistics over
spatially indexed geometries. **Scalability** and **elasticity** — the targeted design handles a city's
worth of reports, with a parallelizable rebuild and stateless intake. **Timeliness** — scheduled
rebuilds are designed to keep the published dataset current; a rebuild-latency budget in CI is a goal,
not yet a CI step. **Affordability** — scale-to-zero serverless intake and a static
published site keep cost near zero with a budget alarm; advocates without budgets can still run it.
**Process capabilities** and **producibility** — `make verify` runs the full local gate (lint, type,
test, accessibility, security) and CI mirrors it; `make reproduce` rebuilds the published dataset
byte-for-byte and asserts a clean `git diff` on `data/published/`.

### Maintainability, evolvability, modularity

**Maintainability**, **modifiability**, **evolvability** — small pipeline stages and statistics modules
behind interfaces; ruff + mypy strict. **Extensibility** and **flexibility** — new hazard types,
exposure sources, and statistics via adapters and config. **Adaptability** — point nearmiss at a new
city with a config and an exposure layer. **Modularity**, **composability**, **orthogonality** —
intake, pipeline, exposure, statistics, publish, and brief are independent stages. **Simplicity** —
plain data between stages; no hidden state. **Reusability** — the exposure-normalization and hotspot
code are usable on any point dataset. **Analyzability** — typed, documented, with a methodology doc.
**Configurability**, **customizability**, **tailorability** — config-over-code is implemented:
[`config/davis-demo.toml`](config/davis-demo.toml), loaded by
[`src/nearmiss/config.py`](src/nearmiss/config.py), controls cities, paths, thresholds, and jitter
without touching code. **Upgradability** — a documented dependency bump path; versioned schemas with
migrations.

### Reliability, resilience, safety of the pipeline

**Dependability** and **reliability** — a malformed or malicious report is rejected at intake, never
silently corrupting the dataset. **Availability** — the published site is static-friendly and the
intake scales to zero; no always-on component to keep paid. **Fault-tolerance**, **resilience**,
**robustness** — one bad geocode or bad report never aborts the rebuild; the stage flags and
continues. **Recoverability** and **survivability** — the dataset rebuilds from raw via `make
reproduce`; published artifacts are versioned. **Degradability** and **failure transparency** — a
segment with no exposure data is shown as "exposure unknown," not silently dropped or falsely rated.
**Redundancy** — multiple exposure sources can corroborate a denominator. **Stability** and
**durability** — the published GeoJSON schema is versioned in
[`schema/dataset.schema.md`](schema/dataset.schema.md) and schema changes are recorded in
[`CHANGELOG.md`](CHANGELOG.md) with a migration path; stability across releases is a commitment, not
yet a track record (v0.1.0).

### Operability, serviceability, sustainability

**Operability** and **manageability** — a maintainer runbook (run a rebuild, rotate an exposure
source, publish a brief); a pipeline status output. **Administrability** — config-over-code is
implemented; [`src/nearmiss/config.py`](src/nearmiss/config.py) loads
[`config/davis-demo.toml`](config/davis-demo.toml), so thresholds and sources are versioned rather than
coded. **Observability** — structured
logs and metrics on intake and each pipeline stage; rebuilds report coverage and quality-flag counts.
**Debuggability** — the figure → notebook → statistic → dataset → raw trace is defined in
[`docs/METHODOLOGY.md`](docs/METHODOLOGY.md), and `nearmiss pipeline --dump` emits the intermediate
clean records for inspection. **Serviceability / supportability** — issue templates and a "paste this to reproduce" path.
**Deployability** and **installability** — `pipx install`, a container image, one-command serverless
deploy. **Repairability** — most fixes are data or threshold edits, recorded and re-run. **Agility** —
CI smoke suite on every PR. **Autonomy** (operational), **self-sustainability**, **sustainability** —
open data and zero-cost hosting mean the dataset survives without a grant or a city's goodwill.
**Testability**, **inspectability**, **demonstrability** — the planted-hotspot fixtures with known
answers (documented in [`tests/README.md`](tests/README.md)) are committed under
[`tests/fixtures/davis/`](tests/fixtures/davis/), 27 pytest tests pass against them, and `make demo`
runs the full pipeline to make the statistics verifiable.

> Each attribute above maps to a documented decision and, where the implementation exists, a
> verifiable artifact or gate. Where an attribute is still aspirational at beta — the reproducible
> notebooks, real geocoder adapters, the deeper axe-plus-manual accessibility audit, and benchmarking
> remain pending, and some VPAT rows are "Partially Supports" — that is stated plainly rather than
> overclaimed. See the [ACR](docs/accessibility/ACR.md) and the [Roadmap](#roadmap).

## Accessibility and Section 508 conformance

nearmiss targets **WCAG 2.2 Level AA** and conformance with the **Revised Section 508 Standards**
(36 CFR Part 1194), which incorporate WCAG 2.0 A/AA by reference for web content and add the functional
performance criteria of Chapter 3. A community advocacy site is not federal ICT, so 508 is not legally
required here. Building to it anyway is deliberate. The audience includes disabled road users, who are
among the most endangered on bad streets and the most likely to be reading a map of where it is unsafe,
and meeting the standard agencies audit to gives an advocate a clean, public artifact when the analysis
lands in front of a city. Full statement: [`docs/ACCESSIBILITY.md`](docs/ACCESSIBILITY.md).

- A committed **Accessibility Conformance Report (ACR)** using the **VPAT 2.5 (Rev 508)** template
  lives at [`docs/accessibility/ACR.md`](docs/accessibility/ACR.md), with tables for the WCAG 2.x
  A/AA success criteria, the Revised 508 software (Chapter 5) and support-documentation (Chapter 6)
  criteria, and the **Functional Performance Criteria** (use without vision, with limited vision,
  without hearing, with limited reach and strength, with limited cognition).
- The map, the report form, the hotspot legends, and every chart pass automated checks (axe) **and**
  manual screen-reader review (NVDA, VoiceOver). Risk level and significance are conveyed in text and
  pattern, never by color alone; the report form is fully keyboard-operable with clear labels and error
  text.
- A **non-visual equivalent** of the map is provided as an accessible, sortable list and table carrying
  the same ranked locations, rates, intervals, and significance flags, so every finding is reachable
  without seeing the map.
- Accessibility is a **merge-blocking CI gate**; a regression fails the build. The ACR is regenerated
  and re-committed on each release, the same audit-as-artifact discipline applied to the statistics.

## Data, privacy, and ethics

Contributor privacy is treated as a **security property**, not a nicety. Precise raw reports are
private and never committed (`data/raw/` is gitignored); the open dataset is aggregated and jittered,
and home-end coordinates are fuzzed, so no individual's routine can be reconstructed from what is
published. The full reasoning, adversaries, mitigations, and honest residual risk are in
[`docs/THREAT-MODEL.md`](docs/THREAT-MODEL.md); what the published dataset contains, what it omits, and
its known biases and limits are in [`docs/DATA-CARD.md`](docs/DATA-CARD.md). If you believe a published
artifact leaks identifying precision, treat it as a security issue and follow [`SECURITY.md`](SECURITY.md).

## Repository layout

| Area | What's there |
| --- | --- |
| [`schema/`](schema/) | [`report.schema.json`](schema/report.schema.json) (intake) and [`dataset.schema.md`](schema/dataset.schema.md) (published GeoJSON) |
| [`src/nearmiss/`](src/nearmiss/) | intake, pipeline stages, exposure, statistics, publish, brief, accessible server, config |
| [`notebooks/`](notebooks/) | deterministic analysis notebooks; the reproducibility backbone |
| [`web/`](web/) | framework-free WCAG 2.2 AA map UI with list/table equivalent |
| [`data/`](data/) | `raw/` (private, gitignored) and `published/` (open GeoJSON + data card) |
| [`tests/`](tests/) | pytest suites and planted-hotspot fixtures with known answers |
| [`docs/`](docs/) | [METHODOLOGY](docs/METHODOLOGY.md), [DATA-CARD](docs/DATA-CARD.md), [THREAT-MODEL](docs/THREAT-MODEL.md), [ACCESSIBILITY](docs/ACCESSIBILITY.md), [ADRs](docs/adr/), [audits](docs/audits/), [accessibility ACR](docs/accessibility/ACR.md) |
| [`infra/`](infra/) | optional serverless intake + scheduled rebuild; scale-to-zero |
| [`.github/`](.github/) | [CI](.github/workflows/ci.yml), Dependabot, CodeQL, issue/PR templates, CODEOWNERS |

## Roadmap

- **Phase 1 — schema, intake, pipeline.** Publish `report.schema.json`; build validated intake and the
  dedupe/geocode/snap/classify/quality pipeline; synthetic fixtures with planted hotspots. Definition
  of done: raw reports become a clean, versioned dataset reproducibly.
- **Phase 2 — exposure and honest statistics.** `exposure.py` denominators; rates with confidence
  intervals; `bias.py` reporting-bias characterization; `kde.py` and `getis_ord.py` hotspots, all
  tested against fixtures with known answers. Commit a baseline analysis, caveats included.
- **Phase 3 — publish and advocate.** Open GeoJSON aligned to the documented schema; aggregated,
  jittered public dataset with a data card; reproducible notebooks; advocacy briefs; the accessible
  map with list/table equivalent, deployed behind a real URL.
- **Phase 4 — generalize.** A config so any city's reports and exposure layers can be added; an "adapt
  this to your city" guide; optional import paths for existing community report sets.

Releases follow [semver](https://semver.org/) and are recorded in [`CHANGELOG.md`](CHANGELOG.md).

## Contributing

Contributions — a hazard report, a sharper confidence interval, a screen-reader fix, a new city config
— are welcome and held to a simple, hard standard: a change should hold up when a skeptical traffic
engineer pushes back. Start with [`CONTRIBUTING.md`](CONTRIBUTING.md), which covers dev setup, the
local gate (`make verify`), conventional commits, the DCO sign-off, how to propose a versioned schema
change, and the one rule with no exceptions: **no precise raw report data is ever committed.** All
participants are bound by the [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md).

Engineering practices: pytest for every deterministic component with known-answer fixtures; ruff +
mypy strict in CI; reproducible, content-hashed dataset and analysis runs; conventional commits;
pinned, SLSA-friendly GitHub Actions; signed releases; Dependabot; and committed audit artifacts.

## Security

Security and privacy reports go through **GitHub private vulnerability reporting**, not public issues —
see [`SECURITY.md`](SECURITY.md). Scope explicitly includes the privacy and data-integrity threats
specific to this project (deanonymization, report poisoning, exposure-source tampering), not only code
CVEs. Supply chain: pinned and hashed dependencies, pip-audit, gitleaks, and CodeQL run in
[CI](.github/workflows/ci.yml); secrets live in the environment and are never committed.

## Governance and independence

nearmiss is an independent, personal open-source project. It is not affiliated with, sponsored by, or
endorsed by any employer, client, city, or public agency, and it contains no proprietary or client
material — see [`NOTICE`](NOTICE). It is intentionally zero-cost and unfunded, so it survives without a
grant or a city's goodwill. Decisions of consequence are recorded as ADRs in
[`docs/adr/`](docs/adr/).

## License and citation

Licensed under the **Apache License 2.0** — see [`LICENSE`](LICENSE). Apache-2.0 is chosen so the
dataset and the methods spread as widely as possible: other advocates, researchers, and even
cooperative city staff can adopt the schema, reuse the statistics code, and build on the open data
without friction, and Apache's patent grant and permissive terms maximize reuse. The privacy
protections live in the data-publishing rules and the threat model, not in a restrictive license,
because the data itself is meant to be free.

If you use nearmiss in research or advocacy, please cite it — citation metadata is in
[`CITATION.cff`](CITATION.cff), and GitHub renders a ready-to-copy citation from it.

## Acknowledgements and related work

- **`davis-bike-hazard-map`** — a sibling project where the product is the map; here it is the data and
  the statistics under it.
- Built on the shoulders of open geospatial and statistical tooling (GeoJSON, kernel density
  estimation, the Getis-Ord Gi\* local statistic) and the open-data documentation traditions of
  *Datasheets for Datasets* and dataset cards.
- Above all, the cyclists and pedestrians who report the close calls that official data never records.

### Definition of done

An advocacy group can `pipx install nearmiss`, stand up a report form with no cloud account or a cheap
scale-to-zero deploy, run real reports through the pipeline into a clean versioned dataset, produce
exposure-normalized risk rates with confidence intervals and Getis-Ord hotspots that recover known
answers on the test fixtures, publish an open GeoJSON aligned to the documented schema with a data card
that names the reporting bias, regenerate every figure in an advocacy brief with `make reproduce`, and
read the map through an accessible interface with a working list/table equivalent — with the ACR
committed and every CI gate green.
