# 19. The dependence-robust FDR is Benjamini-Yekutieli, and the artifact says what it is not

Date: 2026-08-27

## Status

Accepted

## Context

Published Getis-Ord Gi\* significance is decided with a Benjamini-Hochberg
false-discovery-rate correction across the per-segment tests (`METHODOLOGY.md`
§5.5). BH controls the FDR when the tests are independent or **positively
regression dependent** (PRDS).

The local Gi\* tests in this project are neither, by construction. Two
neighbouring segments' Gi\* statistics are computed over overlapping
neighbourhoods and therefore share input values. The dependence is real, and its
sign is not guaranteed: exposure-normalized rates on a street network can be
positively autocorrelated in one corridor and negatively so across a boundary. So
BH is being applied outside the conditions under which it is proved, which is the
concern `RESEARCH-ROADMAP.md` records as **RR-08**.

RR-08 names a specific remedy: "Justify (or move to) a spatial-dependence-aware
FDR for the many local Gi\* tests, per Caldas de Castro & Singer, rather than
vanilla Benjamini-Hochberg."

This raises a problem that is not statistical. **This project does not hold the
text of Caldas de Castro & Singer (2006).** Implementing a method from a
half-remembered description of it would produce a published number derived from
a specification nobody here can check, which is the failure mode every other rule
in this repository exists to prevent. Implementing nothing leaves BH applied
outside its proved conditions with only a footnote.

## Decision

**Ship Benjamini-Yekutieli (2001) as a published comparison beside the
Benjamini-Hochberg decision, and state in the artifact itself that it is not
Caldas de Castro & Singer.**

1. `honest_rates.hotspot.benjamini_yekutieli` is the BH step-up procedure at
   `alpha / c(m)`, with `c(m) = sum(1/i for i in 1..m)` the m-th harmonic number.
   Benjamini & Yekutieli prove this controls the FDR under **arbitrary**
   dependence, which is exactly the property the concern is about, and the
   definition is reproducible from its own citation in two lines.
2. `stats/multiplicity.py` applies it to the same p-value map the published BH
   decision was made from, so the two answers differ only in the correction, and
   publishes the result in every metadata sidecar under `dependence_robustness`,
   plus the brief and the standalone ranked table.
3. **The published decision does not change.** `getis_ord_significant` is still
   the BH decision. The BY rejection set is a subset of the BH one, so this pass
   can only ever report that fewer claims survive, never more.
4. **The artifact carries a `not_implemented` field** stating in the published
   file that this is not the Caldas de Castro & Singer spatially-aware FDR and
   which method it is. A consumer reading the sidecar without reading this ADR
   must not be able to conclude that RR-08's cited method shipped.
5. **The refusal is first class**, per
   [ADR 0016](0016-exposure-sensitivity-uses-declared-denominators-and-may-refuse-to-run.md):
   a dataset that publishes no significant cluster has nothing whose assumption
   could be dropped, and reports `verdict: "not_evaluated"` with a stated reason
   rather than `robust`.

## Consequences

**The Davis demo loses four of its five stars under this correction.** One of the
five BH-significant clusters survives, at a level of 0.0161 instead of 0.05
across 12 simultaneous tests. That is a large, uncomfortable number, and
publishing it is the point: a reader looking at five stars would otherwise read
them as five independent findings, and four of them rest on an assumption the
spatial structure does not supply.

**It does not mean the published flags are wrong.** BH remains a defensible
default, is what the methodology has always documented, and PRDS may well hold in
practice for positively autocorrelated rates. What the artifact reports is how
much of the conclusion depends on that holding. Both numbers are published so a
reader can weigh the question rather than have it decided for them.

**Conservatism is the cost.** BY is strictly more conservative and is known to be
substantially so at large `m`, because `c(m)` grows like `ln(m)`. A city with
5,000 rated segments carries a penalty near 9.1, which will leave few or no
survivors. That is a property of the correction, not a defect in the artifact,
and it is why BY is published as a comparison rather than adopted as the
decision: adopting it would trade one un-checked assumption for a near-guarantee
of publishing nothing.

**RR-08 is not closed by this.** The roadmap item asked for justification *or* a
move, and this is the justification plus a bound: BH is retained, and the reader
is shown what a dependence-agnostic correction would leave. If someone obtains
the Caldas de Castro & Singer text, implementing their spatially-aware procedure
remains open work, and the `not_implemented` field is what will have to change
when it lands.

## Alternatives considered

**Implement Caldas de Castro & Singer from memory or from secondary
descriptions.** Rejected outright. A published statistic derived from a
specification this project cannot check is worse than no statistic, and the
number would carry a citation that could not be verified against the
implementation.

**Adopt Benjamini-Yekutieli as the published decision.** Rejected for the same
reason ADR 0018 declines to promote the permutation reference: changing what
`getis_ord_significant` means is a methodology change requiring the statistician
sign-off `ROADMAP.md` lists as a REVIEW gate, and it would additionally amount to
choosing near-universal non-detection at city scale.

**Say nothing and keep the footnote.** This was the status quo, and it left an
assumption doing load-bearing work with no measurement of how much work.

**Estimate the effective number of independent tests from the neighbourhood
structure and correct against that.** Attractive, and it is roughly the shape of
what a spatially-aware FDR does. Rejected here because the estimator is exactly
the part that needs a source: any particular choice would be a specification this
project invented.

## References

- Benjamini & Yekutieli, *The control of the false discovery rate in multiple
  testing under dependency*, Annals of Statistics 29(4), 2001.
- Benjamini & Hochberg, *Controlling the false discovery rate*, JRSS-B 57(1),
  1995: the published decision.
- Caldas de Castro & Singer, *Controlling the False Discovery Rate: A New
  Application to Account for Multiple and Dependent Tests in Local Statistics of
  Spatial Association*, Geographical Analysis 38(2), 2006: cited by RR-08 as the
  concern, **not** implemented here.
- [ADR 0018](0018-the-permutation-reference-is-published-beside-the-analytic-decision.md),
  the same beside-not-instead decision for the reference distribution.
- [ADR 0017](0017-a-published-statistic-is-checked-against-its-published-description.md),
  the parity standard this phase is held to.
