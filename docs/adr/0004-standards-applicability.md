# 4. Standards applicability declaration

Date: 2026-07-05

## Status

Accepted

## Context

nearmiss is one repo in a portfolio governed by a shared set of standards (vendored at
`docs/standards/`, pinned via `docs/standards/.standards-version`). Those standards require every repo
to **declare, in its README, which standards apply**, and to mark any as `N/A` with a one-line reason —
"silent omission is itself a defect" (`docs/standards/README.md` §"How a repo declares conformance").

A 2026-07-05 conformance audit (external to this repo, not committed here) found that nearmiss's
README declared **none** of the 11 portfolio standards — not even the ones it obviously and strongly
meets (Accessibility, Internationalization) — and, specifically, that the one standard that does not
apply (AI-EVALUATION) had never been written down as `N/A` anywhere, with no ADR recording that call.
Per `CQ-45` in the portfolio's `CODE-QUALITY-STANDARD.md`, declaring a standard `N/A` requires an ADR;
this is that ADR.

## Decision

Declare applicability for all 11 standards in a new "Standards conformance" table in `README.md`
(added 2026-07-05), reproduced here for the ADR record:

| Standard | Applies to nearmiss? | Reason |
|---|---|---|
| QUALITY-AND-METRICS | Applies | All repos are in scope. |
| CODE-QUALITY | Applies | All repos are in scope. |
| SECURITY-AND-SUPPLY-CHAIN | Applies | Ships code (Python package + CLI + static web UI). |
| CI-CD | Applies | Has CI (`ci.yml`, `mutation.yml`). |
| RELEASE-AND-VERSIONING | Applies | CHANGELOG + SemVer + `pyproject` version; a release pipeline is planned but not yet built (see Roadmap). |
| ACCESSIBILITY | Applies | The nationwide FARS studio is live at nearmiss.chelseakr.com; synthetic methods, submission, and embed HTML remain source-only automated accessibility targets. |
| OBSERVABILITY | Applies (Tier C) | Library/CLI + a local, optional read-only server; the live site is static hosting. Tier C is the lightest tier (structured logs + `/livez`/`/readyz`; no OTel tracing/metrics/SLO requirement). |
| INTERNATIONALIZATION | Applies | Public-facing civic surface; bilingual EN/ES brief and web UI. |
| AI-EVALUATION | **N/A** | No LLM/AI SDK usage anywhere in the codebase (verified by grep for `anthropic`/`openai`/`langchain`/`bedrock`/generic `llm` imports across `src/` and `tools/`; clean). **This N/A is a decision, not an oversight — if this repo ever adds an LLM-backed feature (e.g. an auto-summarized brief, an AI-assisted moderation triage), AI-EVALUATION-STANDARD flips from N/A to Applies immediately (per AIEV-01) and this ADR should be superseded, not edited.** |
| DOCUMENTATION | Applies | All repos are in scope. |
| RESPONSIBLE-TECH | Applies | All repos are in scope; carries extra weight here because the repo now ingests public, precise-location submissions from third parties (`#18`, 2026-06-29). |

## Consequences

- **Positive.** The README's Standards Conformance table is now the single place a reviewer (or a
  future contributor, or another portfolio audit) checks to see what's declared, closing the DOC-11 /
  DOC-12 / RTF-07 / CQ-45 gaps identified 2026-07-05.
- **Positive.** The AI-EVALUATION `N/A` is now a recorded, falsifiable decision with a named trigger
  condition (any LLM SDK use flips it to Applies), not silence that could be mistaken for "not
  considered."
- **Negative / accepted limits.** Several "Applies" rows above are not yet fully met (release pipeline,
  GitHub-side governance evidence, several REVIEW-gate artifacts) — declaring "Applies" is not the same
  as declaring conformance. The README table links each such gap to the relevant open item; see
  `README.md` "Standards conformance" for the current state of each row, since that table is kept
  current and this ADR is not (ADRs are append-only per `CQ-46`; a future re-scoping gets a new ADR,
  not an edit to this one).

## Alternatives considered

- **Do nothing / leave the omission.** Rejected: this is the exact "silent omission" the standard
  calls a defect, and the audit specifically flagged it as a P0.
- **Declare only the standards that are fully met.** Rejected: partial or gapped conformance is still
  "Applies" — the point of the table is to be an honest map of what's in scope and where the gaps are,
  not a scorecard of only the wins.
