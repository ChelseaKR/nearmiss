# 20. Empirical-Bayes shrinkage is a ranking check, not the published rate

Date: 2026-08-27

## Status

Accepted

## Context

The published ranking is by the point estimate of the rate, with each rate's
interval beside it and small-sample segments flagged uncertain (`METHODOLOGY.md`
§5.4). That is honest about the imprecision, but it is not robust to it: a
segment with two reports over a tiny denominator can carry the highest point
estimate in the city and sit at rank 1, with only a wide interval to warn the
reader. `LIMITATIONS.md` says so directly ("small numbers are loud").

§5.4 already names one alternative and declines it: ranking by the lower
confidence bound, "a candidate for future work, not the current behavior".
`RESEARCH-ROADMAP.md` records another as **RE-02**, empirical-Bayes smoothing for
small-area rate stability, citing the standard treatment (Marshall 1991; Clayton
& Kaldor 1987): pull each rate toward the overall rate in proportion to how
little information the unit carries, so a rate resting on two reports moves a
long way and one resting on two hundred barely moves.

Implementing the estimator is straightforward. The question this ADR answers is
what to do with the numbers it produces.

The tension is real in both directions.

- **For publishing the shrunk rate.** It is a better estimator of each segment's
  underlying rate under its own assumptions, it is standard practice in
  small-area disease mapping, and it would remove the single most common way this
  kind of ranking misleads.
- **Against.** Shrinkage assumes the units are exchangeable draws from one
  distribution. On a street network they are not: a corridor is not a random
  sample of the city, and the segments that are genuinely most dangerous are
  systematically the ones the estimator pulls hardest toward the middle. It is a
  model-based adjustment, and `METHODOLOGY.md` §6.3 already sets this
  repository's rule for those, in the context of bias reweighting: "A weighting
  model built on weak assumptions would *launder* bias into an
  authoritative-looking number ... Instead we keep the rates transparent and the
  bias *named beside them*, and offer any reweighting only as a clearly-labeled
  sensitivity analysis with its assumptions on the table."

Nothing about shrinkage makes it exempt from the rule §6.3 states.

## Decision

**Empirical-Bayes shrinkage runs on every published dataset and is published as a
re-ranking check. The published rate and the published ranking stay raw.**

1. `honest_rates.rates.empirical_bayes_rates` implements Marshall's global
   empirical-Bayes estimator with a method-of-moments between-unit variance. It
   works on the raw `count / exposure` scale, because the shrinkage weight is
   **not** invariant to rescaling and applying a per-1000 factor first would
   change every weight.
2. `stats/shrinkage.py` re-ranks the published segments on the shrunk rates,
   re-runs Gi\* with the same Benjamini-Hochberg level and the same
   singleton-neighbourhood suppression (ADR-0015), and publishes
   `shrinkage_stability` in every metadata sidecar, plus the brief and the
   standalone ranked table.
3. The artifact reports `top_segment_weight`: how much of its own rate the
   published rank-1 segment keeps. A low weight beside a `stable` verdict is the
   informative combination, and it is why the weight is published rather than
   only the verdict.
4. **The check uses the same numerator as the published rate** (the primary,
   low-confidence-excluded count), for the reason
   [ADR 0017](0017-a-published-statistic-is-checked-against-its-published-description.md)
   established for the MAUP check: a pass that changes the numerator as well as
   the estimator is not measuring the estimator.
5. **The refusal is first class**, per
   [ADR 0016](0016-exposure-sensitivity-uses-declared-denominators-and-may-refuse-to-run.md).
   The between-segment variance can come out at or below zero, meaning the spread
   across segments is no larger than Poisson noise alone would produce. Every
   rate then collapses onto the overall rate and there is no shrunk ranking at
   all; the pass publishes `verdict: "not_evaluated"` with that reason rather
   than a `stable` earned by every value being identical. Fewer than three rated,
   publishable segments refuses the same way.

## Consequences

**A reader gets the number that was missing.** Both committed demos publish
`stable`, and on `davis` the top segment keeps `0.6353` of its own rate at a mean
weight of `0.7891` across 9 rated segments. That is a real answer to "is rank 1
just the quietest block that caught a report?": under an estimator built to
punish exactly that, it stayed first.

**The published order can now be contradicted in public.** A future dataset whose
leader is a sparse segment will publish `fragile` beside its own ranking. That is
the intended behaviour and the same posture as the MAUP result that came back
negative on the one real city this project has run.

**A future maintainer may want to rank by the shrunk rate.** That is a
methodology change: it needs a superseding ADR, the statistician sign-off
`ROADMAP.md` lists as a REVIEW gate, and an argument for exchangeability on a
street network that this ADR does not have. The machinery is now in place either
way, which is deliberate: the argument should be made against a computed
alternative rather than in the abstract.

**No new configuration.** The estimator has no tuning knob to set wrong, which is
part of why it was chosen over alternatives that do.

## Alternatives considered

**Publish the shrunk rate as the rate.** Rejected under §6.3: it is a model-based
adjustment whose assumption (exchangeable segments) is weakest exactly where the
tool is used, and a shrunk rate looks like a measurement.

**Rank by the shrunk rate while publishing the raw one.** Rejected as the worst
of both: the table's order would depend on a model the numbers in it do not
reflect, and a reader could not reconcile the two columns.

**Rank by the lower confidence bound instead.** Still a live candidate and still
future work, as §5.4 says. It penalises sparsity too, without a between-segment
model, and it deserves its own decision rather than being settled as a side
effect of this one.

**A full hierarchical Bayesian model with spatial structure (BYM / CAR).** The
better estimator, and out of reach here: it needs MCMC or an integrated
approximation, which
[ADR 0003](0003-pure-python-statistics-and-planar-geometry.md) rules out for this
codebase, and its priors are exactly the kind of assumption a reader could not
check from the artifact.

## References

- Marshall, *Mapping disease and mortality rates using empirical Bayes
  estimators*, Applied Statistics 40(2), 1991.
- Clayton & Kaldor, *Empirical Bayes estimates of age-standardized relative
  risks*, Biometrics 43(3), 1987.
- `METHODOLOGY.md` §6.3, the existing rule for model-based adjustments.
- [ADR 0016](0016-exposure-sensitivity-uses-declared-denominators-and-may-refuse-to-run.md)
  (the first-class refusal),
  [ADR 0018](0018-the-permutation-reference-is-published-beside-the-analytic-decision.md)
  and
  [ADR 0019](0019-dependence-robust-fdr-is-benjamini-yekutieli-and-says-what-it-is-not.md)
  (the same beside-not-instead posture for inference).
