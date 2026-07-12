# Published dataset schema (open GeoJSON)

**Schema name:** `nearmiss.published.dataset`
**Schema version:** 1.1.0 (semantic; see [Versioning and deprecation](#versioning-and-deprecation-policy))
**Artifact:** `data/published/<city-slug>.geojson` (e.g. `davis.geojson`), with a sidecar
`data/published/<city-slug>.metadata.json` (e.g. `davis.metadata.json`) and the data card at
[`docs/DATA-CARD.md`](../docs/DATA-CARD.md)
**CRS:** WGS84 (EPSG:4326), longitude/latitude decimal degrees, per RFC 7946
**Last reviewed:** 2026-07-07
**Maintainer:** Chelsea Kelly-Reif (GitHub [@ChelseaKR](https://github.com/ChelseaKR))

This document is the contract for the **published, open** dataset that `publish.py` emits — the
aggregated GeoJSON that the accessible map (`server.py`) and the briefs (`brief.py`) read,
and that anyone may mirror, fork, load in QGIS or Leaflet, and redistribute under Apache-2.0. It is a
different artifact from the **intake** contract in
[`report.schema.json`](report.schema.json): that schema accepts a single precise raw report; this one
describes the analyzed, exposure-normalized, privacy-protected result that is safe to make public.

Two files are written per city, both slugged from the city name. The GeoJSON
(`<city-slug>.geojson`, e.g. `davis.geojson`) is the open dataset and carries a self-describing
top-level [`metadata`](#2-top-level-structure) foreign member. The sidecar
(`<city-slug>.metadata.json`, e.g. `davis.metadata.json`) carries the content hash (`geojson_sha256`)
and the full methods and summary; it is the integrity manifest for the GeoJSON. The plain-language
[data card](../docs/DATA-CARD.md) lives at `docs/DATA-CARD.md`.

A third, optional file, `<city-slug>.calibration.json`, is written by `nearmiss analyze --calibrate`
(`src/nearmiss/stats/calibration.py`; see `docs/METHODOLOGY.md` §9.4). It is a per-dataset
null-calibration artifact: the empirical false-positive rate of the hotspot method, measured by
label-shuffling this city's own report counts with exposure and geometry held fixed. It carries only
aggregate statistics (shuffle count, seed, segments tested, mean/max false positives, the resulting
rate) — never a per-shuffle or per-segment listing — and is absent for a city until `--calibrate` has
been run for it.

It is written to the same standard as the rest of the project: it should hold up when a skeptical
traffic engineer pushes back. Every property that carries a risk claim is defined so that the
[five hard rules](../README.md#hard-rules-enforced-not-aspirational) (referenced below as
**HR1**–**HR5**) are visible in the data itself, not just promised in prose.

- **HR1** — No rate without a denominator. Every rate carries its `exposure_estimate`,
  `exposure_source`, `exposure_date`, and `exposure_tier`. A raw count is labeled `report_count`,
  never danger.
- **HR2** — No estimate without an interval. Every `rate` carries `rate_ci_low`, `rate_ci_high`,
  and `n`. Small-sample features are marked uncertain, not ranked as certain.
- **HR3** — Reporting bias is named, not hidden. Per-feature `quality_flags` and the dataset-level
  caveats in `metadata.privacy`/`metadata.significance` surface who and where is over- or
  under-represented; the data card carries the full bias account.
- **HR4** — Contributor privacy is protected. This artifact is aggregated to public street segments. It
  contains **no raw precise reports**, no reporter token, no per-report timestamps, and no per-report
  coordinates. See [Privacy: aggregation and minimum occupancy](#privacy-aggregation-and-minimum-occupancy).
- **HR5** — Open and reproducible end to end. This file, its schema, the pipeline, and the notebooks
  are open; `make reproduce` regenerates it from raw inputs and a hashed manifest pins what was built.

---

## 1. Alignment to a documented near-miss / collision standard

The published dataset is GeoJSON per **RFC 7946**, so it loads in any GIS without a custom reader. On
top of GeoJSON it aligns its feature semantics to documented road-safety data conventions so that a
consumer who already works with collision and near-miss data can map our fields onto theirs:

- **Geometry and CRS** follow **RFC 7946**: WGS84 (EPSG:4326), coordinate order longitude, latitude,
  and a single CRS for the whole file (no per-feature CRS). Linear features are `LineString`; point
  features are `Point`. See [Geometry](#3-feature-geometry).
- **Mode and conflict taxonomy** are aligned to the **MMUCC**-style separation of *roadway user mode*
  (cyclist, pedestrian, and other vulnerable-road-user modes) from *manner of conflict* (the hazard
  type). Our `hazard_breakdown` keys are the same closed vocabulary the intake schema enumerates
  (`close_pass`, `dooring`, `surface_hazard`, `sightline`, `signal`, `debris`, `other`), so a feature's
  conflict mix is interpretable without our code.
- **Severity framing** follows the **near-miss vs. collision** distinction used in safe-systems and
  Vision-Zero reporting: this dataset is dominated by *near misses*, which by definition leave no
  police report, and it says so. Severity here is **self-reported** and is documented as such; it is
  never presented as a verified injury or **KABCO**-coded crash statistic. The dataset card states this
  limit explicitly, and `severity` is not republished per-report — only aggregated counts appear (see
  `quality_flags` and the data card).
- **Linear referencing.** Where a feature is a street segment, its `segment_id` is the project's
  snap-to-segment identifier (stable across releases for the same underlying geometry). The data card
  records which base network the segments came from and its date, so a consumer can join to that network
  the way a linear-referencing system (route + measure) would.

The full alignment table — our field → the standard's field/concept → notes — lives in the data card
([`docs/DATA-CARD.md`](../docs/DATA-CARD.md)) under "Schema crosswalk," because the crosswalk is
versioned with the data it describes. This document defines the fields; the data card maps them to
external standards and states the sources and dates.

---

## 2. Top-level structure

The published GeoJSON (`<city-slug>.geojson`) is a single `FeatureCollection` with three top-level
members: `type`, `features`, and a `metadata` foreign member (permitted by RFC 7946) so that a consumer
reading only the file still gets the version, the license, the exposure unit, and the privacy/significance
parameters that govern interpretation.

```jsonc
{
  "type": "FeatureCollection",
  "metadata": {
    "schema_version": "1.1.0",
    "dataset_version": "0.1.1",
    "city": "Davis",
    "license": "Apache-2.0",
    "dataset_note": "Synthetic demonstration data — not real reports.",
    "exposure_unit": "bike trips (synthetic)",
    "schema_doc": "schema/dataset.schema.md",
    "data_card": "docs/DATA-CARD.md",
    "segments_published": 9,
    "segments_withheld_low_count": 3,
    "significance": "Getis-Ord Gi* on the exposure-normalized rate, Benjamini-Hochberg FDR",
    "privacy": "Aggregated to public street segments; low-count segments withheld (k-anonymity); no per-report coordinate, time, reporter, mode, or severity is published."
  },
  "features": [ /* Feature objects, defined below */ ]
}
```

The embedded `metadata` member is descriptive, not a place to hide a claim. Its fields:

| Field | Type | Description |
|---|---|---|
| `schema_version` | string | The version of **this** published-dataset schema the file conforms to (`MAJOR.MINOR.PATCH`). See [Versioning](#versioning-and-deprecation-policy). |
| `dataset_version` | string | The version of the **data** (the city release), independent of the schema version. |
| `city` | string | The city name (human-readable, e.g. `"Davis"`). The file itself is named from its slug (`davis.geojson`). |
| `license` | string | The license the dataset is published under (`"Apache-2.0"`). |
| `dataset_note` | string \| null | A provenance / demo label from config (e.g. a synthetic-demonstration marker). `null` when no note is configured. |
| `exposure_unit` | string | The human-readable denominator unit (from config `exposure_unit`, e.g. `"bike trips"`) the rates are expressed against; also shown in the brief. |
| `schema_doc` | string | Repo-relative path to this schema document. |
| `schema_json` | string | Repo-relative path to the machine-checkable JSON Schema ([`schema/dataset.schema.json`](dataset.schema.json)) that this document mirrors; the published GeoJSON is validated against it in CI (see [Versioning](#versioning-and-deprecation-policy)). |
| `data_card` | string | Repo-relative path to the data card (`docs/DATA-CARD.md`). |
| `segments_published` | integer | Count of features actually published in this file. |
| `segments_withheld_low_count` | integer | Count of segments withheld entirely under the minimum-occupancy floor (k-anonymity). See [Privacy](#5-privacy-aggregation-and-minimum-occupancy-hr4). |
| `significance` | string | One-line statement of the significance method: Getis-Ord Gi\* on the exposure-normalized rate with a Benjamini-Hochberg FDR correction. |
| `privacy` | string | One-line statement of the aggregation and withholding privacy controls (**HR4**). |

Anything that affects how a rate should be read is mirrored, in full, in the data card.

> **The content hash lives in the sidecar, not the embedded member.** The GeoJSON cannot carry its own
> SHA-256 without being self-referential, so the hash is written to the sidecar
> `<city-slug>.metadata.json` (e.g. `davis.metadata.json`) as `geojson_sha256`, alongside the full
> `methods` and `summary`. The sidecar is the integrity manifest: a reproduction from raw whose canonical
> GeoJSON does not hash to the recorded `geojson_sha256` is evidence of tampering or drift (**HR5**). The
> sidecar's top-level fields are `city`, `version`, `schema_version`, `dataset_note`, `license`, `schema`,
> `schema_json`, `data_card`, `methods` (the rate denominator, confidence level, small-n and min-publish-n thresholds,
> the FDR level, the Getis-Ord band and KDE bandwidth, the significance statement, and a `rate_definition`
labeling the top-level `rate` as the pooled union across all hazard types with per-type rates in
`rates_by_type`), `summary`
> (segment and report counts, `exposure_coverage`, and `excluded_low_confidence_fraction` — the share of
> snapped reports excluded from the primary rate for low confidence), `report_intensity_peak_segment` (the KDE peak as a
> **segment id only**, never a coordinate), `geojson_sha256`, and a `privacy` note. The sidecar is held to
> the same privacy invariant as the GeoJSON: `assert_metadata_clean()` raises if any forbidden key or raw
> coordinate appears in it.

---

## 3. Feature geometry

Each entry in `features` is a GeoJSON `Feature` with a `geometry` and a `properties` object.

| Geometry type | When used | Privacy note |
|---|---|---|
| `LineString` | A street segment (the default aggregation unit). Coordinates trace the real public street centerline from the base network. | The segment is a *place*, not a person; the published geometry is public infrastructure, and sub-segment precision was already discarded at snap time in the pipeline. |
| `Point` | A coarse aggregation cell or a node-like feature (e.g. an intersection approach) where a segment is not the right unit. | The point is the **public aggregation-unit representative** (the cell's representative point), not a report location. There is **no jitter** and **no raw report coordinate**. See [Privacy: aggregation and minimum occupancy](#privacy-aggregation-and-minimum-occupancy). |

Geometry is WGS84 (EPSG:4326), `[longitude, latitude]` order, RFC 7946. No feature carries a raw or
per-report coordinate. For `Point` features the coordinate is the public aggregation-unit
representative (the cell's representative point) — it is not jittered and is not a report location. For
`LineString` features the geometry is the real public base-network street centerline, which is
independent of where within the segment any report fell. There is exactly one geometry per feature and
one CRS for the file.

---

## 4. Feature properties

Every property below appears under the Feature's `properties` object. Types are JSON types. "Nullable"
means the value may be `null` when honestly unknown — a deliberate choice over omitting the key or
inventing a number, so that "unknown" is a first-class, machine-readable state (**HR1**, degradability).

### 4.1 Identity and volume

| Property | Type | Nullable | Description |
|---|---|---|---|
| `segment_id` | string | no | Stable identifier for the aggregation unit (street segment or cell). Stable across releases for the same underlying geometry, so a consumer can join releases over time. Not derived from any contributor identity. For `Point`/cell features this is the cell id. |
| `name` | string | no | Human-readable street-block name for the segment (e.g. `"5th St (C–D)"`), carried from the base network so the map, the table, and the brief can label a place without exposing a coordinate. Real Davis street-block names replace the earlier `"Street seg-NN"` placeholders. |
| `report_count` | integer ≥ 0 | no | **Raw count of reports** aggregated into this feature after dedupe and quality-flagging. This is *report volume*, not danger (**HR1**): it confounds hazard with how many people travel and choose to report here. It is published so consumers can see the basis of the rate and the sample size, and it is the field a "report volume" map must use — never as a standalone risk surface. |

### 4.2 Exposure / the denominator (HR1)

A rate is meaningless without the denominator it was computed against, and the denominator is only
honest if its provenance — including how much to trust it — travels with it. All five exposure fields
move together.

| Property | Type | Nullable | Description |
|---|---|---|---|
| `exposure_estimate` | number > 0 | yes | The exposure denominator attached to this feature by `exposure.py`: an estimate of travel volume / opportunity for a hazard, in the unit named by `exposure_source` (e.g. annual bike+ped trips, or person-km on the segment). `null` means **exposure unknown** for this feature; when `null`, `rate`, `rate_ci_low`, and `rate_ci_high` are also `null` and the feature is labeled "exposure unknown" rather than rated (degradability — a segment is never silently dropped or falsely rated). An estimate at or below the configured **exposure floor** (METHODOLOGY §3.3) is treated the same as `null` — rates blow up as exposure approaches zero, so a floor-violating segment is published "exposure unknown" rather than a giant, meaningless rate. |
| `exposure_source` | string | yes | Identifier of the exposure source used for this feature (e.g. `city-bike-ped-counts-2024`, `demand-model-v2`, `streetlight-import-2025q1`). Sources are the same versioned identifiers used in the checked-in config; a swap or a stale layer is therefore visible per-feature, not silent. `null` only when `exposure_estimate` is `null`. |
| `exposure_date` | string (ISO-8601 date) | yes | The date (or vintage) of the exposure data used, so a consumer can see how current the denominator is. `null` only when `exposure_estimate` is `null`. |
| `exposure_tier` | string | no | The trust tier of `exposure_estimate` (METHODOLOGY §3.1), one of `"observed"` (a direct count station or manual count), `"modeled"` (a demand model, ideally calibrated against observed counts), `"proxy"` (a third-party activity layer, e.g. a fitness-app heatmap, used only when nothing better exists and carrying real representativeness caveats), or `"unknown"` (no tier recorded — the honest default for exposure rows written before this field existed; never silently promoted to `"observed"`). A rate on an `"observed"` denominator and a rate on a `"proxy"` denominator are different measurements and should never be compared as equals. |
| `exposure_disagreement` | number in [0, 1] | yes | Published only when the segment's exposure was corroborated by two or more sources (see below). `1 - min(estimate) / max(estimate)` across all corroborating readings: `0` is perfect agreement, values near `1` flag a large cross-source disagreement — itself a finding (METHODOLOGY §3.1), surfaced rather than averaged away into a false consensus. `null` when the segment has only a single exposure reading (nothing to corroborate). |

> A feature may use a different exposure source from its neighbors (e.g. a counted corridor next to a
> modeled side street). That is why the source, date, and tier are **per-feature**, not only in
> `metadata`. The data card discusses the implications of mixing sources.

**Corroboration (multi-source exposure).** A segment's exposure may be backed by more than one
reading — for example a count station and a demand model both covering the same block. When it is,
`exposure_disagreement` reports how well they agree, computed by `nearmiss.exposure.corroboration`.
`exposure_estimate`/`exposure_source`/`exposure_date`/`exposure_tier` always describe the single
**primary** reading actually used for `rate`; the additional corroborating readings are not
separately published (they carry no report-level detail, only another aggregate estimate), but their
disagreement with the primary is. A high `exposure_disagreement` is a caveat on the rate, not a
reason to distrust `rate` outright — it means the *denominator* is contested, and the interval and
tier should be read accordingly.

The exposure layer joins to the street network by **exact `segment_id`**. A *total* mismatch (no
exposure id matches any street id — almost always two id schemes wired together by mistake) is a hard
error that stops the build with a clear message, rather than silently producing a `0%`
`exposure_coverage` that would read as "no denominators exist." A *partial* mismatch (some exposure ids
have no matching segment) warns and lists the unmatched ids; the unmatched segments are honestly carried
as `exposure_unknown` rather than dropped. The realized join fraction is recorded as
`summary.exposure_coverage` in the sidecar.

### 4.3 Rate and uncertainty (HR2)

| Property | Type | Nullable | Description |
|---|---|---|---|
| `rate` | number ≥ 0 | yes | The exposure-normalized risk estimate: reports per unit of exposure, computed by `rates.py` (`report_count` normalized by `exposure_estimate`, using a count model appropriate to the data). Units are documented in the data card and implied by `exposure_source`. **This — not `report_count` — is the danger estimate.** This is the **pooled rate across every hazard type — an explicit union** (all `report_count` reports over the exposure); per-hazard-type rates are published separately in [`rates_by_type`](#45-hazard-type-breakdown). `null` when `exposure_estimate` is `null`. |
| `rate_ci_low` | number ≥ 0 | yes | Lower bound of the confidence interval on `rate`. |
| `rate_ci_high` | number ≥ 0 | yes | Upper bound of the confidence interval on `rate`. |
| `n` | integer ≥ 0 | no | The sample size the interval is computed from (effective number of independent reports after dedupe). `n` is published alongside the interval so a consumer can judge how thin the estimate is; a small `n` with a wide interval is the honest signal that a feature must not be ranked as certain. |
| `confidence_label` | string | no | A plain-language label for how much weight a reader should put on this feature's rate: one of `"certain"`, `"uncertain"`, or `"exposure_unknown"`. It is the human-readable companion to `n`, the interval, and `quality_flags` — `"exposure_unknown"` corresponds to a `null` rate, `"uncertain"` to a small-sample or wide-interval feature, and `"certain"` to a feature with a usable denominator and adequate sample. It is conveyed as text (never color alone), so the table and brief can state confidence without a legend. |

The CI is a two-sided 95% interval by default; the **method** (e.g. an exact small-count interval for
sparse segments rather than a normal approximation) and the **confidence level** are recorded in the
data card, because the right interval method depends on the count model and changing it changes the
numbers. When `rate` is `null` (exposure unknown), `rate_ci_low` and `rate_ci_high` are `null` too; a
rate is never published without its interval, and an interval is never published without its `n`
(**HR2**). Consumers and the table view must show the interval, not just the point estimate, and must
not rank features whose intervals overlap as if the ordering were established.

### 4.4 Spatial significance (Getis-Ord Gi\*)

| Property | Type | Nullable | Description |
|---|---|---|---|
| `getis_ord_z` | number | yes | The Getis-Ord Gi\* z-score for this feature from `getis_ord.py`, computed on the **exposure-normalized rate** (not raw counts) over the spatial neighborhood. A high positive z indicates a feature whose rate, together with its neighbors', is higher than chance and spatial structure would predict — a candidate "hot because dangerous" cluster, as opposed to merely "hot because busy." `null` when the feature has no rate (exposure unknown) and is therefore excluded from the cluster statistic. |
| `getis_ord_significant` | boolean | yes | Significance flag: `true` when `getis_ord_z` clears the project's significance threshold **after multiple-comparison correction** (e.g. a false-discovery-rate adjustment across features). The threshold, the correction method, and the spatial weights definition are recorded in the data card and the config. `false` means "not a statistically significant hot or cold spot at our threshold," **not** "safe." `null` when `getis_ord_z` is `null`. |
| `rate_sensitivity_delta` | number | yes | Sensitivity of the published rate to the quality-tier split. The published `rate` is the **primary** rate — computed only from high-confidence records (records flagged `low_accuracy` or `far_snap` are excluded, per METHODOLOGY §2 step 4). This field is the signed difference (all-records rate minus primary rate, same units as `rate`) reported **only** when the all-records rate falls outside the primary rate's confidence interval — i.e. when including the excluded low-confidence reports would materially move the rate. `null` (the common case) means the two rates agree within the interval, so the exclusion did not change the published claim. |

`getis_ord_significant` is the field a map should use to mark a cluster as significant, and the
equivalent table must carry it as text — significance is conveyed in text and pattern, never by color
alone (an accessibility requirement that doubles as an honesty one). Reporting bias (`quality_flags` and
the dataset-level bias account in the data card) still applies: a statistically significant cluster can
still be an artifact of where people report, and that caveat is stated rather than overridden by the
flag (**HR3**).

### 4.5 Hazard-type breakdown

| Property | Type | Nullable | Description |
|---|---|---|---|
| `hazard_breakdown` | object | no | Counts of reports at this feature by hazard type, keyed by the closed vocabulary from the intake schema: `close_pass`, `dooring`, `surface_hazard`, `sightline`, `signal`, `debris`, `other`. Values are integers ≥ 0 and sum to `report_count`. Keys with a zero count may be present or omitted; a consumer should treat an absent key as `0`. This describes the *mix of conflict* at a place (a corridor of close passes reads differently from one of surface defects), supporting targeted advocacy without exposing any individual report. |
| `rates_by_type` | object | no | Per-hazard-type **rate layers**: keyed by the same closed hazard vocabulary as `hazard_breakdown`, each value is an object `{ "count", "rate", "rate_ci_low", "rate_ci_high" }` giving that hazard type's own exposure-normalized rate and 95% confidence interval, computed against the **same** `exposure_estimate` denominator by the same method as the top-level [`rate`](#43-rate-and-uncertainty-hr2). The top-level `rate` is the **pooled union** across all types; these are its per-type decomposition, so a consumer can ask "what is the *close-pass* rate here?" without re-deriving it. `count` is the (integer-valued) number of reports of that type and matches the corresponding `hazard_breakdown` entry. Only hazard types whose own `count` is **at or above** the small-sample threshold (`small_n`) appear; a type below the threshold is **suppressed entirely** (no key), for the same small-n uncertainty and re-identification reasons breakdowns are suppressed. Absent for a feature whose total count is below `small_n` (published as `{}`) or whose `exposure_estimate` is `null`. |

Only **aggregated counts** appear here and in `rates_by_type`. Per-report fields — the free-text note,
exact time, severity, mode at the individual level, heading, reporter token — are **not** present in the
published dataset. Where a feature's count is below the small-sample threshold (`small_n`), the
`hazard_breakdown` and `rates_by_type` are **suppressed** and published as an empty object (`{}`),
because a mix built from very few reports is both uncertain and a re-identification risk; the
`low_sample` quality flag (below) also marks such features. Within a feature that clears the threshold,
each individual hazard type in `rates_by_type` must *also* clear `small_n` on its own count, so a
place-plus-type combination is never published from a handful of reports.

### 4.6 Quality flags

| Property | Type | Nullable | Description |
|---|---|---|---|
| `quality_flags` | array of string | no | Zero or more machine-readable flags from a closed vocabulary, surfacing the caveats that govern how this feature should be read. An empty array means no flags were raised, not that the feature is unconditionally trustworthy. |

Published flag vocabulary (additive across schema minor versions; never silently repurposed). The
publication step maps the pipeline's internal flags and the sample size onto this closed, public
vocabulary, so a consumer never has to know the internal flag names:

| Flag | Meaning |
|---|---|
| `low_sample` | `report_count` is non-zero but below the project's small-sample threshold (`small_n`); the rate and any ranking are uncertain (**HR2**). Pair with the wide interval; the `hazard_breakdown` is also suppressed for such features. |
| `geocode_low_confidence` | Aggregated reports here include low-positional-accuracy or far-snap locations (the internal `low_accuracy`/`far_snap` flags); placement is less certain. Address-only reports resolved by the geocoder can also raise this when the resolved location is uncertain. |
| `exposure_unknown` | No exposure denominator was available (including a denominator at or below the configured exposure floor); `exposure_estimate`/`rate`/`rate_ci_low`/`rate_ci_high` are `null` and `confidence_label` is `"exposure_unknown"`. Shown as "exposure unknown," not rated (**HR1**, degradability). |
| `exposure_stale` | The exposure vintage (`exposure_date`) and the reports this feature's rate is built from are more than the configured threshold apart — a temporal-alignment caveat (METHODOLOGY §3.2: "a rate whose exposure was measured in a different period than its reports has a temporal mismatch"). Never set on a feature with `exposure_unknown` — a rate has to exist before its temporal alignment is meaningful. |

These four are the **published** flags emitted by `publish.py`. Flags are intentionally conservative:
it is better to over-mark a feature as uncertain than to present a thin or biased estimate as solid. The
full definitions, thresholds, and the config values behind each flag are in the data card so the
flagging is reproducible and auditable. Wider caveats that apply to the dataset as a whole — notably
reporting bias (**HR3**) — are carried in the embedded `metadata.privacy`/`metadata.significance`
statements and the data card's bias account rather than as a per-feature flag.

---

## 5. Privacy: aggregation and minimum occupancy (HR4)

Every published feature is the product of **deliberate aggregation to a public street segment** and
the **withholding of low-count segments**, and that is recorded both in the file (the embedded
`metadata.privacy` note and `metadata.segments_withheld_low_count`, plus `methods.min_publish_n` in the
sidecar) and, in plain language, in the data card. This is not lossy rounding by accident; it is a
privacy control with auditable parameters, enforced in code rather than promised in prose.

What that means concretely for a consumer of this file:

- **Aggregated to a public segment, never per-report.** Reports are aggregated onto the real public
  street centerline (public infrastructure). The published geometry is the segment itself, not a
  perturbed point and not a report location. The public unit is always a place, not a person.
- **Minimum occupancy (k-anonymity), or withheld.** Any segment whose non-zero report count is below
  `min_publish_n` (default 3) is **withheld entirely** — from the published GeoJSON, from the metadata,
  and from the brief. No published place can mean "one or two people reported an incident here." This is
  enforced by `assert_published_clean()` (which raises on violation) and covered by the test suite.
- **No jitter, no published coordinate.** There is **no coordinate fuzzing and no jitter** anywhere in
  `publish.py`. Privacy comes from aggregation onto a public segment plus withholding low-count
  segments — not from perturbing a point. No per-report coordinate is ever published.
- **No per-report timestamp.** **No per-report timestamp is published** in this artifact, and no feature
  exposes an ordered per-contributor sequence.
- **Small-sample suppression of breakdowns.** A `hazard_breakdown` for a segment with a count below the
  small-sample threshold (`small_n`) is suppressed (published as `{}`), so a thin mix cannot be read off
  a sparse segment.
- **Intensity peak as a segment id only.** The KDE report-intensity peak is published **only as a
  segment id**, never as a coordinate.
- **No identity or sensitive text.** No `reporter_token`, no free-text `note`, no per-report `severity`,
  `mode`, `heading`, or `accuracy` reaches this file. Reports are pseudonymous upstream and the linkage
  is dropped at publication. What is allowed into a published feature is fixed by an allowlist in
  `publish._feature`, and `assert_published_clean()` additionally enforces a denylist invariant (with
  `assert_metadata_clean()` covering the sidecar metadata).
- **Raw is never here.** Precise raw reports live only in the gitignored `data/raw/` private store and
  are never published or committed. Nothing in the public path (`publish.py`, `server.py`, this GeoJSON,
  the map) reads from raw. The dev server (`server.py` / `nearmiss serve`) is read-only (GET/HEAD) and
  refuses any request under `data/raw/` or any dotfile path with HTTP 403, even when launched on the
  repo root. See the [threat model](../docs/THREAT-MODEL.md), T1.

Residual risk is stated honestly in the threat model and the data card: aggregation to a public segment
plus withholding of low-count segments protect a single report well and scattered reports adequately,
but a contributor who files reports across several segments can still leak a linkage pattern. Aggregation
and withholding reduce that risk; they do not erase it. That limitation is named, not hidden.

---

## 6. A worked example feature

```jsonc
{
  "type": "Feature",
  "geometry": {
    "type": "LineString",
    "coordinates": [[-121.741, 38.5449], [-121.7395, 38.5461]]
  },
  "properties": {
    "segment_id": "seg-davis-00417",
    "name": "5th St (C–D)",
    "report_count": 12,
    "n": 12,
    "exposure_estimate": 184000,
    "exposure_source": "city-bike-ped-counts-2024",
    "exposure_date": "2024-09-30",
    "exposure_tier": "observed",
    "exposure_disagreement": null,
    "rate": 6.52e-05,
    "rate_ci_low": 3.37e-05,
    "rate_ci_high": 1.14e-04,
    "getis_ord_z": 2.91,
    "getis_ord_significant": true,
    "confidence_label": "certain",
    "hazard_breakdown": {
      "close_pass": 7,
      "dooring": 3,
      "surface_hazard": 2
    },
    "rates_by_type": {
      "close_pass": {
        "count": 7,
        "rate": 3.8e-05,
        "rate_ci_low": 1.52e-05,
        "rate_ci_high": 7.84e-05
      }
    },
    "quality_flags": []
  }
}
```

How to read it honestly: `report_count` (12) is *volume*; the danger estimate is `rate` with its
interval (`rate_ci_low`..`rate_ci_high`), computed against an `"observed"`-tier 2024 count denominator
— the most trusted class (METHODOLOGY §3.1). `exposure_disagreement` is `null` because this segment has
only the one reading; there is nothing to corroborate it against. The Gi\* flag
(`getis_ord_significant: true`) marks a statistically significant cluster — but the dataset-level bias
account still applies, so the cluster should be read with the caveat that this corridor may be
over-represented by commuter reporters, exactly as the brief and data card state it. An empty
`quality_flags` array means no per-feature caveat was raised, **not** that the feature is unconditionally
trustworthy. The top-level `rate` is the **pooled union** of all 12 reports; `rates_by_type` decomposes
it, here publishing only `close_pass` (7 reports) because `dooring` (3) and `surface_hazard` (2) each
fall below `small_n` and are suppressed — so a place-plus-type rate is never built from a handful of
reports.

A segment corroborated by a second, disagreeing source carries that disagreement, not a false consensus:

```jsonc
{
  "type": "Feature",
  "geometry": { "type": "LineString", "coordinates": [[-117.396, 33.953], [-117.395, 33.954]] },
  "properties": {
    "segment_id": "seg-riverside-00042",
    "name": "Main St (5th–6th)",
    "report_count": 3,
    "n": 3,
    "exposure_estimate": 1500,
    "exposure_source": "count-station-12",
    "exposure_date": "2026-05-01",
    "exposure_tier": "observed",
    "exposure_disagreement": 0.2,
    "rate": 2.0,
    "rate_ci_low": 0.41,
    "rate_ci_high": 5.85,
    "getis_ord_z": -0.98,
    "getis_ord_significant": false,
    "confidence_label": "uncertain",
    "hazard_breakdown": {},
    "quality_flags": []
  }
}
```

`rate` here is computed against the `"observed"` primary reading (1500), same as any single-source
feature — corroboration does not change the rate. But a demand model covering the same block estimated
only 1200, a 20% disagreement (`exposure_disagreement: 0.2`), which METHODOLOGY §3.1 calls "itself a
finding": the count and the model disagree on how busy this block is, and a reader deciding how much to
trust `rate` should know that, not just the interval.

A feature with no usable denominator looks different and says so:

```jsonc
{
  "type": "Feature",
  "geometry": { "type": "LineString", "coordinates": [[-121.760, 38.551], [-121.759, 38.552]] },
  "properties": {
    "segment_id": "seg-davis-01188",
    "name": "C St (3rd–4th)",
    "report_count": 4,
    "n": 4,
    "exposure_estimate": null,
    "exposure_source": null,
    "exposure_date": null,
    "exposure_tier": "unknown",
    "exposure_disagreement": null,
    "rate": null,
    "rate_ci_low": null,
    "rate_ci_high": null,
    "getis_ord_z": null,
    "getis_ord_significant": null,
    "confidence_label": "exposure_unknown",
    "hazard_breakdown": {},
    "rates_by_type": {},
    "quality_flags": ["exposure_unknown", "low_sample"]
  }
}
```

---

## 7. Versioning and deprecation policy

The published schema is versioned with **semantic versioning** (`MAJOR.MINOR.PATCH`), carried in
`metadata.schema_version` in every file and in this document's header. It is versioned **independently**
of the intake `report.schema.json` version, because the two contracts evolve on different schedules.

What each bump means for this published artifact:

- **PATCH** — clarifications, documentation fixes, additional examples, or non-semantic corrections that
  do not change the shape or meaning of any field. No consumer action needed.
- **MINOR** — **backward-compatible additions**: a new optional property, a new `quality_flags` value, a
  new `exposure_source` identifier, or a new permitted `hazard_breakdown` key. Existing properties keep
  their names, types, and meaning. A consumer written for an earlier `1.x` keeps working; it should
  ignore properties and flag values it does not recognize. Flag and hazard vocabularies are **additive**
  — values are never silently repurposed.
- **MAJOR** — a **breaking change**: removing or renaming a property, changing a type or unit, changing
  the meaning of an existing field, changing the default CI level or the significance/correction method
  in a way that alters published numbers' interpretation, or changing the geometry/CRS conventions.

**Deprecation policy.** Breaking changes are not made silently or abruptly:

1. A field slated for removal or change is marked **deprecated** in this document and in the data card,
   with the target removal version and the migration path stated, at least **one MINOR release** before
   the breaking MAJOR release. Where feasible, the deprecated field is retained alongside its replacement
   during the deprecation window so consumers can migrate without a flag day.
2. Every change is recorded in the repository **CHANGELOG** under the schema heading, with the version,
   date, and rationale, following conventional commits. The threat model and data card are reviewed when
   the schema changes (they list "schema change" as a trigger).
3. Releases are **signed**, and each published file pins `metadata.schema_version` in the GeoJSON while
   its sidecar (`<city-slug>.metadata.json`) pins `geojson_sha256`, so a consumer can always tell exactly
   which schema version and which build a file conforms to and verify it was not altered after the fact
   (**HR5**).
4. `$schema`/machine-validation: the published GeoJSON is validated in CI against the JSON Schema
   [`schema/dataset.schema.json`](dataset.schema.json), which mirrors this document; that validator is
   versioned in lockstep (`const` `schema_version` `1.1.0`) and is the authoritative, machine-checkable
   form of this contract. `publish.py` runs the same validation before writing any file, so a build that
   would violate the contract fails instead of shipping.

Older published files are not rewritten in place when the schema advances; each release is an immutable,
hashed artifact at its own version. A consumer pins to a `MAJOR` line, reads `metadata.schema_version` to
confirm, and treats unknown additive content as ignorable.

---

## 8. What is guaranteed to be absent

To make **HR4** checkable rather than merely promised, the following are guaranteed **never** to appear
in this artifact. The guarantee is enforced in code: `publish._feature` writes only allowlisted fields,
`assert_published_clean()` enforces a denylist invariant and the minimum-occupancy rule (and raises on
violation), and `assert_metadata_clean()` covers the sidecar metadata — all covered by the test suite.

- Raw or per-report coordinates of any kind. The only geometry published is a public street segment
  centerline or a public aggregation-cell representative point — no jitter, no report location.
- Per-report records of any kind — every value is an aggregate, and any segment below `min_publish_n`
  reports is withheld entirely.
- `reporter_token`, account ids, emails, device identifiers, or any field reversible to a person.
- Free-text `note` content (never republished verbatim).
- Per-report `occurred_at` timestamps (no per-report timestamp is published), per-report `severity`,
  `mode`, `heading_deg`, or `accuracy_m`.
- Any ordered per-contributor sequence of reports.

If you find any of the above in a published `nearmiss` dataset, treat it as a privacy defect and report
it through the channel in [`SECURITY.md`](../SECURITY.md); it is a build that should never have shipped.

---

## References

- [`schema/report.schema.json`](report.schema.json) — the intake contract for a single precise report.
- [`README.md`](../README.md) — project overview and the five hard rules.
- [`docs/THREAT-MODEL.md`](../docs/THREAT-MODEL.md) — assets, adversaries, and the privacy/integrity
  controls this schema implements (notably T1, T2, T3).
- [`docs/DATA-CARD.md`](../docs/DATA-CARD.md) — sources, methods, limits, the bias account, the schema
  crosswalk to external standards, and the exact CI method, significance threshold, and flag thresholds.
- RFC 7946 (The GeoJSON Format); WGS84 / EPSG:4326; MMUCC and KABCO are referenced for taxonomy and
  severity framing only — this dataset does not claim to be a police-coded crash dataset.
