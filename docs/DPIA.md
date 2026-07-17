# Data Protection Impact Assessment (DPIA) — nearmiss public submission intake

**Status: initial DPIA, v1.** **Date: 2026-07-05.** **Assessor: Chelsea Kelly-Reif (sole maintainer).**
**Next review: before any material change to the intake, moderation, or publish path, and at minimum
alongside the next dated review of [`docs/THREAT-MODEL.md`](THREAT-MODEL.md).**

> **Deployment update (2026-07-16):** the synthetic city UI and browser submission prototype are no
> longer included in the production static artifact. The source, CLI intake/moderation path, and this
> DPIA remain because local/operator imports still process precise reports and any future public
> intake reactivation must be reviewed against this document before deployment.

> **Honesty note.** This is a maintainer-authored, first-pass DPIA for a solo-maintainer open-source
> project — not a formal legal opinion, not reviewed by a data-protection officer or counsel, and not a
> claim of regulatory compliance with any specific jurisdiction's law. It follows the standard DPIA
> shape (screening, description of processing, necessity/proportionality, risk identification,
> mitigations, sign-off) so it is checkable against that shape, and it is written to the same standard
> as the rest of this project: where something is a gap, it says so. This document became due the
> moment the public submission form and moderation queue shipped (`#18`, 2026-06-29), because that
> feature accepts precise location data — the most sensitive input this project handles — directly
> from third parties for the first time. It should have been written closer to that date; this is a
>2026-07-05 correction of that lag, not a claim that the gap didn't exist in between.

---

## 1. Screening — is a DPIA needed?

| Screening question | Answer |
|---|---|
| Does the processing involve systematic and extensive evaluation of personal aspects, automated decision-making with legal/significant effects? | No individual-level automated decisions are made about a person; the pipeline produces *segment-level* aggregate statistics, never a per-person score or decision. |
| Large-scale processing of special-category data? | No special-category data (health, ethnicity, religion, etc.) is intentionally collected. Precise **location** data tied to a real person's movement pattern is collected and is treated here as sensitive-by-nature even though it is not a GDPR "special category," because it can reveal where someone lives, works, and travels. |
| Systematic monitoring of a publicly accessible area? | Arguably yes in a loose sense (near-miss reports describe public streets), but nearmiss does not monitor continuously or track identified individuals — it accepts voluntary, episodic, self-submitted reports. |
| New technology, or a novel/large-scale use of data? | The public submission form (2026-06-29) is a materially new data flow: third parties now submit precise coordinates directly, where previously only the maintainer's own CLI-driven imports touched the private raw store. **This is the trigger for this DPIA.** |
| Could the processing prevent someone exercising a right, using a service, or entering a contract? | No — reporting is voluntary and reporting nothing has no consequence for the reporter. |

**Conclusion: a DPIA is warranted and this is it.** The trigger is specifically the shift from
maintainer-curated imports to **direct public submission of precise location data by third parties**.

## 2. Description of the processing

- **What is collected** (`schema/report.schema.json`, via `web/submit.html` / `web/submit.js` or
  `nearmiss submit`): a precise `location` (lat/lon) **or** a free-text address; `occurred_at`
  (timestamp); `mode` (e.g. cyclist); `hazard_type`; `severity`; an optional free-text `note`; an
  optional BCP-47 `language` tag; an optional pseudonymous reporter token. **No name, email, phone,
  account, or device identifier is collected by design** (`docs/SUBMISSIONS.md` "Privacy posture").
- **Why it's collected (purpose).** To build an exposure-normalized, statistically honest public dataset
  of road-hazard risk for safe-streets advocacy — see README "Why this exists." The precise location is
  necessary transiently (to snap a report to the correct street segment); it is not needed, and is not
  used, at its submitted precision for anything published.
- **Where it lives.** Submissions land first in the **private, gitignored** pending store
  (`data/pending/`), then — after human moderation approval (`nearmiss moderate approve`) — in the
  **private, gitignored** raw store (`data/raw/`). Neither directory is ever committed, served, or
  reachable through the read-only map server (`server.py` refuses `data/raw/`-scoped requests with
  HTTP 403 even when launched at the repo root).
