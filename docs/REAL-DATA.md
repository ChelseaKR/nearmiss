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

## 2. Street network — real, but needs a source you choose

`streets.geojson` is the base network reports snap to (`segment_id`, `name`, `LineString`). The
natural real source is **OpenStreetMap** (e.g. an Overpass query for `highway=*` in the bounding box,
or an extract from Geofabrik), exported to GeoJSON with a stable `segment_id` per way. This is
mechanical but not yet automated here; it is the next tool to add (`tools/fetch_osm_streets.py`).

## 3. Exposure — the genuinely hard part

`exposure.json` is the denominator: how much cycling each segment carries. **This is the make-or-break
input and the reason most maps skip normalization.** Real options, roughly in order of fidelity:

- **Strava Metro** — segment-level ridership, free for governments/researchers but access-gated.
- **Permanent/temporary bike counters** — many cities publish counts as open data; sparse coverage.
- **Modeled exposure** — estimate from population, network, and land use when counts are missing.

A rate without a denominator is forbidden by the project's hard rules (HR1), so a segment with no
exposure is published as `exposure unknown`, never ranked as if certain. A real deployment stands or
falls on the quality of this layer; do not skip it or fake it.

## Network egress note

If you run this in a restricted environment (e.g. Claude Code on the web with a strict egress
allowlist), the BikeMaps and OSM hosts may be blocked, returning `403 Host not in allowlist`. Either
add `bikemaps.org` (and your OSM/Overpass host) to the environment's network egress settings, or fetch
the data where the network is open and commit/transfer the resulting files. The live website is
unaffected — visitors' browsers load OSM tiles directly.

## Putting it together

```bash
# 1. Incidents (real)
python tools/fetch_bikemaps.py --city victoria --out data/raw/victoria/reports.json
# 2. Streets (real; your OSM export) -> tests/fixtures/victoria/streets.geojson (or a config path)
# 3. Exposure (real; your counts/model) -> exposure.json
# 4. Point a config at the three inputs (copy config/davis-demo.toml), then:
nearmiss run --config config/victoria.toml
nearmiss serve   # open web/index.html — the two maps now show real reports
```

Steps 2 and 3 are the real work. Step 1 is solved today.
