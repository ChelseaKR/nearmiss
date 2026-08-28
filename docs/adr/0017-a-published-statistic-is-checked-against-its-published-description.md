# 17. A published statistic is checked against its published description

Date: 2026-08-27

## Status

Accepted

## Context

The repository's whole claim on a reader's trust is that its numbers are
described accurately. `METHODOLOGY.md` and `schema/dataset.schema.md` are written
in the present tense: they say what the code computes, not what it is meant to
compute one day. A sentence that stops being true is therefore not a stale
comment; it is a false statement about a published number, and the reader has no
way to detect it.

[ADR 0016](0016-exposure-sensitivity-uses-declared-denominators-and-may-refuse-to-run.md)
was accepted after exactly that failure: METHODOLOGY §3.3 and ADR 0002 had both
described an exposure-sensitivity pass in the present tense since 2026-06-16, and
no such code existed. The fix landed the pass, and it landed a test that reads the
paragraph and the committed artifacts and checks them against each other
(`test_methodology_describes_what_the_code_actually_computes`). That test caught
one paragraph. Nothing generalised it.

Auditing the rest of the published statistics against their own descriptions found
four more of the same class in the 0.4.0 tree. None of them is a crash, a lint
error, or a type error; every one of them is a number or a sentence that says
something the code does not do.

1. **The per-hazard-type intervals never inherited the overdispersion widening**
   (issue #201). METHODOLOGY §4 says enabling `overdispersion_adjust` "widens every
   published interval by `sqrt(phi)`", and the schema says each `rates_by_type`
   entry is computed "by the same method as the top-level `rate`". `_rates_by_type`
   called `rate_with_ci` without the dispersion argument, so with the adjustment on
   the type layers stayed pure Poisson while the pooled interval on the same
   feature was widened. On the Davis fixture the correct type interval is about
   3.3 times wider than the one that was published. The one real-city run this
   project has published, Potsdam, was made with `overdispersion_adjust = true`.

2. **The MAUP check rated its coarse units on a different numerator than the
   published rate.** The published rate is the primary, low-confidence-excluded
   count; `rank_stability` summed `report_count`, the all-records total. A check
   whose fine ranking uses one numerator and whose coarse ranking uses another can
   report "the hotspot did not survive re-segmentation" when what actually moved
   was the definition of the count. It also read the exposure floor as 0 rather
   than the configured `exposure_floor`, so a segment published as "exposure
   unknown" could still push a coarse unit up the coarse ranking.

3. **The brief reported a fallen rank as a held one.** `top_hotspot_survives` is
   false for two different reasons: the top unit held rank 1 and lost Gi\*
   significance, or its rank fell. `figures._stability_note` distinguished them.
   `brief._render_robustness` did not, and said the hotspot "stays the highest-rate
   unit but loses statistical significance" in both cases. Two renderings of one
   result described it differently, and the one a reader is most likely to see was
   the wrong one, in the direction that flatters the finding.

4. **The reporting-bias audit chose its top three before the k-anonymity filter**
   (issue #200). The schema calls the block "the reporting-bias audit over
   publishable segment ids"; the code took the top three findings and then dropped
   the withheld ones, with nothing backfilled. A segment with very few reports is
   both the kind that gets withheld and the kind that produces an extreme share
   ratio, so the two conditions coincide rather than being independent, and the
   published audit could name two segments while claiming to name three.

Two properties are common to all four. They are invisible to every gate the
repository runs, because lint, types, coverage, conformance and reproducibility
all check the code against itself. And each one is a statement in a document that
a reader would reasonably act on.

## Decision

**A published statistic is checked against its published description, by a test
that reads both at test time.**

Concretely:

1. Where a document makes an absolute claim about how a published number is
   computed, the claim is wrapped in a `<!-- claim:… -->` tag, listed in
   `docs/CLAIMS.md`, and its witness is the test that makes it true. `make claims`
   runs the witness, so a claim whose witness stops passing fails the build.
2. Where the claim is about a *value* rather than a method, the test reads the
   committed artifact and recomputes the property from it. Two such tests ship
   here: the MAUP coarse ranking is rebuilt out of the published GeoJSON's own
   rates and exposures, and the bias block is rebuilt from the analysis and
   compared to the committed sidecar.
3. Where two artifacts render the same result for different audiences, the
   decision of *which* result it is lives in one function that both call.
   `stats/maup.py::stability_outcome` is that function for the re-segmentation
   check. The wording may differ, and in a translated brief it must; the case
   cannot.
4. Documentation of a corrected computation states the versions it was wrong in.
   A consumer holding a `1.2.0`-or-earlier artifact needs to know that its
   `maup_rank_stability` block is not comparable to a `1.3.0` one.

This ADR does not make a claim tag mandatory for every sentence in the
methodology. It makes one mandatory for a sentence that asserts a property of a
published number in the present tense, which is the sentence a reader checks.

## Consequences

**What this buys.** The four defects above cannot silently return. Each is now
either a claim with a running witness or an invariant recomputed from the
committed artifact. The pattern is cheap to extend: a new published statistic
costs one claim tag and one witness test.

**What it costs.** Adding a published statistic is now more work, deliberately.
Writing the paragraph and writing the test are the same task, and neither ships
without the other. `make claims` gets slower with every witness, because a witness
that names a test is run rather than merely found.

**What it does not fix.** Two of the four defects did not move either committed
demo: `davis` and `riverside` publish with `overdispersion_adjust` off, an
exposure floor of 0, and no withheld segment in the bias top three, so
`make reproduce` stays byte-for-byte across this change. That is a fact about the
fixtures, not a mitigation. The defects were reachable in exactly the
configuration a real city uses, which is how the Potsdam run reached one of them.
Synthetic fixtures with convenient properties are the reason four defects of this
class survived every gate, and a future audit should assume there are more.

**What it says about the older artifacts.** `docs/findings/2026-08-15-potsdam-real-run.md`
is a dated record of a run made with the then-current code. Its MAUP result held
rank 1, so the brief-wording defect did not touch it, but its coarse rates were
built from the all-records numerator. It is left as written, because a finding is
a record of what was run, and re-running it would need the private input it was
made from. The correction history in `schema/dataset.schema.md` §10.1 is what a
reader of that finding should be pointed at.

## Alternatives considered

**Assert the docs in prose review only.** This is what was in place. It found
nothing in four defects across two months, because a reviewer reads a paragraph
for plausibility and the paragraph was plausible.

**Generate the documentation from the code.** A generated methodology cannot be
wrong, but it also cannot say *why* a method was chosen, which is most of what the
methodology is for. The repository already generates the parts that are pure
inventory (`make docs-audit`) and hand-writes the parts that are argument. The
split stands.

**Fail the build on any untagged present-tense claim.** Tempting and
unimplementable: distinguishing "the code does X" from "one could do X" is a
natural-language judgment, and a gate that guesses would be either trivially
evaded or constantly wrong. The tag is authored deliberately, and the reviewer
checklist in `CONTRIBUTING.md` is where the judgment lives.

## References

- Issue #200 (reporting-bias top-three selection), issue #201 (`rates_by_type`
  and the overdispersion widening).
- [ADR 0016](0016-exposure-sensitivity-uses-declared-denominators-and-may-refuse-to-run.md),
  the same failure one paragraph earlier.
- [ADR 0015](0015-a-singleton-gi-star-neighborhood-is-labeled-and-never-significant.md),
  which established that one definition of a published word lives in one place.
- `docs/STATISTICAL-INTEGRITY-PROGRAM.md`, the multiyear sequence this is phase 1 of.