- **What gets published.** Only the aggregated output of `publish.py`: per-**street-segment** (not
  per-report) counts, exposure-normalized rates with confidence intervals, and quality flags — with
  segments below `min_publish_n` (default 3) withheld entirely. No per-report coordinate, timestamp,
  reporter token, note, mode, severity, or heading is ever published (`assert_published_clean`,
  `assert_metadata_clean`, tested in `tests/test_publish_privacy.py`).
- **Who processes it.** The sole maintainer, via the CLI moderation workflow
  (`nearmiss moderate list/approve/reject/export`, `src/nearmiss/moderation.py`). No third-party
  processor, analytics vendor, or ad network touches submission data. No AI/LLM system processes it
  (see [`docs/adr/0004-standards-applicability.md`](adr/0004-standards-applicability.md) — AI-EVALUATION
  is N/A for this whole repo).
- **Retention.** Precise reports in `data/pending/` and `data/raw/` are retained **indefinitely on the
  maintainer's local/private storage today — there is no automated retention/deletion policy or
  scheduled purge job.** This is a genuine gap, named here rather than glossed over (see §5, Gap G1).
  The **published, aggregated** artifact is versioned and retained per the release/deprecation policy in
  `CHANGELOG.md` (superseded versions are withdrawn or annotated, never silently mutated).
- **Cross-border transfer.** None beyond wherever the maintainer's machine and GitHub's infrastructure
  are located; there is no third-party data processor and no international transfer mechanism to
  assess.

## 3. Necessity and proportionality

- **Is precise location necessary?** Yes, transiently: the pipeline must snap a report to the correct
  street segment, which requires a coordinate (or a geocodable address) at least as precise as "which
  block." It is **not** necessary at that precision for anything downstream of the snap step, and it is
  discarded (not published) after snapping — this is enforced structurally (allowlist in
  `publish._feature`, denylist invariant in `assert_published_clean`), not just by policy.
- **Is a free-text note necessary?** No — it is optional, and its absence does not block a submission.
  Its value (context on what happened) is weighed against its risk (a note can contain
  self-identifying detail or identify a third party); the identifier-leak heuristic in
  `moderation.py` flags — but does not block or silently strip — notes matching an email/phone/plate
  pattern, surfacing them for human review rather than auto-publishing or auto-rejecting.
