# Contributing to nearmiss

Thanks for being here. nearmiss exists because vulnerable road users absorb most of the
risk on streets and produce almost none of the official data, and because "show us the
data" deserves a careful, honest answer instead of a heat map that points at the busiest
bike route and calls it the most dangerous one. Every contribution — a hazard report, a
bug fix, a new city config, a sharper confidence interval, a screen-reader fix — moves
that work forward.

This guide is meant to be welcoming and exact at the same time. The bar is simple to
state and hard to clear: a change should **hold up when a skeptical traffic engineer
pushes back**. If you read this whole file before opening your first pull request, you
will pass review faster and we will both enjoy it more.

The product is the **dataset and the analysis**, not an app. Keep that in mind: the most
valuable contributions usually make a number more honest, a method more reproducible, or a
finding more accessible — not just prettier.

## Table of contents

- [Code of conduct](#code-of-conduct)
- [The five hard rules (read these first)](#the-five-hard-rules-read-these-first)
- [Two ways to contribute](#two-ways-to-contribute)
  - [Submit a hazard report](#submit-a-hazard-report)
  - [Contribute code, data methods, or docs](#contribute-code-data-methods-or-docs)
- [The privacy rule that has no exceptions](#the-privacy-rule-that-has-no-exceptions)
- [Set up your development environment](#set-up-your-development-environment)
- [The gates you must pass locally (`make verify`)](#the-gates-you-must-pass-locally-make-verify)
- [Commit message format (conventional commits)](#commit-message-format-conventional-commits)
- [Developer Certificate of Origin and licensing](#developer-certificate-of-origin-and-licensing)
- [Proposing a schema change](#proposing-a-schema-change)
- [Adding a city, an exposure source, or a hazard type](#adding-a-city-an-exposure-source-or-a-hazard-type)
- [Pull request checklist](#pull-request-checklist)
- [Where to ask questions](#where-to-ask-questions)

## Code of conduct

This project follows a Code of Conduct. By participating you agree to uphold it. Read it
at [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md) before you open an issue or a pull request.

In short: be decent. We are mostly people who have been buzzed by a driver or thrown by a
pothole, building shared evidence so it happens to fewer of us. Disagree about statistics
all you like — that is the job — but do it with respect. Report conduct concerns through
the contact path named in `CODE_OF_CONDUCT.md`.

## The five hard rules (read these first)

These are enforced in CI and by review policy. They are not aspirational, and "it's just
a small thing" is not an exception. If your change touches analysis or publishing, expect
review to check it against these directly.

1. **No rate without a denominator.** Every risk claim is a rate normalized by an exposure
   estimate (bike/ped counts, a demand model, or an exposure layer), and the source and its
   date are stated. A map or table of raw counts is labeled **report volume**, never
   **danger**.
2. **No estimate without an interval.** Every published rate, ranking, and comparison
   carries a confidence interval and an `n`. Small-sample segments are shown as uncertain,
   not ranked as if they were certain.
3. **Reporting bias is named, not hidden.** The analysis states who is over- and
   under-represented (route choice, demographics, app access, language) and what that does
   to the conclusions. A finding that could be an artifact of where people report is flagged
   as such.
4. **Contributor privacy is protected.** Reports are pseudonymous; exact home-end
   coordinates are fuzzed before publication; the open dataset is aggregated and jittered;
   raw precise reports stay **private and gitignored** in `data/raw/`. No report is published
   at a precision that could identify a person's routine. See
   [the privacy rule below](#the-privacy-rule-that-has-no-exceptions) — it is the one rule
   with zero room to negotiate.
5. **Open and reproducible end to end.** The schema, the pipeline, the notebooks, and the
   published GeoJSON are open, and `make reproduce` regenerates every figure and table from
   raw inputs. A claim no one can reproduce is not published.

If a contribution requires breaking one of these to "make the result look better," the
answer is no, and the result was never the right one.

## Two ways to contribute

There are two very different things people mean by "contribute," and they go through
different doors.

### Submit a hazard report

If you witnessed or experienced a close pass, a door-zone scare, a blind corner, a pothole
that nearly threw you, or any other hazard, you are contributing **data**, not code.

- **Do not** open a GitHub issue or pull request with the report details. That is the wrong
  channel, and it can leak a precise location publicly.
- Use the **report form** (the intake path described in the README and `docs/`), or the
  documented JSON submission route validated against
  [`schema/report.schema.json`](schema/report.schema.json).
- Reports are **pseudonymous**. Do not include your real name, the names of others, license
  plates, or anything that identifies a specific person. Describe the hazard, not the
  individuals.
- Reports are validated at intake and land in the **private** raw store. They are never
  committed to this repository. The public dataset you see published is aggregated and
  jittered precisely so your routine cannot be reconstructed from it.

A clear note about what happened and an accurate location are worth more than volume. One
honest report on a quiet street can matter more than thirty on the city's busiest route —
that is the whole point of exposure normalization.

nearmiss is a **community-owned evidence base**, not a city 311 queue or a public-works
complaint inbox. If you need a pothole filled, also call your city. Reporting here helps
the analysis; it does not dispatch a crew.

#### Reporting a hazard (vs. contributing code)

To be unambiguous about which door is which: a hazard **report** is a data submission, not a
code change, and it goes through the **hazard-report issue form**
([`.github/ISSUE_TEMPLATE/hazard_report.yml`](.github/ISSUE_TEMPLATE/hazard_report.yml)), not a
pull request. That issue is **public**, so never include identifying detail — no names, plates,
contact details, your home address, your exact start/end point, or precise coordinates of where
you live. Describe **where the hazard is**, coarsely (a corner, block, or landmark), not where
you live. (Full-precision coordinates are only ever accepted privately at intake, never typed
into the public form.)

After you submit, the report is **triaged** out of the public issue into the **private** intake
store, **validated** against [`schema/report.schema.json`](schema/report.schema.json), and then
**aggregated** to public street segments — or **withheld** when a segment falls below the
k-anonymity floor — before anything is published. Submitting a report **does not dispatch a
crew** or open a work order; it feeds the analysis. If you need a hazard actually fixed, also
call your city.

A report can note the **language** it was submitted in via the optional BCP-47 `language` tag
(for example `"en"` or `"es"`; it defaults to `en` when absent), which lets the bias analysis
characterize language-based under-representation. The brief renders in either language — pass
`--lang es` to `nearmiss brief` (or `nearmiss run`) to read it in Spanish instead of English.

### Contribute code, data methods, or docs

This covers everything else: pipeline stages, statistics, exposure adapters, schema
changes, the accessible map and table, briefs, tests, fixtures, and documentation. The
rest of this guide is for you. Start with an issue if the change is non-trivial, so we can
agree on the approach before you invest time.

## The privacy rule that has no exceptions

**No precise raw report data may ever be committed to this repository. Ever.**

- `data/raw/` is **gitignored** and holds the private, precise reports. Nothing in it is
  tracked. Do not remove its entries from `.gitignore`, do not force-add a file with
  `git add -f`, and do not paste raw report contents into issues, pull requests, commit
  messages, test fixtures, or notebooks.
- The only report-shaped data that belongs in the repo is **synthetic** (the planted-hotspot
  fixtures in `tests/fixtures/` with known answers) or **published** (the aggregated,
  jittered open GeoJSON and data card in `data/published/`).
- Fuzzing of home-end coordinates and the aggregation/jitter of the public dataset happen in
  `publish.py`. If you change publication precision, aggregation, or jitter, you are touching
  a privacy control — call it out explicitly in your PR and expect close review against
  `docs/THREAT-MODEL`.
- `gitleaks` runs in CI and pre-commit. It is a backstop, not your permission to be careless.
  If you suspect raw data reached a commit, **stop, do not push**, and contact the maintainer
  through the channel in [`SECURITY.md`](SECURITY.md) before doing anything else. History
  rewrites of leaked precise locations are handled deliberately, not in a panic.

When in doubt, treat a report's location as if it could identify where someone lives,
works, or rides every morning — because it can.

## Set up your development environment

You need **Python 3.11 or newer** and a standard geospatial toolchain (the pinned,
hashed dependencies install what you need). Linux and macOS are the supported platforms.

```bash
# 1. Clone your fork
git clone https://github.com/<your-username>/nearmiss.git
cd nearmiss

# 2. Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate          # on macOS/Linux

# 3. Install the package in editable mode with the dev extras
pip install -e ".[dev]"

# 4. Install the git hooks (lint, type, gitleaks, commit-message check)
pre-commit install
pre-commit install --hook-type commit-msg

# 5. Confirm everything works
make verify
```

`make verify` reproduces the full local gate. `make reproduce` regenerates every figure and
table in the briefs from raw inputs. `make demo` runs the full pipeline over the synthetic
fixtures and renders a sample brief — a good way to see the whole system end to end without
any real data.

This project is also held to the cross-cutting portfolio standards vendored at
[`docs/standards/`](docs/standards/) (pinned to a specific release via
`docs/standards/.standards-version`). See the README's
[Standards conformance](README.md#standards-conformance) table for which ones apply to nearmiss and
the current state of each; a change that touches lint/type/test config, CI, release, accessibility,
i18n, observability, or the privacy/threat-model surface should hold up against the relevant vendored
standard, not just against this file.

Dependencies are **pinned and hashed**. Do not bump them by hand in a feature PR; dependency
updates flow through Dependabot and a documented bump path so the hashes and the audit stay
in sync.

## The gates you must pass locally (`make verify`)

CI runs these on every pull request, and so should you before you push. `make verify` is the
single command that runs the whole gate; the individual targets exist so you can iterate
quickly on one thing.

| Gate | Command | What it checks |
| --- | --- | --- |
| Lint | `make lint` | `ruff` — style, imports, common bugs. |
| Types | `make type` | `mypy --strict` — no untyped or loosely typed code. |
| Tests | `make test` | `pytest` over deterministic components, with synthetic fixtures whose answers are **known** (planted hotspots recovered, interval coverage checks). |
| Accessibility | `make accessibility` | `axe` automated checks on the map, table, form, legends, and charts. Manual NVDA/VoiceOver review is required for UI changes and is a merge-blocking gate; note your manual result in the PR. |
| Security | `make security` | `pip-audit`, `gitleaks`, and CodeQL-equivalent checks. Pinned, hashed deps verified. |
| Everything | `make verify` | All of the above. This is the gate. |

Notes that save you a round trip:

- **Determinism is required.** Pipelines and analyses are seeded and must produce the same
  dataset and figures every run. A test that passes only sometimes is a bug, not a flake to
  retry.
- **Tests carry their own ground truth.** New statistical code ships with a fixture whose
  correct answer is known by construction (for example, a synthetic report set with a planted
  hotspot at a known location and a known exposure surface). "It looks right on real data" is
  not a test.
- **Accessibility is not optional for UI work.** Risk level and significance must be conveyed
  in text and pattern, never by color alone. Every map finding must be reachable through the
  equivalent sortable list/table. An axe pass plus a manual screen-reader pass is the bar.
- If a gate is failing for a reason you believe is environmental, say so in the PR rather than
  disabling the check. We fix the gate; we do not route around it.

## Commit message format (conventional commits)

We use [Conventional Commits](https://www.conventionalcommits.org/) and **semantic
versioning**. The commit-msg hook enforces the format, and the changelog and release
versions are derived from it, so the prefix is load-bearing.

Format:

```text
<type>(<optional scope>): <short imperative summary>

<optional body explaining what and why, wrapped at ~72 chars>

<optional footers: BREAKING CHANGE:, Refs:, Signed-off-by:>
```

Common types: `feat`, `fix`, `docs`, `refactor`, `perf`, `test`, `build`, `ci`, `chore`,
`revert`. Useful scopes in this repo include `intake`, `pipeline`, `exposure`, `stats`,
`publish`, `brief`, `server`, `web`, `schema`, `config`, `docs`, and `ci`.

Examples that fit this project:

```text
feat(stats): add small-count confidence interval for sparse segments

Use an exact Poisson interval below n=20 so low-report segments are
shown as uncertain instead of being ranked as certain. Adds a fixture
that checks interval coverage on planted-rate data.

Signed-off-by: Jane Rider <jane@example.com>
```

```text
fix(publish): widen jitter so single-report cells cannot be re-identified

Refs: #142
Signed-off-by: Jane Rider <jane@example.com>
```

```text
feat(config): add Davis, CA with Strava-style exposure layer

Signed-off-by: Jane Rider <jane@example.com>
```

```text
feat(schema)!: require exposure_date on every rate record

BREAKING CHANGE: report.schema.json major-bumps to 2.0; existing raw
reports migrate via migrations/0002_exposure_date.py. See
docs/adr/0007-require-exposure-date.md.

Signed-off-by: Jane Rider <jane@example.com>
```

A breaking change is marked with a `!` after the type/scope **and** a `BREAKING CHANGE:`
footer. Breaking changes drive a major version bump under semver, so do not mark one lightly
and do not hide one.

## Developer Certificate of Origin and licensing

Contributions are accepted under the **Apache License 2.0**, the project's license. By
contributing, you agree your contribution is licensed under Apache-2.0 and that you have the
right to submit it.

We use the **Developer Certificate of Origin (DCO)**. Every commit must be signed off,
certifying the DCO (the full text lives at <https://developercertificate.org/>). Add the
sign-off with the `-s` flag:

```bash
git commit -s -m "fix(pipeline): skip a single bad geocode without aborting the rebuild"
```

This appends a trailer to your message:

```text
Signed-off-by: Your Name <your.email@example.com>
```

The name and email must be real and must match your git identity. If you forget the sign-off,
amend the last commit with `git commit --amend -s` (or, for several commits, rebase and add
sign-off to each). The CI DCO check is strict: an unsigned commit blocks the merge.

New source files carry an SPDX header so the license is machine-readable:

```python
# SPDX-License-Identifier: Apache-2.0
```

Do not contribute code, data, or text that you do not have the right to license under
Apache-2.0. In particular, this project contains **no proprietary or client material**, and
contributions must keep it that way.

## Proposing a schema change

The report schema (`schema/report.schema.json`) and the published dataset schema
(`schema/dataset.schema.md`) are **versioned contracts**. Other people's pipelines and
mirrors depend on them, so changes follow a deliberate process rather than an ad-hoc edit.

A schema change is not done until **all four** of these exist in the same pull request:

1. **A versioned schema.** Bump the schema `version` under semver. A backward-compatible
   addition (a new optional field) is a minor bump; a change that can break existing readers
   or existing raw reports (renaming, removing, or making a field required) is a major bump
   and must be marked `BREAKING CHANGE` in the commit.
2. **A CHANGELOG entry.** Record the change in the CHANGELOG under the new schema version:
   what changed, why, and whether it is breaking. The CHANGELOG is the audit trail for the
   schema; every schema change appears there.
3. **A migration.** Provide a migration (under `migrations/`, named like
   `0002_<short_description>.py`) that upgrades existing data to the new version, plus a test
   that runs the migration on a fixture and checks the result. No data is left stranded on an
   old version.
4. **An ADR.** Add an Architecture Decision Record under `docs/adr/` (for example,
   `docs/adr/0007-require-exposure-date.md`) explaining the decision, the alternatives
   considered, and the consequences — especially the privacy and reproducibility
   consequences. This is where you make the case that the change holds up.

Open an issue first for any schema change. Schema churn is expensive for everyone downstream,
so we agree on the shape before writing the migration. Follow the deprecation policy in the
docs: a field is deprecated for a release before it is removed, never yanked without notice.

## Adding a city, an exposure source, or a hazard type

nearmiss is built to move to a new city by configuration, and to grow new exposure sources
and hazard types behind small adapter interfaces. This is **config-over-code** by design:
cities, exposure sources, thresholds, and jitter live in versioned configuration files read
by `config.py`, not scattered through the pipeline.

### Add a new city

1. Add the city to the configuration `config.py` reads (its bounds, the street-segment
   reference it snaps to, and which exposure source to use).
2. Attach at least one **exposure source** for the city. A city with reports but no
   denominator cannot publish rates — under hard rule 1, those segments are surfaced as
   **exposure unknown**, not silently rated or dropped.
3. State the exposure **source and its date** in the config and the data card. A rate without
   a dated denominator is not publishable.
4. Add a fixture or smoke test so the new city builds end to end through `make demo`.

### Add a new exposure source

Exposure sources (observed counts, a demand model, or an imported exposure layer) sit behind
**one interface** so they are interchangeable. To add one:

1. Implement the exposure adapter against the existing interface in `exposure.py` so it
   returns a per-segment denominator and records which source and date produced it.
2. Make the source selectable from config — no city should need code changes to switch its
   denominator.
3. Add a test on a synthetic segment with a known exposure value, so the rate computed
   downstream has a checkable answer.
4. Document the source, its provenance, its known biases, and its date in the data card and
   methodology doc. Naming the bias is hard rule 3; a new exposure layer comes with its own
   blind spots, and they get stated.

### Add a new hazard type

Hazard types (close pass, dooring, surface hazard, sightline, signal, debris, and so on) are
classified in the pipeline and validated by the report schema.

1. Add the new type to `report.schema.json` — which is a **schema change**, so follow the
   [schema change process](#proposing-a-schema-change) in full (version, CHANGELOG, migration,
   ADR).
2. Add or extend the classifier in `pipeline/classify.py` and its quality flags in
   `pipeline/quality.py`, behind the existing classification interface.
3. Add a fixture with reports of the new type and the expected classification, so the new
   type is tested against a known answer.
4. Confirm the new type flows through exposure, statistics, publishing, and the accessible
   table — a hazard type that cannot be normalized, bounded, and read non-visually is not
   finished.

The guiding principle: a new city, source, or type should be **adapters and config**, not a
fork of the pipeline. If you find yourself special-casing logic deep in a stage, raise it in
the issue — the right fix is usually a cleaner interface.

## Pull request checklist

Before you mark a pull request ready for review, walk this list. Copy it into the PR
description and check the boxes that apply.

- [ ] This PR contains **no precise raw report data** — nothing from `data/raw/`, no real
      locations, no identifying details in code, fixtures, tests, notebooks, commit messages,
      or the PR itself.
- [ ] `make verify` passes locally (lint, types, tests, accessibility, security).
- [ ] New or changed analysis honors the five hard rules: rates have **denominators** with a
      dated source; estimates have **confidence intervals** and an `n`; relevant **reporting
      bias** is named; nothing is published at identifying precision.
- [ ] New statistical or pipeline code ships with a **synthetic fixture whose answer is known**
      (planted hotspot, known exposure, or interval-coverage check).
- [ ] Changes are **deterministic** — seeded, reproducible, and re-runnable via
      `make reproduce` where figures or tables are affected.
- [ ] UI changes pass `axe` **and** a manual NVDA/VoiceOver pass; risk and significance are in
      text and pattern, not color alone; every finding is reachable via the list/table
      equivalent. The manual result is noted in the PR.
- [ ] Commits use **Conventional Commits** and are **DCO signed off** (`git commit -s`).
- [ ] If the schema changed: the schema is **versioned**, the **CHANGELOG** is updated, a
      **migration** plus its test is included, and an **ADR** is added.
- [ ] Docs are updated where behavior, methods, or assumptions changed (README, methodology
      doc, data card, ADRs, or `docs/audits/` as appropriate).
- [ ] Dependencies are unchanged, or the change goes through the documented pinned-and-hashed
      bump path rather than a hand edit.
- [ ] The change would **hold up if a skeptical traffic engineer pushed back** on it.

Smaller PRs review faster and break less. One coherent change per pull request is ideal.

## Where to ask questions

- **Bug or feature idea:** open a GitHub issue with the relevant template, including a
  "paste this to reproduce" path where you can.
- **Security or privacy concern** (including a suspected raw-data leak): follow
  [`SECURITY.md`](SECURITY.md) — do **not** open a public issue for these.
- **Conduct concern:** use the contact path in [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md).
- **Anything else:** open an issue and ask. A question that improves this guide is itself a
  contribution.

This is an independent personal open-source project maintained by Chelsea Kelly-Reif
([@ChelseaKR](https://github.com/ChelseaKR)); contact is via GitHub. Thank you for helping
make the evidence honest and the streets safer.
