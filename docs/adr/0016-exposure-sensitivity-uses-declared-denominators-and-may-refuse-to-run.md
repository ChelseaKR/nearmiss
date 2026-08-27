# 16. Exposure sensitivity uses declared denominators, and is allowed to refuse to run

- Status: Accepted
- Date: 2026-08-27
- Deciders: Chelsea Kelly-Reif (maintainer)
- Tags: statistics, exposure, published-contract, honesty, hard-rule-1, hard-rule-2

## Context

[ADR 0002](0002-exposure-normalization-and-confidence-intervals.md) settled that the published
interval is a small-count Poisson interval on the **count**, with exposure treated as a known
constant. That leaves the shakiest input in the pipeline uncovered by the one number a reader uses to
judge certainty, and both ADR 0002 and [`METHODOLOGY.md`](../METHODOLOGY.md) §3.3 answered it with the
same sentence, in the present tense:

> An exposure-sensitivity pass re-runs the ranking under plausible alternative denominators; a
> ranking that survives only one choice of exposure source is reported as fragile, not as settled.

**No such pass existed.** From 2026-06-16 until this decision, that sentence described code nobody had
written, in the two documents a skeptical reader is most likely to check. It is the failure mode this
repository exists to refuse, arriving from the inside: a promise about a number, published as though
it were a property of the number.

Writing the pass forces a question the sentence hides. *Where do "plausible alternative denominators"
come from?* Three answers were available:

1. **Perturb the published estimate** — re-rank at, say, plus or minus 30%, or at a multiplier keyed
   to the exposure trust tier (observed / modeled / proxy).
2. **Model the denominator's error** and sample from it.
3. **Use the alternative denominators that already exist** — the corroborating readings a segment's
   own exposure record carries (`Exposure.sources`, METHODOLOGY §3.1), which the pipeline already
   loads, already compares (`exposure.corroboration`), and already publishes disagreement for.

The first two are more impressive and produce a result for every dataset. They also require this
project to invent a number about a quantity it did not measure, and then rank on it. A ±30% band is a
number someone made up; a tier multiplier is the same number with a justification attached. Both would
convert an unmeasured uncertainty into a published, authoritative-looking sensitivity result — the
exact laundering ADR 0002 already rejected for reporting bias ("a weighting model built on weak
assumptions would *launder* bias into an authoritative-looking number").

The third answer is honest and has a cost that has to be accepted openly: **it frequently produces no
result at all.** Most exposure records declare a single reading. Of the two committed demo cities,
`davis` declares no corroborating reading anywhere.

## Decision

**The exposure-sensitivity pass (`stats/exposure_sensitivity.py`) re-ranks only under denominators
the input data itself declares, and when there are none it reports that it did not run.**

- **Declared, never invented.** The scenarios are built from `Exposure.sources`: `declared_low` gives
  each segment the smallest usable reading its own record declares, `declared_high` the largest. The
  minimum and maximum are taken over the primary estimate together with its corroborating readings, so
  no scenario moves a segment outside the range its sources published. No perturbation, no
  tier-derived multiplier, no assumed error bar.
- **A reading the pipeline would refuse is not an alternative.** Readings at or below the configured
  exposure floor are excluded by the same rule `exposure.is_usable` applies to the primary estimate
  (METHODOLOGY §3.3). A zero-exposure alternative would divide by zero or manufacture an enormous
  rate from an estimate that is not a denominator.
- **The numerator is never touched.** Rates are re-derived as `rate * (E_base / E_alt)`, exact for a
  count over an offset, so a scenario is the published ranking with only the denominator swapped —
  not a second analysis with its own filters.
- **Significance means the same thing in a scenario as in the dataset.** Gi\* is re-run on the
  scenario rates over the same street-network neighborhoods, at the same Benjamini-Hochberg level,
  with the same singleton-neighborhood suppression ([ADR 0015](0015-a-singleton-gi-star-neighborhood-is-labeled-and-never-significant.md)).
- **Not evaluated is a first-class verdict, and it is not a pass.** With no declared alternative the
  artifact publishes `verdict: "not_evaluated"`, `top_segment_survives: null`, and a stated reason.
  Never `"stable"`, and never `false` either: neither "it held" nor "it broke" is true when nothing
  was tested. The brief and the standalone ranked table each say so in a sentence rather than
  omitting the line, because a reader who sees a re-segmentation result and no denominator result
  will reasonably assume the denominator check passed.
- **Coverage is published beside the verdict.** `alternative_coverage` — the share of rated segments
  that had an alternative at all — travels with every result, so `"stable"` is always readable
  against how much of the network was actually varied. `riverside` publishes `stable` at
  `0.1667`: a real answer, and a visibly thin one.
- **Survival is rank-first, and significance can only be lost.** The published top segment survives
  when it is still rank 1 in every scenario and, *if it was a significant cluster in the published
  dataset*, still is. A top segment that was never starred is not called fragile for failing to
  become one under a denominator it never had.
- **This is a sensitivity analysis, not an interval.** It does not widen the published confidence
  interval, which still covers the count only. The other half of RR-03 — propagating exposure
  uncertainty into the interval itself — stays open, and `LIMITATIONS.md` §4 still says so.

The result is published in the metadata sidecar's `exposure_sensitivity` block (published dataset
schema `1.2.0` -> `1.3.0`, additive; contract in `schema/dataset.schema.md` §10.2), in the standalone
ranked table, and in the brief's robustness section in both shipped languages.

