# 2. Exposure normalization and confidence intervals

- Status: Accepted
- Date: 2026-06-16
- Deciders: Chelsea Kelly-Reif (maintainer)
- Tags: statistics, methodology, exposure, uncertainty, hard-rule-1, hard-rule-2

## Context

The single most natural thing to do with a pile of near-miss reports is to plot them and smooth
them. Drop every report on a basemap, run a kernel density estimate, and you get a warm, persuasive
heat map. It looks authoritative, it is trivial to produce, and it is the headline image most
"hazard mapping" projects ship. It is also, as a danger map, a lie — and it is the specific lie
`nearmiss` exists to refuse.

A raw heat map of report locations is a map of **report volume**, and report volume is driven by
three things at once:

1. how **dangerous** a place is — the only thing we actually want to measure;
2. how **busy** it is — its exposure: more travelers produce more reports even at identical danger;
3. how **surveilled** it is by this dataset — reporting propensity: who has the app, who speaks the
   form's language, which routes engaged contributors ride (the reporting bias of Hard Rule 3).

Because exposure and reporting propensity both peak on the same popular corridors, a raw
count map — or its smoothed KDE cousin — will reliably light up the **busiest bike route** and
invite the reader to call it the most dangerous. The flagship corridor that carries fifty times the
riders gets ten times the reports and is announced as a death trap; the quiet connector where a
rider gets buzzed at speed every other day, but where almost no one rides and no one reports, stays
cold. The map points at where people *are*, not at where they are *at risk*, and dresses the
confusion in a color ramp that reads as certainty.

There is a second, compounding failure. Most street segments are **sparse**: they carry a handful
of reports or none. A point estimate on a 2-report segment, or a difference between a 2-report and a
4-report segment, carries enormous sampling uncertainty, but a colored pixel or a ranked table row
shows none of it. Ranking segments by point estimate lets a single lucky report rocket a quiet
segment to the top of a "most dangerous streets" list, and lets two statistically indistinguishable
segments be drawn as if one is clearly worse than the other. The naive presentation manufactures
confidence it has not earned.

`nearmiss` is built to the standard that its claims "hold up when a skeptical traffic engineer
pushes back." A traffic engineer will, correctly, ask two questions of any hazard ranking: *per
what?* (what is the denominator — you are showing me counts, not rates) and *how sure are you?*
(what is the interval and the sample size on that segment). A project that cannot answer both has
nothing an engineer should act on. These two questions are exactly Hard Rule 1 (*no rate without a
denominator*) and Hard Rule 2 (*no estimate without an interval*) from the README. This ADR records
the decision that those two rules are not editorial guidelines but enforced invariants of the
pipeline and the published product, and it documents *why* — so the decision can be defended,
audited, and, if ever revisited, superseded honestly rather than eroded by a convenient shortcut.

## Decision

**No risk rate is published without an exposure denominator, and no published estimate, ranking, or
comparison is shown without a confidence interval and a sample size `n`.** Concretely:

### Hard Rule 1 — exposure-normalized rates, denominator stated with its date

- **Counts are never published as risk.** A map or table of per-segment report counts `y_s` is
  labeled **"report volume"** (and a smoothed point-density surface, **"report intensity"**) in
  every artifact: map legend, table column header, brief prose, and data card. The words "danger,"
  "risk," "most dangerous," and "hotspot" are reserved for exposure-normalized, interval-bearing
  quantities. This labeling discipline is the rule at the level of a single number.
- **The published risk quantity is a rate** `theta_s = y_s / E_s` — reports per unit exposure —
  computed by `stats/rates.py` after `exposure.py` attaches an exposure estimate `E_s` to each
  street segment (the unit of analysis). Dividing by `E_s` removes the "busy" component and lets a
  quiet connector with few reports and tiny exposure correctly outrank a flagship route with many
  reports and huge exposure.
- **Exposure has a trust tier and a date, recorded per segment.** `E_s` is drawn from, in
  descending order of trust: observed bike/ped counts (measured), a calibrated demand model
  (modeled), or a third-party exposure layer such as a fitness-app surface (proxy). The **source
  identifier, the source date/coverage window, the unit, and the trust tier** travel with every
  published rate, in the record and the data card. The date is non-negotiable because exposure
  drifts (a new protected lane, a school reopening, a seasonal swing); a rate whose denominator was
  measured in a different period than its reports carries a temporal-alignment caveat. Rates are
  compared only on the same exposure unit, window, and tier — or not compared at all.
