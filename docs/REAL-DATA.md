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
a TOML manifest per source under `src/nearmiss/adapters/crosswalks/`. Adding a new source (a city
311/SeeClickFix export, an advocacy-group spreadsheet, …) is meant to touch no pipeline code: write a
crosswalk TOML, a small adapter module that reads that source's file format, and a conformance test
(`tests/test_adapters_conformance.py` round-trips every registered adapter's output through
`validation.validate_report`).

Every adapter also returns a **provenance block** alongside its reports — not part of the report
payload itself (`schema/report.schema.json` sets `additionalProperties: false` on purpose, so
provenance never gets tangled with the schema-validated payload), but a sibling record naming the
source, its license, and, critically, **that source's own reporting-bias profile** (`bias_label` +
`bias_notes`). This is what lets an imported dataset carry its own honesty into `stats/bias.py`'s
narrative and this project's data card, rather than quietly averaging every source's skew into one
undifferentiated pile of points — see each source's crosswalk manifest for its specific biases, and
[`docs/DATA-CARD.md`](DATA-CARD.md#known-reporting-biases-who-is-over--and-under-represented) for how
that shows up in the published dataset's own documentation.

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
    "FARS2024NationalCSV.zip",
    release_status="final",
)
```

NHTSA describes FARS as a nationwide census of fatal motor-vehicle traffic crashes and publishes
annual downloads from 1975 onward at the
[official FARS data page](https://www.nhtsa.gov/research-data/fatality-analysis-reporting-system-fars).
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
nearmiss ingest-fars /private/downloads/FARS2024NationalCSV.zip \
  --root "$HOME/.local/share/nearmiss/ingestion" \
  --year 2024 \
  --release-status final \
  --distribution-url \
    https://static.nhtsa.gov/nhtsa/downloads/FARS/2024/National/FARS2024NationalCSV.zip \
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

This is still crash-table context, not outcome triangulation. A later slice must join `person.csv` for
road-user modes, link outcomes to street segments and time windows, and make coverage trust only the
artifact/receipt/raw hash chain before any comparative capability appears.

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

| BikeMaps field / value | intake field | Mapping |
|---|---|---|
| endpoint `nearmiss` / `hazards` | `severity` | `near_miss` |
| endpoint `collisions`, `injury` hospital/hospitalized | `severity` | `serious` |
| endpoint `collisions`, any other injury | `severity` | `minor` (contact occurred) |
| `incident_with` = "Vehicle, passing" | `hazard_type` | `close_pass` |
| `incident_with` = "Vehicle, open door" | `hazard_type` | `dooring` |
| `incident_with` = Pothole / Curb / Train Tracks / Lane divider / Roadway | `hazard_type` | `surface_hazard` |
| `incident_with` = Sign/Post | `hazard_type` | `sightline` |
| `incident_with` = other vehicle / person / animal | `hazard_type` | `other` |
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

| | Davis, CA | Sacramento, CA |
|---|---|---|
| Incidents | BikeMaps.org (`--city davis`) — thin coverage | BikeMaps.org (`--city sacramento`) — denser |
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

To put a real city on the live website, copy its published GeoJSON into `data/published/` (e.g.
`data/published/sacramento.geojson`) and open the map with `?city=sacramento` (or `?data=<path>`). The
web app is source-agnostic and reads the dataset's own embedded `metadata`, so the provenance banner
and title switch automatically: a `dataset_note` mentioning "synthetic"/"demo" shows the amber demo
warning, anything else shows a green **real data** banner with the city, exposure unit, and source. No
code change is needed — the synthetic demo stays correctly labeled, and a real dataset announces itself
as real.

## Network egress note

If you run this in a restricted environment (e.g. Claude Code on the web with a strict egress
allowlist), the BikeMaps and OSM hosts may be blocked, returning `403 Host not in allowlist`. Either
add `bikemaps.org` (and your OSM/Overpass host) to the environment's network egress settings, or fetch
the data where the network is open and commit/transfer the resulting files. The live website is
unaffected — visitors' browsers load OSM tiles directly.

## Putting it together

```bash
# 1. Incidents (real, BikeMaps)
python tools/fetch_bikemaps.py --city victoria --out data/raw/victoria/reports.json
# 2. Streets (real, OpenStreetMap)
python tools/fetch_osm_streets.py --city victoria --out data/raw/victoria/streets.geojson
# 3. Exposure (real; your counts/model) -> exposure.json   <-- the remaining real work
# 4. Point a config at the three inputs (copy config/davis-demo.toml), then:
nearmiss run --config config/victoria.toml
nearmiss serve   # open web/index.html — the two maps now show real reports
```

Steps 1 and 2 are solved today. **Step 3 (exposure) is the remaining real work** — and it is the
input that distinguishes this project from a dot-map, so it is worth doing properly rather than
faking.

Last verified: 2026-07-12

Recheck cadence: Quarterly, and before changing any external source URL, field mapping, or access
claim.
