# Published dataset schema (open GeoJSON)

**Schema name:** `nearmiss.published.dataset`
**Schema version:** 1.0.0 (semantic; see [Versioning and deprecation](#versioning-and-deprecation-policy))
**Artifact:** `data/published/nearmiss.geojson` (plus a hashed manifest and the data card)
**CRS:** WGS84 (EPSG:4326), longitude/latitude decimal degrees, per RFC 7946
**Last reviewed:** 2026-06-16
**Maintainer:** Chelsea Kelly-Reif (GitHub [@ChelseaKR](https://github.com/ChelseaKR))

This document is the contract for the **published, open** dataset that `publish.py` emits — the
aggregated GeoJSON that the accessible map (`server.py`) and the briefs (`brief.py`) read,
and that anyone may mirror, fork, load in QGIS or Leaflet, and redistribute under Apache-2.0. It is a
different artifact from the **intake** contract in
[`report.schema.json`](report.schema.json): that schema accepts a single precise raw report; this one
describes the analyzed, exposure-normalized, privacy-protected result that is safe to make public.

It is written to the same standard as the rest of the project: it should hold up when a skeptical
traffic engineer pushes back. Every property that carries a risk claim is defined so that the
[five hard rules](../README.md#hard-rules-enforced-not-aspirational) (referenced below as
**HR1**–**HR5**) are visible in the data itself, not just promised in prose.

- **HR1** — No rate without a denominator. Every rate carries its `exposure_estimate`,
  `exposure_source`, and `exposure_date`. A raw count is labeled `report_count`, never danger.
- **HR2** — No estimate without an interval. Every `rate` carries `rate_ci_low`, `rate_ci_high`,
  and `n`. Small-sample features are marked uncertain, not ranked as certain.
- **HR3** — Reporting bias is named, not hidden. The dataset-level bias statement and per-feature
  `quality_flags` surface who and where is over- or under-represented; the data card carries the full
  account.
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
(`data/published/DATA-CARD.md`) under "Schema crosswalk," because the crosswalk is versioned with the
data it describes. This document defines the fields; the data card maps them to external standards and
states the sources and dates.

---

## 2. Top-level structure

The artifact is a single GeoJSON `FeatureCollection`. Project-level metadata is carried in a top-level
`metadata` member (permitted by RFC 7946 as a foreign member) so that a consumer reading only the file
still gets the version, the build provenance, and the privacy parameters that govern interpretation.

```jsonc
{
  "type": "FeatureCollection",
  "metadata": {
    "schema_name": "nearmiss.published.dataset",
    "schema_version": "1.0.0",
    "generated_at": "2026-06-16T00:00:00Z",
    "city": "davis-ca",
    "report_window": { "start": "2025-01-01", "end": "2026-05-31" },
    "aggregation": {
      "unit": "street_segment",
      "min_reports_per_feature": 3
    },
    "exposure_default_source": "city-bike-ped-counts-2024",
    "bias_statement": "Reporters over-represent commute corridors and app-using cyclists; quiet residential and non-English-speaking areas are under-represented. See DATA-CARD.md §Bias.",
    "data_card": "DATA-CARD.md",
    "license": "Apache-2.0",
    "content_hash": "sha256:…",
    "rng_seed": 20260616
  },
  "features": [ /* Feature objects, defined below */ ]
}
```

`metadata` is descriptive, not a place to hide a claim: anything that affects how a rate should be read
(the default exposure source, the aggregation unit, the minimum reports per published feature, the bias
statement) is here and is repeated, in full, in the data card. `content_hash` and `rng_seed` make the
file reproducible and
its integrity checkable (**HR5**); a reproduction from raw that does not match the hash is evidence of
tampering or drift.

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
| `report_count` | integer ≥ 0 | no | **Raw count of reports** aggregated into this feature after dedupe and quality-flagging. This is *report volume*, not danger (**HR1**): it confounds hazard with how many people travel and choose to report here. It is published so consumers can see the basis of the rate and the sample size, and it is the field a "report volume" map must use — never as a standalone risk surface. |

### 4.2 Exposure / the denominator (HR1)

A rate is meaningless without the denominator it was computed against, and the denominator is only
honest if its provenance travels with it. All three exposure fields move together.

| Property | Type | Nullable | Description |
|---|---|---|---|
| `exposure_estimate` | number > 0 | yes | The exposure denominator attached to this feature by `exposure.py`: an estimate of travel volume / opportunity for a hazard, in the unit named by `exposure_source` (e.g. annual bike+ped trips, or person-km on the segment). `null` means **exposure unknown** for this feature; when `null`, `rate`, `rate_ci_low`, and `rate_ci_high` are also `null` and the feature is labeled "exposure unknown" rather than rated (degradability — a segment is never silently dropped or falsely rated). |
| `exposure_source` | string | yes | Identifier of the exposure source used for this feature (e.g. `city-bike-ped-counts-2024`, `demand-model-v2`, `streetlight-import-2025q1`). Sources are the same versioned identifiers used in the checked-in config; a swap or a stale layer is therefore visible per-feature, not silent. `null` only when `exposure_estimate` is `null`. |
| `exposure_date` | string (ISO-8601 date) | yes | The date (or vintage) of the exposure data used, so a consumer can see how current the denominator is. `null` only when `exposure_estimate` is `null`. |

> A feature may use a different exposure source from its neighbors (e.g. a counted corridor next to a
> modeled side street). That is why the source and date are **per-feature**, not only in `metadata`.
> The data card discusses the implications of mixing sources.

### 4.3 Rate and uncertainty (HR2)

| Property | Type | Nullable | Description |
|---|---|---|---|
| `rate` | number ≥ 0 | yes | The exposure-normalized risk estimate: reports per unit of exposure, computed by `rates.py` (`report_count` normalized by `exposure_estimate`, using a count model appropriate to the data). Units are documented in the data card and implied by `exposure_source`. **This — not `report_count` — is the danger estimate.** `null` when `exposure_estimate` is `null`. |
| `rate_ci_low` | number ≥ 0 | yes | Lower bound of the confidence interval on `rate`. |
| `rate_ci_high` | number ≥ 0 | yes | Upper bound of the confidence interval on `rate`. |
| `n` | integer ≥ 0 | no | The sample size the interval is computed from (effective number of independent reports after dedupe). `n` is published alongside the interval so a consumer can judge how thin the estimate is; a small `n` with a wide interval is the honest signal that a feature must not be ranked as certain. |

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

`getis_ord_significant` is the field a map should use to mark a cluster as significant, and the
equivalent table must carry it as text — significance is conveyed in text and pattern, never by color
alone (an accessibility requirement that doubles as an honesty one). Reporting bias (`quality_flags`,
the dataset bias statement) still applies: a statistically significant cluster can still be an artifact
of where people report, and that caveat is stated rather than overridden by the flag (**HR3**).

### 4.5 Hazard-type breakdown

| Property | Type | Nullable | Description |
|---|---|---|---|
| `hazard_breakdown` | object | no | Counts of reports at this feature by hazard type, keyed by the closed vocabulary from the intake schema: `close_pass`, `dooring`, `surface_hazard`, `sightline`, `signal`, `debris`, `other`. Values are integers ≥ 0 and sum to `report_count`. Keys with a zero count may be present or omitted; a consumer should treat an absent key as `0`. This describes the *mix of conflict* at a place (a corridor of close passes reads differently from one of surface defects), supporting targeted advocacy without exposing any individual report. |

Only **aggregated counts** appear here. Per-report fields — the free-text note, exact time, severity,
mode at the individual level, heading, reporter token — are **not** present in the published dataset.
Where a feature's count is below the small-sample threshold (`small_n`), the `hazard_breakdown` is
**suppressed** and published as an empty object (`{}`), because a mix built from very few reports is both
uncertain and a re-identification risk; the `low_sample` quality flag (below) also marks such features.

### 4.6 Quality flags

| Property | Type | Nullable | Description |
|---|---|---|---|
| `quality_flags` | array of string | no | Zero or more machine-readable flags from a closed vocabulary, surfacing the caveats that govern how this feature should be read. An empty array means no flags were raised, not that the feature is unconditionally trustworthy. |

Flag vocabulary (additive across schema minor versions; never silently repurposed):

| Flag | Meaning |
|---|---|
| `low_sample` | `n` is below the project's small-sample threshold; the rate and any ranking are uncertain (**HR2**). Pair with the wide interval. |
| `exposure_unknown` | No exposure denominator was available; `exposure_estimate`/`rate`/CI are `null`. Shown as "exposure unknown," not rated (**HR1**, degradability). |
| `exposure_modeled` | The denominator came from a demand model or imported layer rather than an observed count; the rate is more assumption-dependent. See `exposure_source`. |
| `exposure_stale` | The `exposure_date` is older than the freshness window in config relative to the report window; the rate may be mismatched in time. |
| `reporting_bias_suspected` | This feature is in an area the bias analysis (`bias.py`) flags as likely over- or under-represented; the value may be a reporting artifact (**HR3**). |
| `geocode_low_confidence` | Aggregated reports here include low-positional-accuracy locations; placement is less certain. |
| `ci_unstable` | The interval method's assumptions are stressed for this feature (e.g. extreme sparsity); treat the bounds as indicative. |

Flags are intentionally conservative: it is better to over-mark a feature as uncertain than to present
a thin or biased estimate as solid. The full definitions, thresholds, and the config values behind each
flag are in the data card so the flagging is reproducible and auditable.

---

## 5. Privacy: aggregation and minimum occupancy (HR4)

Every published feature is the product of **deliberate aggregation to a public street segment** and
the **withholding of low-count segments**, and that is recorded both in `metadata.aggregation` and, in
plain language, in the data card. This is not lossy rounding by accident; it is a privacy control with
auditable parameters, enforced in code rather than promised in prose.

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
    "report_count": 12,
    "exposure_estimate": 184000,
    "exposure_source": "city-bike-ped-counts-2024",
    "exposure_date": "2024-09-30",
    "rate": 6.52e-05,
    "rate_ci_low": 3.37e-05,
    "rate_ci_high": 1.14e-04,
    "n": 12,
    "getis_ord_z": 2.91,
    "getis_ord_significant": true,
    "hazard_breakdown": {
      "close_pass": 7,
      "dooring": 3,
      "surface_hazard": 2
    },
    "quality_flags": ["reporting_bias_suspected"]
  }
}
```

How to read it honestly: `report_count` (12) is *volume*; the danger estimate is `rate` with its
interval (`rate_ci_low`..`rate_ci_high`), computed against an observed 2024 count denominator. The Gi\*
flag marks a statistically significant cluster — but `reporting_bias_suspected` warns that this corridor
may be over-represented by commuter reporters, so the cluster should be read with that caveat, exactly
as the brief and data card state it.

A feature with no usable denominator looks different and says so:

```jsonc
{
  "type": "Feature",
  "geometry": { "type": "LineString", "coordinates": [[-121.760, 38.551], [-121.759, 38.552]] },
  "properties": {
    "segment_id": "seg-davis-01188",
    "report_count": 4,
    "exposure_estimate": null,
    "exposure_source": null,
    "exposure_date": null,
    "rate": null,
    "rate_ci_low": null,
    "rate_ci_high": null,
    "n": 4,
    "getis_ord_z": null,
    "getis_ord_significant": null,
    "hazard_breakdown": { "surface_hazard": 4 },
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
3. Releases are **signed**, and each published file pins `metadata.schema_version`, `metadata.content_hash`,
   and `metadata.rng_seed`, so a consumer can always tell exactly which schema version and which build a
   file conforms to and verify it was not altered after the fact (**HR5**).
4. `$schema`/machine-validation: the published GeoJSON is validated in CI against a JSON Schema that
   mirrors this document; that validator is versioned in lockstep and is the authoritative,
   machine-checkable form of this contract.

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
- `data/published/DATA-CARD.md` — sources, methods, limits, the bias account, the schema crosswalk to
  external standards, and the exact CI method, significance threshold, and flag thresholds.
- RFC 7946 (The GeoJSON Format); WGS84 / EPSG:4326; MMUCC and KABCO are referenced for taxonomy and
  severity framing only — this dataset does not claim to be a police-coded crash dataset.
