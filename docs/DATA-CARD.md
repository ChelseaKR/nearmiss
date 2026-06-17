# Data Card — nearmiss published open dataset

This card documents the **published, open** nearmiss dataset: the GeoJSON aggregated to
public street segments and the accompanying rate tables emitted by `publish.py`. It follows the spirit of
*Datasheets for Datasets* (Gebru et al.) and HuggingFace dataset cards: what the data is,
how it was made, what it can and cannot support, and where it will mislead you if you
misuse it.

It is written to hold up when a skeptical traffic engineer pushes back. Where the data is
weak, this card says so plainly. Read the "Out-of-scope and discouraged uses" and the
"Known reporting biases" sections before you cite a number.

- **Dataset name:** nearmiss published open dataset
- **Version:** tracks the release tag of the repository (semver); the exact dataset version,
  schema version, and content hash are recorded in the published data card sidecar
  (`data/published/datacard.json`) shipped next to the GeoJSON.
- **Maintainer:** Chelsea Kelly-Reif (GitHub [@ChelseaKR](https://github.com/ChelseaKR)).
  Contact via the GitHub repository's issues. This is an independent personal open-source
  project, unaffiliated with any employer or client.
- **Repository:** `github.com/ChelseaKR/nearmiss` (private during development).
- **License:** Apache-2.0 (see [License and citation](#license-and-citation)).
- **Schema:** report intake schema at `schema/report.schema.json`; published GeoJSON schema
  at `schema/dataset.schema.md`.

---

## Dataset summary

nearmiss publishes an **exposure-normalized analysis of road-hazard and near-miss reports**
made by people on bikes and on foot — close passes, door-zone conflicts, blind-corner /
sightline problems, surface hazards (potholes), debris, and signal/crossing problems. The
core idea is that raw report counts confound *danger* with *traffic*: the busiest bike route
collects the most reports whether or not it is the most dangerous. The published dataset is
therefore not a pile of pins. It is:

1. a **segment-aggregated GeoJSON** of near-miss reports, where the published geometry is the
   real public street centerline (public infrastructure) and no per-report coordinate is
   published, plus
2. **per-segment rate estimates** that divide report counts by an **exposure denominator**
   (a bike/pedestrian volume or demand estimate), each carrying a **confidence interval**
   and an **n**, plus
3. **hotspot outputs** — a kernel-density surface labeled by what it actually shows, and
   Getis-Ord Gi\* clusters flagged as statistically significant given exposure and spatial
   structure — plus
4. a machine-readable **data card sidecar** recording sources, dates, methods, thresholds,
   and the content hash for reproducibility.

The dataset is the product, not an app. The accessible web map and table are just two views
of these published artifacts.

### Five rules this dataset is built to honor

This card is bound by the project's five hard rules (enforced in CI and by policy):

1. **No rate without a denominator.** Every risk number here is a rate per unit of exposure,
   with the exposure source and its date stated. Raw-count layers exist but are labeled
   **"report volume,"** never "danger."
2. **No estimate without an interval.** Every published rate, ranking, and comparison carries
   a confidence interval and an `n`. Small-sample segments are marked uncertain, not ranked.
3. **Reporting bias is named, not hidden.** See [Known reporting biases](#known-reporting-biases-who-is-over--and-under-represented).
4. **Contributor privacy is protected.** Reports are pseudonymous; the open dataset is
   aggregated to public street segments, low-count segments are withheld entirely, and raw
   precise reports stay private. See
   [Privacy: aggregation and minimum occupancy](#privacy-aggregation-and-minimum-occupancy).
5. **Open and reproducible end to end.** `make reproduce` regenerates every figure and table
   from raw inputs. See [Maintenance and updates](#maintenance-and-updates).

---

## Motivation

### Why this dataset exists

Vulnerable road users absorb most of the risk on streets and produce almost none of the
official data. A near miss leaves no police report, and even collisions involving people on
bikes and on foot are routinely undercounted. Advocates are then told "show us the data" by
the same agencies whose data does not capture the problem. nearmiss exists to collect that
missing evidence carefully and to analyze it without cheating — specifically, to refuse the
tempting lie of a raw heat map that confidently points at the busiest, best-lit bike route
and calls it the most dangerous one.

The published dataset turns the reports cyclists and pedestrians already make into a
rigorous, open, reusable evidence base that advocates, researchers, journalists, and
cooperative city staff can check, fork, and build on.

### Who built it and who funded it

Built and maintained by a single person (Chelsea Kelly-Reif) as an independent personal
open-source project. **There is no funding, sponsor, employer, or client behind it**, and it
contains no proprietary or client material. There are no contributors beyond the maintainer
at the time of writing; community contributions, when they arrive, will be acknowledged in
the repository.

### What gap it fills

It is a community-owned evidence base — **not a city 311 queue and not a public-works
complaint inbox.** Filing a report here does not dispatch a crew or fix a pothole. The value
is the open dataset and the honest analysis under it, available to anyone, independent of any
city's data portal or goodwill.

---

## Composition

### What a record is

The published dataset has two coupled layers, both keyed to **street segments** (not to
addresses or to exact points):

- **Report-volume layer** — segment-aggregated geometry representing where near-miss
  reports cluster. A feature here answers "how many reports of what type fell on this
  segment," **after** aggregation to the public street segment. It is explicitly labeled
  report volume, not danger.
- **Rate layer** — per-segment rate estimates: report count over an exposure denominator,
  with an interval and an `n`. This is the layer that makes a risk claim.

A published record is therefore a **GeoJSON `Feature`** whose `geometry` is the real public
street centerline `LineString` for a segment, and whose `properties` carry the
classification, counts, exposure, rate, interval, and quality/significance flags. **No
published record is an individual person's report, and no per-report coordinate is
published.** Individual raw reports exist only in the private store.

### Published feature fields

The authoritative, versioned field list and types live in `schema/dataset.schema.md`. The
table below is the human summary; if the two disagree, the schema file wins.

| Field (`properties.*`)   | Type / values                                                            | Meaning |
|--------------------------|--------------------------------------------------------------------------|---------|
| `feature_kind`           | `report_volume` \| `rate` \| `kde_cell` \| `gi_star_cluster`             | Which published layer this feature belongs to. |
| `segment_id`             | string (stable, opaque)                                                  | Internal street-segment identifier the report was snapped to. Opaque; not a street address. |
| `hazard_type`            | `close_pass` \| `dooring` \| `surface_hazard` \| `sightline` \| `signal` \| `debris` \| `other` | Classified hazard category. |
| `report_count`          | integer ≥ 0                                                              | Number of reports aggregated into this feature after dedupe. |
| `period_start`           | date (ISO 8601)                                                          | Start of the aggregation window. |
| `period_end`             | date (ISO 8601)                                                          | End of the aggregation window. |
| `exposure_value`         | number \| `null`                                                         | Exposure denominator (e.g. estimated bike/ped volume) for the segment and window. `null` means exposure unknown. |
| `exposure_source`        | string                                                                   | Provenance of the denominator (count program, demand model, or named exposure layer). |
| `exposure_date`          | date (ISO 8601)                                                          | The date/vintage of the exposure source. |
| `rate`                   | number \| `null`                                                         | `report_count / exposure_value`, in the documented units. `null` when exposure is unknown. |
| `rate_ci_low`            | number \| `null`                                                         | Lower bound of the rate confidence interval. |
| `rate_ci_high`           | number \| `null`                                                         | Upper bound of the rate confidence interval. |
| `ci_method`              | string                                                                   | The interval method used (small-count method for sparse segments). |
| `n`                      | integer ≥ 0                                                              | Sample size behind the estimate (alias of the contributing report count). |
| `gi_star_z`              | number \| `null`                                                         | Getis-Ord Gi\* z-score, where computed. |
| `getis_ord_significant`  | boolean                                                                  | Whether the segment is a statistically significant cluster after multiple-comparison handling. |
| `quality_flags`          | array of strings                                                         | Pipeline quality flags (e.g. `low_geocode_confidence`, `outside_study_area`, `exposure_unknown`, `small_n`). |
| `confidence_label`       | `certain` \| `uncertain` \| `exposure_unknown`                           | Plain-language reliability label surfaced in the map and table. |

The intake (private) report schema — what a contributor actually submits — is separately
documented in `schema/report.schema.json` and includes the optional free-text note, the
pseudonymous contributor token, and the precise location, **none of which appear in the
published dataset at full fidelity** (see privacy section).

### Instances, labels, and what is missing

- **Instances:** aggregated segment/point features, not individual reports. Count and
  geographic extent depend on the deployment (city) and the reporting window; the data card
  sidecar records the exact totals for each release.
- **"Labels":** the `hazard_type`, `getis_ord_significant`, and `confidence_label` fields are
  the closest thing to labels. They are **classifier and statistical outputs**, not adjudicated
  ground truth.
- **Deliberately absent:** per-report coordinates, any per-report timestamp, contributor
  identity, the free-text note, mode, severity, heading, route/home-end information, and any
  field that would let a reader reconstruct an individual's routine. These are withheld by
  design, not lost.

### Relationship to other datasets

The published GeoJSON is aligned to a documented near-miss/collision schema so it can sit
beside official collision data and exposure layers. It is a **sibling** to
`davis-bike-hazard-map` (there the product is the map; here it is the data and the statistics
under it). Exposure denominators are *imported* from external sources (count programs,
demand models, or exposure layers); those sources keep their own licenses and vintages and
are cited per feature.

---

## Collection process

### How a report enters

Reports are made by people on bikes and on foot through a short form, a documented JSON
submission, or an import path, and capture: location, time, mode, hazard type, an optional
severity, and an optional free-text note. Reporting is **self-selected and voluntary** — this
is central to the bias discussion below.

### Intake and validation (`intake.py`)

Every incoming report is validated against `schema/report.schema.json` before it is accepted.
Malformed or out-of-range submissions are rejected at the door rather than silently corrupting
the dataset; intake is rate-limited to resist spam and poisoning. Accepted reports land in the
**private raw store** (`data/raw/`, gitignored) and never leave it at full precision.

### Pipeline transforms (recorded, inspectable)

The pipeline is a sequence of pure transforms, each emitting plain inspectable data so a
published number traces back to its inputs:

1. **Dedupe** (`pipeline/dedupe.py`) — collapse duplicate and near-duplicate submissions
   (same event reported twice, or by two people) using spatial/temporal/type proximity, so
   one event is not double-counted.
2. **Geocode** (`pipeline/geocode.py`) — resolve location text or coarse input to coordinates,
   attaching a geocode-confidence value; low-confidence results are flagged, not dropped.
3. **Snap-to-segment** (`pipeline/snap.py`) — snap each report to a street segment so analysis
   is per-segment rather than per-pin; the precise offset is used internally and discarded
   before publication.
4. **Classify** (`pipeline/classify.py`) — assign the `hazard_type` from the report's
   structured fields (and, where present, the note) into the documented categories.
5. **Quality-flag** (`pipeline/quality.py`) — attach `quality_flags` (e.g. low geocode
   confidence, outside study area, small sample, exposure unknown) that follow the record
   into publication so consumers can filter.

A single bad geocode or bad report flags and continues; it never aborts the rebuild.

### Timeframe, languages, and consent

- **Timeframe:** each release covers a stated reporting window recorded in the data card
  sidecar (`period_start`/`period_end`).
- **Language:** intake supports the report form in the languages of the community it is
  deployed for; coverage is uneven and is itself a known bias (below).
- **Consent:** contributors submit voluntarily and pseudonymously, with the understanding
  (stated at intake) that a segment-aggregated, de-identified form of their report will be
  published openly under Apache-2.0, and that the precise report will not be.

---

## Preprocessing and cleaning

Beyond the pipeline stages above, the following cleaning is applied between raw intake and
publication. Every step is deterministic and seeded so a rebuild reproduces the same output.

- **Deduplication** removes double-reported events; the surviving `report_count` reflects
  distinct events, not raw submissions.
- **Geocoding** normalizes location to coordinates with a confidence score; results below the
  configured confidence threshold are flagged `low_geocode_confidence` and are eligible for
  exclusion from rate estimates while remaining visible in the report-volume layer.
- **Snapping** moves analysis to the segment level; this is also a privacy step, because it
  removes the exact point a reporter chose.
- **Classification** maps reports to the documented hazard categories; anything that does not
  fit is `other`, never force-fit.
- **Quality flags** mark records that are geographically out of the study area, exposure-less,
  or too sparse to support a rate. A segment with no exposure data is published with
  `confidence_label = exposure_unknown` and a `null` rate — **shown, not silently dropped and
  not falsely rated.**
- **Aggregation to public street segments and withholding of low-count segments** (the final,
  irreversible cleaning step) are applied by `publish.py` — see the privacy section.

The raw, precise data is **never** part of any published or committed artifact.

---

## Exposure assumptions behind every rate

This is the section a traffic engineer will read first, so it is explicit.

**Every rate in this dataset is `report_count / exposure_value`.** The exposure value is an
*estimate* of how much biking/walking happened on that segment in that window — the
denominator that turns a count into a rate. Without it, more reports on a busy street would
masquerade as more danger.

- **What exposure can be.** Depending on the deployment, `exposure_value` comes from one of:
  observed bike/pedestrian counts where a count program exists; a demand model; or an imported
  exposure layer (e.g. a Strava/StreetLight-style volume surface). The specific source and its
  vintage are recorded per feature in `exposure_source` and `exposure_date`, and
  summarized in the data card sidecar. **Sources are interchangeable behind one interface**, so
  a given city's denominators may come from a different source than another's.
- **Assumptions baked into the denominator.** The rate is only as good as the exposure
  estimate. Known assumptions and their failure modes:
  - *Spatial coverage gaps.* Count programs cover a fraction of segments; the rest rely on
    modeled or imported exposure, which is smoother and less locally accurate. Segments with no
    usable exposure get `exposure_unknown` and no rate.
  - *Temporal mismatch.* The exposure source's vintage rarely matches the reporting window
    exactly; `exposure_date` exposes this gap. Big ridership changes between the two
    dates bias the rate.
  - *Mode and time-of-day aggregation.* Exposure is typically a coarse volume, not matched to
    the specific mode, hour, or direction of each report; rates are averages over that
    coarseness.
  - *Modeled-demand circularity.* If demand is modeled partly from infrastructure that also
    influences where people report, the denominator and numerator are not fully independent.
    This is disclosed where it applies.
- **What this means for the numbers.** Rates are **estimates with intervals**, computed with a
  count model appropriate to the data and a small-count interval method for sparse segments
  (`ci_method`). A segment is never ranked above another on a difference the interval does not
  support. The exposure sensitivity of the headline findings is checked in a reproducible
  notebook, and material sensitivity is stated in the briefs.

If you change the exposure source, you change the ranking. That is expected and is why every
rate ships its denominator's identity and date.

---

## Known reporting biases (who is over- and under-represented)

The dataset is built from **voluntary, self-selected reports**, and that biases it in ways
that are named here rather than hidden. `bias.py` characterizes these by comparing the
reporter pool and the geographic spread of reports against ridership and demographic
baselines; the briefs restate the relevant ones in plain language.

- **Route-choice / "busy-route" bias.** Reports concentrate where people actually ride and
  walk. Without exposure normalization, the busiest corridors look the most dangerous. This is
  the central bias the whole rate pipeline exists to counter — but normalization only corrects
  it to the quality of the exposure estimate.
- **Reporter-pool bias (who reports).** People who file near-miss reports skew toward
  confident, regular, English-comfortable, smartphone-carrying riders who know the project
  exists. Occasional riders, children, people walking, people without app access, and people
  who already avoid dangerous streets entirely are under-represented.
- **App-access and digital-divide bias.** A report requires a device, connectivity, and the
  awareness to submit. Lower-income and less-connected areas are likely under-reported even
  where risk is high.
- **Language bias.** Where the form is not available in a community's language, that community
  is under-represented. Form-language coverage is uneven across deployments.
- **Demographic and geographic skew.** Reports may over-represent areas and groups with more
  advocacy presence and under-represent others; `bias.py` reports the direction where a
  baseline exists.
- **Survivorship / avoidance bias.** The most dangerous segments may show *few* reports
  because few people will ride or walk them at all. Low report volume is not safety.
- **Salience and severity bias.** Dramatic events (a close pass at speed) are more likely to be
  reported than mundane chronic hazards; report mix is not an unbiased sample of all hazards.
- **Temporal and campaign bias.** A local campaign, a news story, or a crash can cause a
  reporting spike that is about attention, not a change in danger.

**Net effect:** treat the dataset as a biased sample of *reported* near misses, partially
corrected for traffic by exposure, with residual bias that cannot be fully removed. Findings
that could be artifacts of who reports are labeled as such in the outputs.

---

## Privacy: aggregation and minimum occupancy

Contributor privacy is a hard rule, and the published dataset is engineered around it.

- **Pseudonymous reports.** Reports carry an opaque contributor token, not an identity. The
  token is **not** published.
- **Aggregation to public street segments.** Publication aggregates reports to public street
  segments. The published geometry is the real public street centerline (public
  infrastructure) — **not** a perturbed point and **not** a report location. No per-report
  coordinate is published.
- **No per-report timestamp.** No per-report timestamp is published; only the aggregation
  window (`period_start`/`period_end`) appears.
- **k-anonymity / minimum occupancy.** Any segment with a non-zero report count below
  `min_publish_n` (default 3) is **withheld entirely** from the published GeoJSON, the data
  card sidecar metadata, and the briefs. No published place can mean "one or two people
  reported an incident here." This is enforced in `publish.py` by `assert_published_clean`
  (which raises) and `assert_metadata_clean`, and is covered by the test suite.
- **Small-sample suppression.** Hazard-type breakdowns for segments with a count below
  `small_n` are suppressed (emitted as `{}`), and `small_n` is flagged.
- **What is deliberately withheld.** Per-report coordinates; any per-report timestamp; the
  free-text note; contributor token/identity; mode, severity, and heading; route and home-end
  detail; and any combination that could re-identify an individual. Publication is enforced by
  an allowlist in `publish._feature` and a denylist invariant in `assert_published_clean()`,
  with `assert_metadata_clean()` covering the sidecar metadata. The KDE report-intensity peak
  is published only as a segment id, never a coordinate.
- **The raw store is private.** Precise reports live only in `data/raw/`, which is gitignored
  and never committed, deployed, or served. The dev server (`server.py` / `nearmiss serve`) is
  read-only (GET/HEAD) and refuses any request under `data/raw/` or any dotfile path with HTTP
  403, even when launched on the repo root.
- **Residual risk.** Aggregation and withholding reduce but do not erase re-identification
  risk: a repeat contributor reporting across multiple segments could still be linked across
  those segments. This residual risk remains and is not claimed away.

These are publishing-rule and threat-model protections, not license restrictions — the data
itself is meant to be free, so the privacy lives in *what* is published, not in legal terms.
See `docs/THREAT-MODEL.md` for the full analysis.

---

## Recommended uses

This dataset is built for, and holds up under, uses like:

- **Safe-streets advocacy** — pointing at exposure-normalized, interval-bearing risk rates and
  statistically significant Getis-Ord Gi\* hotspots when asking a city to fix specific
  corridors, with the bias caveats stated.
- **Corroborating official collision data** — overlaying reported near misses on collision and
  exposure layers to surface near-miss-heavy, collision-light segments (the "lucky so far"
  problem).
- **Prioritization with uncertainty** — ranking candidate locations for intervention while
  respecting the confidence intervals and the `confidence_label`, not over-reading sparse
  segments.
- **Research and journalism** — reusing the open GeoJSON, the schema, and the reproducible
  notebooks, with the documented biases and exposure assumptions cited.
- **Method reuse** — adopting the schema and the exposure-normalization/hotspot code for other
  point-hazard datasets.

Always cite the exposure source and date, the interval, and the `n` alongside any rate, and
carry the reporting-bias statement into your own work.

## Out-of-scope and discouraged uses

Do **not** use this dataset for the following. These are not edge cases; they are the standard
ways this kind of data is misused.

- **Do not treat it as a census or an unbiased sample.** It is a voluntary, self-selected,
  biased sample of *reported* near misses, not a complete record of hazards or of risk.
- **Do not rank or target individual addresses, homes, or people.** The data is aggregated to
  public street segments on purpose, and no per-report coordinate is published; using it to
  infer a person's routine, identity, residence, or movements is a misuse and is defeated by
  the published precision.
- **Do not read raw report volume as danger.** The report-volume layer is labeled report
  volume. Mapping raw counts as "where it's dangerous" reproduces exactly the lie this project
  exists to refuse. Use the rate layer.
- **Do not rank sparse segments as if they were certain.** Respect the intervals and the
  `confidence_label`. A segment marked `uncertain` or `exposure_unknown` cannot be placed
  confidently above or below another.
- **Do not treat it as a 311 queue or expect a response.** Submitting or citing a report does
  not dispatch repairs, enforcement, or emergency response. For an active hazard or emergency,
  contact the responsible authority directly.
- **Do not use it for enforcement, surveillance, insurance, or punitive action against
  individuals.** The dataset is not designed or licensed-in-spirit for adverse action against
  people; its de-identification makes such use both wrong and unreliable.
- **Do not compare across cities or sources without accounting for different exposure sources
  and reporting cultures.** Denominators and reporter pools differ; cross-deployment
  comparison requires explicit care.
- **Do not strip the caveats.** Publishing a rate, ranking, or map from this data without its
  interval, `n`, exposure source/date, and bias statement misrepresents it.

---

## Maintenance and updates

- **Maintainer.** Chelsea Kelly-Reif ([@ChelseaKR](https://github.com/ChelseaKR)); contact via
  the repository's GitHub issues. Single maintainer; no other contributors at this time.
- **Update cadence.** The published dataset is regenerated on scheduled rebuilds as new reports
  accumulate and on each release. There is no service-level guarantee on freshness; the live
  window and the build date are always recorded in the data card sidecar. As an independent,
  zero-cost, volunteer project, update frequency is best-effort, not contractual.
- **Reproducibility.** The dataset is fully reproducible from raw inputs: `make reproduce`
  regenerates every published figure, table, and GeoJSON deterministically (seeded pipelines and
  analyses). `make verify` reproduces the full CI gate (lint, types, tests including
  planted-hotspot fixtures, accessibility, security).
- **Versioning and stability.** Releases follow semver. The published GeoJSON schema is
  versioned with a deprecation policy and migrations; schema changes are recorded in the
  CHANGELOG and ADRs. Published artifacts are content-hashed so tampering or drift is detectable.
- **Errata and corrections.** Data and threshold fixes are made as recorded, re-run edits;
  corrections ship in a new versioned release rather than mutating a published one.
- **Deprecation.** Superseded dataset versions remain identifiable by version and hash; consumers
  should pin the version they cite.

---

## License and citation

### License

The nearmiss code, schema, pipeline, notebooks, and published dataset are released under the
**Apache License 2.0**. Apache-2.0 is chosen so the dataset and the methods spread as widely as
possible: its patent grant and permissive terms let other advocates, researchers, and
cooperative city staff adopt the schema, reuse the statistics code, and build on the open data
without friction. Privacy is enforced by the publishing rules and threat model, **not** by a
restrictive license — the data is meant to be free.

**Third-party exposure sources** (count programs, demand models, exposure layers) used as
denominators retain their own licenses and terms; consult `exposure_source` /
`exposure_date` and the data card sidecar before redistributing derived exposure values.

### How to cite

Cite the dataset with its version, the access date, and the repository. Suggested form:

```text
Kelly-Reif, C. nearmiss: an open dataset and statistically honest analysis of road hazards
and near misses for safe-streets advocacy [data set]. Version <vX.Y.Z>. Apache-2.0.
github.com/ChelseaKR/nearmiss (accessed <YYYY-MM-DD>).
```

When you cite a specific rate, ranking, or hotspot, also report the exposure source and date,
the confidence interval, the `n`, and the reporting-bias caveat — that is the honest unit of
this dataset, and a number from here without them is not this dataset's claim.

### See also

- `schema/report.schema.json` — intake (private) report schema.
- `schema/dataset.schema.md` — published GeoJSON schema (authoritative field reference).
- `docs/METHODOLOGY.md` — full statistical methodology (rates, intervals, KDE, Getis-Ord Gi\*).
- `docs/THREAT-MODEL.md` — privacy threat model and the basis for the withheld-precision rules.
- `data/published/datacard.json` — per-release machine-readable card (versions, hashes, sources,
  windows, totals).
