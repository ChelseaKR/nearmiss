# Roadmap ideation — large-scale fixes & expansions

**Drafted 2026-07-01.** This folder is the third planning layer for nearmiss: extensive
ideation on deep structural fixes and larger expansions that the existing planning
documents do **not** already contain. It was produced from a fresh read of the code,
docs, CI, and git history on 2026-07-01.

## How this relates to the existing planning layers

nearmiss already has three planning layers. This folder references them by ID and
deliberately does not repeat them:

1. **The README Roadmap** (`README.md` § Roadmap) — the original build spec, Phases 1–4
   (schema/intake/pipeline → exposure & honest statistics → publish & advocate →
   generalize). Largely delivered at beta.
2. **The 2026-06-20 synthetic user panel**
   (`docs/research/2026-06-20-synthetic-user-interviews.md`) — 24 personas, backlog IDs
   `R1–R70` (remediations) and `E1–E60` (expansions), plus an anti-features list.
3. **The 2026-06-30 research pass** — `docs/RESEARCH-ROADMAP.md` (IDs `RR-01…RR-15`,
   `RE-01…RE-12`) and `docs/USER-RESEARCH.md`. **Honesty note (updated 2026-07-12):**
   the 2026-07-01 revision of this paragraph recorded that these documents, the `RR-02`
   overdispersion code, and the `RR-05` MAUP rank-stability module existed only on the
   unmerged branch `research-panel-and-roadmap`. That branch has since been reconciled
   (FIX-01): all of it is on `main` now.

Where an idea below builds on an existing item, it cites the item's ID (`R#`, `E#`,
`RR-#`, `RE-#`) and states what is *new beyond it*. Nothing in this folder restates an
item those documents already carry.

## Contents

| File | What it holds |
| --- | --- |
| [`01-deep-dive.md`](01-deep-dive.md) | Current-state assessment from a 2026-07-01 read of the code: architecture, genuine strengths, observed structural debt, portfolio position. |
| [`02-large-scale-fixes.md`](02-large-scale-fixes.md) | 14 deep structural fixes (FIX-01…FIX-14): correctness, data model, doc-code parity, privacy, performance, operability. |
| [`03-expansions.md`](03-expansions.md) | 16 expansion ideas (EXP-01…EXP-16) in three horizons: deepen the core, adjacent capabilities, transformative bets. |
| [`04-impact-and-sequencing.md`](04-impact-and-sequencing.md) | Impact×effort matrix over all IDs, dependencies, a Now/Next/Later sequence beyond the existing roadmaps, and the human/legal/SME/real-data gate list. |

## Status ledger (2026-07-12)

Every item now carries an inline **Status** line under its heading. As of
2026-07-12 all fourteen fixes (FIX-01…FIX-14) and fourteen of the sixteen
expansions are shipped on `main`; the two that remain open are the gated
transformative bets **EXP-14** (governed open data standard) and **EXP-15**
(federated instance commons), both blocked on real external partners and
legal/SDO processes rather than on code.

## What this folder is not

These are **ideas for evaluation, not commitments**. Effort tiers are first-pass triage,
not estimates anyone has signed up for. Several items are explicitly gated on things
that cannot and should not be faked — real collision data, a real statistician's review,
a real screen-reader session, legal review of data-sharing terms — and
`04-impact-and-sequencing.md` names those gates rather than pretending they are
optional. Where this folder and the code disagree, the code and its tests are
authoritative and this folder is the bug (the same rule `docs/METHODOLOGY.md` applies to
itself).
