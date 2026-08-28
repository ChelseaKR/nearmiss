# Statistical integrity program, 2026 to 2029

A multiyear sequence for one narrow thing: **every number this repository
publishes matches what its own documents say it computes, and every robustness
claim it makes is one that can come back negative.**

This document is a plan with a status column, not a wish list. Each phase is
marked **built**, **buildable**, or **blocked**, and a blocked phase says what
blocks it and what would unblock it. A phase is never marked done on the strength
of a stub, a disabled config key, or a placeholder. Where a phase is blocked on a
person, a credential, an external dataset, or a decision that is the maintainer's
to make, that is written down rather than worked around.

## What this program is not

It is **not** a product plan and it does not overrule one.
[`PRODUCT-EXPANSION-PLAN.md`](PRODUCT-EXPANSION-PLAN.md) is the product strategy;
its "Do not build" list and its freeze on broad expansion are decisions with
stated reasons, and this program honours them. In particular this program adds no
new user surface, no new collection channel, no new public map, and no cross-city
comparison. Everything it touches is the analysis layer that already ships, its
documentation, and its tests.

It is also not a substitute for [`RESEARCH-ROADMAP.md`](RESEARCH-ROADMAP.md),
which remains the backlog of `RR-`/`RE-` items with their citations. This document
sequences the subset of that backlog which is (a) about whether a published number
is correctly described, (b) implementable offline against fixtures with no new
privacy surface, and (c) not on the product plan's stop list. Where the two
disagree about priority, the research roadmap's evidence is the argument and this
document is only the schedule.

The capacity guideline in the product plan applies: the codebase is ahead of its
adoption evidence, and more than half of any period's work should not be another
methods expansion. This program is sized to be the minority share.

## The standard every phase is held to

From [ADR 0017](adr/0017-a-published-statistic-is-checked-against-its-published-description.md):
a published statistic is checked against its published description by a test that
reads both at test time. A phase that adds a statistic ships, in the same change:

- the computation;
- the paragraph in [`METHODOLOGY.md`](METHODOLOGY.md) that describes it in the
  present tense, wrapped in a `<!-- claim:… -->` tag;
- the field-by-field entry in [`schema/dataset.schema.md`](../schema/dataset.schema.md)
  for anything that reaches a published artifact;
- a witness test listed in [`CLAIMS.md`](CLAIMS.md) that `make claims` runs; and
- for any robustness pass, a first-class "did not run" outcome, so a check that
  had nothing to test can never report success (the rule
  [ADR 0016](adr/0016-exposure-sensitivity-uses-declared-denominators-and-may-refuse-to-run.md)
  set for the exposure-sensitivity pass).

A phase that cannot meet all five is not ready, and is listed here as blocked
rather than shipped in half.

---

## Phase 1: published-statistic parity

**Status: built, 2026-08-27.** Planned window 2026 Q3.

