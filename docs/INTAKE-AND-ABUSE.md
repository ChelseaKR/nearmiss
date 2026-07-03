# Contributor intake & abuse defense — design proposal

**Status:** design + phase-1 slice built. The contributor form and the
moderation queue described here are **implemented** — see
[`docs/SUBMISSIONS.md`](SUBMISSIONS.md) for what shipped (the form, the
pending → approved/rejected lifecycle, schema validation, identifier-leak and
near-duplicate flagging) and what remains future work (the network-edge defenses
B2–B3/B6 below). Drives backlog items **R40–R44** and **E13–E16** from the
[synthetic user-research panel](research/2026-06-20-synthetic-user-interviews.md).

Three advocacy personas came to *contribute a near-miss* and found no door — the
site is read-only; intake today is a JSON schema (`schema/report.schema.json`)
and a CLI (`nearmiss intake`). Opening that door is the single most-requested
expansion. It is also the one that **triples the threat model**: the moment we
accept public reports, we invite flooding, astroturfing, doxxing-by-report, and
data poisoning. This document scopes the form *and* the defense together, because
shipping one without the other would be a mistake.

It is deliberately a design, not code: several choices are the maintainer's to
make (collected in [Open decisions](#open-decisions-for-the-maintainer)).

## Goals and non-goals

**Goals**
- An accessible, mobile-first, bilingual way to submit a near-miss in under ~20
  seconds from the curb (persona P03/P04).
- Preserve every hard rule, especially **HR4 (contributor privacy)** and **HR3
  (bias named, not hidden)**, end to end.
- Make the published artifact no less trustworthy than it is today — ideally more,
  because abuse is actively resisted rather than assumed away.

**Non-goals**
- Not a 311 queue, not a complaint inbox, not a driver/plate-reporting tool (see
  the anti-features in the research panel). No real-time raw feed.
- No accounts with personal identity. No per-reporter public profiles.

## Part A — The contributor path

### A1. The form
- **Minimal and fast:** one map pin (or "use my location" with a coarse default),
  one-tap `hazard_type`, one-tap `severity`, optional note. Everything else
  (mode default `cyclist`, timestamp, language) inferred or optional.
- **Accessible by construction:** native controls, full keyboard operation,
  labels + error text, target sizes ≥ 24×24 px, works at 200% zoom and with a
  screen reader — the same WCAG 2.2 AA bar the rest of the site meets. **No visual
  CAPTCHA** (it breaks that bar); see [A4](#a4-abuse-resistance-that-doesnt-break-accessibility).
- **Bilingual first:** EN/ES parity with the rest of the chrome, `language`
  recorded per the schema so `bias.py` can characterize language-based
  under-reporting.
- **Privacy explainer *before* the first field** (persona P04): one sentence —
  "We publish only aggregated street-block rates; we fuzz locations and never
  publish your exact spot, time, or any identifier." Link to the threat model.
- **Offline-capable (PWA):** capture in a dead zone, queue locally, sync later
  (E13). Optional photo is a *later* phase (it carries EXIF/PII risk — strip
  metadata, and treat as private-only).

### A2. The endpoint
- **Serverless, scale-to-zero** intake function. It validates the payload against
  `report.schema.json` (the contract already exists), assigns a UUID, and writes
  to the **private** raw store (`data/raw/`, gitignored — HR4). It returns only a
  thank-you; it never echoes other reports.
- **No precise data ever leaves the private boundary.** Publication remains the
  only path from `raw/` to `published/` (`publish.py`), which already aggregates
  to segments, applies jitter, and withholds low-count blocks (k-anonymity).
- **Acknowledgement loop** (R43): "your report helped flag B St" once a segment
  crosses the publish threshold — computed from public aggregates, never exposing
  who else reported.

## Part B — Abuse defense (the part that must exist before launch)

### B1. Expanded threat model
Public intake adds adversaries the published-only artifact never faced:

| Threat | What it looks like | Primary defense |
|---|---|---|
| **Flooding / DoS** | thousands of junk reports | rate limits (B2), proof-of-work (B3), serverless autoscaling + cost caps |
| **Astroturf / ballot-stuffing** | many reports on one block to manufacture a hotspot | per-source influence caps (B4), burst/outlier detection (B5), moderation (B6) |
| **Targeted false reports** | inventing danger on a street to push a project, or suppressing a real one | influence caps + human review of anomalies; publish only aggregates |
| **Doxxing-by-report** | crafting a report to expose where a specific person rides | k-anonymity + jitter already withhold this; add rare-combination suppression (B7) |
| **Scraping the raw store** | exfiltrating private precise reports | the raw store is never public; endpoint is write-only |
| **Data poisoning of the stats** | skewing rates/significance with crafted inputs | robust aggregation (B4) + the existing dedup/snap thresholds |

This extends [`docs/THREAT-MODEL.md`](THREAT-MODEL.md); building intake means
updating that document, not just this one.

### B2. Rate limiting
- Layered: per-IP, per-session, and per-coarse-area, with low ceilings (a human
  on the curb reports a handful of times a day, not hundreds). Sliding-window.
- Soft-fail accessibly: over the limit returns a clear, polite message, never a
  silent drop.

### B3. Friction without a CAPTCHA (accessibility-safe)
- Prefer **invisible** challenges: a lightweight **proof-of-work** token computed
  in the browser (costs an abuser at scale, invisible to one honest user, fully
  accessible), plus timing/behavioral heuristics.
- If a challenge is ever needed, use an **accessible** one (e.g. a privacy-
  respecting, no-visual-puzzle provider), never an image/audio CAPTCHA that fails
  WCAG. The anti-abuse budget must not be paid by disabled contributors.

### B4. Bounded influence (poisoning resistance)
- Cap how much a single source (token/IP/device) can move a segment: e.g. count
  *distinct reporters* per block, not raw submissions, when computing the rate;
  or down-weight repeated reports from one source. This makes a flood of reports
  from one actor near-worthless without blocking a genuine repeat witness.
- Keep the existing spatial/temporal **dedup** (`pipeline/dedupe.py`) and the
  `min_publish_n` k-anonymity floor — both already blunt single-actor manipulation.

### B5. Burst / outlier detection
- Flag anomalous spikes: many reports on one segment in a short window, from few
  sources, or with improbable spatial/temporal patterns. Flagged clusters go to
  review (B6), not straight to publish. This is an *analysis* control, fully
  reproducible and testable on fixtures.

### B6. Moderation queue & trust tiers
- A human-review queue for flagged/anomalous reports before they influence a
  published release. Most reports pass automatically; only anomalies surface.
- Optional trust tiers: known-good pseudonymous tokens (verified contributors,
  partner orgs) get lighter friction; brand-new sources get more. No identity,
  just reputation on an opaque token.

### B7. Privacy hardening for rare combinations
- A rare `hazard_type` on a low-traffic block at a fine location could re-identify
  a reporter even after aggregation. Suppress rare-attribute combinations below a
  threshold (extend the existing small-n `hazard_breakdown` suppression), and
  document the re-identification model (R47). The re-identification model is now
  documented in [`RE-IDENTIFICATION.md`](RE-IDENTIFICATION.md); the
  extend-suppression half of B7 is still pending.

### B8. Reproducibility of the defenses
- Every automated control (rate caps, influence caps, burst detection) is a
  documented, **testable** rule with fixtures — same standard as the stats. "We
  blocked this" must be as reproducible as "we ranked this" (HR5).

## Rollout phases

1. **Closed pilot** — one city, invite-only tokens, manual review of every
   report. Validates the form, the privacy boundary, and the acknowledgement loop
   with near-zero abuse risk.
2. **Invite / partner** — advocacy orgs distribute tokens; trust tiers on;
   automated dedup + influence caps live; moderation reviews anomalies only.
3. **Open** — public form with full B2–B7 stack and a published, plain-language
   moderation policy. Only enter this phase once the defenses are proven in 1–2.

A report never short-circuits the privacy or significance pipeline; it always
flows raw → (validate, rate-limit, dedup, influence-cap, burst-check) →
private store → `publish.py` (aggregate, jitter, k-anon) → public.

## Open decisions for the maintainer

These are yours to set before build; each changes the design materially:

1. **Hosting:** which serverless platform / region (cost, privacy jurisdiction)?
2. **Identity:** anonymous-only, or optional pseudonymous tokens for trust tiers?
3. **Moderation:** who staffs the review queue, and at what SLA? (Gates the open
   phase.)
4. **Friction:** proof-of-work only, or an accessible challenge provider as
   backup — and which?
5. **First city:** pilot where you have ground-truth to sanity-check against
   (Davis? Sacramento, with SACOG counts?).
6. **Photos/notes:** include in phase 1, or defer until metadata-stripping and
   note-moderation are built?

## Why this order

The research panel's privacy/security persona put it plainly: *"Your published
file is careful. The moment you accept public reports, your threat model triples.
Plan it now, not after."* This proposal exists so that when the form ships, the
defenses ship with it — not as a retrofit after the first astroturf campaign.
