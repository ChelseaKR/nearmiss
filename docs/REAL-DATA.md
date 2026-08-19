# Real data: from synthetic demo to real reports

The committed demo (`config/davis-demo.toml`) runs on **synthetic** fixtures with known planted
answers — that is deliberate, because it makes the pipeline's correctness testable (the tests recover
the planted hotspot and reject the busy decoy). This document is the recipe for pointing the same
pipeline at **real** data, and it is honest about which inputs are easy and which are hard.

The project's value is **not** "another dot-map of incidents." Tools like
[BikeMaps.org](https://bikemaps.org) and municipal Vision Zero dashboards already collect and plot
raw reports. The value here is the analytical layer those tools skip: **exposure normalization,
confidence intervals, and significance testing**, so that report *volume* is never mistaken for
*danger*. The published research is blunt that raw crash/near-miss counts are a biased danger signal
because of the "safety in numbers" effect — the busiest street collects the most reports simply
because the most people are there. This pipeline exists to correct exactly that, and the web UI shows
the correction side by side (see [`web/README.md`](../web/README.md)).

A real city needs **three** inputs (the same three the demo fixtures provide). They differ wildly in
how available they are.

## Source adapters

Incident sources (this section) are implemented as **source adapters**: a `SourceAdapter`
(`src/nearmiss/adapters/base.py`) is a small `fetch()`/`parse()` contract, and the source-specific
vocabulary mapping — the crosswalk tables below rendered as prose — is **declarative data**, not code:
a TOML manifest per source under `src/nearmiss/adapters/crosswalks/`. Adding a new source (another
crowdsourced near-miss platform, an advocacy-group spreadsheet, …) is meant to touch no pipeline
code: write a crosswalk TOML, a small adapter module that reads that source's file format, and a
conformance test (`tests/test_adapters_conformance.py` round-trips every registered adapter's output
through `validation.validate_report`).

**Not every point dataset qualifies.** An intake report is a conflict *event experienced by a
person*, so it carries `mode` (who was involved) and `severity` (what happened to them). A source of
*condition* records — a 311/SeeClickFix service request, a pavement-inspection export, an asset
inventory — describes infrastructure with no person in it and can supply neither field. Read
[What this does not license](#what-this-does-not-license) below before
you invest in a source, and open a
[source proposal](../.github/ISSUE_TEMPLATE/source_proposal.yml) first so record kind, licensing,
and bias labeling are settled before any code is written.

Every adapter also returns a **provenance block** alongside its reports — not part of the report
payload itself (`schema/report.schema.json` sets `additionalProperties: false` on purpose, so
provenance never gets tangled with the schema-validated payload), but a sibling record naming the
source, its license, and, critically, **that source's own reporting-bias profile** (`bias_label` +
an eight-axis `bias_profile`). This is what lets an imported dataset carry its own honesty into
`stats/bias.py`'s narrative and this project's data card, rather than quietly averaging every
source's skew into one undifferentiated pile of points — see each source's crosswalk manifest for its
specific biases, and
[`docs/DATA-CARD.md`](DATA-CARD.md#known-reporting-biases-who-is-over--and-under-represented) for how
that shows up in the published dataset's own documentation.

### The bias profile every source must answer

`bias_label` is a one-line summary. The `[source.bias_profile]` table is the real work: a manifest
must answer **all eight** of the bias axes the data card names, in its own source's terms, and
`load_crosswalk` rejects a manifest that leaves one blank or fills it with a placeholder. The axes
are `route_choice`, `reporter_pool`, `app_access`, `language`, `demographic_skew`, `survivorship`,
`salience`, and `temporal_campaign`; each is documented inline in
[`crosswalks/bikemaps.toml`](../src/nearmiss/adapters/crosswalks/bikemaps.toml). If an axis genuinely
does not apply to a source, say so **and say why** — "not applicable" without a reason is the thing
this check exists to stop. Answering these honestly is usually the hardest part of adding a source,
and it is the part reviewers will push on.

Two adapters exist today: `bikemaps` and `simra` (below). Both are `--from-file`/`--dir` testable with
no network, and both are exercised by `tests/test_adapters_conformance.py` in addition to their own
fixture tests.

## Official outcomes — national context, not an intake source

Near-miss reports are a leading signal; official crash outcomes are a separate, lagging signal.
nearmiss therefore does **not** force official records through `schema/report.schema.json` or register
them as contributor `SourceAdapter`s. They implement the sibling `OfficialOutcomeAdapter` contract
and validate against `schema/official-outcome.schema.json`.

The first official adapter reads NHTSA Fatality Analysis Reporting System (FARS) crash-level
`accident.csv` data from either an extracted CSV or NHTSA's nested national ZIP export:

```python
from nearmiss.adapters import FarsAdapter

outcomes, provenance = FarsAdapter().parse(
    "FARS2023NationalCSV.zip",
    release_status="final",
)
```

NHTSA describes FARS as a nationwide census of fatal motor-vehicle traffic crashes and publishes
annual downloads from 1975 onward at the
[official FARS data page](https://www.nhtsa.gov/research-data/fatality-analysis-reporting-system-fars).
NHTSA's April 2026 analytical manual identifies 2024 as the Annual Report File (ARF), not a Final
File. NHTSA replaces an ARF with a final file after its later review cycle, so release stage is part
of the immutable annual source contract rather than a cosmetic label.
The crash table provides a nationwide baseline but cannot identify pedestrian or cyclist involvement
by itself; that requires a later join to FARS `person.csv`. It also says nothing about nonfatal or
unreported near misses. For file-backed exports, the adapter preserves the input SHA-256 along with
the operator-supplied release label, source years, accepted count, and every rejection reason so later
analysis can prove exactly what it used. Programmatic row iterables have no source-byte digest and are
intended for controlled transformations and tests.

`nearmiss ingest-fars` connects a local official export to the
[fail-closed ingestion foundation](INGESTION.md). It does not download the file; acquisition remains a
separate operator step so the exact bytes can be reviewed and pinned before normalization.

```bash
nearmiss ingest-fars /private/downloads/FARS2023NationalCSV.zip \
  --root "$HOME/.local/share/nearmiss/ingestion" \
  --year 2023 \
  --release-status final \
  --distribution-url \
    https://static.nhtsa.gov/nhtsa/downloads/FARS/2023/National/FARS2023NationalCSV.zip \
  --max-invalid-fraction 0.01 \
  --max-raw-bytes 67108864 \
  --max-normalized-bytes 67108864
```

The command writes owner-only, content-addressed raw and normalized files plus an active receipt and
immutable history. Its stdout summary contains hashes, counts and root-relative paths, never outcome
coordinates. The distribution URL is a constrained operator assertion about the local bytes, not a
download authentication or an NHTSA signature. A suspicious record-count regression or rollback to an
older dataset year fails closed unless the operator explicitly acknowledges the specific condition.
These distinct controls prevent a valid-looking truncated or stale file from silently replacing the
national last-known-good artifact. When an override is used, that policy choice is stored in the
normalized artifact.

For the reviewed annual accident/person path, `nearmiss ingest-fars-year` accepts only the exact
National ZIP registered for an explicit year and append-only contract revision. The current registry
covers 2020–2023 at revision 1 and 2024 through revision 2. Archive size and SHA-256, CSV members and encodings, release stage,
mapping versions, row ceilings, and permitted regression categories all come from that immutable
contract; the CLI has no flags that can replace them. Revisions 1 and 2 are retained for 2024:
revision 1 preserves the originally published provenance bytes, while revision 2 corrects the stage
to `annual_report_file` without changing the pinned raw archive or mapping versions.

```bash
# A fresh 2024 lineage must preserve the originally published revision first.
nearmiss ingest-fars-year /private/downloads/FARS2024NationalCSV.zip \
  --root "$HOME/.local/share/nearmiss/ingestion" \
  --year 2024 \
  --contract-revision 1

# Then advance the same private lineage to the provenance-corrected revision.
nearmiss ingest-fars-year /private/downloads/FARS2024NationalCSV.zip \
  --root "$HOME/.local/share/nearmiss/ingestion" \
  --year 2024 \
  --contract-revision 2
```

Each command performs the registered `accident.csv`/`person.csv` join, activates the canonical private
annual artifact under source ID `fars-joined-<year>`, and prints one JSON line of verified aggregate
lineage evidence. That line contains contract/mapping identities, hashes, and crash/person/case
accounting—not private paths, coordinates, or normalized records. Run the command from inside the
nearmiss checkout or assembled public site: even under pipx/wheel installation, the CLI rejects a
private root inside that real operator-visible boundary and fails closed when it cannot identify one.
Revision 2 is accepted only after revision 1 is active in that same private root; a fresh lineage
cannot skip retained history.
Keep the private root outside every other served tree as an explicit operator control. Acquisition
remains a separate reviewed step; a stable NHTSA URL alone is not accepted as proof of the bytes.

After the city registry explicitly declares `id = "fars"` with
`kind = "official_outcomes"`, an operator can verify the private lineage without publishing it:

```bash
nearmiss coverage --config config/city.toml \
  --fars-root "$HOME/.local/share/nearmiss/ingestion"
```

The verifier replays normalization from the preserved raw bytes and returns only safe aggregate
lineage metadata. A declaration without verified bytes and verified bytes without the matching
declaration both grant no capability. The matched state grants only `verified_official_outcomes`, not
mode involvement, segment/time comparison, or triangulation.

The legacy `ingest-fars`/`coverage --fars-root` flow is still crash-table context, not outcome
triangulation. The annual command now performs the exact `person.csv` join for road-user modes, but
those annual lineages are private and are not yet consumed by coverage, street-segment/time-window
comparison, or publication. Those consumers require a separate reviewed methodology and privacy
boundary before any comparative capability appears.

### Publishing annual state × mode context

The public nationwide page consumes one canonical artifact per released year and the closed current
[`fars-state-mode-index-v2.json`](../data/published/fars-state-mode-index-v2.json) allowlist. The index is
not a place to announce work in progress: it contains only years with an exact reviewed public
artifact, pins every artifact by bytes and SHA-256, and binds it to that year's registered NHTSA
archive, annual contract digest, semantic regime, crash/person mappings, state-code system, and
geography crosswalk. The browser verifies the index and selected artifact before showing any count;
an unknown or unpublished `?year=` fails closed instead of falling back to zero or another year.
The page surfaces those method identities and explicitly warns that 2020–2021 and 2022–2024 use
different reviewed person-type semantic regimes.

Production inputs required to add a year are:

1. the exact activated registered annual revision for that year, authenticated through its full
   private receipt/raw/normalized lineage;
2. a deterministic public projection from those authenticated bytes containing exactly 51 states ×
   six involved modes, with every sub-`k=10` or zero cell represented only as
   `suppressed_or_zero` and with reconciled aggregate accounting;
3. canonical UTF-8 JSON named `fars-YYYY-state-mode.json` for revision 1 or
   `fars-YYYY-state-mode-rN.json` for a later immutable revision, independently checked against the
   registered annual source identity and privacy-forbidden-field tests; and
4. a regenerated index built from an explicit list of all released annual files:

   ```bash
   python tools/build_fars_public_index.py \
     --artifact data/published/fars-2020-state-mode.json \
     --artifact data/published/fars-2021-state-mode.json \
     --artifact data/published/fars-2022-state-mode.json \
     --artifact data/published/fars-2023-state-mode.json \
     --artifact data/published/fars-2024-state-mode-r2.json \
     --out data/published/fars-state-mode-index-v2.json
   ```

   A provenance correction also rebuilds its closed ledger from the two immutable generations:

   ```bash
   python tools/build_fars_correction_ledger.py \
     --prior-artifact data/published/fars-2024-state-mode.json \
     --replacement-artifact data/published/fars-2024-state-mode-r2.json \
     --prior-index data/published/fars-state-mode-index.json \
     --replacement-index data/published/fars-state-mode-index-v2.json \
     --out data/published/fars-release-corrections.json
   ```

The checked-in production index publishes the proof-bound 2020–2024 projections. The superseded
`fars-2024-state-mode.json` and `fars-state-mode-index.json` URLs remain byte-identical and are bound
to their replacements by `fars-release-corrections.json`; the browser consumes only the corrected
revision-2 catalog. The browser
contract exercises all five exact public artifacts, including transitions across the 2020–2021 and
2022–2024 semantic regimes. A private annual activation proof alone must never be relabeled as a
public result: any future year remains unpublished until its projection and annual contract are
generated, independently reviewed, and added to the closed release inventory.

### Official Census boundary geometry

The nationwide view uses [`us-state-boundaries-2024.json`](../data/published/us-state-boundaries-2024.json)
only for map geometry. It is a deterministic GeoJSON conversion of the U.S. Census Bureau's 2024
national 1:20,000,000 cartographic-boundary KML, retaining the 50 states and District of Columbia;
it supplies no crash values. The builder pins the source ZIP, validates the full state crosswalk,
and fails closed on byte drift. Regenerate the reviewed asset with:

```bash
.venv/bin/python tools/build_us_state_boundaries.py
```

## 1. Incidents — real, and available today (BikeMaps.org)

[BikeMaps.org](https://bikemaps.org) is a crowdsourced global map of cycling **collisions, near
misses, hazards, and thefts** — the closest real analogue to this project's own input, including the
near misses that never reach a police report.

`tools/fetch_bikemaps.py` is the bridge. It reads BikeMaps' public GeoJSON (or an exported file) and
emits reports in the intake contract (`schema/report.schema.json`), ready for `nearmiss intake`:

```bash
# Live, by known city bounding box (Victoria, BC has the densest data):
python tools/fetch_bikemaps.py --city victoria --out data/raw/victoria/reports.json

# Live, by explicit bounding box  W,S,E,N:
python tools/fetch_bikemaps.py --bbox=-123.46,48.40,-123.28,48.50 --out reports.json

# Offline, from BikeMaps' own admin "Export" (no network needed):
python tools/fetch_bikemaps.py --from-file bikemaps-export.geojson --kind nearmiss --out reports.json
```

The public endpoints are `https://bikemaps.org/{nearmiss,collisions,hazards}.json` (from
`SPARLab/BikeMaps` `mapApp/urls.py`).

### Crosswalk (BikeMaps → intake)

Derived from `SPARLab/BikeMaps` `mapApp/models/incident.py`. Where BikeMaps draws a distinction our
closed `hazard_type` vocabulary cannot represent, we fall back to `other` rather than overstate the
conflict — honesty over precision we don't have.

**How much falls through, measured.** That fallback is not a small tail. Against BikeMaps' live
near-miss extract — 6,222 reports, fetched 2026-08-04, every one schema-valid — it takes **76.6%** of
the corpus:

| | reports | share |
|---|---:|---:|
| Named conflict geometry, no enum member → `other` | 4,768 | 76.6% |
| Mapped to a specific `hazard_type` | 1,047 | 16.8% |
| Genuinely miscellaneous (pedestrian, cyclist, animal, "Other") | 397 | 6.4% |
| Unmapped source value (`E-scooter`) | 10 | 0.2% |

The discarded majority is conflict *geometry* — `Vehicle, side` (1,515), `Vehicle, turning right`
(904), `Vehicle, head on` (893), `Vehicle, turning left` (539), `Vehicle, angle` (504),
`Vehicle, rear end` (413). `hazard_type` has no member for any of it, because that enum is built
around hazard *features* (pothole, sightline, debris) plus close-pass and dooring.

This costs interpretation, not correctness: exposure normalization, confidence intervals, and
hotspot significance are all unaffected by type. What is lost is the ability to say whether a
significant hotspot is a right-hook corner or a rear-end corridor — different findings calling for
different interventions.

So the adapter keeps each record's source vocabulary verbatim in a **`source_terms`** map (report id
→ source term), written as a sibling key to `reports` and never inside a report:
`schema/report.schema.json` sets `additionalProperties: false` deliberately, and a source's raw
vocabulary is not an intake claim. All 5,175 `other` reports in that extract are recoverable through
it. Nothing downstream is required to consume it; it exists so the detail is not destroyed at
intake, and so a later decision to widen the enum has the evidence to justify itself.

| BikeMaps field / value | intake field | Mapping |
|---|---|---|
| endpoint `nearmiss` / `hazards` | `severity` | `near_miss` |
| endpoint `collisions`, `injury` hospital/hospitalized | `severity` | `serious` |
| endpoint `collisions`, any other injury | `severity` | `minor` (contact occurred) |
| `incident_with` = "Vehicle, passing" | `hazard_type` | `close_pass` |
| `incident_with` = "Vehicle, open door" | `hazard_type` | `dooring` |
| `incident_with` = Pothole / Curb / Train Tracks / Lane divider / Roadway | `hazard_type` | `surface_hazard` |
| `incident_with` = Sign/Post | `hazard_type` | `sightline` |
| `incident_with` = turning / head-on / side / angle / rear-end, or person / animal | `hazard_type` | `other` (76.6% of the live extract — the source term is kept in `source_terms`) |
| `date` | `occurred_at` | passed through; a naive value gets `--utc-offset` |
| `pk` | `id` | deterministic `uuid5` (stable, never personal) |
| (reporter is a cyclist) | `mode` | `cyclist` |

BikeMaps publishes its points publicly (already slightly fuzzed for privacy), so using them does not
re-expose anyone; we still aggregate to segments downstream like any other source.

The full crosswalk (including every rule's stated rationale) is the machine-readable source of truth
at `src/nearmiss/adapters/crosswalks/bikemaps.toml`; this table is a rendering of it for readers who
don't want to open a TOML file.

## 1b. Incidents — SimRa (TU Berlin), the second source adapter

[SimRa](https://github.com/simra-project/dataset) (TU Berlin) is a crowdsourced, openly-published
dataset of **bicycle near-crashes** with GPS, collected via a research-partner smartphone app. It is
unusual among real-data sources in that the same download also carries the *ride* GPS traces — a
natural exposure denominator (not wired into `tools/build_exposure.py` yet; see the exposure section
below) — alongside the annotated incidents.

`tools/fetch_simra.py` (the second `SourceAdapter` implementation, landing what had been an unmerged
branch) reads a directory of SimRa ride files — each one a CSV-like block of annotated incident rows,
a divider line, then the raw GPS trace — and emits reports in the intake contract:

```bash
# A downloaded SimRa region folder (or a parent directory of several):
python tools/fetch_simra.py --dir path/to/SimRa/Berlin_2023_03 --out reports.json

# Restrict to a known city's bounding box (berlin, london, munich):
python tools/fetch_simra.py --dir path/to/SimRa --city berlin --out reports.json
```

SimRa has no live API — you download a region's data from the
[simra-project/dataset](https://github.com/simra-project/dataset) repository (or a research partner's
mirror) and point `--dir` at it, which is also why this source needs no network egress allowlisting.

### Crosswalk (SimRa → intake)

Derived from the SimRa incident-code enum (Close pass, pulling in/out, near left/right hook, head-on,
tailgating, near-dooring, dodging an obstacle, other). SimRa records near-misses only — there is no
injury/outcome field at all — so **every** SimRa report is intake `severity: near_miss`; this source
alone can never speak to collision severity.

| SimRa `incident` code | intake field | Mapping |
|---|---|---|
| (any row) | `severity` | `near_miss` (SimRa has no injury/outcome field) |
| `1` (Close pass) | `hazard_type` | `close_pass` |
| `7` (near-dooring) | `hazard_type` | `dooring` |
| `8` (dodging an obstacle) | `hazard_type` | `surface_hazard` |
| `2`-`6`, `9` (pulling in/out, near hook, head-on, tailgating, other) | `hazard_type` | `other` (no generic "vehicle conflict" type) |
| epoch-ms `ts` | `occurred_at` | converted to RFC 3339 UTC |
| (reporter is a cyclist) | `mode` | `cyclist` |

The full crosswalk (with rationale) is `src/nearmiss/adapters/crosswalks/simra.toml`. SimRa's own bias
profile — app-recruited, region-limited, near-miss-detection-only — is in that manifest's
`bias_notes` and is meaningfully different from BikeMaps': combining the two sources without naming
each one's skew separately would be exactly the kind of averaging-away this project's bias rule (HR3)
exists to prevent.

## 2. Street network — real, available today (OpenStreetMap)

`streets.geojson` is the base network reports snap to (`segment_id`, `name`, `LineString`). The real
source is **OpenStreetMap**, and `tools/fetch_osm_streets.py` is the bridge: it pulls
cycling-relevant highways inside the bounding box from the Overpass API and writes exactly what
`loaders.load_streets` expects. By default it **splits each OSM way at intersections**, so a segment
is a block between cross streets (like the demo's "B St (1st–2nd)") — the right granularity for
snapping and per-segment rates.

```bash
# Live (Overpass), split into per-block segments:
python tools/fetch_osm_streets.py --city victoria --out streets.geojson

# Offline: run an Overpass query in your browser, save the JSON, then:
python tools/fetch_osm_streets.py --from-file overpass.json --out streets.geojson
```

`segment_id` is stable (`osm-w<wayid>-<block>`), so re-running on the same area is reproducible.
Choose the road classes with `--highway`, or keep whole ways with `--no-split`.

### Joining the published data to your own layers (segment IDs)

The published GeoJSON uses the project's own `segment_id`, which is *not* your city's
centerline key — so here is the crosswalk (this is roadmap item **R31**):

| Source of streets | `segment_id` format | How to recover the source key |
|---|---|---|
| OpenStreetMap (this fetcher) | `osm-w<wayid>-<block>` | The OSM way is the middle field: split on `-`, take `w<wayid>` → OSM way `https://www.openstreetmap.org/way/<wayid>`. `<block>` is the 1-based segment between intersections along that way. |
| Synthetic fixtures (demo) | `seg-NN` | A demo identifier only; not a real-world key. |
| Your own `streets.geojson` | whatever you put in `properties.segment_id` (or `id`) | The loader (`loaders.load_streets`) takes `segment_id`, then `id`, then the GeoJSON feature `id`, in that order. |

To conflate to a municipal centerline file, two practical routes:

1. **Via OSM way id.** Recover `<wayid>` as above and join to any layer that carries OSM
   ids (many open street layers do, or can be matched once).
2. **Spatial conflation.** Buffer each published `LineString` a few metres and take the
   maximum-overlap centerline segment. Because each published segment is already a
   single block (split at intersections), one-to-one matches are common; review the
   ambiguous ones. A documented conflation helper is a future tool.

Every published segment is `LineString` geometry in WGS84 ([lon, lat]) per RFC 7946, so it
joins in QGIS/PostGIS without a custom reader; the full attribute contract (and which fields
are nullable / suppressed) is in [`schema/dataset.schema.md`](../schema/dataset.schema.md).

## 3. Exposure — the genuinely hard part (but real data exists)

`exposure.json` is the denominator: how much cycling each segment carries. **This is the make-or-break
input and the reason most maps skip normalization.** `tools/build_exposure.py` turns point count
observations into per-segment exposure by snapping each counter to its nearest segment with the *same*
geometry the pipeline uses for reports:

```bash
python tools/build_exposure.py --streets streets.geojson --counts counts.csv \
    --count-field count --source "CA AT Count Dataset 2025" --date 2025-01-01 \
    --out exposure.json
```

Counts may be a CSV (`--lat-field`/`--lon-field`/`--count-field`) or GeoJSON points. By default a
segment with no nearby counter gets **no** exposure and is published as `exposure unknown` (HR1: a
rate without a denominator is forbidden). `--model-fallback` will, only if you ask, fill uncovered
segments with a clearly-labeled flat prior (`source: modeled_flat_prior …`) — a weak placeholder for
visualization, never to be passed off as measured. Prefer real counts.

### Measured 2026-08-04: the two open California datasets do not overlap

Both halves of the California recipe exist, are open, and are real. They are also in different
places, which is the finding that matters before anyone budgets time for a real run.

The [CA AT Count Dataset](https://data.ca.gov/dataset/at-count-dataset) (CC-BY) 2025 bicycle file is
857,656 hourly rows over **81 counter locations** statewide, 837,917 bicycles counted — genuinely
usable as a denominator. BikeMaps' live near-miss extract the same day held 6,222 reports worldwide.
Intersecting them:

| Area | BikeMaps reports | AT counters | bicycles counted 2025 |
|---|---:|---:|---:|
| Santa Barbara | 113 | 1 | 24,534 |
| Irvine / Orange County | 57 | 25 | 253,563 |
| Berkeley / Oakland | 1 | 9 | 129,321 |
| San Diego | 44 | 0 | 0 |
| Davis | 0 | 0 | 0 |
| Sacramento | 1 | 0 | 0 |

They are close to anti-correlated: the places with reports have no counters, and the place with 25
counters has 57 reports. Testing every counter against every report directly:

| search radius | counters with ≥1 report | counters with ≥3 reports (`min_publish_n`) |
|---|---:|---:|
| 25 m (the configured `snap_max_m`) | 1 of 81 | **0** |
| 100 m | 2 of 81 | **0** |
| 250 m | 4 of 81 | **0** |

So a California run pairing these two sources publishes **no rate at all** — not because the pipeline
is wrong but because it is right: HR1 forbids a rate without a denominator, and `min_publish_n`
withholds any segment under three reports. Both rules fire on every segment. That is the correct
outcome, and it is worth knowing before the run rather than after.

### What this does not license

A 311 or SeeClickFix export is the obvious-looking substitute for the
empty incident half, and it is the wrong shape. A 311 record is a static infrastructure complaint —
a pothole, a blocked lane — with no person in it. An intake report carries `mode` (who was involved)
and `severity` (`near_miss`/`minor`/`serious`), because the statistics downstream are about conflict
*events* per unit of exposure. Mixing condition reports into that numerator would produce a ratio of
two unrelated quantities and quietly invalidate every rate built on it. A substitute incident source
has to be reports of conflicts involving a person, not reports of infrastructure.

Three of the six **required** intake fields have no honest value in a 311 record, which is what makes
this a contract violation rather than a preference:

| Required field | Why a 311 record cannot fill it |
|---|---|
| `mode` | The enum is `cyclist`/`pedestrian`/`wheelchair`/`scooter`/`other` and has **no `unknown`** — `other` means "a mode we did not enumerate", not "no idea". The existing adapters hardcode `cyclist` because BikeMaps and SimRa are cycling-specific tools; a service request has no traveller in it at all. |
| `severity` | Documented as *self-reported outcome severity*, where `near_miss` means a hazard avoided with no contact. A standing pothole is not an avoided event, and calling it `near_miss` invents an experience nobody had. |
| `occurred_at` | Defined as **event time, not submission time**. 311 supplies `requested_datetime`, i.e. when someone got annoyed enough to call, which for a chronic condition can be months late. |

`hazard_type` would in fact map cleanly (four of its seven members are condition-shaped:
`surface_hazard`, `sightline`, `signal`, `debris`). The crosswalk is not the problem; the
person-shaped fields are.

**Measured 2026-08-07, San Francisco's 311 export (8,820,143 records).** The categories plausibly
describing a road-surface or obstruction hazard — Street Defects, Sidewalk or Curb, Blocked Street or
Sidewalk — total 230,548, or **2.61%** of the corpus. Complaints about encampments, graffiti,
parking, abandoned vehicles, illegal postings, and noise total 2,908,181, or **33%**. So even a
tightly category-scoped 311 adapter would salvage under 3% of the feed, still with no mode and no
severity, from a stream whose single largest component is complaints about unhoused people.

There is a second, independent blocker: **licensing**. SeeClickFix's own API terms
([dev.seeclickfix.com](https://dev.seeclickfix.com/)) license its data **CC BY-NC-SA 3.0 US**. The
NonCommercial clause fails the Open Definition and is incompatible with this project's Apache-2.0
posture; the ShareAlike clause is viral and would force NC-SA onto any dataset it were merged into;
and the same terms require prior permission for "more than occasional queries", so bulk reuse is not
a standing grant. Open311 does not fix that — it is a *specification*, not a data license, and
conveys no reuse rights. Per-city open-data portals are the license-clean route but are uneven and
must be checked one city at a time: San Francisco is PDDL 1.0, Boston ODC-PDDL, Los Angeles CC0 1.0,
Austin and Kansas City public domain, while New York City sets **no license field at all** and
Chicago's terms reserve a right to require you to stop distributing and expressly grant no IP
rights. "It is on an open data portal" is not evidence of a redistribution right.

**The general rule.** An intake report is a conflict event experienced by a person, so it has a mode
and an outcome. A condition record describes a place. Sources of the second kind do not become
sources of the first kind by way of a crosswalk. Condition data is a legitimate subject for
exposure-normalized analysis — that is exactly what the sibling
[`honest_rates`](../src/honest_rates/README.md) library is for — it just is not a nearmiss intake
source.

Real options, roughly in order of fidelity:

- **Strava Metro** — segment-level ridership, free for governments/researchers but access-gated.
- **Permanent/temporary bike counters** — many regions publish counts as open data (see the cities
  below); coverage is sparse, which is exactly why uncovered segments stay "exposure unknown."
- **Modeled exposure** — estimate from population, network, and land use when counts are missing.

A real deployment stands or falls on the quality of this layer; do not skip it or fake it.

## Concrete cities: Davis and Sacramento

Two committed real configs — `config/davis.toml` and `config/sacramento.toml` — wire the three inputs
for these California cities. Their inputs and outputs live under the gitignored `data/real/` tree, so a
real run never clobbers the committed synthetic demo or the `make reproduce` gate.

> **Measured 2026-08-04: the BikeMaps half of this recipe does not execute for either city.**
> The live `/nearmiss.json` extract (6,222 reports worldwide) contains **0** reports inside the
> `davis` bbox and **1** inside `sacramento`. "Thin coverage" and "denser" below were optimistic;
> the correct word is empty. BikeMaps is a Canadian project — Victoria (1,071) and Vancouver (982)
> hold a third of the worldwide corpus between them, and the densest *US* box is Phoenix–Tempe at
> 126. So the exposure half of this recipe is the half that works in California: the CA AT Count
> Dataset is real, open, and statewide, while the incidents it would normalize do not exist here.
> Pairing a California exposure layer with a non-BikeMaps incident source is the open path; see the
> adapter framework above, which is built for exactly that substitution. It has to be a source of
> *conflict events involving a person* — a 311/SeeClickFix export cannot fill the gap, for the
> reasons in [What this does not license](#what-this-does-not-license)
> below. The nearest in-scope candidate is a California crowdsourced near-miss platform that records
> traveller mode and injury outcome; whichever is chosen, its license and redistribution terms have
> to be confirmed in writing before any adapter is written.

| | Davis, CA | Sacramento, CA |
|---|---|---|
| Incidents | BikeMaps.org (`--city davis`) — **0 reports as of 2026-08-04**; needs another source | BikeMaps.org (`--city sacramento`) — **1 report**; needs another source |
| Streets | OpenStreetMap / Overpass (`--city davis`) | OpenStreetMap / Overpass (`--city sacramento`) |
| Exposure | [California AT Count Dataset](https://lab.data.ca.gov/dataset/at-count-dataset) (statewide bike counts); City of Davis counters | [SACOG regional bike/ped counts](https://www.sacog.org/planning/transportation/active-transportation/bike-ped-counting-equipment) + the CA AT Count Dataset |

Run one end to end (where the network is open):

```bash
make real CITY=davis COUNTS=path/to/ca_at_counts.csv   # fetch streets + reports, build exposure
nearmiss run --config config/davis.toml                # publish to data/real/davis/published/
```

Davis is the harder, more honest case: it is one of the highest cycling-share cities in the US, yet
crowdsourced near-miss reports and open per-segment counts are both sparse, so expect many
"exposure unknown" segments. That is the point — the tool says what it does not know rather than
inventing a denominator. Sacramento has denser incident coverage and a regional count program, so it
normalizes more fully.

To evaluate a real city in the local methods UI, copy its published GeoJSON into `data/published/`
(e.g. `data/published/sacramento.geojson`), add its slug and constant path to the local web runtime's
explicit allowlist, and open the map with `?city=sacramento` (or the explicit
`?data=../data/published/sacramento.geojson` form). Dataset selectors are restricted to allowlisted
filename slugs inside `data/published/`; origins, other directories, traversal, queries, fragments,
and duplicates fail closed to the Davis default. The web app reads the dataset's own embedded `metadata`,
so the provenance banner
and title switch automatically: a `dataset_note` mentioning "synthetic"/"demo" shows the amber demo
warning, anything else shows a green **real data** banner with the city, exposure unit, and source. No
other rendering code is needed — the synthetic demo stays correctly labeled, and a real dataset announces itself
as real. The production builder intentionally publishes only the reviewed national FARS ledger; a
city-data deployment requires a separate product, privacy, provenance, and release review rather
than appearing merely because a file exists in `data/published/`.

## Network egress note

If you run this in a restricted environment (e.g. Claude Code on the web with a strict egress
allowlist), the BikeMaps and OSM hosts may be blocked, returning `403 Host not in allowlist`. Either
add `bikemaps.org` (and your OSM/Overpass host) to the environment's network egress settings, or fetch
the data where the network is open and commit/transfer the resulting files. The national production
site is unaffected because it does not deploy the local city UI or its OSM tile runtime.

## Putting it together

```bash
# 1. Incidents (real, BikeMaps)
python tools/fetch_bikemaps.py --city victoria --out data/raw/victoria/reports.json
# 2. Streets (real, OpenStreetMap)
python tools/fetch_osm_streets.py --city victoria --out data/raw/victoria/streets.geojson
# 3. Exposure (real; your counts/model) -> exposure.json   <-- the remaining real work
# 4. Point a config at the three inputs (copy config/davis-demo.toml), then:
nearmiss run --config config/victoria.toml
nearmiss serve   # open web/davis-demo.html — the local two-map method UI shows the artifact
```

Steps 1 and 2 are solved today. **Step 3 (exposure) is the remaining real work** — and it is the
input that distinguishes this project from a dot-map, so it is worth doing properly rather than
faking.

> **It has been done once, outside California.** A full end-to-end run against Potsdam, Germany
> derived a real exposure denominator from SimRa ride GPS traces (distinct rides per OSM segment,
> floored at five rides for k-anonymity) and produced a published artifact. The inputs are
> CC BY-NC 4.0, so no file from that run is committed and none can be; the method result is written
> up in [`findings/2026-08-15-potsdam-real-run.md`](findings/2026-08-15-potsdam-real-run.md),
> including a coverage figure of 1.5% of segments (holding 91% of the reports) and a MAUP
> rank-stability failure worth reading before you trust either committed demo. Anyone building step
> 3 should read that finding first: it is the only evidence this project has about what its own
> pipeline does when the denominators are real and sparse.

Last verified: 2026-07-12

Recheck cadence: Quarterly, and before changing any external source URL, field mapping, or access
claim.
