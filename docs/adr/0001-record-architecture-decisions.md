# 1. Record architecture decisions

- Status: Accepted
- Date: 2026-06-16
- Deciders: Chelsea Kelly-Reif (maintainer)
- Tags: process, governance, documentation

## Context

`nearmiss` makes claims that are supposed to hold up when a skeptical traffic engineer pushes back.
The same standard applies to how the project is built, not only to what it publishes. The dataset and
the analysis are the product, and their value is entirely a function of trust, so the decisions that
shape the pipeline — how reports are deduped, how a denominator is attached, which significance test
defines a "cluster," how coordinates are fuzzed before publication — are load-bearing. They deserve a
record that explains *why*, not just a diff that shows *what changed*.

This project has specific properties that make undocumented decisions expensive:

- **It is single-maintainer and long-lived.** There is one person (the maintainer) and no team memory
  to fall back on. A decision made in 2026 has to be legible to the same person in 2028, and to any
  future contributor or auditor, without a verbal hand-off that will never happen.
- **It is reproducible end to end (HR5).** `make reproduce` regenerates every figure and table from
  raw inputs. The *code* of a transform is reproducible, but the *reasoning* behind a parameter — why
  Getis-Ord Gi\* rather than raw KDE peaks for "statistically significant cluster," why a particular
  fuzzing radius, why a given small-sample threshold — is not visible in the code and is exactly what a
  reviewer needs to evaluate.
- **It makes statistical and privacy commitments that constrain design.** The five hard rules (no rate
  without a denominator; no estimate without an interval; reporting bias named, not hidden; contributor
  privacy protected; open and reproducible) are enforced in CI and by policy. When a design choice
  trades against one of those rules, the trade-off must be recorded so it can be revisited honestly
  rather than silently eroded.
- **It is auditable on purpose.** The repo already commits `docs/audits/`, a threat model, a data card,
  and an accessibility conformance trail toward a VPAT 2.5 (Rev 508) ACR. An auditor reconstructing why
  the system behaves as it does needs the decision history, and reconstructing it from commit messages
  and chat logs after the fact is unreliable and lossy.

Without a durable record, decisions get re-litigated, reversed by accident, or forgotten until a
change quietly breaks an invariant a reviewer assumed was deliberate. Commit messages are too granular
and code comments answer "what," not "why this over the alternatives." We need a lightweight,
in-repo, version-controlled artifact that captures the context, the decision, and the consequences of
each significant architectural choice.

## Decision

We will record significant architecture decisions as **Architecture Decision Records (ADRs)**, using
the lightweight format described by Michael Nygard in "Documenting Architecture Decisions" (2011),
which is also the basis of the MADR (Markdown Any Decision Records) convention.

Concretely:

- **Location.** ADRs live in `docs/adr/` as Markdown files, one decision per file.
- **Naming.** Files are named `NNNN-title-in-kebab-case.md`, where `NNNN` is a zero-padded,
  monotonically increasing serial number. This document is `0001-record-architecture-decisions.md`.
- **Structure.** Each ADR has a title, a **Status**, and the sections **Context**, **Decision**, and
  **Consequences** (the Nygard core). MADR-style metadata — date, deciders, and optional
  *Considered options* / *Pros and cons* — may be added when a decision had real alternatives worth
  recording. We keep the format minimal and add sections only when they carry information.
- **Status lifecycle.** An ADR is `Proposed`, then `Accepted` or `Rejected`. A decision that is later
  reversed is marked `Superseded by NNNN` and the superseding ADR notes `Supersedes NNNN`; a no-longer-
  relevant decision is marked `Deprecated`. **ADRs are immutable once Accepted** — we do not rewrite
  history; we supersede it. Typos and broken links may be corrected in place.
- **Scope — what warrants an ADR.** A decision is ADR-worthy when it is architecturally significant:
  it affects the structure of the recorded pipeline stages (`intake` → `pipeline/` → `exposure` →
  `stats/` → `publish` → `brief` → `server`), the published schema or data contract, a statistical
  method or its defining parameters, a privacy/anonymization control, the build or reproducibility
  story, or a cross-cutting commitment such as accessibility conformance. Routine, easily reversible
  choices do not need one.
- **Authoring flow.** A new ADR starts as `Proposed` in a pull request, is reviewed against the five
  hard rules, and is set to `Accepted` when merged. The ADR is part of the same PR as the change it
  justifies whenever practical, so the decision and its implementation land together.

This ADR is the first record and exists to establish the practice itself.

## Consequences

**Positive**

- The reasoning behind the architecture — especially the statistical and privacy choices that the five
  hard rules constrain — becomes a first-class, version-controlled, reviewable artifact instead of
  tribal knowledge held by one maintainer.
- ADRs strengthen reproducibility and auditability. Alongside `make reproduce` and the committed
  `docs/audits/`, threat model, and data card, an auditor or future contributor can reconstruct not
  only *what* the pipeline does but *why* it was designed that way.
- Decisions are reversed deliberately, with a documented supersession, rather than drifting silently.
  An invariant a reviewer assumed was intentional cannot be undone without leaving a trace.
- New contributors gain a fast, honest path into the project's design history without a verbal hand-off.

**Negative / costs**

- Every significant decision now carries a small documentation tax. We accept this; the cost of writing
  a short ADR is far below the cost of re-deriving or accidentally reversing a privacy or statistics
  decision later.
- ADRs can go stale if status transitions are neglected. The immutable-plus-supersede lifecycle and PR
  review mitigate this, but it requires discipline to keep statuses honest.
- There is judgment in deciding what is "architecturally significant." We err toward recording a
  decision when it touches a pipeline stage, the published schema, a statistical method, a privacy
  control, or a hard-rule trade-off, and toward *not* writing one for trivially reversible choices.

**Neutral**

- ADRs are plain Markdown and must pass the same Markdown lint and link checks as the rest of the
  repository. They are documentation, not code, and have no runtime effect.
- This decision is intentionally conventional. Nygard-style ADRs are widely understood, which lowers
  the barrier for any future reader and keeps the project's process legible to outside reviewers.

## References

- Michael Nygard, "Documenting Architecture Decisions" (2011) —
  <https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions>
- MADR (Markdown Any Decision Records) — <https://adr.github.io/madr/>
- ADR overview and patterns — <https://adr.github.io/>
- Project README, "Five hard rules" (HR1–HR5), and `docs/` audit trail (`docs/audits/`,
  `docs/THREAT-MODEL.md`, `docs/DATA-CARD.md`, `docs/ACCESSIBILITY.md`).
