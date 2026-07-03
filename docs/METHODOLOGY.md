# nearmiss — Statistical Methodology

This is the statistical reference for nearmiss. It describes, step by step, how a pile of
biased, sparse, voluntary hazard reports becomes an exposure-normalized risk rate with a stated
uncertainty, and exactly where that chain stops being trustworthy. The standard it is written to
is the one in the README: it has to hold up when a skeptical traffic engineer pushes back.

Everything here is enforced by the [Five Hard Rules](../README.md#hard-rules-enforced-not-aspirational),
the architecture stages, and the test fixtures. Where this document and the code disagree, the
code and its tests are authoritative and this document is the bug. Every method named here lives
in a specific module (`stats/rates.py`, `stats/bias.py`, `stats/kde.py`, `stats/getis_ord.py`)
and is exercised against synthetic fixtures with known answers in `tests/`.

A reader in a hurry should read two sections: [Hot because dangerous vs. hot because
busy](#7-hot-because-dangerous-vs-hot-because-busy) and [Limitations: what these numbers do NOT
support](#10-limitations-what-these-numbers-do-not-support). They are the whole point.

---

## TL;DR (one screen)

For a council member, a journalist, or anyone who needs the method in ten lines:

1. **Count.** Snap each report to a street segment (a block between intersections); count reports per block.
2. **Normalize.** Divide by **exposure** — how much cycling that block carries — to get a *rate per rider*, not a raw count. This is the whole game: a busy street collects many reports because many people use it, not because it is dangerous.
3. **No denominator, no rate.** A block with no trustworthy exposure is published as **"exposure unknown,"** never ranked as if we were sure (HR1).
4. **Put error bars on it.** Every rate carries a 95% confidence interval and its sample size `n`; small samples are marked uncertain, not ranked as certain (HR2). The interval covers the count, not yet the exposure (see [LIMITATIONS](LIMITATIONS.md)).
5. **Find real hotspots.** A block is flagged **★ Significant** only when Getis-Ord Gi\* (with a Benjamini-Hochberg false-discovery-rate correction) says it is hotter than exposure and chance alone explain — not merely "loud."
6. **Name the bias.** Who reports is self-selected; the bias is described, not hidden (HR3).
7. **Reproduce it.** `make reproduce` regenerates every published number from raw inputs (HR5).

The honest one-liner: nearmiss tells you **where the near-miss rate per rider is statistically higher than exposure and chance explain** — a narrower, more defensible claim than "the most dangerous street." Everything below is the detail behind these seven steps.

---

## Table of contents

1. [Notation and the unit of analysis](#1-notation-and-the-unit-of-analysis)
2. [From raw reports to counts](#2-from-raw-reports-to-counts)
3. [Exposure: choosing and recording a denominator](#3-exposure-choosing-and-recording-a-denominator)
4. [Rates: turning counts and exposure into risk](#4-rates-turning-counts-and-exposure-into-risk)
5. [Confidence intervals for sparse counts](#5-confidence-intervals-for-sparse-counts)
6. [Reporting bias: characterizing who and where is missing](#6-reporting-bias-characterizing-who-and-where-is-missing)
7. [Hot because dangerous vs. hot because busy](#7-hot-because-dangerous-vs-hot-because-busy)
8. [Spatial hotspots: KDE intensity vs. Getis-Ord Gi\*](#8-spatial-hotspots-kde-intensity-vs-getis-ord-gi)
9. [Validation against synthetic fixtures](#9-validation-against-synthetic-fixtures)
10. [Limitations: what these numbers do NOT support](#10-limitations-what-these-numbers-do-not-support)
11. [Reproducibility and provenance](#11-reproducibility-and-provenance)
12. [References](#12-references)

---

## 1. Notation and the unit of analysis

The unit of analysis is a **street segment** `s` — the smallest stretch of street between two
nodes in the reference network, after the pipeline has snapped each report to a segment
(`pipeline/snap.py`). Segments, not raw coordinates, are the thing we rate, rank, and publish,
because a rate needs a denominator and exposure is only defined on the network. Where the text
says "location," it means a segment unless stated otherwise.

For a segment `s` over an analysis window `[t0, t1]`:

- `y_s` — count of valid, deduplicated, quality-passing reports on `s` (Section 2).
- `E_s` — **exposure**: an estimate of how much travel happened on `s` in the window, in a
  documented unit such as person-kilometers or count-station-equivalent passes (Section 3).
- `theta_s = y_s / E_s` — the **rate**: reports per unit exposure. This, with an interval, is
  the published risk estimate (Section 4).
- `n_s` — sample size for `s`; here `n_s = y_s`, the report count, because that is what the
  interval width is governed by. Small `n_s` is the central statistical problem of this project.

<!-- claim:rate-union-not-per-type -->
Hazard **type** (close pass, dooring, surface hazard, sightline, signal, debris) is carried
through every step and published per segment as a `hazard_breakdown` count by type. **Today the
single published `rate` per segment is computed over the union of all hazard types** — `aggregate.py`
sums every type into one segment count that `rates.py` normalizes — so the published rate is an
all-types union, and the `hazard_breakdown` beside it shows the type mix. Publishing **type-specific
rate layers** (a separate dooring rate, surface-hazard rate, and so on, each with its own interval
where `n` permits) is PLANNED, not yet implemented. Until it lands, read the published rate as an
all-hazard-types union; a dooring rate and a pothole rate are different quantities and separating
them into per-type rates is future work.
<!-- /claim:rate-union-not-per-type -->

The analysis window, the reference network version, the exposure source, and the hazard type are
recorded with every published number. A rate with no window, network, source, and type attached
is not a publishable number.

---

## 2. From raw reports to counts

Counts are the input to everything downstream, so the steps that produce them are pure, recorded,
and inspectable (the architecture's `intake.py` → `pipeline/` stages). A count is not "rows in a
spreadsheet"; it is the surviving population after the following filters, each of which is logged
with how many reports it removed.

1. **Schema validation** (`intake.py` vs. `schema/report.schema.json`). A report missing a
   location, time, or type, or failing a field constraint, never enters the dataset. Rejections
   are counted, not silently dropped, so we can see if a form change started shedding reports.
2. **Deduplication** (`pipeline/dedupe.py`). Two reports are treated as duplicates when they
   match on type and fall within a small space-time radius (configured per city, default 25 m and
   10 minutes) *and* share a contributor pseudonym or an obvious resubmission signature. The rule
   is deliberately conservative: collapsing two genuine independent reports understates risk,
   so when in doubt we keep both and flag, rather than merge.
3. **Geocoding and snapping** (`pipeline/geocode.py`, `pipeline/snap.py`). A report is placed on
   a segment. A report that cannot be snapped within the tolerance is **quality-flagged**, not
   force-snapped to the nearest segment, because a forced snap manufactures a count on a segment
   no one reported.
4. **Classification and quality flags** (`pipeline/classify.py`, `pipeline/quality.py`). Each
   report gets a quality tier.
   <!-- claim:low-confidence-flagged-not-excluded -->
   Low-confidence reports (low positional accuracy or a snap beyond tolerance — the internal
   `low_accuracy` / `far_snap` flags) are **flagged**: the segment they land on carries the published
   `geocode_low_confidence` quality flag so a consumer sees the caveat (`stats/__init__.py`,
   `_LOW_CONFIDENCE_RAW`). **They are currently still counted in the primary rate.** Splitting them
   out — excluding low-confidence reports from the primary rate, computing a separate sensitivity
   rate, and publishing the excluded fraction — is PLANNED, not yet implemented; today the flag is
   surfaced but the rate is not recomputed without the flagged reports.
   <!-- /claim:low-confidence-flagged-not-excluded -->

`y_s` is the count of reports on `s` that pass all four. The per-segment counts, the per-filter
removal counts, and the quality-tier breakdown are emitted as inspectable intermediate data
(`--dump`) so the journey from raw to count is auditable end to end.

**A count is not a risk.** A map of `y_s` is labeled **"report volume,"** never "danger," in
every artifact — map legend, table column header, brief, and data card. This is Hard Rule 1 at
the level of a single number. The conversion of `y_s` into a risk statement only happens after a
denominator is attached (Section 3) and an interval is computed (Section 5).

---

## 3. Exposure: choosing and recording a denominator

A count confounds **danger** with **traffic**. Thirty close-pass reports on the city's flagship
bike route and three on a quiet connector do not mean the flagship is ten times as dangerous;
they may mean it carries fifty times the riders. Hard Rule 1 — *no rate without a denominator* —
exists to stop exactly this error. `exposure.py` attaches an exposure estimate `E_s` to each
segment and records its provenance.

### 3.1 The three denominator sources, best first

Exposure is hard to measure and we are explicit about that. nearmiss supports three classes of
denominator, in descending order of trust. The config picks a source per segment and the chosen
source is recorded *per segment*, because a city is usually a patchwork of well-measured and
unmeasured streets.

1. **Observed counts** (most trusted). Bike/pedestrian volumes from permanent or temporary count
   stations, manual counts, or instrumented intersections. These are direct measurements of
   exposure. Their weakness is coverage: most segments have no count station, so observed counts
   anchor a minority of the network and must be extended by a model or layer to cover the rest.
2. **Demand model** (modeled). A network-assignment or facility-demand model that estimates
   volume on unmeasured segments, ideally calibrated against the observed counts above. A demand
   model's estimates inherit the model's assumptions and any bias in its calibration data; it is
   trusted less than a direct count and more than a generic activity layer.
3. **Exposure layer** (proxy). A third-party activity surface — for example a GPS-fitness-app
   heatmap such as Strava Metro, or a location-data product such as StreetLight — used as a
   *proxy* for relative exposure. These have wide coverage and severe representativeness
   problems: a fitness-app layer over-weights recreational and fast riders and under-weights
   short utility trips, children, and lower-income riders without the app. An exposure proxy is
   used only when nothing better exists for a segment, its representativeness caveat is carried
   into the bias analysis (Section 6), and segments rated on a proxy are visibly marked.

When two or more sources cover the same segment they can **corroborate** the denominator; a large
disagreement between, say, a count station and the exposure layer is itself a finding and is
surfaced, not averaged away into a false consensus.

### 3.2 Recording the source and its date — non-negotiable

Every `E_s` carries, in the published record and the data card:

- the **source identifier** (which count program, which model run, which exposure-layer vintage);
- the **source date / coverage window** — *when the exposure was measured or modeled*, which is
  often not the same window as the reports;
- the **unit** of `E_s` (person-km, station-equivalent passes, normalized layer intensity);
- a **trust tier** (observed / modeled / proxy) from the list above.

This is Hard Rule 1's second clause: the exposure source *and its date* are stated alongside the
rate. The date matters because exposure drifts — a new protected lane, a school reopening, a
seasonal swing — and a rate built on a denominator measured years before or after the reports is
comparing two different cities. A mismatch between the report window and the exposure window is
flagged as a temporal-alignment caveat on that rate.

### 3.3 The exposure floor and "exposure unknown"

Rates blow up as `E_s -> 0`: one report on a segment with near-zero estimated exposure produces an
enormous, meaningless rate. Two guards:

- **Exposure floor.** Segments whose exposure estimate is below a configured floor are not
  assigned a finite rate. They are not silently dropped (that would hide a real hazard) and not
  force-rated (that would fabricate a giant rate). They are published as **"exposure unknown"** /
  below-floor and shown in the table with their raw report volume and an explicit no-rate flag —
  the README's "degradability / failure transparency" behavior.
- **Uncertainty propagation.** Where exposure is itself an estimate with error (a model or a
  proxy), that error is acknowledged. The primary interval (Section 5) treats `E_s` as fixed and
  captures only sampling error in the count; an **exposure-sensitivity** pass re-runs the ranking
  under plausible alternative denominators and reports how much the conclusion moves. A ranking
  that survives only one choice of exposure source is reported as fragile.

---

## 4. Rates: turning counts and exposure into risk

With a count `y_s` and an exposure `E_s` for a comparable window, the rate is

```
theta_s = y_s / E_s          (reports per unit exposure)
```

This is modeled as a count over an exposure offset — the standard rate model. We treat `y_s` as a
realization of a count process with mean `theta_s * E_s`. The working assumption is Poisson
(`y_s ~ Poisson(theta_s * E_s)`), which is the right default for counts of rare events over an
exposure base and which gives us principled small-count intervals (Section 5).

**Overdispersion is expected — and the check is implemented (config-gated).** Real report
counts are usually *more* variable than Poisson because reporting clusters — one viral post, one
active local group, one bad week drives a burst of correlated reports. The behavior is: the pooled
quasi-Poisson dispersion statistic `phi` is **always computed** (`stats/rates.py::pearson_dispersion`,
a Pearson chi-square residual against the pooled rate/offset model) and always reported — in every
published metadata sidecar under `methods.dispersion.phi` and in the advocacy brief's robustness
section. When `phi` is materially above 1 (overdispersion, variance > mean), the per-segment Poisson
intervals understate uncertainty by roughly `sqrt(phi)`; enabling the `overdispersion_adjust` config
key widens every published interval by `sqrt(phi)` (a quasi-Poisson treatment, `stats/rates.py::quasi_poisson_ci`).
Widening is **off by default** so that turning it on is a deliberate, versioned methodology change
rather than a silent rewrite of every published interval; when it is off, `phi` is still published so
a reader can see the clustering and read the intervals as a lower bound on the true uncertainty. The
estimate is conservative by construction — taken against one pooled rate, genuine between-segment rate
heterogeneity inflates `phi` too, so it is an upper bound on nuisance overdispersion and the widening
errs only toward wider, more cautious intervals. (Negative-binomial estimation of the dispersion
remains possible future work; the quasi-Poisson path is what ships.)

Rates are compared on the **same exposure unit and window** or not compared at all. A rate built
on observed counts and a rate built on a fitness-app proxy are different measurements; the
trust-tier flag travels with each so a reader never silently compares across tiers.

---

## 5. Confidence intervals for sparse counts

Hard Rule 2 — *no estimate without an interval* — is the load-bearing rule of this whole project,
and it is hardest exactly where it matters most: segments with a handful of reports. Most
segments are sparse. The wrong interval method here is the single most common way an honest-looking
analysis lies, so this section is specific about *which* method and *why*.

### 5.1 Why small-count methods are mandatory, not optional

The textbook "estimate ± 1.96 · standard error" (a Wald / normal-approximation interval) is
catastrophically wrong for small counts. For a Poisson count it can produce a **negative lower
bound** (a negative number of reports), and for a binomial proportion near 0 it produces intervals
with true coverage far below the nominal 95% — it claims more certainty than it has. A segment with
2 reports does not have a symmetric, normal sampling distribution. Using a normal approximation
there is not a rounding error; it is a false confidence claim, and false confidence is the exact
failure mode this project is built to avoid. **The Wald interval is therefore prohibited for the
published rates.** It is acceptable only as a clearly-labeled teaching contrast in a notebook.

### 5.2 Interval for a single segment's rate (Poisson count over exposure)

For the rate `theta_s = y_s / E_s` with `y_s` a Poisson count and `E_s` a known exposure offset,
the interval comes from the count, then is divided by the offset:

- **Byar's approximation to the Poisson interval** — the implemented default (`stats/rates.py`,
  `poisson_ci`), a closed-form approximation that stays well behaved all the way down to count 0
  and is used whenever a small-count interval is wanted, including when `y_s = 0`:

  ```
  lower(y) = y * (1 - 1/(9*y) - z/(3*sqrt(y)))**3                 # 0 when y = 0
  upper(y) = (y + 1) * (1 - 1/(9*(y+1)) + z/(3*sqrt(y+1)))**3     # z = z_(1-alpha/2)
  CI(theta_s) = [ lower(y_s) / E_s , upper(y_s) / E_s ]
  ```

  Byar's approximation never returns a negative lower bound, handles `y_s = 0` correctly (lower
  bound 0, finite upper bound — "we have no reports here, but here is how high the true rate could
  still plausibly be"), and tracks the exact Poisson interval closely even at very small counts
  while being cheap and dependency-light. It is what the published rates use today.

- **Exact (Garwood) Poisson interval** via the chi-square relationship is a possible *future*
  option for cases where strictly guaranteed (>= nominal) coverage is wanted rather than Byar's
  close approximation. It is **not** the implemented default and is noted here only as planned work.

- **Score-based interval** as a further alternative when a less conservative, well-calibrated
  interval is preferred and counts are not tiny. Score intervals (the Poisson analogue of the
  Wilson score interval for proportions) have average coverage closer to nominal than the exact
  interval and far better than Wald, without Wald's pathologies.

<!-- claim:byar-poisson-ci -->
The implemented `poisson_ci` (Byar's approximation, `stats/rates.py`) and the chosen `alpha` are
recorded with every published interval. Byar's approximation is the implemented default small-count
Poisson interval — it returns a `0` lower bound at count 0 and a finite upper bound, and is exercised
by `tests/test_rates.py`. We do not mix methods within a single comparison.
<!-- /claim:byar-poisson-ci -->

### 5.3 Proportions, when the question is a share

Some questions are proportions, not rates — e.g. "what share of reports on this corridor are
dooring?"
<!-- claim:wilson-proportions -->
For a proportion `p = k / m` we use **Wilson score** intervals by default (`stats/rates.py`,
`wilson_ci`), and **Clopper-Pearson exact** intervals when guaranteed coverage is required, never
Wald. Wilson is the well-established small-sample default: it stays inside `[0, 1]`, behaves near 0
and 1, and has good coverage at small `m`. `wilson_ci` is exercised by `tests/test_rates.py`
(bounds stay in `[0, 1]`; `successes > trials` is rejected). Clopper-Pearson exact intervals are
noted here as an option, not the implemented default.
<!-- /claim:wilson-proportions -->

### 5.4 What the interval does to ranking

This is where intervals earn their keep. Segments are ranked by the point estimate of the rate,
but a point estimate is **never published alone** — its interval travels with it and small-sample
segments are flagged so the order is read with its uncertainty, not as bare certainty.

- Two segments whose intervals overlap substantially are reported as **not distinguishable** at
  the stated confidence, even if their point rates differ. The table says so; the map does not
  draw a hard boundary between them.
- A segment with too few reports to produce a usefully narrow interval is shown as **uncertain**
  and is *not* given a confident rank — Hard Rule 2's "shown as uncertain, not ranked as certain."
  In practice we suppress a hard numeric rank below a configured minimum count and label the
  segment "insufficient data to rank," carrying its volume and its wide interval instead.
- The default published ranking is by the **point estimate** of the rate (descending). Each
  ranked rate is shown *with* its confidence interval (Section 5.2), and small-sample segments are
  flagged as **uncertain** rather than presented as precise, so a reader sees the imprecision
  beside the rank instead of trusting the order blindly. Ranking by the **lower confidence bound**
  of the rate — which would automatically penalize sparse, uncertain segments instead of letting a
  single lucky report rocket a quiet segment to the top — is a candidate for future work, not the
  current behavior. The choice of ranking statistic is stated in the brief.

### 5.5 Multiplicity

Scanning every segment in a city for "significant" hotspots runs hundreds or thousands of tests;
some will look extreme by chance.
<!-- claim:bh-fdr -->
Wherever we make a many-segments significance claim (the Getis-Ord step, Section 8, and any
per-segment flagging), we control for multiple comparisons with a false-discovery-rate
(Benjamini-Hochberg) adjustment by default (`stats/getis_ord.py`, `benjamini_hochberg`); the
published `getis_ord_significant` flag is the FDR-corrected decision, not a raw per-segment
`p < 0.05`, and this is exercised by `tests/test_fdr.py`.
<!-- /claim:bh-fdr -->
An unadjusted "this segment is significant at p < 0.05" out of a thousand segments is not a finding,
and we do not present it as one.

---

## 6. Reporting bias: characterizing who and where is missing

Hard Rule 3 — *reporting bias is named, not hidden*. nearmiss data is **voluntary and
non-random**. It records where people *chose to report*, filtered through who has the app, who
speaks the form's language, who feels safe reporting, and which streets are even traveled. This is
not noise to be averaged out; it is a structural property of the dataset, and `stats/bias.py`
characterizes it explicitly and the briefs state it in plain language.

### 6.1 The two biases we name

- **Who reports (reporter-pool bias).** The contributors are not a representative sample of road
  users. We compare the reporter pool, on every attribute we ethically have, against ridership and
  demographic baselines: mode share, and area-level demographics (age, income, language, car
  access) from census/ACS-style sources for the reporting areas. Where the reporter pool skews —
  e.g. toward confident commuter cyclists and away from children, older adults, and lower-income
  riders — we say so and we name the direction of the likely distortion.
- **Where reports come from (geographic-coverage bias).** Reports cluster on popular routes and in
  engaged neighborhoods. We compare the geographic spread of reports against the exposure surface
  (Section 3) and against the network itself: which segments and which neighborhoods generate
  reports out of proportion to their travel, and — more important — which generate *none*. A
  segment with zero reports can be genuinely safe, genuinely unused, or simply un-surveilled by
  this dataset, and we cannot tell which from counts alone.

### 6.2 How we measure and report it

- **Representativeness comparison.** For each baseline (mode share, demographics, exposure), we
  report the reporter/report distribution beside the baseline distribution, with the gap quantified
  (a simple representation ratio per group, with its own interval). This is a description of
  coverage, stated honestly; it is *not* silently used to "correct" rates.
- **Coverage maps.** A reports-vs-exposure comparison highlights well-covered and under-covered
  areas, so a reader sees where the dataset is thin before trusting a local rate.
- **Plain-language bias statement.** Every brief and the data card carry a sentence in plain
  language naming who is likely over- and under-represented and *what that does to the conclusion*
  — e.g. "this dataset under-represents trips by children and by riders without the reporting app;
  hazards on routes those groups use are likely undercounted, so absence of reports there is not
  evidence of safety."

### 6.3 Why we do not "bias-correct" the rates by default

It is tempting to reweight reports to make the pool look representative. We do not do this in the
published rates by default, for a stated reason: post-stratification weighting requires a credible
model of the reporting probability for every group on every segment, and we do not have one. A
weighting model built on weak assumptions would *launder* bias into an authoritative-looking number
and quietly violate the spirit of Hard Rule 3. Instead we keep the rates transparent and the bias
*named beside them*, and offer any reweighting only as a clearly-labeled sensitivity analysis with
its assumptions on the table. Naming a bias we cannot remove is more honest than removing it with a
model we cannot defend.

---

## 7. Hot because dangerous vs. hot because busy

This is the distinction the entire project exists to get right, so it gets its own section.

A naive heat map of report locations is a map of **report volume**. Report volume is driven by
three things at once:

1. how **dangerous** a place is (what we want to measure),
2. how **busy** it is — exposure (more travelers, more reports, even at equal danger),
3. how **surveilled** it is by this dataset — reporting propensity (Section 6).

A raw kernel-density heat map collapses all three into one warm blob and, because exposure and
reporting propensity both peak on the popular routes, it will reliably light up the **busiest bike
corridor** and invite the reader to call it the most dangerous. That is the heat-map lie this
project refuses to tell.

The defenses, layered:

- **Normalize by exposure (Section 3).** Dividing by `E_s` removes the "busy" component, turning
  volume into a rate. A quiet connector with 3 reports and tiny exposure can correctly outrank a
  flagship route with 30 reports and huge exposure.
- **Carry an interval (Section 5).** Removes the "lucky-few-reports" component, so a quiet segment
  cannot top the ranking on a single report.
- **Name the reporting bias (Section 6).** Addresses the "surveillance" component — it cannot be
  divided out, so it is stated.
- **Use exposure-aware spatial statistics (Section 8).** Gives a *significance* test for clusters,
  so "hot" means "hot beyond what exposure and chance explain," not "hot because lots of people are
  here."

Concretely, every published hotspot answers the question **"is this segment's report *rate*
high, with an interval that excludes the city norm, given its exposure?"** — not "did this
segment get a lot of reports?" The two can and do disagree, and when they disagree the rate-based,
exposure-aware answer is the published one. The brief explicitly contrasts the volume ranking and
the rate ranking so the reader sees the difference rather than taking the map's word for it.

---

## 8. Spatial hotspots: KDE intensity vs. Getis-Ord Gi\*

Two spatial tools, two different jobs. We use both and we are explicit that they are not
interchangeable.

### 8.1 Kernel density estimation — a smoothed intensity surface, not a danger map

`stats/kde.py` computes a kernel density surface over report (or rate) locations. KDE answers
"where is report activity concentrated, smoothed over a bandwidth," producing a continuous surface
that is easy to read and easy to *mis*-read.

Why a raw KDE is misleading and how we constrain it:

- **A raw KDE of report *points* is a smoothed volume map** — it carries every bias in Section 7.
  Smoothing makes it look authoritative and removes the visible point density that would warn a
  reader the surface rests on three reports. A density surface over biased counts is a prettier
  biased count.
- We therefore **never publish a raw point-density KDE as a danger surface.** A KDE built on report
  points is labeled **"report intensity,"** explicitly not danger, in the legend and the data card
  — the same labeling discipline as Section 2.
- When KDE is used as an *input to a risk surface*, it is **exposure-aware**: either a
  kernel-smoothed **rate** (smoothed reports over a comparably smoothed exposure surface) or a
  density that is explicitly contextualized by an exposure density. A bare numerator surface is
  not a risk surface.
- **Bandwidth is a stated choice, not a default.** The bandwidth controls how much the surface is
  smoothed and can manufacture or erase a hotspot; it is recorded with the figure and varied in a
  sensitivity check. KDE is treated as a **visualization and exploratory** tool — for *significance*
  we use Getis-Ord, below.

### 8.2 Getis-Ord Gi\* — statistically significant clusters

`stats/getis_ord.py` computes the **Getis-Ord Gi\*** local statistic to identify clusters that are
statistically significant given spatial structure. Gi\* asks, for each segment, whether the values
in its neighborhood (itself included) sum to more than would be expected if the values were randomly
arranged across the network — yielding a z-score and a p-value per segment, so a "hotspot" is a
*tested* claim, not a warm color.

Decisions that make Gi\* honest here, rather than a fancier heat map:

<!-- claim:gi-on-rate-not-count -->
- **Run it on the rate, not the raw count.** This is the crucial choice. Gi\* on raw report counts
  finds clusters of *volume* and re-tells the heat-map lie with a p-value attached. Gi\* on the
  exposure-normalized rate `theta_s` (Section 4) finds clusters of elevated *risk* — clusters of
  "hot because dangerous," which is what we publish. The input to `getis_ord_star` is the rate
  (`stats/__init__.py` feeds it `rate_values`, not counts), exercised by `tests/test_hotspot.py`
  (the planted low-exposure corridor is recovered as the significant cluster while the busy decoy is
  not).
<!-- /claim:gi-on-rate-not-count -->
<!-- claim:gi-weights-straightline -->
- **The spatial weights matrix, honestly described.** Neighbors are currently defined by a **binary
  straight-line distance band**: two segments are neighbors when their centroids fall within
  `gi_band_m` of each other, measured as great-circle (haversine) distance, with the focal segment
  included as Gi\* requires (`stats/getis_ord.py` calls `haversine_m` between `polyline_centroid`
  points). The band is recorded with the result (`metadata.methods.getis_ord_band_m`).
  **Street-network adjacency / network-distance weights — which would keep two segments on opposite
  sides of a river or freeway from counting as neighbors — are PLANNED, not yet implemented.** Until
  they land, a Euclidean band can treat barrier-separated segments as neighbors and so manufacture or
  dilute a cluster near a barrier; this is a known limitation, flagged here rather than hidden.
<!-- /claim:gi-weights-straightline -->
- **Analytic inference, with multiplicity control.** Significance comes from the **analytic
  normal-approximation Gi\* z-score** (`stats/getis_ord.py`) — the standard closed-form Gi\*
  statistic and its asymptotic normal reference — and across the many per-segment tests we apply
  the false-discovery-rate (Benjamini-Hochberg) control from Section 5.5 to decide which segments
  are significant. We report both raw and FDR-adjusted significance. A **conditional permutation
  reference distribution**, which would relax the normal-approximation assumption, is possible
  future work; it is **not** what is computed today.
- **Honest about sparse and uncertain inputs.** Gi\* run on rates that are themselves wildly
  uncertain (sparse segments) inherits that uncertainty. Below-floor / "exposure unknown" segments
  (Section 3.3) are handled explicitly — excluded or shown as untested — never fed in as if they
  carried a solid rate, and the handling is recorded.

### 8.3 What we publish from the spatial layer

The published hotspot product is the set of segments that are **significant hot clusters of the
exposure-normalized rate** under Gi\* (FDR-adjusted), each carrying its rate, its interval, its n,
its exposure source and date, and its significance. The KDE surface, if shown, is published beside
it strictly as labeled report-intensity context. Significance is conveyed in **text and pattern, not
color alone** (the accessibility requirement), and the same ranked, flagged set is available in the
non-visual list/table equivalent.

**Re-segmentation sensitivity (MAUP) — implemented.** Street segments are an arbitrary areal unit, so
a hotspot drawn at one granularity can dissolve at another (the modifiable areal unit problem; see
[LIMITATIONS §5](LIMITATIONS.md)). Rather than only caveating this, we answer it with a reproducible
artifact: `stats/maup.py::rank_stability` deterministically **re-segments the network** into a coarser
partition (a greedy nearest-neighbour pairing that moves both MAUP axes at once — scale *and* zoning),
recomputes the exposure-normalized rate ranking and the Gi\* + FDR significance on the coarser units,
and reports whether the top hotspot **survives** (stays the top-ranked coarse unit and still a
significant cluster) together with a top-k rank-overlap scalar. This ships in every published metadata
sidecar under `maup_rank_stability` and is surfaced in the advocacy brief's robustness section, so a
reader can see whether a headline hotspot is a real cluster or an artifact of where the block lines
were drawn.

---

## 9. Validation against synthetic fixtures

Methodology claims are worthless unless tested, and you cannot test a danger map against reality
because the ground truth (true danger) is unobserved — that is the entire problem. So we test
against **synthetic fixtures whose answers we planted and therefore know** (`tests/fixtures/`),
following Hard Rule 5. This is how we keep ourselves honest about our own honesty.

### 9.1 Planted-hotspot recovery

We generate synthetic report sets on a known network with **planted hotspots** — segments seeded
with an elevated true rate — and a known exposure surface, including deliberately **busy-but-safe**
decoy segments (high exposure, baseline rate) and **quiet-but-dangerous** segments (low exposure,
elevated rate). The pipeline and statistics must:

- **recover the planted dangerous segments** as significant hot clusters, and
- **not flag the busy-but-safe decoys** — the explicit test of Section 7. A build where the busy
  decoy lights up as a hotspot is a failing build, because it means we re-told the heat-map lie.

### 9.2 Interval checks (Monte-Carlo coverage simulations PLANNED)

<!-- claim:coverage-sims-planned -->
For the confidence intervals (Section 5) the committed suite (`tests/test_rates.py`) tests the
interval **properties** directly: that Byar's Poisson interval contains the point estimate and widens
relatively for small `n`, that count 0 yields a `0` lower bound with a finite upper bound, that the
rate scales correctly by exposure, and that Wilson bounds stay inside `[0, 1]` and reject
`successes > trials`. **Monte-Carlo coverage simulations — simulate many datasets from a known true
rate, build a 95% interval each time, and confirm ~95% contain the truth — are PLANNED, not yet
implemented.** They are the check that would catch a method that claims 95% but covers 80% (exactly
the lie the banned Wald interval of Section 5.1 tells); until they land, the property tests above,
not a coverage simulation, are what guards the interval code. This gap is flagged here rather than
implied away.
<!-- /claim:coverage-sims-planned -->

### 9.3 Bias and null behavior

- **Bias recovery.** Fixtures with a *planted* reporting bias (a region seeded to under-report)
  confirm that `bias.py` detects and reports the under-coverage, and that the bias statement points
  in the correct direction.
- **Null / no-signal behavior.** A fixture with reports scattered at a uniform true rate (no real
  hotspot) must yield **no** significant clusters beyond the controlled false-discovery rate. A
  method that "finds" hotspots in pure noise is finding artifacts, and this fixture fails it.
- **Sparse-data behavior.** Fixtures dominated by 0-, 1-, and 2-report segments confirm that
  sparse segments are surfaced as *uncertain* and not ranked as certain, and that 0-report segments
  get a finite upper bound rather than an error.

These fixtures, their planted answers, and the assertions are committed; `make reproduce` and the
CI test gate re-run them, so a regression in any statistical claim breaks the build.

---

## 10. Limitations: what these numbers do NOT support

Stated plainly, because credibility depends on it and Hard Rule 3 demands it. These are the things
a careful reader — or a skeptical traffic engineer — is right to hold us to.

**This dataset measures reported near-misses, not danger directly.** Every number is downstream of
who chose to report. Read it as "where reporters experienced and recorded hazards, normalized by
our best exposure estimate," not as a ground-truth danger ranking.

These numbers do **NOT** support:

1. **"No reports here means it is safe."** Absence of reports is absence of *reporting*, which
   conflates safe, unused, and un-surveilled. Zero-report segments are not safe by inference, and
   we never publish them as such (Section 6).
2. **Comparing rates across different exposure sources or windows as if equal.** A rate on observed
   counts and a rate on a fitness-app proxy are different measurements; a rate whose exposure was
   measured in a different period than its reports has a temporal mismatch. The trust tier and dates
   travel with every number precisely so these are not compared naively (Sections 3, 4).
3. **Ranking sparse segments with confidence.** A segment with a handful of reports has a wide
   interval and is shown as uncertain, not ranked as certain (Section 5). Do not read the point
   estimate of a 2-report segment as a precise risk.
4. **Treating the contributor pool as representative.** It over-represents app-equipped, confident,
   often commuter cyclists and under-represents children, older adults, riders without the app, and
   non-English-speaking communities (Section 6). Conclusions about those groups' risks are weaker
   than the headline numbers and are flagged as such.
5. **Causal claims.** A hot cluster says risk concentrates there; it does **not** establish *why*,
   nor that a specific intervention will fix it. nearmiss locates and quantifies; it does not run
   the experiment that proves a cause or a cure.
6. **Predicting collisions or casualties.** Near-misses are a related but distinct signal; this
   project does not claim a calibrated near-miss-to-collision conversion and publishes no such
   prediction.
7. **Individual surveillance or blame.** The published data is aggregated to public street segments,
   with low-count segments withheld (k-anonymity) and no precise coordinates or timestamps published,
   precisely so it cannot identify a person, a routine, or a single driver (Hard Rule 4); it must
   not be used to target individuals. It is a community evidence base, not a 311 queue and not an
   enforcement tool.
8. **Substituting for local knowledge or official safety data.** It is a complement to engineering
   judgment, resident experience, and collision records — a way to surface and quantify what those
   sources miss — not a replacement for them.

Where any of these limits bites a specific finding, the brief says so *at that finding*, not only
here. A limitation buried in a methodology appendix while the headline overclaims would itself
violate the rules this document enforces.

---

## 11. Reproducibility and provenance

Hard Rule 5 — *open and reproducible end to end*. Every figure, table, rate, interval, and hotspot
in a published brief is produced by a committed notebook from the raw inputs, and `make reproduce`
regenerates all of them deterministically. Runs are seeded and content-hashed so the same inputs
yield the same outputs, and a published number traces back through:

```
brief figure  ->  notebook cell  ->  statistic (rates/bias/kde/getis_ord)
              ->  exposure attach  ->  cleaned dataset  ->  pipeline stage  ->  raw report
```

Every published number carries its **provenance bundle**: analysis window, reference-network
version, hazard type, exposure source + date + trust tier, count `n`, interval method and `alpha`,
ranking statistic, and (for clusters) the spatial-weights definition and the significance/FDR
settings. A number without its bundle is not publishable. The synthetic fixtures and their planted
answers are committed so the statistical claims are checkable by anyone, not taken on trust — which
is the whole standard this document is held to.

---

## 12. References

Methods here are standard; these are the anchors a reviewer can check the implementation against.

- Byar's approximation to the Poisson confidence interval (a closed-form cube-root /
  Wilson-Hilferty-style approximation; see Rothman, K. J., Greenland, S., & Lash, T. L., *Modern
  Epidemiology*) — the **implemented** small-count Poisson interval, Section 5.2.
- Garwood, F. (1936). Fiducial limits for the Poisson distribution. *Biometrika* — the exact
  Poisson interval noted in Section 5.2 as a possible future option, not the current default.
- Clopper, C. J., & Pearson, E. S. (1934). The use of confidence or fiducial limits illustrated in
  the case of the binomial. *Biometrika* — the exact binomial interval, Section 5.3.
- Wilson, E. B. (1927). Probable inference, the law of succession, and statistical inference.
  *JASA* — the score interval for proportions, Section 5.3.
- Brown, L. D., Cai, T. T., & DasGupta, A. (2001). Interval estimation for a binomial proportion.
  *Statistical Science* — why Wald fails and score/exact intervals are preferred (Section 5.1).
- Getis, A., & Ord, J. K. (1992). The analysis of spatial association by use of distance
  statistics. *Geographical Analysis* — the Gi\* statistic, Section 8.2.
- Ord, J. K., & Getis, A. (1995). Local spatial autocorrelation statistics: distributional issues
  and an application. *Geographical Analysis* — local Gi\* inference, Section 8.2.
- Benjamini, Y., & Hochberg, Y. (1995). Controlling the false discovery rate. *JRSS B* — the
  multiplicity control of Sections 5.5 and 8.2.
- Silverman, B. W. (1986). *Density Estimation for Statistics and Data Analysis* — kernel density
  estimation and bandwidth choice, Section 8.1.

---

*This document is part of the nearmiss open methodology. It is versioned with the code; material
changes are recorded in the CHANGELOG and, where they alter a published method, in an ADR under
[`docs/adr/`](./adr/). Corrections and challenges are welcome via the repository — the analysis is
meant to be checked.*
