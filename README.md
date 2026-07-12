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
[![Live demo](https://img.shields.io/badge/live-demo-nearmiss.report-success.svg)](https://nearmiss.report)

**Live demo (accessible map + data view):** <https://nearmiss.report>

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
> intake, the dedupe/geocode/snap/classify/quality pipeline (including offline geocoding of
> address-only reports), the exposure normalization and statistics (Poisson/Wilson confidence
> intervals, bias, KDE, Getis-Ord Gi\* with Benjamini-Hochberg FDR), publishing with a
> self-describing metadata block, the bilingual (English/Spanish) advocacy brief and web data view,
> address-or-coordinate intake with an offline gazetteer geocoder **and** an opt-in networked
> (Nominatim) adapter, a reproducible analysis notebook, a second demo city (Riverside) proving
> config-over-code, a committed hashed lockfile, and a performance benchmark all exist and pass the
> gates: `make demo`, `make verify`, and `make reproduce` run, 193 tests pass, and ruff + mypy
> `--strict` are clean. An automated `axe-core` run is wired via `make axe` alongside the structural
> accessibility gate. What remains is genuinely small: the **manual NVDA/VoiceOver screen-reader
> pass** that complements the automated axe run, and **deeper localization** beyond English/Spanish
> (see [Roadmap](#roadmap)). The repository is public and nearmiss is in pre-1.0 beta.

---

## Table of contents

- [Standards conformance](#standards-conformance)
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
- [Observability](#observability)
- [Data, privacy, and ethics](#data-privacy-and-ethics)
- [Repository layout](#repository-layout)
- [Roadmap](#roadmap)
- [Contributing](#contributing)
- [Security](#security)
- [Governance and independence](#governance-and-independence)
- [License and citation](#license-and-citation)
- [Acknowledgements and related work](#acknowledgements-and-related-work)

---

## Standards conformance

nearmiss is governed by a shared set of cross-cutting portfolio standards. Silent omission of a
standard is treated as a defect in its own right, so every standard gets a row below — including the
one that's `N/A` (the ADR making that call is
[`docs/adr/0004-standards-applicability.md`](docs/adr/0004-standards-applicability.md)). This table
declares *applicability*; it is not a claim that every applicable standard is fully met — open gaps are
named plainly rather than implied away.

| Standard | Applies? | Current state |
|---|---|---|
| QUALITY-AND-METRICS | Applies | AUTO gates strong (90% branch-coverage floor, advisory mutation testing on the stats core); REVIEW-gate artifacts (metrics ledger, `DEFINITION_OF_DONE.md`) not yet committed. |
| CODE-QUALITY | Applies | Lint/type/test are merge-blocking and green (ruff, `mypy --strict`, pytest); a few config/floor gaps are open (see [Contributing](#contributing)). |
| SECURITY-AND-SUPPLY-CHAIN | Applies | `pip-audit --strict` (blocking, no mute) + gitleaks + CodeQL run in CI, from a hashed dev-toolchain lock (`requirements-dev.lock`, `--require-hashes`); an SBOM/signing/SLSA pipeline exists (`.github/workflows/release.yml`) but is **not yet exercised** — no tag has been pushed. An ASVS level is not yet declared (see [Security](#security) and [`docs/RESPONSIBLE-TECH-AUDITS.md`](docs/RESPONSIBLE-TECH-AUDITS.md)). |
| CI-CD | Applies | The core pipeline (lint/type/test/i18n/accessibility/security/reproducibility) is merge-blocking; `zizmor`, CodeQL for GitHub Actions and web JS, and a committed branch-ruleset artifact are open gaps (branch protection is a live GitHub setting with no committed evidence yet). |
| RELEASE-AND-VERSIONING | Applies | SemVer + [`CHANGELOG.md`](CHANGELOG.md) are maintained; a tag-triggered release pipeline now exists (`.github/workflows/release.yml`) but **no version has ever been git-tagged and PyPI Trusted Publishing is not yet registered** — see the dated correction at the top of the CHANGELOG and the NOTE at the top of `release.yml`. |
| ACCESSIBILITY | Applies | WCAG 2.2 AA target; the structural gate and an automated axe-core (jsdom) run are both merge-blocking; manual NVDA/VoiceOver review and browser-rendered gates (Lighthouse, pa11y) are still pending — see [Accessibility and Section 508 conformance](#accessibility-and-section-508-conformance). |
| OBSERVABILITY | Applies (Tier C) | Structured JSON logs + `/livez`/`/readyz`; Tier C is a local-only CLI/library tier (OTel tracing/metrics/SLOs out of scope) — see [Operability, serviceability, sustainability](#operability-serviceability-sustainability). |
| INTERNATIONALIZATION | Applies | The strongest area: gettext catalogs with four blocking CI gates (POT drift, `msgfmt --check`, EN/ES parity, BCP-47 validity) — see [`docs/I18N.md`](docs/I18N.md). |
| AI-EVALUATION | **N/A** | No LLM/AI SDK usage anywhere in the codebase (verified: a grep for `anthropic`/`openai`/`langchain`/`bedrock`/generic LLM-client imports across `src/` and `tools/` is clean). See [`docs/adr/0004-standards-applicability.md`](docs/adr/0004-standards-applicability.md) — this flips to **Applies** immediately, per the standard's own AIEV-01, the moment any LLM-backed feature is added (e.g. an AI-assisted moderation triage or an auto-summarized brief). |
| DOCUMENTATION | Applies | CHANGELOG, ADRs, `CITATION.cff`, `SECURITY.md` are all present and current; this table itself closes the prior gap (the README declared no standards before 2026-07-05). |
| RESPONSIBLE-TECH | Applies | The threat model and mechanical misuse-resistance tests (k-anonymity floor, privacy leak tests, reproducibility tripwire) are strong; a DPIA, an ASVS-level declaration, and a residual-risk register are new or being added — see [Data, privacy, and ethics](#data-privacy-and-ethics) and [`docs/RESPONSIBLE-TECH-AUDITS.md`](docs/RESPONSIBLE-TECH-AUDITS.md). |

Portfolio practice links each open gap above to a GitHub tracking issue. **That issue-linking step is
not done as of this table's creation (2026-07-05)** — opening tracking issues is a live-repository
action for the maintainer to take, not a file edit, so it is named here rather than silently skipped.
Until issues exist, treat this table itself, plus [`CHANGELOG.md`](CHANGELOG.md) and
[`docs/RESPONSIBLE-TECH-AUDITS.md`](docs/RESPONSIBLE-TECH-AUDITS.md), as the source of truth for gap
status.

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

> **Report a hazard:** open the hazard-report issue form at
> [`.github/ISSUE_TEMPLATE/hazard_report.yml`](.github/ISSUE_TEMPLATE/hazard_report.yml) — a close
> pass, door zone, blind corner, or surface hazard — and it enters intake validated against the
> [published schema](schema/report.schema.json).

- **Intakes** a hazard or near-miss report — location (as a lat/lon **or** a free-text address, which
  is resolved at the geocode stage via an offline gazetteer), time, mode, type (close pass, dooring,
  surface hazard, sightline, signal, debris), severity, an optional note, and an optional BCP-47
  language tag — through a simple form, an import path, or a documented JSON submission, validated
  against a [published schema](schema/report.schema.json).
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
- **Publishes** open data — a self-describing **GeoJSON** `FeatureCollection` (`<city-slug>.geojson`,
  e.g. `davis.geojson`) aligned to a [documented near-miss/collision schema](schema/dataset.schema.md),
  carrying a top-level `metadata` foreign member (dataset/schema versions, license, city, exposure unit,
  privacy and significance notes) with a content-hashed sidecar (`<city-slug>.metadata.json`) —
  reproducible analysis notebooks, and advocacy-ready outputs: ranked locations with intervals,
  plain-language **bilingual (English/Spanish) briefs** with a glossary and a bottom-line, and maps with
  honest legends and a non-visual table equivalent.

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
4. **Contributor privacy is protected.** Reports are pseudonymous. The open dataset is aggregated to
   public street segments — the published geometry is the real public street centerline, never a
   report location — and no per-report coordinate, timestamp, reporter token, note, mode, or severity
   is ever published. Any segment with a non-zero report count below the minimum-occupancy floor
   (k-anonymity) is withheld entirely, so no published place can mean "one or two people reported an
   incident here." Precise raw reports stay private and are never committed.
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
# From a clone (recommended for contributors)
make install                 # pip install -e ".[dev]" + pre-commit install

# As a tool, isolated (the packaging/release goal once published to PyPI)
pipx install nearmiss

# Reproducible, hash-verified install — what CI actually runs (make lock-dev / requirements-dev.lock)
python -m pip install --require-hashes -r requirements-dev.lock
python -m pip install --no-deps -e .
```

<!-- claim:lockfile-committed-hashed -->
`requirements.lock` (runtime only, `make lock`) and `requirements-dev.lock` (runtime + the full dev
toolchain, `make lock-dev`) are both committed, generated by `pip-compile --generate-hashes`, and kept
current by Dependabot/Renovate on each dependency bump. CI installs from the dev lock with
`--require-hashes` (FIX-11), so the gates run against the exact hashed toolchain the locks pin.
<!-- /claim:lockfile-committed-hashed -->

A container image and a one-command serverless intake deploy are described in
[`infra/`](infra/). Configuration — cities, exposure sources, thresholds, and the minimum-occupancy
floor — lives in versioned files under [`src/nearmiss/config.py`](src/nearmiss) and city config, never
in code.

## Usage

```bash
# Canonical end-to-end run: intake -> pipeline -> analyze -> publish -> brief
make demo                                                   # equivalent to the line below
nearmiss run --config config/davis-demo.toml                # the full pipeline on the Davis demo
nearmiss run --config config/davis-demo.toml --lang es      # same run, brief rendered in Spanish

# Validate and intake reports (form export, import file, or documented JSON)
nearmiss intake reports.json --config config/davis-demo.toml   # validated against schema/report.schema.json
                                                               # (source is optional; defaults to the config)
                                                               # a report carries a lat/lon OR an address (geocoded
                                                               # offline via the configured gazetteer)

# Render the advocacy brief in English (default) or Spanish (gettext catalogs via src/nearmiss/i18n.py)
nearmiss brief --config config/davis-demo.toml --lang es       # English/Spanish brief; en is the default

# Run the documented pipeline: dedupe -> geocode -> snap -> classify -> quality-flag
nearmiss pipeline --config config/davis-demo.toml [--dump]  # --dump prints the intermediate clean records

# Attach exposure denominators and compute exposure-normalized rates with intervals
nearmiss analyze --config config/davis-demo.toml            # rates + CIs + bias + KDE + Gi* + time-of-day

# "We attacked our own dataset": label-shuffle this city's own counts (exposure and
# geometry held fixed) and publish the method's empirical false-positive rate
nearmiss analyze --config config/davis-demo.toml --calibrate   # writes <slug>.calibration.json

# Audit what this city's declared + loaded sources can honestly support
nearmiss coverage --config config/davis-demo.toml  # evidence tier, freshness, capabilities, gaps
# Optionally prove a declared id="fars" source from its private raw/artifact/receipt chain;
# this grants verified crash context only, never triangulation or a tier promotion.
nearmiss coverage --config config/city.toml --fars-root "$HOME/.local/share/nearmiss/ingestion"

# Public crowdsourced submissions: queue one for review, then moderate it in
nearmiss submit submission.json --config config/davis-demo.toml      # -> PENDING (private)
nearmiss moderate list --config config/davis-demo.toml               # review the queue + flags
nearmiss moderate approve <id> --config config/davis-demo.toml       # only approved enter the dataset
nearmiss moderate export approved.json --config config/davis-demo.toml

# Contributor data-rights (token possession is the ONLY auth — no account/identity):
nearmiss contributor export <reporter_token> --config config/davis-demo.toml   # my reports, as JSON
nearmiss contributor delete <reporter_token> --config config/davis-demo.toml   # delete + tombstone them
nearmiss contributor purge-expired --config config/davis-demo.toml             # enforce retention_days
# NOTE: after a delete/purge, `make reproduce` output legitimately changes — the
# deleted reports no longer feed aggregation; re-run and commit the new artifacts.

# Publish the open GeoJSON aggregated to public street segments + data card
nearmiss publish --config config/davis-demo.toml

# Regenerate every figure and table in the briefs from raw inputs (the reproducibility proof)
make reproduce

# Serve the accessible map with its equivalent sortable list/table view (read-only)
nearmiss serve                              # WCAG 2.2 AA; data view is the non-visual equivalent
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
│   ├── geocoder.py                # pluggable Geocoder protocol + offline GazetteerGeocoder (default)
│   ├── pipeline/                  # dedupe.py, geocode.py (address→coords), snap.py, classify.py, quality.py
│   ├── exposure.py                # denominator layers: counts, demand model, exposure imports
│   ├── stats/                     # rates.py (CIs), bias.py, kde.py, getis_ord.py
│   ├── publish.py                 # build open <city>.geojson + <city>.metadata.json (hashed)
│   ├── brief.py                   # generate advocacy briefs (ranked locations, intervals, prose)
│   ├── i18n.py                    # gettext seam (locales/) for the English/Spanish bilingual brief
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
is: `exposure.py` attaches denominators by an exact `segment_id` join (a total id-scheme mismatch
raises a clear error rather than silently reporting 0% coverage; a partial mismatch warns), `rates.py`
computes rates with confidence intervals, `bias.py` characterizes and reports the reporting bias, and
`kde.py`/`getis_ord.py` produce the hotspot surfaces and significant clusters. `publish.py` aggregates
to public street segments and emits the open `<city-slug>.geojson` plus a content-hashed
`<city-slug>.metadata.json` sidecar, withholding any segment whose non-zero report count falls below the
minimum-occupancy floor; `brief.py` turns the results into advocacy outputs in English or Spanish. The
map server reads only published artifacts and always ships an equivalent table. Nothing in the public
path exposes a precise raw report.

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
n and an interval; internal coordinates and segments are preserved without lossy rounding, while the
published unit is the public street segment, not a precise point. **Determinability** and
**predictability** — seeded pipelines and analyses yield
the same dataset and figures every run. **Repeatability** and **reproducibility** — `make reproduce`
regenerates every brief figure and table from raw inputs; notebooks are deterministic. **Provability**
— each published number records its method, exposure source, and threshold. **Traceability** — a
mapped hotspot traces from figure → notebook → statistic → cleaned dataset → raw reports.
**Relevance** — findings are exposure-normalized so they reflect risk, not traffic. **Effectiveness**
— the test design (planted-hotspot fixtures, interval-coverage checks) is documented in
[`tests/README.md`](tests/README.md), and the committed fixtures validate it: the tests recover the
planted hotspot `seg-06` (`5th St (C–D)`) and its unique Getis-Ord Gi\* significance (z = 3.25) while
the busy decoy `seg-03` (`3rd St (B–C)`) — the most-reported segment — correctly ranks low on
exposure-normalized rate.
**Accountability** — the data card and methodology doc state what the numbers do and do not support.

### Standards, interoperability, openness

**Standards compliance** — GeoJSON output aligned to a documented near-miss/collision schema; SPDX
headers; semver; conventional commits. **Interoperability** — published GeoJSON loads in QGIS,
Leaflet, and any GIS, and is self-describing via an embedded top-level `metadata` foreign member
(dataset and schema versions, license, city, exposure unit, and privacy/significance notes); the
report schema is documented JSON. **Interchangeability** — exposure sources
(counts, demand model, imports) swap behind one interface. **Compatibility** — CI tests Python 3.11 and
3.12 per [`ci.yml`](.github/workflows/ci.yml); the package is pure-typed-Python with a single runtime
dependency (`jsonschema`), using a local equirectangular projection and pure-Python statistics instead
of numpy/shapely/pyproj per [`docs/adr/0003-pure-python-statistics-and-planar-geometry.md`](docs/adr/0003-pure-python-statistics-and-planar-geometry.md).
**Composability** and **inspectability** — every stage
emits plain, inspectable data others can pipe and check. **Portability** and **distributability** —
the dataset and pipeline move to any city by config, and the published GeoJSON is a single file anyone
can mirror, fork, or redistribute; nothing is bound to one locale or host.

### Privacy, security, accountability

**Confidentiality** — precise raw reports stay private; the public dataset is aggregated to public
street segments, and no per-report coordinate, timestamp, reporter token, note, mode, or severity is
ever published. **Securability** — secrets via env, never committed; intake validates
and rate-limits to resist spam and poisoning. **Integrity** (data) — schema validation at intake and
hashed published artifacts make tampering detectable. **Safety** — no published place can mean "one or
two people reported an incident here": segments with a non-zero report count below the minimum-occupancy
floor are withheld entirely, enforced by `assert_published_clean` and covered by the test suite.
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
in `make verify`, an automated `axe-core` run (jsdom) runs in CI via `make axe`
([`web/axe_check.mjs`](web/axe_check.mjs)), and the web view ships an authoritative sortable data
table carrying the same ranked locations and intervals as the supplementary map — its segment-name
column is sticky (usable at 200% zoom) and column sorts announce through an `aria-live` region. The
manual NVDA/VoiceOver screen-reader pass that complements these automated checks is still a conformance
target.
**Usability** and **convenience** — reporting is a short form; the dataset is one download.
**Learnability**, **familiarity**, **intuitiveness** — the map and table read the way people expect;
the report form asks plain questions. **Interactivity** and **responsiveness** — the map filters and
the table sort quickly on published data. **Discoverability** — the data card, schema, and notebooks
are linked from the first screen. **Seamlessness** — map and table are two views of one published
artifact. **Localizability** — partially delivered: the advocacy brief now renders in English or
Spanish (`--lang es`, via [`src/nearmiss/i18n.py`](src/nearmiss/i18n.py)), the report schema carries an
optional BCP-47 `language` tag, and the report form is bilingual; deeper prose localization and
per-language interface and form-string bundles for additional languages remain in progress.
**Mobility** and **ubiquity** — mobile-first reporting, because hazards are reported from the roadside.

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
code are extracted as [`honest_rates`](src/honest_rates/README.md), a standalone, dependency-free
library with no nearmiss import anywhere in it, usable on any point-event dataset (nearmiss is its
first consumer — see [`src/nearmiss/stats/rates.py`](src/nearmiss/stats/rates.py) and
[`src/nearmiss/stats/getis_ord.py`](src/nearmiss/stats/getis_ord.py)). **Analyzability** — typed,
documented, with a methodology doc.
**Configurability**, **customizability**, **tailorability** — config-over-code is implemented:
[`config/davis-demo.toml`](config/davis-demo.toml), loaded by
[`src/nearmiss/config.py`](src/nearmiss/config.py), controls the city, the three input paths, every
threshold (including the minimum-occupancy floor `min_publish_n` and the FDR level `fdr_alpha`), the
brief's `exposure_unit`, an optional offline `gazetteer`, and a `dataset_note` provenance label —
without touching code. **Upgradability** — a documented dependency bump path; versioned schemas with
migrations.

### Reliability, resilience, safety of the pipeline

**Dependability** and **reliability** — a malformed or malicious report is rejected at intake, never
silently corrupting the dataset. **Availability** — the published site is static-friendly and the
intake scales to zero; no always-on component to keep paid. **Fault-tolerance**, **resilience**,
**robustness** — one bad geocode or bad report never aborts the rebuild; the stage flags and
continues, and an address that cannot be resolved is left unplaced and caught downstream as unsnapped,
never snapped to an invented location. **Recoverability** and **survivability** — the dataset rebuilds
from raw via `make reproduce`; published artifacts are versioned. **Degradability** and **failure
transparency** — a segment with no exposure data is shown as "exposure unknown" (one of the published
`quality_flags`, alongside `low_sample` and `geocode_low_confidence`), not silently dropped or falsely
rated; conversely a wholesale exposure/street id mismatch fails loudly rather than degrading to a
silent 0% coverage.
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
coded. **Observability** — Tier C, declared with its rationale and gates in its own
[Observability](#observability) section per OBS-21 (structured JSON logs, redacted request logging,
`/livez`/`/readyz`).
**Debuggability** — the figure → notebook → statistic → dataset → raw trace is defined in
[`docs/METHODOLOGY.md`](docs/METHODOLOGY.md), and `nearmiss pipeline --config <cfg> --dump` emits the
intermediate clean records for inspection. **Serviceability / supportability** — issue templates and a "paste this to reproduce" path.
**Deployability** and **installability** — `pipx install`, a container image, one-command serverless
deploy. **Repairability** — most fixes are data or threshold edits, recorded and re-run. **Agility** —
CI smoke suite on every PR. **Autonomy** (operational), **self-sustainability**, **sustainability** —
open data and zero-cost hosting mean the dataset survives without a grant or a city's goodwill.
**Testability**, **inspectability**, **demonstrability** — the planted-hotspot fixtures with known
answers (documented in [`tests/README.md`](tests/README.md)) are committed under
[`tests/fixtures/davis/`](tests/fixtures/davis/), 193 pytest tests pass against them, and `make demo`
runs the full pipeline to make the statistics verifiable.

> Each attribute above maps to a documented decision and, where the implementation exists, a
> verifiable artifact or gate. The reproducible notebook, the networked geocoder adapter, the second
> demo city, and the performance benchmark are now implemented; what remains aspirational at beta is
> the manual NVDA/VoiceOver screen-reader review that complements the automated axe-core run and
> deeper localization beyond English/Spanish, and some VPAT rows are "Partially Supports" — stated
> plainly rather than overclaimed. See the [ACR](docs/accessibility/ACR.md), the
> [performance benchmark](docs/PERFORMANCE.md), and the [Roadmap](#roadmap).

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
- The web view runs against automated checks on every CI run (`axe-core` via `make axe`, plus the
  structural gate in `make verify`); the segment-name table column is sticky for use at 200% zoom and column sorts announce
  through an `aria-live` region. The complementary **manual** screen-reader review (NVDA, VoiceOver) is
  still pending and is named honestly as such. Risk level and significance are conveyed in text and
  pattern, never by color alone; the report form is fully keyboard-operable with clear labels and error
  text.
- A **non-visual equivalent** of the map is provided as an accessible, sortable list and table carrying
  the same ranked locations, rates, intervals, and significance flags, so every finding is reachable
  without seeing the map.
- Accessibility is a **merge-blocking CI gate**; a regression fails the build. The ACR is regenerated
  and re-committed on each release, the same audit-as-artifact discipline applied to the statistics.

## Observability

**Tier C** per the portfolio `OBSERVABILITY-STANDARD` — nearmiss is a local-only CLI/library with an
optional, local, read-only server; the live public site is static hosting. Tiers A/B (OpenTelemetry
distributed tracing, metrics/SLO dashboards, burn-rate alerting) are **out of scope at this tier** — there
is no always-on distributed service to trace or alert on. What Tier C requires, and what's shipped:

- **Structured logs.**
  <!-- claim:obs-intake-only -->
  `src/nearmiss/obs.py` emits structured JSON lines (timestamp, level, message, service, `request_id`,
  latency) for the read-only server's request intake ([`src/nearmiss/server.py`](src/nearmiss/server.py));
  per-pipeline-stage instrumentation is planned, not yet wired. Rebuilds report coverage and
  quality-flag counts.
  <!-- /claim:obs-intake-only -->
- **No secrets or PII in logs.** The read-only server ([`src/nearmiss/server.py`](src/nearmiss/server.py))
  emits one JSON line per request (method, status, latency, `request_id`, and a **redacted** path — a
  protected `data/raw/` or dotfile target collapses to `<blocked>`) — hard rule #4 (contributor privacy)
  holds in the log stream too, and this is covered by `tests/test_observability.py`.
- **Liveness / readiness.** The server exposes `GET /livez` (liveness) and `GET /readyz` (readiness —
  fail-closed `503` when the served data directory is unavailable).

This declaration is the README `## Observability` section that a doc-lint (OBS-21) looks for; see
[Standards conformance](#standards-conformance) for how this fits the other ten standards.

## Data, privacy, and ethics

Contributor privacy is treated as a **security property**, not a nicety. Precise raw reports are
private and never committed (`data/raw/` is gitignored). The open dataset is aggregated to public street
segments — the published geometry is the real public street centerline, never a report location — and
no per-report coordinate, timestamp, reporter token, note, mode, severity, or heading is ever published;
an allowlist in `publish` and a denylist invariant in `assert_published_clean` (with
`assert_metadata_clean` for the sidecar metadata) enforce this and raise rather than emit a leaky file.
Any segment with a non-zero report count below the minimum-occupancy floor (`min_publish_n`, default 3)
is withheld entirely from the GeoJSON, the metadata, and the brief (k-anonymity), so no published place
can mean "one or two people reported an incident here"; small-sample hazard breakdowns are suppressed,
and the KDE report-intensity peak is reported only as a segment id, never a coordinate. A residual risk
remains — a repeat contributor could in principle be linked across several segments — and aggregation
plus withholding reduce but do not erase it. The full reasoning, adversaries, mitigations, and honest
residual risk are in [`docs/THREAT-MODEL.md`](docs/THREAT-MODEL.md); what the published dataset
contains, what it omits, and its known biases and limits are in [`docs/DATA-CARD.md`](docs/DATA-CARD.md).
If you believe a published artifact leaks identifying precision, treat it as a security issue and follow
[`SECURITY.md`](SECURITY.md).

## Repository layout

| Area | What's there |
| --- | --- |
| [`schema/`](schema/) | [`report.schema.json`](schema/report.schema.json) (intake) and [`dataset.schema.md`](schema/dataset.schema.md) (published GeoJSON) |
| [`src/nearmiss/`](src/nearmiss/) | intake, pipeline stages, exposure, statistics, publish, brief, accessible server, config |
| [`notebooks/`](notebooks/) | deterministic analysis notebooks; the reproducibility backbone |
| [`web/`](web/) | framework-free WCAG 2.2 AA map UI with list/table equivalent; public submission form (`submit.html`); embeddable hotspot widget (`embed.html` + `nearmiss-embed.js`) |
| [`data/`](data/) | `raw/` (private, gitignored) and `published/` (open GeoJSON + data card) |
| [`tests/`](tests/) | pytest suites and planted-hotspot fixtures with known answers |
| [`docs/`](docs/) | [METHODOLOGY](docs/METHODOLOGY.md), [DATA-CARD](docs/DATA-CARD.md), [COVERAGE-TIERS](docs/COVERAGE-TIERS.md), [ADAPTING](docs/ADAPTING.md), [THREAT-MODEL](docs/THREAT-MODEL.md), [SUBMISSIONS](docs/SUBMISSIONS.md), [INTAKE-AND-ABUSE](docs/INTAKE-AND-ABUSE.md), [ACCESSIBILITY](docs/ACCESSIBILITY.md), [ADRs](docs/adr/), [audits](docs/audits/), [accessibility ACR](docs/accessibility/ACR.md) |
| [`infra/`](infra/) | optional serverless intake + scheduled rebuild; scale-to-zero |
| [`.github/`](.github/) | [CI](.github/workflows/ci.yml), Dependabot, CodeQL, issue/PR templates, CODEOWNERS |

## Roadmap

- **Phase 1 — schema, intake, pipeline.** Publish `report.schema.json`; build validated intake and the
  dedupe/geocode/snap/classify/quality pipeline; synthetic fixtures with planted hotspots. Definition
  of done: raw reports become a clean, versioned dataset reproducibly.
- **Phase 2 — exposure and honest statistics.** `exposure.py` denominators; rates with confidence
  intervals; `bias.py` reporting-bias characterization; `kde.py` and `getis_ord.py` hotspots, all
  tested against fixtures with known answers. Commit a baseline analysis, caveats included.
- **Phase 3 — publish and advocate.** Open GeoJSON aligned to the documented schema; a public dataset
  aggregated to public street segments, withholding low-count segments, with a data card; reproducible
  notebooks; advocacy briefs; the accessible map with list/table equivalent, deployed behind a real URL.
- **Phase 4 — generalize.** A config so any city's reports and exposure layers can be added; an "adapt
  this to your city" guide (committed at [`docs/ADAPTING.md`](docs/ADAPTING.md)); optional import paths
  for existing community report sets, now a pluggable `SourceAdapter` framework
  (`src/nearmiss/adapters/`) with declarative TOML crosswalks — BikeMaps.org and SimRa (TU Berlin) are
  the two adapters today, each with its own named reporting-bias profile (see
  [`docs/REAL-DATA.md`](docs/REAL-DATA.md#source-adapters)).

Releases follow [semver](https://semver.org/) and are recorded in [`CHANGELOG.md`](CHANGELOG.md).

## Contributing

Contributions — a hazard report, a sharper confidence interval, a screen-reader fix, a new city config
— are welcome and held to a simple, hard standard: a change should hold up when a skeptical traffic
engineer pushes back. Start with [`CONTRIBUTING.md`](CONTRIBUTING.md), which covers dev setup, the
local gate (`make verify`), conventional commits, the DCO sign-off, how to propose a versioned schema
change, and the one rule with no exceptions: **no precise raw report data is ever committed.** All
participants are bound by the [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md).

Engineering practices: pytest for every deterministic component with known-answer fixtures; ruff +
mypy strict in CI, installed from a hashed toolchain lock; reproducible, content-hashed dataset and
analysis runs; conventional commits; pinned, SLSA-friendly GitHub Actions; a tag-triggered SBOM/Sigstore/SLSA release pipeline (not yet
exercised — see `.github/workflows/release.yml` and "How to verify a release" in
[`docs/DATA-CARD.md`](docs/DATA-CARD.md)); Dependabot; and committed audit artifacts.

## Security

Security and privacy reports go through **GitHub private vulnerability reporting**, not public issues —
see [`SECURITY.md`](SECURITY.md). Scope explicitly includes the privacy and data-integrity threats
specific to this project (deanonymization, report poisoning, exposure-source tampering), not only code
CVEs. Supply chain: pinned and hashed dependencies, pip-audit, gitleaks, and CodeQL run in
[CI](.github/workflows/ci.yml); secrets live in the environment and are never committed.
**Supported versions:** the latest released `0.1.x` minor line (best-effort backport of high/critical
fixes to the previous minor) — see the full table in [`SECURITY.md` § Supported versions](SECURITY.md#supported-versions).

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