- **Is a reporter token necessary?** No — it is optional and pseudonymous by design; there is no
  identity field anywhere in the schema, and none is planned. This is treated as a hard, non-negotiable
  design constraint (see README hard rule 4 and `CONTRIBUTING.md`'s privacy rule), not a default that
  could be quietly loosened.
- **Could a less intrusive design achieve the purpose?** Considered and rejected: collecting only a
  segment ID instead of a coordinate would remove the pipeline's ability to independently verify or
  audit snapping quality and would push the precision burden onto the *reporter* to self-select the
  correct segment — worse for people unfamiliar with segment boundaries and worse for data quality. The
  current design (accept a coordinate, discard it after use) is judged proportionate: the sensitive
  input is used for the minimum necessary purpose and does not survive into the published artifact.

## 4. Risk identification and mitigations

This section names the same risks as [`docs/THREAT-MODEL.md`](THREAT-MODEL.md) T1/T2 and the
[Residual risk register](THREAT-MODEL.md#residual-risk-register) RR-1/RR-2, from the data-subject's
(the reporter's) point of view rather than the project's.

| Risk to the data subject (reporter) | Likelihood | Severity if realized | Mitigation | Residual risk |
|---|---|---|---|---|
| A published artifact re-identifies where I live/work/travel | Low (per-submission) | High | Aggregation to public street segments; k-anonymity floor (`min_publish_n`); no per-report coordinate, time, or token published; small-sample hazard-breakdown suppression | **Medium** if I (the reporter) submit many reports clustered near one address — named in THREAT-MODEL RR-1, disclosed to reporters via the pre-submission privacy explainer in `web/submit.html`/`submit.js` |
| My free-text note leaks my identity or someone else's | Low | Medium–High | Identifier-leak heuristic flags for human review before anything is published; notes are never published verbatim under any circumstance (not in scope, `assert_published_clean`) | Low — the note never reaches the public artifact regardless of the flag outcome |
| My submission sits in an unretained private store indefinitely, beyond what's needed | Certain (this is the current default behavior) | Low–Medium (a longer-lived copy is a larger blast radius if the maintainer's storage or account is compromised — see THREAT-MODEL RR-6) | None implemented yet | **Medium — this is Gap G1 below, not yet mitigated** |
| A moderator (the maintainer) mishandles or over-shares a pending/raw report | Low (solo maintainer, no other humans see pending data) | High if it happened | Moderation is a private, local CLI workflow; no pending/raw data is ever transmitted to a third party or service | Low, but see RR-6 (no separation of duties — a structural, disclosed limitation of a one-person project) |
| A public submission is used to target or harass someone named in a note, or to infer a home address from repeat reports | Low | High | No name/identity field exists; notes are never published; aggregation + k-anonymity as above | Medium — same underlying risk as row 1, from an adversary's perspective rather than accidental disclosure |

## 5. Gaps (named, not hidden)

- **G1 — No retention/deletion policy for `data/pending/` and `data/raw/`.** Precise submissions
  persist indefinitely with no automated purge, and there is no contributor-facing mechanism to request
  deletion of a specific submission before or after moderation. **This is the single most material gap
  this DPIA surfaces.** Recommended remediation (not yet built): (a) a stated retention window (e.g.
  raw reports purged N months after the last release that could plausibly include them), (b) a
  `nearmiss moderate forget <id>` command so a contributor's deletion request has a concrete mechanism,
  (c) documenting both in `docs/SUBMISSIONS.md` and `SECURITY.md`.
- **G2 — No lawful-basis-equivalent statement for jurisdictions with a legal deletion/access right**
  (e.g. GDPR Art. 15/17 access and erasure rights, CCPA/CPRA analogs). As a personal, non-commercial,
  U.S.-based open-source project with no accounts and no monetization, the applicability of these
  regimes is genuinely unclear and has not been reviewed by counsel; this DPIA does not resolve that
  question and does not claim GDPR/CCPA compliance. It is named as an open question, not silently
  assumed away.
- **G3 — No documented process for handling a deletion or access request today**, beyond "email the
  maintainer via `SECURITY.md`'s private-reporting channel," which is not built for this purpose and is
  not advertised to reporters as a deletion path.

None of G1–G3 is fabricated as solved. They are the concrete list a future PR should work through,
and they are the reason this DPIA is versioned "v1" rather than presented as a finished audit.

## 6. Consultation

No external data-protection authority, works council, or formal stakeholder consultation was
conducted — appropriate for a personal open-source project's first-pass DPIA, but named so the scope
of "consultation" here is not overstated: it consists of the maintainer's own review against this
document's structure and the existing `docs/THREAT-MODEL.md` analysis.

## 7. Sign-off

| Field | Value |
|---|---|
| Assessed by | Chelsea Kelly-Reif (sole maintainer) |
| Date | 2026-07-05 |
| Outcome | Processing proceeds. Necessity/proportionality reviewed and judged acceptable for the stated purpose. Residual risks RR-1/RR-2 (THREAT-MODEL) are accepted and disclosed to reporters via the pre-submission privacy explainer. **Gap G1 (no retention policy) is the one open item that should be prioritized before this DPIA can be called complete rather than initial.** |
| Next review trigger | Before any change to intake/moderation/publish; before opening the "Invite/partner" or "Open" rollout phases in `docs/INTAKE-AND-ABUSE.md`; at minimum alongside the next `docs/THREAT-MODEL.md` review. |

## See also

- [`docs/THREAT-MODEL.md`](THREAT-MODEL.md) — the full adversary model and residual-risk register this
  DPIA draws its risk table from.
- [`docs/SUBMISSIONS.md`](SUBMISSIONS.md) — what the public submission form and moderation queue
  actually implement today.
- [`docs/INTAKE-AND-ABUSE.md`](INTAKE-AND-ABUSE.md) — the fuller abuse-defense design, including the
  network-edge controls (rate limiting, proof-of-work) not yet built.
- [`docs/DATA-CARD.md`](DATA-CARD.md) § Privacy: aggregation and minimum occupancy.
- [`docs/RESPONSIBLE-TECH-AUDITS.md`](RESPONSIBLE-TECH-AUDITS.md) — the ASVS level and §A–F
  applicability declarations this DPIA is referenced from (RTF-04).