Four statements in the published documents that the published numbers did not
support: the per-hazard-type intervals that never inherited the RR-02
overdispersion widening (#201), the MAUP check whose coarse units were rated on
the all-records count while the published rate uses the primary count and whose
exposure floor was read as 0, the advocacy brief that reported a fallen hotspot
rank as a held one, and the reporting-bias audit that chose its top three before
the k-anonymity filter (#200).

Landed with the parity gate itself: `tests/test_statistic_parity.py` rebuilds the
MAUP coarse ranking out of the published GeoJSON's own rates, rebuilds the bias
block from the analysis and compares it to the committed sidecar, and checks the
two METHODOLOGY claim blocks name the code they describe.
`stats/maup.py::stability_outcome` gives the brief and the ranked table one shared
definition of which outcome happened.

**Why this was first.** Every later phase adds a number, and a repository that
cannot keep its existing numbers aligned with its existing prose should not be
adding more. Phase 1 also builds the gate the later phases are checked by.

## Phase 2: Gi\* inference robustness, a conditional-permutation reference

**Status: built, 2026-08-27.** Planned window 2026 Q4.

RR-09. METHODOLOGY §8.2 named the conditional-permutation reference distribution
as future work and was explicit that it "is **not** what is computed today", so
this phase is the honest kind of gap: a stated absence, not a false claim.

Significance today comes from the analytic normal-approximation Gi\* z-score,
which assumes an asymptotic normal reference that sparse, skewed,
exposure-normalized rates over small neighbourhoods do not reliably satisfy. The
permutation reference asks the same question empirically: hold the unit's own
value fixed, permute the remaining values across the other units, recompute Gi\*,
and read the observed statistic against that distribution.

The published significance decision **does not change**. The permutation result is
published beside it as a robustness artifact that can disagree, in the same shape
as the MAUP and exposure-sensitivity passes, because changing what "significant"
means in a published dataset is a methodology change and not a bug fix.

It does disagree. On the committed `davis` demo, three of the five
FDR-significant clusters do not clear `fdr_alpha` against their own permutation
reference; on `riverside` every segment is a Gi\* singleton, so the pass
publishes `not_evaluated` rather than a verdict it did not earn. Multiplicity is
deliberately not re-run under permutation, because a pseudo p-value cannot fall
below `1 / (m + 1)` while the Benjamini-Hochberg critical values at hundreds of
tests lie below that floor; the artifact states that limit in its own
`multiplicity` field, and the pass refuses to run when the permutation count
cannot resolve `alpha` at all.

## Phase 3: multiplicity control that survives spatial dependence

**Status: built, 2026-08-27.** Planned window 2027 Q1.

RR-08. Benjamini-Hochberg controls the false discovery rate under independence or
positive regression dependence; the local Gi\* tests are neither independent nor
guaranteed to satisfy PRDS, because neighbouring units share the values in their
overlapping neighbourhoods.

The research roadmap cites Caldas de Castro & Singer (2006) for a spatially-aware
FDR. **That method is not implemented here, and this phase will not claim it is.**
What is planned is Benjamini-Yekutieli (2001), whose control of the FDR under
*arbitrary* dependence is exactly the property the concern is about and whose
definition is fully specified: reject at the BH threshold scaled by
`1 / sum(1/i for i in 1..m)`. It is published as a second, strictly more
conservative decision beside the BH one, with the difference between them
reported, so a reader can see how much of the significance rests on the
dependence assumption. BH remains the published decision, and the artifact says
so, including in a `not_implemented` field naming the method it is not.

The difference is large. On the committed `davis` demo **one of the five**
BH-significant clusters survives, at a level of 0.0161 instead of 0.05 across 12
simultaneous tests; on `riverside` there is no significant cluster at all, so the
comparison publishes `not_evaluated` rather than `robust`. The
Benjamini-Yekutieli rejection set is always a subset of the Benjamini-Hochberg
one, so this pass can only ever report that fewer claims survive, never more.

## Phase 4: small-area rate stability under shrinkage

**Status: planned, 2027 Q2.**

RE-02. Sparse segments produce unstable rates: one report moves a low-exposure
block a long way, which is the mechanism behind most spurious "worst street"
findings. Empirical-Bayes shrinkage (Marshall 1991; Clayton & Kaldor 1987) borrows
strength across units by pulling each rate toward the global rate in proportion to
how little information it carries.

To ship as a **robustness pass, not a published rate**, for the reason METHODOLOGY
§6.3 gives for not bias-correcting rates by default: a smoothed number that looks
authoritative can launder a modelling assumption into a fact. The pass re-runs the
ranking on shrunk rates and reports whether the top segment survives, alongside the
MAUP and exposure-sensitivity verdicts. The published rate stays the raw one.

---

## Blocked phases

These are real work with real value. None of them can be completed by an agent
working offline in this repository, and each is recorded here with what blocks it
and what would clear the block.

### RR-03's interval half: propagating exposure uncertainty into the CI

**Blocked on a decision that is the maintainer's, and on data that does not exist
yet.** The published interval is a Poisson interval on the count with exposure
treated as a known constant (METHODOLOGY §5.2), and
[`LIMITATIONS.md`](LIMITATIONS.md) §4 says so in the reader's own words.
Propagating the denominator's uncertainty requires a distribution for it. No
exposure source this project consumes publishes a standard error, and
[ADR 0016](adr/0016-exposure-sensitivity-uses-declared-denominators-and-may-refuse-to-run.md)
decided that this project does not invent one: no perturbation model, no
tier-derived multiplier, no assumed error bar. The sensitivity half of RR-03
shipped in #209 precisely because it needs no invented distribution.

**What would unblock it:** either an exposure source that publishes its own
uncertainty (a count programme reporting a standard error or a replicate design),
or an explicit, cited decision by the maintainer to adopt a named error model and
to publish intervals that depend on it. The second is a methodology change with a
statistician's sign-off attached, which `ROADMAP.md` already lists as a REVIEW
gate. An agent choosing that model would be doing the exact thing ADR 0016 forbids.

### RR-14: the real NVDA and VoiceOver pass

**Blocked on a person.** `ROADMAP.md` already states this: "an automated agent
cannot perform or sign a human assistive-technology walkthrough." The ACR's manual
rows stay **Not performed** until a human runs the screen readers and signs the
result. ADR 0012's provisional attestation records accepted residual risk for a
bounded preview; it does not close the work and no code change can.

**What would unblock it:** a sighted-or-not human tester running NVDA on Windows
and VoiceOver on macOS/iOS against the shipped pages, at 200% zoom, and committing
dated results.

### RR-11: a minted DOI

**Blocked on an external account and on a release action this agent must not
take.** `CITATION.cff`'s `doi:` field is empty and carries a linked marker. Minting
a DOI requires a Zenodo (or equivalent) account linked to the repository and a
tagged release for it to attach to. Tagging, releasing and changing repository
settings are explicitly out of scope for this work.

**What would unblock it:** the maintainer linking the archive account and cutting
a tag; the `CITATION.cff` edit is then a one-line follow-up.

### RE-01, RE-03, RE-07, RE-08: validation, tri-view, exposure depth, before/after

**Blocked on external datasets that cannot be obtained here.** Every one of these
needs data this repository does not and should not vendor: official collision
records (SWITRS/TIMS or equivalent) for the validation study and the Vision Zero
tri-view, a counts portal or Strava Metro agreement for real exposure depth, and
two comparable time periods around a real intervention for before/after. The
adapter framework's own open issue (#186) records the shape of the problem: the
sources with an open licence have no data here, and the source with data has a
NonCommercial clause.

**What would unblock them:** a data-sharing agreement or an open licensed extract,
plus the review the research roadmap already requires ("statistical items need a
statistician's sign-off, not a persona's"). RE-01 in particular is a study with
error bars, and its framing constraint is as binding as its data requirement.

### RE-04: the equity overlay

**Blocked on consent and co-design, by the research roadmap's own instruction.**
"An equity overlay done badly stigmatizes neighborhoods instead of surfacing
under-reporting; build it with the consent/co-design posture the data-feminism
literature requires, or not at all." That posture is a relationship with affected
communities, not a code change, and an agent cannot enter into it.

**What would unblock it:** community partners who want it, a consent model, and a
DPIA review of the new attribute surface.

### RE-10: the anti-astroturf toolkit

**Not a phase; a gate.** The research roadmap marks it `P0-for-launch` and the
threat model is explicit that public intake triples the attack surface. Nothing in
this program opens intake, so the gate is not being approached. It is listed here
so that a future reader does not mistake its absence for an oversight: it becomes
work when, and only when, someone decides to open a public form, and it must land
before that form does.

### The Product Expansion Plan's own phases

**Blocked on real people, and deliberately so.** The plan's "Now" phase is eight
to twelve interviews with real organisations and three concierge dossiers with
real partners, and its exit gates are stated in terms of what those people say and
do. Its first action is a four-week freeze on broad expansion. An agent cannot
recruit an interviewee, and synthesising one would be the precise failure the plan
warns about when it says "do not count existing synthetic personas."

**What would unblock it:** the maintainer running the interviews. Until then the
honest status of every phase after "Now" is *not started, and correctly so*.

---

## Deliberately not built

From the product plan's "Do not build" list, restated here because a program
document that lists only additions reads as if everything is eventually coming:

- another general-purpose incident reporting network;
- turn-by-turn safe routing or a personal risk score;
- a real-time raw-report feed, public point map, or reporter profile;
- automated engineering prescriptions or causal claims;
- cross-city safety leaderboards pooling incompatible exposure units;
- gamification, bounties, or streaks;
- a national standard or federation before two independent adopters exist;
- more national FARS visualisations without a validated user task.

Two additions specific to this program:

- **No robustness check whose result is only published when it passes.** Every
  pass added here publishes its verdict either way, and publishes a distinct
  "did not run" outcome when it had nothing to test.
- **No change to what "significant" means in a published dataset without an ADR.**
  Phases 2 and 3 both compute alternative inference and both leave the published
  decision alone, on purpose.

## Review

Re-read this document whenever a phase lands or a block clears, and correct the
status in the same change. A plan that says "buildable" about something that has
been blocked for a year is the same category of defect as a methodology paragraph
describing code that was never written.
