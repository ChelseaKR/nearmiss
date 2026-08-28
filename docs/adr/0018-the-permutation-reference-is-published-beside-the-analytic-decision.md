# 18. The permutation reference is published beside the analytic decision, never instead of it

Date: 2026-08-27

## Status

Accepted

## Context

Published Getis-Ord Gi\* significance in this project is the **analytic** result:
the closed-form Gi\* statistic read against its asymptotic normal reference, with
a Benjamini-Hochberg correction across the many per-segment tests
(`METHODOLOGY.md` §5.5, §8.2). METHODOLOGY §8.2 has always named the alternative,
and named it honestly: a conditional-permutation reference distribution "is
possible future work; it is **not** what is computed today."

The normal approximation is least comfortable exactly where this project
operates. Rates are exposure-normalized, sparse, and strongly right-skewed;
neighbourhoods on a street network are small; and a published significance flag
is a claim a city planner may act on. RR-09 exists because a reader is entitled
to ask whether the flag survives dropping the distributional assumption.

Implementing it raises a question that is not about statistics: **once you have a
second answer, which one is published?**

Three facts make this decision, rather than leaving it to taste.

1. **A permutation p-value has a floor.** From `m` permutations the smallest
   reportable pseudo p-value is `1 / (m + 1)`, counting the observed arrangement
   as one of its own reference draws (North, Curtis & Sham 2002). Benjamini-Hochberg
   over `t` simultaneous tests compares the smallest p-value against `alpha / t`.
   For a city with a few hundred rated segments, `alpha / t` is well below
   `1 / (m + 1)` at any `m` this pure-Python implementation can afford. A
   permutation-based FDR would therefore reject nothing, and "no segment is
   significant under permutation" would be a statement about `m`.

2. **Monte Carlo output in a published decision breaks reproducibility guarantees
   in the wrong way.** The seed can be fixed and is, so `make reproduce` stays
   byte-for-byte. But a published `getis_ord_significant` that depends on a seed
   means a consumer's ability to reproduce the flag rests on an implementation
   detail rather than on the data, and any future change to the sampler silently
   moves published claims.

3. **Changing what "significant" means is a REVIEW gate, not a code change.**
   `ROADMAP.md` lists statistical validity as requiring known-answer evidence and
   specialist review. An agent or a maintainer swapping the published inference
   procedure in a robustness pull request would be routing a methodology change
   around the gate that exists for it.

## Decision

**The conditional-permutation reference is computed, published, and allowed to
disagree. It does not change any published number.**

1. `getis_ord_significant` remains the analytic normal-approximation z-score with
   Benjamini-Hochberg. No published rate, interval, rank, or flag depends on
   `gi_permutations` or `gi_permutation_seed`.
2. The permutation result is published in every metadata sidecar under
   `gi_permutation`, in the advocacy brief, and in the standalone ranked table,
   **whatever it says**. On the committed `davis` demo it says three of the five
   FDR-significant clusters do not clear `fdr_alpha` against their own reference.
   That is the whole value of the artifact.
3. **Multiplicity is not re-run under permutation**, for reason (1) above, and the
   artifact carries a `multiplicity` field saying so in the file rather than only
   in this ADR. Each tested segment is compared at the single-test level
   `fdr_alpha`. When `1 / (permutations + 1) > fdr_alpha`, the pass refuses to run
   and publishes `verdict: "not_evaluated"` with a reason, because a test that
   could not have detected significance has not failed to find any.
4. **Scope is stated in the artifact.** The tested set is the FDR-significant
   clusters plus the top-ranked segments by rate, which are the segments a reader
   acts on. This pass cannot promote a segment the analytic test did not flag, and
   the `scope` field says so, so an untested segment is never readable as a tested
   one that passed. Singleton Gi\* neighbourhoods are excluded (ADR-0015): a
   global z-score has no cluster to corroborate.
5. **The refusal is first class**, following
   [ADR 0016](0016-exposure-sensitivity-uses-declared-denominators-and-may-refuse-to-run.md):
   `not_evaluated` is a verdict, not an omission, and it never reads as
   `corroborated`. Every committed demo exercises one of the two paths, and
   `riverside` exercises the refusal.

## Consequences

**The published dataset now carries a number that argues with it.** Three of five
Davis clusters are flagged as resting on the normal approximation. That is
uncomfortable and correct: the fixture's planted hotspots sit on short
neighbourhoods with few rated peers, which is where the asymptotic reference is
weakest. A reader who trusted the ★ column alone now has a second column telling
them how much of that ★ is distributional assumption.

**The cost is bounded because the scope is.** Testing every rated segment at 999
permutations costs roughly two seconds on an 800-segment city, which would be a
visible regression against the `PERFORMANCE.md` statistics-stage baseline.
Testing the segments the dataset makes a claim about costs milliseconds. The
trade is stated rather than hidden: this pass answers "do the published claims
hold up", not "is there a claim we missed".

**A future maintainer may want the permutation result to *be* the decision.**
That is a legitimate position and this ADR does not foreclose it. It requires a
superseding ADR, a statistician's sign-off per the ROADMAP REVIEW gate, a schema
MAJOR bump (the meaning of `getis_ord_significant` would change), and an answer to
the multiplicity floor in (1). None of those is a robustness pass's business.

**Two new config keys exist and are live.** `gi_permutations` (default 999) and
`gi_permutation_seed` (default 1) both change the published artifact, and a test
asserts they do, so neither is decoration.

## Alternatives considered

**Run the permutation over every rated segment and apply BH to the pseudo
p-values.** Rejected on arithmetic: at hundreds of tests the BH critical values
sit below the pseudo p-value floor, so the procedure would reject nothing and
publish a fact about the permutation count as though it were a fact about the
city. This is exactly the "check that reports a result it did not earn" failure
ADR 0016 was written against, arriving from the other direction.

**Replace the analytic decision outright.** Rejected for reasons (2) and (3): it
routes a methodology change around the review gate that exists for methodology
changes, and it makes a published flag depend on a Monte Carlo seed.

**Publish nothing until the permutation result can be the decision.** Rejected
because the disagreement is itself the finding a reader needs, and withholding it
until it can be promoted is the pattern this repository already refuses for the
MAUP check: a robustness result published only when convenient is not a
robustness result.

**Approximate the reference distribution analytically (a saddlepoint or Edgeworth
correction).** Better asymptotics, no Monte Carlo, no seed. Rejected as
out of scope here rather than as wrong: it needs a derivation and a source this
repository can cite exactly, and the conditional-permutation scheme is the one
METHODOLOGY §8.2 has named as the intended future work since it was written.

## References

- Anselin, *Local Indicators of Spatial Association (LISA)*, Geographical Analysis
  27(2), 1995: the conditional-permutation scheme for local spatial statistics.
- Ord & Getis, *Local Spatial Autocorrelation Statistics*, Geographical Analysis
  27(4), 1995.
- North, Curtis & Sham, *A note on the calculation of empirical P values from
  Monte Carlo procedures*, American Journal of Human Genetics 71(2), 2002: the
  `(1 + r) / (m + 1)` correction.
- [ADR 0015](0015-a-singleton-gi-star-neighborhood-is-labeled-and-never-significant.md),
  for why singleton neighbourhoods are excluded here too.
- [ADR 0016](0016-exposure-sensitivity-uses-declared-denominators-and-may-refuse-to-run.md),
  for the first-class refusal.
- [ADR 0017](0017-a-published-statistic-is-checked-against-its-published-description.md),
  for the parity standard this phase is held to.
