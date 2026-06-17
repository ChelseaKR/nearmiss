# Security Policy

nearmiss is an open dataset and a statistically honest analysis of road hazards and near misses,
built for safe-streets advocacy. It is a community-owned evidence base, not a city 311 queue. Because
the product is data about real people moving through real streets, "security" here covers more than
code defects. **Contributor privacy and dataset integrity are treated as first-class security
properties**, on equal footing with the confidentiality of secrets or the soundness of dependencies.

This document explains what versions are supported, how to report a vulnerability privately, what to
expect after you do, and what is in scope — including the data-integrity and privacy threats specific
to this project. It is the operational companion to the project threat model in
[`docs/THREAT-MODEL.md`](docs/THREAT-MODEL.md), which enumerates the assets, adversaries, and
mitigations in full. Read both together: the threat model says *what we are defending and against
whom*; this policy says *how to tell us when a defense has failed*.

Maintainer: Chelsea Kelly-Reif ([@ChelseaKR](https://github.com/ChelseaKR)). This is an independent
personal open-source project under Apache-2.0, unaffiliated with any employer or client, containing
no proprietary or client material. There is one maintainer; please size your expectations to a
single volunteer, not a staffed security team.

## Supported versions

nearmiss follows [Semantic Versioning](https://semver.org/). Security fixes are issued against the
latest released minor line. The published dataset and the report/dataset schemas are versioned
independently of the code; a privacy or integrity defect that affects published data is treated as a
security issue regardless of which code version produced it.

| Channel                                   | Supported                                  |
| ----------------------------------------- | ------------------------------------------ |
| Latest released `MINOR` (e.g. `0.4.x`)    | Yes — receives security fixes              |
| Previous `MINOR`                          | Best-effort backport for high/critical only |
| Older releases                            | No — please upgrade                        |
| `main` (unreleased)                       | Fixed directly; not a "supported" release  |
| Latest published dataset version          | Yes — re-published if a defect is found    |
| Superseded published dataset versions     | Withdrawn or annotated, not silently fixed |

During the private pre-1.0 development phase, the supported surface is whatever is currently on `main`
plus the most recent tagged release. There is no long-term-support promise before 1.0.

## Reporting a vulnerability

**Do not open a public issue, discussion, or pull request for a security or privacy problem.** A
public report can itself cause harm here — for example, a comment that names a re-identifiable
contributor, or that explains a working report-poisoning technique, is damage, not a bug report.

Use GitHub's private vulnerability reporting instead:

1. Go to the repository's **Security** tab → **Report a vulnerability** (this opens a private GitHub
   Security Advisory visible only to you and the maintainer).
   Direct link: `https://github.com/ChelseaKR/nearmiss/security/advisories/new`.
2. If you cannot use that flow, open a **minimal** GitHub issue that says only "I need to report a
   security issue privately, please enable a private channel" — with **no technical detail** — and
   wait for a private advisory thread. Do not describe the issue in the open.

Please include, to the extent you can:

- A description of the issue and the **security or privacy property it breaks** (confidentiality,
  data integrity, contributor anonymity, availability).
- The component or stage involved — for example `intake.py`, a `pipeline/` step, `exposure.py`,
  `stats/`, `publish.py`, the published GeoJSON, the public dataset, or `server.py`.
- Steps to reproduce, ideally against the **synthetic test fixtures** rather than real reports.
- Impact: who is harmed, and whether real contributor data is or could be exposed.
- Any suggested remediation.

**Please do not include real personal data, precise real-report coordinates, or a deanonymization of
an actual contributor in your report.** If your finding *is* that a real contributor can be
re-identified, describe the *method* and *which published artifact* enables it — not the identity.
Demonstrate with fixtures or with your own test report. Reports that attach real victim data will be
asked to be re-sent without it.

We support coordinated disclosure and will credit reporters who want credit. We do not operate a paid
bug-bounty program.

## Response timeline

This is a single-maintainer project; these are good-faith targets, not contractual SLAs.

| Stage                                                  | Target                          |
| ------------------------------------------------------ | ------------------------------- |
| Acknowledge receipt                                    | Within 3 business days          |
| Initial assessment + severity triage                  | Within 7 business days          |
| Fix or mitigation for **privacy / data-exposure** issues | Prioritized; mitigation ASAP, often by withdrawing or re-publishing the affected dataset first |
| Fix for high/critical code issues                     | Target 30 days                  |
| Fix for low/moderate issues                           | Next regular release            |
| Public advisory + disclosure                          | Coordinated with you, after a fix or mitigation is available |

Privacy and data-integrity issues that affect **already-published** artifacts get the fastest path:
the first action is usually to **un-publish or roll back** the affected GeoJSON or public dataset
(removing the harmful artifact from the open path) while a corrected, re-jittered, re-aggregated
version is rebuilt with `make reproduce`. Because every published number is reproducible from raw
inputs, withdrawal-then-rebuild is a safe default.

## Scope

nearmiss is data infrastructure, so its threat surface is not only "code that runs." The scope below
mirrors the asset and adversary catalog in [`docs/THREAT-MODEL.md`](docs/THREAT-MODEL.md). All of the
following are **in scope** as security issues.

### In scope — privacy threats (treated as security)

Contributor privacy is a security property, not a feature. The hard rule is that no report is ever
published at a precision that could identify a person's routine. In scope:

- **Deanonymization via precise coordinates.** Any path by which a contributor's home end, workplace,
  routine, or identity can be recovered from published artifacts — including residual precision in the
  open GeoJSON, insufficient jitter or aggregation in the public dataset, fuzzing that is reversible,
  or a low-`n` cell that uniquely fingerprints one person.
- **Re-identification by correlation.** Linking published reports across time, mode, or rare
  hazard/severity combinations to single out an individual, even when each field alone looks safe.
- **Leakage of the private raw store.** Any way to reach `data/raw/` precise reports, intake payloads,
  or pre-jitter intermediate data through the published site, the API, server responses, logs,
  error messages, debug dumps, or a committed file that should have been gitignored.
- **Metadata leakage.** Timestamps, free-text notes, contributor pseudonym handling, or request
  metadata that narrows a contributor to a small group.
- **Pseudonymity defeats.** Anything that turns a pseudonymous report back into a linkable identity.

If you find that the published dataset can re-identify someone, that is a **high-severity** issue
even if no traditional "vulnerability" (injection, auth bypass) is involved.

### In scope — data-integrity threats (treated as security)

The credibility of the analysis is the product. Anything that lets an adversary make the dataset
quietly lie is a security issue:

- **Report poisoning / spam.** Mass-submitting fabricated reports, coordinated submissions to inflate
  or suppress a location, automated flooding, or crafted reports designed to skew a rate, a ranking,
  a KDE surface, or a Getis-Ord Gi\* cluster. Bypassing intake validation, schema checks, dedupe, or
  rate-limiting belongs here.
- **Exposure-source tampering.** Manipulating, spoofing, or substituting the denominator — the
  bike/ped counts, demand model, or exposure layer attached in `exposure.py`. Because every risk
  claim is a rate normalized by exposure (hard rule #1), corrupting the denominator is as damaging as
  corrupting the numerator. Stale, swapped, or forged exposure inputs that aren't caught and dated are
  in scope.
- **Pipeline / classification manipulation.** Inputs that cause `pipeline/` stages (geocode, snap,
  classify, quality-flag) to mislabel, misplace, or wrongly drop reports in a way that biases results.
- **Published-artifact tampering.** Modification of the open GeoJSON, the public dataset, the data
  card, or release assets after build, or any gap that would let a tampered artifact pass as genuine
  (broken or missing content hashes, unsigned or mis-signed releases).
- **Provenance / reproducibility breaks.** Any defect that makes `make reproduce` fail to regenerate a
  published figure or table from raw inputs, or that breaks the trace from a published number back to
  its source — because an unreproducible claim cannot be trusted or audited.

### In scope — conventional code & infrastructure threats

- Memory-safety, injection, deserialization, path-traversal, or SSRF issues in `intake.py`,
  `server.py`, the pipeline, or the web map/table.
- Authentication, authorization, or access-control flaws on any intake or admin path.
- Denial of service against intake or the rebuild (the intake is meant to be stateless and
  scale-to-zero; an attack that makes it expensive or unavailable is in scope).
- Secrets exposure (see [Secrets handling](#secrets-handling)).
- Vulnerable or compromised dependencies (see [Supply-chain posture](#supply-chain-posture)).
- Accessibility-affecting security behavior — e.g. a security control that breaks the WCAG 2.2 AA map
  or its equivalent table/list view, since the non-visual equivalent must stay usable.

### Out of scope

- Findings against the **synthetic fixtures** that don't generalize to real data (the fixtures contain
  planted, public, fake hotspots by design — re-identifying a fixture "contributor" is not a finding).
- Reports requiring physical access to the maintainer's machine, or a fully compromised contributor
  device.
- Social-engineering of the maintainer or of contributors.
- Missing security hardening with no demonstrated impact (e.g. "header X is absent") absent an
  exploit or concrete risk.
- Volumetric/network-layer DDoS against third-party hosting infrastructure.
- Disagreement with a documented statistical or methodological choice — that belongs in a normal issue
  or discussion, not a security advisory. (We welcome it there.)

## Supply-chain posture

Dependencies and the release pipeline are treated as part of the attack surface:

- **Pinned and hashed dependencies.** Runtime and CI dependencies are pinned to exact versions and
  verified by hash (e.g. `--require-hashes`), so a resolver cannot silently pull a different artifact.
- **`pip-audit`** runs in CI to flag known-vulnerable dependencies; a new advisory against a pinned
  dep is a security event, not a routine bump.
- **`gitleaks`** runs in CI to catch secrets before they reach history.
- **CodeQL** runs static analysis on the codebase for common vulnerability classes.
- **Dependabot** opens dependency-update and security-update PRs, which go through the same lint,
  type, test, and audit gates as any change.
- **Signed releases.** Release tags and artifacts are signed, and published dataset/release artifacts
  carry content hashes, so a consumer can verify they have the genuine, untampered file. SLSA-friendly,
  pinned GitHub Actions are used for the build.
- **Conventional commits, semver, ADRs, and committed `docs/audits/`** keep the provenance of every
  change auditable.

If you find a malicious or vulnerable dependency, a way to bypass the pinning/hashing, or a flaw in
the release-signing or artifact-verification path, report it through the private channel above.

## Secrets handling

- Secrets and credentials are supplied via **environment variables (or the CI secret store) only, and
  are never committed** to the repository. There are no secrets in source, fixtures, notebooks, or
  the published data path.
- `gitleaks` runs in CI as a backstop against accidental commits of credentials.
- The published GeoJSON, public dataset, data card, and the read-only map server are built from
  already-public, aggregated, jittered artifacts and must never carry a secret, a raw report, or a
  pre-jitter coordinate.
- If you discover a leaked secret in the repository, its history, the published artifacts, logs, or
  CI output, **report it privately** — do not post it. If a live credential is exposed, we will treat
  rotation as the first action.

## A note on contributor privacy as a security property

Most projects scope security to code execution and secrets. nearmiss deliberately scopes it wider.
The people this dataset is built to protect — cyclists and pedestrians, disproportionately the
disabled, low-income, and otherwise vulnerable road users — take on real risk by telling us *where
they travel and where they were nearly hurt*. A dataset that re-identifies them, or that an adversary
can poison to discredit, is not merely buggy; it is unsafe in exactly the way the project exists to
oppose.

So the same disclosure discipline applied to a remote-code-execution bug is applied to a
re-identification path or a poisoning technique. Privacy and integrity defects are triaged with the
same seriousness, mitigated with the same urgency, and — where a published artifact is implicated —
withdrawn first and rebuilt reproducibly. The full reasoning, asset inventory, adversary model, and
mitigations live in [`docs/THREAT-MODEL.md`](docs/THREAT-MODEL.md).

Thank you for helping keep the people behind the data safe.
