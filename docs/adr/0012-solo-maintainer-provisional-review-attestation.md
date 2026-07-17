# ADR 0012: Allow provisional solo-maintainer review attestation for public previews

- Status: Accepted
- Date: 2026-07-16

## Context

NearMiss is maintained by one person. Its portfolio standards divide controls into mandatory
AUTO-GATEs and judgment-based REVIEW-GATEs. That model correctly prevents an automated check from
being described as a human accessibility review, but an unconditional second-person sign-off can
also make every public preview impossible while the portfolio has no second maintainer.

Browser simulations, DOM inspection, axe, and scripted keyboard paths can produce useful evidence.
They cannot report what NVDA or VoiceOver announced to a human, exercise human judgment on behalf of
the accountable owner, or establish WCAG or ACR conformance. Waiting indefinitely would also delay
feedback from the disabled people the preview is intended to serve. The standard therefore needs a
narrow temporary disposition that preserves both facts.

## Decision

While the portfolio has exactly one accountable maintainer, a REVIEW-GATE may be **provisionally
satisfied for a staged or explicitly labeled public preview** by synthetic/browser evidence plus an
explicit attestation from that human owner. This remains a REVIEW-GATE disposition; it is not a third
gate type and it is not a completed human review.

Every use of this disposition must satisfy all of the following:

1. Every applicable AUTO-GATE is mandatory and green for the exact candidate. This decision creates
   no waiver, warning-only mode, retry-to-green exception, or administrative bypass.
2. A dated, committed review artifact identifies the revision, surface, and REVIEW-GATE; records the
   exact methods, tools/environments, and results; and links durable evidence where available.
3. The artifact lists every material check that was **not performed**. Synthetic results must never
   be relabeled as a manual, assistive-technology, independent, or user test.
4. The artifact names the residual risks, the accountable human owner, the date and source of the
   owner's explicit attestation, and the risk the owner accepts. An AI agent, browser harness, CI job,
   or generated signature cannot be the accountable owner or attest for that person.
5. The artifact limits the disposition to a public-preview or staged scope, gives a concrete rollback
   path and rollback triggers, and supplies an expiry date plus earlier recheck triggers.
6. The public language says which checks remain outstanding and makes **no WCAG, Section 508, ACR,
   VPAT, certification, or complete-conformance claim** on the strength of provisional evidence.
7. A legal, contractual, procurement, safety-critical, or customer requirement for a specified human
   or independent reviewer cannot use this exception. A stable/GA release cannot use it either.

The disposition expires at the earliest of its recorded **expiry date**, a material change to the
reviewed interaction, a relevant accessibility report, an AUTO-GATE regression, the addition of
another active maintainer, or a move from public preview to stable/GA. Renewal requires a new dated
artifact, fresh green AUTO-GATE evidence, and a new explicit owner attestation. Adding a second
maintainer ends the solo-maintainer exception; normal independent review applies from that point
forward.

For accessibility specifically, a screen-reader row remains **Not performed** until a person actually
runs the named assistive technology and browser. Provisional deployment does not change any ACR row or
turn a target into a supported finding.

## Consequences

- A one-person portfolio can expose a bounded preview to real-world feedback without inventing a
  second reviewer or weakening its deterministic gates.
- The accountable owner, evidence, unperformed work, residual risk, rollback, and expiry become
  reviewable in the same repository as the code.
- A provisionally satisfied REVIEW-GATE remains incomplete for conformance, procurement, stable
  release, and any later release whose scope or expiry falls outside the record.
- The process adds recurring re-attestation work until the missing human review is completed or a
  second maintainer joins.

## Alternatives considered

- **Treat synthetic browser evidence as a completed screen-reader or human review.** Rejected because
  it would be a false test result and a false conformance claim.
- **Allow the AI agent or CI system to self-attest.** Rejected because neither can accept human
  accountability or experience an assistive-technology interaction.
- **Waive the REVIEW-GATE without a durable artifact.** Rejected because silent risk acceptance is not
  an enforceable standard.
- **Block every preview until independent review is available.** Rejected for a one-person pre-1.0
  portfolio because a bounded, reversible preview with explicit residual risk can produce valuable
  user evidence without being represented as conformant.
