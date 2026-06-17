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

To put a real city on the live website, copy its published GeoJSON into `data/published/` and point
the web app at it (the map and table are source-agnostic); keep the synthetic demo clearly labeled as
such until you do.

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
