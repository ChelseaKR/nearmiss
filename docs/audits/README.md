# Audit artifacts

**Maintainer:** Chelsea Kelly-Reif (GitHub [@ChelseaKR](https://github.com/ChelseaKR)).
**Applies to:** every released version of nearmiss and the dataset it publishes.

This directory holds nearmiss's **audit artifacts**: the security scans, accessibility conformance
reports, dependency audits, and reproducibility / interval-coverage checks that demonstrate the
project did what it says it does. They are committed to version control as durable, dated evidence —
not generated on demand and thrown away, not linked off to a CI dashboard that expires, not screenshots
in a chat. This is the **"audit as artifact"** discipline: an audit that cannot be re-read, diffed, and
cited a year later is not evidence, it is a claim.

The standard for these files is the same one the analysis is held to: they should **hold up when a
skeptical reviewer pushes back.** An auditor, a traffic engineer, an advocate at a public hearing, or a
future version of the single maintainer should be able to open this directory and reconstruct what was
checked, when, with which tool at which version, what passed, what did not, and what the open
remediation items were — without a verbal hand-off that will never happen.

---

## Why these are committed, not ephemeral

CI runs are the *execution* of an audit; the files in here are its *record*. CI logs roll off, runners
are torn down, and a green check mark proves nothing to someone reading the repository six months later.
The five hard rules (see the [README](../../README.md#hard-rules-enforced-not-aspirational)) make the
dataset and the analysis the product, and the value of that product is entirely a function of trust.
Trust needs a paper trail that lives next to the code.

Committing the artifacts buys four things:

- **Durability.** The evidence survives the CI run that produced it. A published dataset version can be
  paired, forever, with the exact audit state at its release.
- **Diffability.** Because each artifact is plain Markdown (or plain text/JSON), `git diff` between two
  releases shows precisely what changed — a newly suppressed lint rule, a dependency advisory that
  appeared, an accessibility criterion that slipped from *Supports* to *Partially Supports*. Regressions
  are visible, not silent.
- **Citability.** An advocacy brief or the data card can reference a specific, permanent file at a
  specific commit: "as of the `0.4.0` release, the dependency audit reported zero known-exploitable
  advisories (see `docs/audits/YYYY-MM-DD-dependency-audit.md`)."
- **Auditability on purpose.** The repo already commits ADRs (`docs/adr/`), a threat model, a data card,
  and an accessibility conformance trail. This directory is the corresponding evidence trail. Together
  they let an outside reviewer verify the project rather than take its word.

These files are **records, not gates.** The gate is CI — lint, types, tests, accessibility, and security
checks block merges and releases. The artifacts here are the committed *proof* that the gate ran and what
it found. A failing or honestly-caveated artifact is information, not an embarrassment to hide; a
*Partially Supports* row with a named gap and a remediation status is more credible than a wall of green.

---

## Naming and date convention

Every artifact is named:

```text
YYYY-MM-DD-<kind>.md
```

- **`YYYY-MM-DD`** is the ISO 8601 date the audit was *run and committed* (the release date for
  release audits, or the run date for an out-of-cycle check). Lexical sort equals chronological sort, so
  the directory listing is the timeline.
- **`<kind>`** is one of the audit kinds below, in lowercase kebab-case (for example
  `security-scan`, `dependency-audit`, `axe-report`, `interval-coverage`).
- The **extension** is `.md` for human-readable reports. Where a tool emits a machine-readable record
  worth keeping verbatim (an SBOM, a raw axe JSON, a `pip-audit` JSON), it is committed alongside the
  Markdown summary with the same date-and-kind stem and the tool's native extension — for example
  `YYYY-MM-DD-dependency-audit.json` next to `YYYY-MM-DD-dependency-audit.md`. The Markdown is the
  narrative an auditor reads; the raw file is the artifact a tool can re-verify.

If more than one audit of the same kind is committed on the same calendar day (rare — usually an
out-of-cycle re-run after a fix), append a short, lowercase suffix: `YYYY-MM-DD-<kind>-2.md`.

Each artifact begins with a short header that records, at minimum: the **kind**, the **date**, the
**release tag or commit** it corresponds to, the **tool and exact version** used (so the result is
reproducible and a tool-version change is visible in the diff), and a one-line **summary verdict** with
any open remediation items called out. Do not rely on the filename alone to carry this — the filename is
the index, the header is the record.

---

## Regenerated and re-committed on each release

Audits are **regenerated and re-committed on every release.** A tagged release is not complete until the
audit set for that version is produced and committed. This keeps the evidence honest in two directions:

1. **Every release has a matching, dated audit set.** There is no released version whose security,
   accessibility, dependency, and reproducibility state is undocumented. The audit dated nearest a
   release tag *is* that release's evidence.
2. **Drift is visible.** Because old artifacts are kept rather than overwritten in place, the diff
   between one release's audit and the next shows the project's trajectory — advisories opened and
   closed, accessibility criteria gained or regressed, interval-coverage holding or slipping. The
   history is the point; we do not rewrite it.

Out-of-cycle audits also belong here when something material happens between releases — a security
advisory against a pinned dependency, an accessibility fix verified before its release ships, a
reproducibility break and its repair. They follow the same naming convention and are dated to the day
they ran.

The release flow, at a high level:

- `make verify` reproduces the full CI gate locally (lint, types, tests, accessibility, security).
- `make reproduce` regenerates every figure and table in the briefs from raw inputs, which is what the
  reproducibility and interval-coverage audits attest to (HR5).
- The resulting artifacts are written here with today's date, reviewed, and committed as part of the
  release — under conventional commits and a signed tag, like everything else in the repo.

---

## Kinds of audits kept here

The set below is the standing list. Each maps to a hard rule, a CI gate, or both, and to the companion
document that explains the policy the audit verifies.

### Security

- **`<date>-security-scan.md`** — results of the static and secret-scanning gates: **CodeQL** static
  analysis, **gitleaks** secret detection, and any other code-security checks. Records findings,
  triage, and dispositions. Companion: [`SECURITY.md`](../../SECURITY.md),
  [`THREAT-MODEL.md`](../THREAT-MODEL.md).
- **`<date>-dependency-audit.md`** (plus a `.json` and/or **SBOM** where useful) — **`pip-audit`**
  output against the **pinned, hashed** dependency set, with each known advisory listed and its status
  (not applicable / mitigated / accepted with rationale / fixed). Records the dependency snapshot the
  release was built from. Companion: [`SECURITY.md`](../../SECURITY.md).
- **`<date>-supply-chain.md`** — the integrity story for a release: that runtime and CI dependencies are
  pinned and verified by hash, that GitHub Actions are pinned, that the release is **signed** and its
  published artifacts carry **content hashes** a consumer can verify. Companion:
  [`SECURITY.md`](../../SECURITY.md).

### Accessibility

- **`<date>-axe-report.md`** (plus raw axe JSON where useful) — automated accessibility scan results
  from **axe-core** across the map view, the equivalent list/table view, the data table, the report
  form, the hotspot legends, and the charts. Companion: [`ACCESSIBILITY.md`](../ACCESSIBILITY.md).
- **`<date>-manual-a11y-review.md`** — the manual screen-reader and keyboard pass that automation cannot
  replace: **NVDA** and **VoiceOver** traversal, keyboard-only operation, focus order and visibility,
  and — most importantly — that **every finding on the map is reachable in full without seeing the map**
  via the equivalent view. Companion: [`ACCESSIBILITY.md`](../ACCESSIBILITY.md).
- **`<date>-acr-snapshot.md`** — the release-pinned state of the **Accessibility Conformance Report
  (VPAT 2.5, Rev 508)**. The living ACR lives at [`docs/accessibility/ACR.md`](../accessibility/ACR.md);
  this is the dated snapshot that ties a specific conformance claim to a specific release, including any
  *Partially Supports* rows and their open remediation items. Companion:
  [`docs/accessibility/ACR.md`](../accessibility/ACR.md).

### Reproducibility and statistical integrity

- **`<date>-reproducibility.md`** — attests that `make reproduce` regenerates every published figure,
  table, and the public GeoJSON from raw inputs, and that the regenerated outputs match by content hash
  (HR5). Records the input snapshot, the tool/environment versions, and the resulting hashes.
- **`<date>-interval-coverage.md`** — the check that confidence intervals are honest, not decorative
  (HR2): on the synthetic fixtures with **known planted hotspots and known true rates**, the reported
  intervals achieve their nominal coverage, small-sample segments are shown as uncertain rather than
  ranked as certain, and Getis-Ord Gi\* recovers the planted clusters at the stated significance.
  Companion: [`METHODOLOGY.md`](../METHODOLOGY.md).
- **`<date>-denominator-and-bias.md`** — verifies the rate/exposure and bias-disclosure rules: that no
  published rate lacks a stated denominator with a source and date (HR1), that raw-count surfaces are
  labeled "report volume" and never "danger," and that the reporting-bias characterization produced by
  `bias.py` is present and names who is over- and under-represented (HR3). Companion:
  [`METHODOLOGY.md`](../METHODOLOGY.md), [`DATA-CARD.md`](../DATA-CARD.md).

### Privacy

- **`<date>-privacy-review.md`** — verifies the contributor-privacy controls before a dataset version
  ships (HR4): that the public dataset is aggregated to public street segments, that low-count segments
  are withheld (k-anonymity), and that no precise coordinate, timestamp, or reporter token appears in any
  published artifact, so no report is published at a precision that could identify a person's routine,
  and that raw precise reports remain private and gitignored (`data/raw/` is never committed). Companion:
  [`THREAT-MODEL.md`](../THREAT-MODEL.md), [`DATA-CARD.md`](../DATA-CARD.md).

This list grows as the project does. A new standing check earns a new `<kind>`; a one-off investigation
is dated and committed under the closest existing kind with a descriptive header. When the *meaning* of a
kind changes — a new tool, a changed threshold, a different scope — that is an architectural decision and
is recorded as an ADR in [`docs/adr/`](../adr/), with the audit artifacts showing the change from the
release it takes effect.

---

## How to read an artifact in this directory

1. **Start from the header.** It states the kind, the date, the release/commit, the tool versions, and
   the verdict. That is the fastest honest summary.
2. **Read the open items, not just the verdict.** A credible audit names its gaps. *Partially Supports*,
   *accepted with rationale*, and *remediation tracked in #NN* are the rows that matter most.
3. **Diff against the previous release** to see what moved. `git log` over this directory is the
   project's audit timeline; `git diff <old>..<new> -- docs/audits/` is its changelog of trust.
4. **Reproduce it.** The header records the tool and version; `make verify` and `make reproduce` re-run
   the underlying checks. An artifact you can regenerate is the only kind worth committing.

For the policies these artifacts verify, see [`SECURITY.md`](../../SECURITY.md),
[`docs/THREAT-MODEL.md`](../THREAT-MODEL.md), [`docs/ACCESSIBILITY.md`](../ACCESSIBILITY.md),
[`docs/accessibility/ACR.md`](../accessibility/ACR.md), [`docs/METHODOLOGY.md`](../METHODOLOGY.md),
[`docs/DATA-CARD.md`](../DATA-CARD.md), and the architecture decisions in [`docs/adr/`](../adr/).