- **Degraded exposure does not produce a fabricated rate.** Segments below a configured exposure
  floor are published as **"exposure unknown"** with their raw report volume and an explicit no-rate
  flag — neither silently dropped (which would hide a real hazard) nor force-rated (which would
  invent an enormous, meaningless rate as `E_s -> 0`). An exposure-sensitivity pass re-runs the
  ranking under plausible alternative denominators; a ranking that survives only one choice of
  exposure source is reported as fragile, not as settled.

### Hard Rule 2 — every estimate carries an interval and an `n`

- **Every published rate, ranking, and comparison carries a confidence interval and the count `n`
  it rests on** (`n_s = y_s`). The interval is computed with **small-count methods**, because most
  segments are sparse and the sparse case is where an honest-looking analysis most easily lies.
- **The Wald / normal-approximation interval is prohibited** for published rates and proportions. It
  produces negative lower bounds for small Poisson counts and badly under-covers near 0 and 1 — it
  claims more certainty than it has, which is the exact failure mode this project is built to avoid.
  It is permitted only as a clearly labeled teaching contrast in a notebook.
- **Default interval methods.** For a rate (Poisson count over a known exposure offset), the
  **exact Garwood Poisson** interval is the default — it never returns a negative lower bound,
  handles `y_s = 0` with a finite upper bound, and guarantees at-least-nominal coverage; a
  **score-based** Poisson interval is the alternative when a less conservative, well-calibrated
  interval is wanted and counts are not tiny. For a proportion (a share, e.g. "what fraction of
  reports here are dooring"), **Wilson score** is the default and **Clopper-Pearson exact** the
  guaranteed-coverage option. The chosen method and `alpha` are recorded with every interval, and
  methods are not mixed within a single comparison.
- **Overdispersion is checked, not assumed away.** Reporting clusters (one viral post, one active
  local group, one bad week) make real counts more variable than Poisson. When a dispersion check
  shows overdispersion, intervals are widened via a quasi-Poisson / negative-binomial treatment.
  Reporting a too-narrow interval by assuming clean Poisson on overdispersed data would obey Hard
  Rule 2 in letter while violating it in spirit.
- **Uncertainty governs ranking, not just decoration.** Segments are not ranked by point estimate.
  Segments whose intervals overlap substantially are reported as **not distinguishable** at the
  stated confidence; a segment with too few reports to yield a usefully narrow interval is shown as
  **uncertain** and labeled "insufficient data to rank" rather than given a confident rank
  (Hard Rule 2's "shown as uncertain, not ranked as certain"). The default published ranking is by
  the **lower confidence bound** of the rate, which automatically penalizes sparse, uncertain
  segments instead of rewarding a lucky report. The ranking statistic is stated in the brief.
- **Multiplicity is controlled.** Where many segments are scanned for significance — the Getis-Ord
  Gi\* hotspot step and any per-segment flagging — a false-discovery-rate (Benjamini-Hochberg)
  adjustment is applied by default, and both raw and adjusted results are reported. An unadjusted
  "significant at p < 0.05" out of a thousand tested segments is not a finding.

### Spatial statistics inherit both rules

- **KDE is exploratory, never a published danger surface.** A raw point-density KDE is a smoothed
  volume map carrying every bias above; it is published only as labeled **"report intensity"**
  context, with its bandwidth recorded and varied in a sensitivity check. A risk surface, if
  produced, is exposure-aware (smoothed rate, or density explicitly contextualized by an exposure
  density), not a bare numerator surface.
- **Getis-Ord Gi\* runs on the rate, not the raw count.** Gi\* on raw counts finds clusters of
  *volume* and re-tells the heat-map lie with a p-value attached; Gi\* on the exposure-normalized
  rate finds clusters of elevated *risk*. The published hotspot product is the set of segments that
  are significant hot clusters of the rate under Gi\* (FDR-adjusted), each carrying its rate,
  interval, `n`, exposure source and date, and significance.

### Enforcement

This is enforced, not aspirational. `publish.py` refuses to emit any feature carrying a risk-typed
field (rate, rank, significance) unless it also carries an interval, an `n`, and a complete exposure
provenance bundle; a count-only feature must be typed and labeled as report volume. The
provenance/interval invariant and the Wald prohibition are checked in the test suite against
synthetic fixtures with planted answers — including **busy-but-safe decoy** segments (high exposure,
baseline rate) that must *not* be flagged and **quiet-but-dangerous** segments that must be
recovered — and interval-coverage simulations confirm the methods cover at or above nominal. These
tests run in CI and under `make reproduce`; a regression that publishes a rate without a denominator,
an estimate without an interval, or a Wald interval breaks the build. The full derivation lives in
[`docs/METHODOLOGY.md`](../METHODOLOGY.md); this ADR records the decision and its rationale.

## Consequences

**Positive**

- The published product answers the skeptical engineer's two questions by construction: every risk
  number is *per* a stated, dated exposure denominator and *bounded* by an interval with an `n`.
  This is the project's core credibility claim, made structural rather than promised.
- The heat-map lie is designed out, not merely discouraged. "Hot" can only mean "hot beyond what
  exposure and chance explain," because the rate, the interval, and the exposure-aware Gi\* step
  each strip out one of the volume / luck / busyness confounds before anything is called a hotspot.
- Lower-confidence cells are visibly uncertain. Sparse segments are surfaced as "uncertain" or
  "insufficient data to rank" and 0-report segments get finite upper bounds, so a reader is never
  invited to over-read a 2-report segment as a precise risk.
- Failure is transparent. Where exposure is missing the segment is published as "exposure unknown"
  with its volume, rather than dropped or fabricated — the reader sees the gap instead of a
  confident wrong answer.
- The discipline is auditable and reproducible. Every published number traces back through its
  provenance bundle to a raw report, and the planted-fixture and coverage tests let an outside
  reviewer check that the rules actually hold, not take them on trust.

**Negative / costs**

- It is substantially more work. Attaching, sourcing, dating, and tiering an exposure estimate per
  segment — and finding a credible denominator at all on streets with no count station — is the
  hardest part of the pipeline and the main reason a finding is slow to publish. A raw heat map
  needs none of this.
- The headline is less punchy. "Here is a corridor where the close-pass rate, normalized by
  modeled exposure measured in spring 2026, is elevated with a 95% interval that excludes the city
  norm, n = 41" does not fit on a thumbnail the way a red blob does. We accept a quieter, defensible
  story over a louder, indefensible one.
- Coverage shrinks. Segments without a usable denominator cannot be rated and segments with too few
  reports cannot be confidently ranked, so the map of *confident risk* is sparser than the map of
  *reports*. This is honest but can read as "less data" to someone expecting full coverage; the
  data card states why.
- The published rate inherits its exposure source's bias. A proxy denominator (e.g. a fitness-app
  layer over-weighting recreational riders) can distort a rate; we mitigate by recording the trust
  tier, running exposure-sensitivity, and naming the caveat (Hard Rule 3), but normalization does
  not make a weak denominator strong, and we do not pretend it does.
- There is a real risk of false precision *about the uncertainty itself* — e.g. assuming Poisson on
  overdispersed counts. The dispersion check and the coverage simulations exist specifically to
  catch this, and they add their own implementation and test burden.

**Neutral**

- The choices are deliberately conventional and citable (Garwood, Wilson, Clopper-Pearson,
  Getis-Ord Gi\*, Benjamini-Hochberg). Nothing here is novel; the contribution is enforcing the
  textbook-correct method instead of the convenient one, which keeps the methodology legible to any
  reviewer who wants to check it.
- This ADR governs *how* a rate and its interval are produced and presented. It does not by itself
  decide a city's specific exposure source, floor, bandwidth, or `alpha` — those are recorded
  per-run configuration, defaulted and documented in `docs/METHODOLOGY.md`, and revisited there
  rather than by superseding this decision.

## Alternatives considered

### Raw kernel density (KDE) heat map as the danger surface — rejected

The default of the field: smooth report points into a continuous density surface and present it as a
danger map. **Rejected** because a point-density KDE is a *smoothed volume* map. Smoothing makes it
look more authoritative while hiding the point density that would warn a reader the surface rests on
three reports, so it is a prettier version of the same bias — it inherits exposure and reporting-bias
confounds wholesale and, because both peak on popular routes, reliably mislabels the busiest corridor
as the most dangerous. It violates Hard Rule 1 (no denominator) and offers no interval (Hard Rule 2).
KDE is retained, but only as an exploratory, explicitly labeled "report intensity" layer with a
recorded bandwidth — never as a published risk surface.

### Simple report counts / count rankings — rejected

Publish per-segment counts, or a "most-reported streets" ranking, and let the reader interpret.
**Rejected** for the same Hard Rule 1 failure (a count confounds danger with traffic and surveillance)
and an additional Hard Rule 2 failure: a count has no interval, so a 30-report and a 28-report segment
are presented as distinguishable when they are not, and a single report can move a ranking. Counts are
not discarded — they are published, but strictly as **"report volume,"** never as risk, and the brief
explicitly contrasts the volume ranking against the rate ranking so a reader sees the two disagree.

### Counts normalized by a single citywide rate or area, not segment exposure — rejected

Normalize every segment by one global figure (total ridership, or reports per square kilometer)
instead of a per-segment exposure estimate. **Rejected** because a single global denominator does not
remove the *spatial* concentration of traffic that is the actual confound; the busy corridor still
dominates because it is busy relative to the city, and area-based normalization measures report density
per land area, not per traveler. Exposure must be attached *per segment* to separate danger from
busyness where the busyness actually varies.

### Point estimates with no interval, or with Wald intervals — rejected

Rank by `theta_s` alone, or attach the easy textbook "estimate ± 1.96 · SE" interval. **Rejected**
under Hard Rule 2. Bare point estimates hide sampling uncertainty and let sparse segments be ranked as
certain. The Wald interval is actively wrong for the small counts that dominate this dataset: it
produces negative lower bounds and under-covers near the boundaries, manufacturing exactly the false
confidence this project refuses. We require exact-Poisson / score (rate) and Wilson / Clopper-Pearson
(proportion) intervals, verified by coverage simulation, and rank by the lower confidence bound.

### Statistically reweighting reports to "bias-correct" the rates by default — rejected

Post-stratify or reweight reports so the contributor pool looks representative, and publish the
corrected rates. **Rejected** as a default because credible reweighting needs a defensible model of
the reporting probability for every group on every segment, which we do not have. A weighting model
built on weak assumptions would *launder* bias into an authoritative-looking number and quietly
undercut Hard Rule 3. The rates are kept transparent with the bias **named beside them**; any
reweighting is offered only as a clearly labeled sensitivity analysis with its assumptions on the
table. (Recorded here because it is the tempting "fix" a reviewer will propose; naming a bias we
cannot defensibly remove is more honest than removing it with a model we cannot defend.)

## References

- Project README, "Five hard rules" — HR1 (no rate without a denominator) and HR2 (no estimate
  without an interval) — and the architecture stages `exposure.py` → `stats/` → `publish.py`.
- [`docs/METHODOLOGY.md`](../METHODOLOGY.md) — the full statistical derivation: exposure denominators
  and their dates (§3), rates (§4), small-count intervals and the Wald prohibition (§5),
  "hot because dangerous vs. hot because busy" (§7), KDE vs. Getis-Ord Gi\* (§8), and the
  synthetic-fixture validation including the busy-but-safe decoys (§9).
- [`docs/adr/0001-record-architecture-decisions.md`](./0001-record-architecture-decisions.md) — the
  ADR practice this record follows.
- Garwood, F. (1936). Fiducial limits for the Poisson distribution. *Biometrika* — exact Poisson
  rate interval.
- Wilson, E. B. (1927). Probable inference, the law of succession, and statistical inference. *JASA*
  — score interval for proportions.
- Clopper, C. J., & Pearson, E. S. (1934). The use of confidence or fiducial limits illustrated in
  the case of the binomial. *Biometrika* — exact binomial interval.
- Brown, L. D., Cai, T. T., & DasGupta, A. (2001). Interval estimation for a binomial proportion.
  *Statistical Science* — why the Wald interval is rejected.
- Getis, A., & Ord, J. K. (1992); Ord, J. K., & Getis, A. (1995). *Geographical Analysis* — the
  Gi\* local cluster statistic, run on the rate.
- Benjamini, Y., & Hochberg, Y. (1995). Controlling the false discovery rate. *JRSS B* —
  multiplicity control.