## Consequences

**Positive**

- The sentence in ADR 0002 and METHODOLOGY §3.3 is now a description of running code, and
  `tests/test_exposure_sensitivity.py` checks the methodology paragraph's own figures against the
  committed artifacts and every published key against the schema table, so it cannot silently become
  a promise again.
- No number in the sensitivity result is invented. Every denominator it ranks on was published by
  someone for that segment.
- The failure mode this project keeps finding in other people's dashboards — a green check that
  cannot go red — is designed out here rather than merely avoided by luck: the most common outcome on
  today's data is an explicit refusal to answer.
- The cost of a thin exposure record becomes visible. "Only one of six rated segments had a second
  reading" is an argument for collecting a second denominator, printed in the artifact.

**Negative / costs**

- The pass is silent exactly where it would be most useful: a city with one exposure source per
  segment gets `not_evaluated` forever, no matter how uncertain that source is. The honest answer to
  "how much does the denominator matter here?" is, for such a dataset, "this project cannot tell you,"
  and that is what it now says.
- Two scenarios bracket the declared readings; they are not a distribution, and the result is not a
  probability of anything.
- The verdict inherits whatever the declaring sources happened to disagree about. A segment whose two
  readings agree closely contributes a scenario that barely moves, and `alternative_coverage` counts
  it the same as a segment whose readings differ by a factor of three.

**Neutral**

- Adding a corroborating reading to an exposure file now changes a published robustness verdict.
  That is intended: declaring a second denominator is how a dataset asks this question, and
  `exposure_disagreement` already made the disagreement itself visible per segment.

## Alternatives considered

### Perturb the denominator by a fixed band or a trust-tier multiplier — rejected

Re-rank at ±20/30%, or scale by a factor keyed to observed/modeled/proxy. **Rejected** because the
band is invented. It would produce a confident-looking sensitivity result for every dataset, including
those with no evidence at all about their denominator's error, and the result's shape would be
governed by the constant rather than by anything measured. "Never invent a denominator" is Hard Rule 1
read one level up: a fabricated *uncertainty* about a denominator is still a fabrication.

### Propagate exposure uncertainty into the published interval — deferred, not rejected

The stronger answer, and RR-03's actual ask. **Deferred** because it needs a defensible error model
for each exposure source, which is the same missing input as above; doing it badly would widen every
published interval by an invented amount and would be far harder to notice than a fabricated scenario.
It stays open in `LIMITATIONS.md` §4 and the research roadmap rather than being quietly closed by this
decision.

### Report "stable" when there is nothing to test — rejected

The tempting default, and the one that produces the prettiest artifacts: nothing moved, so nothing is
fragile. **Rejected** outright. It is the defect class this repository already documents in
`docs/findings/` — a check whose result is only ever published when it passes — and it would make the
most common outcome on real data a false reassurance about the input the project itself calls its
shakiest. `tests/test_exposure_sensitivity.py::test_no_declared_alternative_is_not_evaluated_never_stable`
exists to keep that from being reintroduced.

## References

- [`ADR 0002`](0002-exposure-normalization-and-confidence-intervals.md) — the decision this one
  implements the missing half of.
- [`ADR 0015`](0015-a-singleton-gi-star-neighborhood-is-labeled-and-never-significant.md) — the
  singleton-neighborhood rule the scenario Gi\* reuses.
- [`docs/METHODOLOGY.md`](../METHODOLOGY.md) §3.3 (the claim block) and §5.2 (what the interval
  covers); [`docs/LIMITATIONS.md`](../LIMITATIONS.md) §4.
- [`schema/dataset.schema.md`](../../schema/dataset.schema.md) §10 — the published contract for both
  robustness artifacts.
- `docs/RESEARCH-ROADMAP.md` — RR-03, and the R28 item it corroborates.
- FHWA, *Methods for estimating pedestrian and bicyclist exposure*; Elvik & Bjornskau (2019),
  *Safety-in-numbers: an updated meta-analysis* — why a safety conclusion can rest on the exposure
  choice alone.
