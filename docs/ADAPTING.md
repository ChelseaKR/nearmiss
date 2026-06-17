# Adapt nearmiss to your city

This is the practical, end-to-end guide to pointing nearmiss at a city that is not Davis. The
promise of the project is **config-over-code**: a new city is a new config file, three input files,
and an exposure layer — no Python changes. This document walks the whole path, from the three inputs
you supply, through the city config, the offline geocoder for address-only reports, and the run
commands, to an honest accounting of what you still have to do yourself.

Where this guide and the code disagree, the code and its tests
([`tests/`](../tests/)) are authoritative and this document is the bug. The fastest way to learn the
shape of every input is to copy the committed Davis demo:
[`config/davis-demo.toml`](../config/davis-demo.toml) and
[`tests/fixtures/davis/`](../tests/fixtures/davis/).

For the statistics behind the numbers this produces, read
[`docs/METHODOLOGY.md`](METHODOLOGY.md); for what the published dataset does and does not claim, read
[`docs/DATA-CARD.md`](DATA-CARD.md); for the privacy rules that govern publishing, read
[`docs/THREAT-MODEL.md`](THREAT-MODEL.md). The [Five Hard
Rules](../README.md#hard-rules-enforced-not-aspirational) apply to your city exactly as they apply to
Davis — most of all the one that says *no rate without a denominator*, which is why a real exposure
layer is not optional.

---

## Table of contents

1. [The three inputs you supply](#1-the-three-inputs-you-supply)
2. [Writing a city config](#2-writing-a-city-config)
3. [Address-only reports: the offline gazetteer geocoder](#3-address-only-reports-the-offline-gazetteer-geocoder)
4. [Running it](#4-running-it)
5. [What you still have to do yourself (honestly)](#5-what-you-still-have-to-do-yourself-honestly)
6. [A minimal checklist](#6-a-minimal-checklist)

---

## 1. The three inputs you supply

nearmiss takes three files. **The single most important thing to get right is the `segment_id`**: it
is the join key that ties all three together. Your streets define the segment ids; your exposure file
must use the *same* ids; and your reports are placed onto those segments by snapping. Get the ids
consistent and everything else follows. Get them inconsistent and the analysis will tell you so,
loudly — see the note on the exposure join below.

### 1a. Streets — a GeoJSON `FeatureCollection`

A GeoJSON file of `LineString` features, one per street block (segment). Each feature needs a
`segment_id` and a human-readable `name` in its `properties`. The `name` is what shows up in the
brief and the map table, so use real block names (`"5th St (C–D)"`), not `"seg-01"`.

```json
{
  "type": "FeatureCollection",
  "features": [
    {
      "type": "Feature",
      "geometry": {
        "type": "LineString",
        "coordinates": [[-121.7413, 38.5449], [-121.7397, 38.5449]]
      },
      "properties": { "segment_id": "seg-01", "name": "B St (1st–2nd)" }
    }
  ]
}
```

Notes:

- Coordinates are GeoJSON order: `[lon, lat]`, WGS84 (EPSG:4326).
- `segment_id` is required and must be unique. If it is missing the loader falls back to `id`, but do
  not rely on that — set `segment_id` explicitly so it matches your exposure file exactly.
- `name` defaults to the `segment_id` if absent. That is a code smell, not a feature: supply real
  names.
- This is the *only* geometry nearmiss publishes. The published GeoJSON is your street centerlines,
  never a report location, so these lines are the public face of the dataset. See
  [`schema/dataset.schema.md`](../schema/dataset.schema.md).

### 1b. Exposure — a JSON keyed by the SAME `segment_id`

A JSON file giving each segment a denominator: how many people travel it, so a count can become a
rate. The shape is a `{"segments": [...]}` object (a bare array also works), one row per segment:

```json
{
  "segments": [
    { "segment_id": "seg-01", "estimate": 1500.0, "source": "city_bike_count_2025", "date": "2025-05-01" },
    { "segment_id": "seg-03", "estimate": 8000.0, "source": "city_bike_count_2025", "date": "2025-05-01" }
  ]
}
```

Each row needs four fields:

- `segment_id` — **must match a street `segment_id` exactly.** This is the join.
- `estimate` — the exposure denominator (e.g. average daily bike trips on that block). The unit is up
  to you; you name it in the config (`exposure_unit`).
- `source` — where the number came from (a count program, a demand model, a Strava/StreetLight-style
  layer). This is published alongside the rate; be specific and honest.
- `date` — when the exposure was measured or modeled, ISO `YYYY-MM-DD`. Published too.

**The exposure join is by exact `segment_id`, and a mismatch is caught, not swallowed:**

- A **total** mismatch — *no* exposure id matches *any* street id — raises a clear error and stops the
  run. This almost always means the two layers use different id schemes (e.g. streets use `seg-01`
  but exposure uses OSM way ids). The error names example ids from each side so you can see the
  mismatch immediately. This is deliberate: silently producing 0% exposure coverage would read as "no
  denominators exist" instead of the truth, "you wired it up wrong."
- A **partial** mismatch — some exposure ids match, some do not — prints a warning naming the
  unmatched ids and continues. Segments with no matching exposure are shown as *exposure unknown* and
  are not ranked, never silently dropped or falsely rated.

Coverage is reported in the brief ("X% of segments have an exposure denominator"), so a low number is
visible, not hidden. You do not have to cover every segment to run, but uncovered segments cannot be
ranked, and rule 1 (*no rate without a denominator*) means an uncovered segment never gets a risk
claim.

### 1c. Reports — lat/lon OR address

The reports your contributors submit, validated at intake against
[`schema/report.schema.json`](../schema/report.schema.json). A report is a JSON object; the file is a
`{"reports": [...]}` wrapper or a bare array. The required fields are `schema_version`, `id`,
`occurred_at`, `mode`, `hazard_type`, and `severity`, **plus a location** — and here is the part that
is new and worth emphasizing:

> A report must carry **either** a `location` (a precise `lat`/`lon`) **or** an `address`
> (free text). The schema enforces this as an `anyOf`: one or the other is required.

A coordinate report:

```json
{
  "schema_version": "1.0.0",
  "id": "00000000-0000-4000-8000-000000000001",
  "occurred_at": "2026-06-10T07:20:00-07:00",
  "location": { "lat": 38.544879, "lon": -121.740919, "accuracy_m": 60.0 },
  "mode": "cyclist",
  "hazard_type": "close_pass",
  "severity": "near_miss"
}
```

An address-only report (no coordinates available — a contributor typing where it happened):

```json
{
  "schema_version": "1.0.0",
  "id": "00000000-0000-4000-8000-000000000002",
  "occurred_at": "2026-06-10T08:05:00-07:00",
  "address": "B St & 3rd St, Davis CA",
  "mode": "pedestrian",
  "hazard_type": "sightline",
  "severity": "near_miss"
}
```

The address is resolved to coordinates at the geocode stage (see [section 3](#3-address-only-reports-the-offline-gazetteer-geocoder))
and is treated as the location thereafter. An optional BCP-47 `language` tag (e.g. `"en"`, `"es"`)
records the language the report was submitted in; it defaults to `"en"` and feeds the bias analysis.

Like all precise location data, both `location` and `address` are **private**. They live under your
`raw_dir` (which is gitignored) and are never published; the public dataset is aggregated to street
segments. Do not commit raw reports — that is the one rule with no exceptions.

---

## 2. Writing a city config

Copy [`config/davis-demo.toml`](../config/davis-demo.toml) to `config/your-city.toml` and edit it.
Paths in the config resolve **relative to the config file's own directory**, so keep it next to (or
with sensible relative paths to) your data. Here is the demo, annotated for adaptation:

```toml
# config/your-city.toml
city = "Your City"
dataset_note = "Pilot dataset — community-collected, see DATA-CARD for limits."
exposure_unit = "bike trips"          # the human unit shown in the brief, e.g. "20 reports per 1000 bike trips"

streets  = "../data/your-city/streets.geojson"   # 1a above
reports  = "../data/your-city/reports.json"       # 1c above (private inputs; keep out of git if real)
exposure = "../data/your-city/exposure.json"      # 1b above

raw_dir = "../data/raw/your-city"     # PRIVATE, gitignored — precise reports live here
out_dir = "../data/published"         # open, committed — the published GeoJSON lands here

ref_lat = 38.5449                      # a reference point near your city centre; used by the
ref_lon = -121.7405                    # local equirectangular projection for distances

# gazetteer = "../data/your-city/gazetteer.json"   # optional; only if you accept address-only reports (section 3)

[thresholds]
snap_max_m = 25            # a report farther than this from any segment is left unsnapped
dedupe_window_s = 600      # two reports within this time AND distance are treated as duplicates
dedupe_distance_m = 15
small_n = 5                # at or below this report count, a segment is labelled "uncertain"
min_publish_n = 3          # k-anonymity floor: segments with 0 < reports < this are WITHHELD entirely
rate_per = 1000            # rates are expressed per this many exposure units
confidence_z = 1.96        # 95% confidence interval
fdr_alpha = 0.05           # Benjamini-Hochberg false-discovery-rate level for hotspot significance
gi_band_m = 300            # Getis-Ord Gi* neighbourhood distance band
kde_bandwidth_m = 150      # kernel density bandwidth
kde_grid = 20              # KDE grid resolution
```

Keys worth thinking about for a real city:

- **`min_publish_n`** (default 3) is the privacy floor. Any segment with a non-zero report count below
  it is withheld from the GeoJSON, the metadata, and the brief, so no published place can mean "one or
  two people reported here." Raise it if your community is small and re-identification risk is higher;
  do not lower it below 3 without reading [`docs/THREAT-MODEL.md`](THREAT-MODEL.md).
- **`small_n`** (default 5) controls the "uncertain" label, not withholding. A segment above
  `min_publish_n` but at or below `small_n` is published but flagged as low-confidence.
- **`exposure_unit`** is a string, purely cosmetic but important for honesty: it is what the brief
  prints ("reports per 1000 **bike trips**"). Make it match what your `estimate` actually counts.
- **`dataset_note`** is a provenance label carried into the brief and the published metadata. Use it
  to mark a dataset as a pilot, synthetic, or community-collected, so a reader knows what they are
  looking at.
- **`ref_lat` / `ref_lon`** anchor the local planar projection used for all distance math. Any point
  near your city centre is fine; precision here does not matter, but being on the wrong continent
  does.
- **`fdr_alpha`** is the multiple-comparison correction level for Getis-Ord significance. Leave it at
  0.05 unless you have a reason and have read the methodology.

Config is loaded by [`src/nearmiss/config.py`](../src/nearmiss/config.py); a missing required key or a
non-numeric threshold is a clean configuration error, not a stack trace. TOML is the documented
format; JSON also loads.

---

## 3. Address-only reports: the offline gazetteer geocoder

If any of your reports use `address` instead of `lat`/`lon`, you need a **geocoder** to turn the text
into coordinates. nearmiss ships a pluggable `Geocoder` protocol
([`src/nearmiss/geocoder.py`](../src/nearmiss/geocoder.py)); the **default is an offline
`GazetteerGeocoder`** backed by a small address-to-coordinate table you supply. It is offline and
deterministic on purpose, so the demo and the tests run anywhere with no network and no API key.

You opt in by setting the `gazetteer` key in your config to a JSON file:

```toml
gazetteer = "../data/your-city/gazetteer.json"
```

The gazetteer JSON is a list of address → coordinate rows:

```json
{
  "addresses": [
    { "address": "B St & 3rd St, Davis CA", "lat": 38.5449, "lon": -121.7405 },
    { "address": "5th St & C St, Davis CA",  "lat": 38.5461, "lon": -121.7388 }
  ]
}
```

How it behaves:

- Matching is **case-insensitive and whitespace-normalized**, so `"b st &  3rd st"` resolves the same
  as `"B St & 3rd St"`. It is otherwise exact: the address string has to be in the table.
- It is **deterministic**: the same address always maps to the same coordinate.
- A report whose address is **not** in the table is left unplaced. It is not snapped to an invented
  location; instead it is caught downstream as unsnapped (and counts toward your unsnapped total),
  which is the honest failure mode.
- If you do not set `gazetteer`, address-only reports stay unplaced. So if you accept addresses, you
  must provide a gazetteer.

A networked geocoder (e.g. Nominatim/OpenStreetMap) would implement the same one-method `Geocoder`
protocol and could be dropped in — but **it is intentionally not the default and is not provided**.
The analysis is designed to run with no external service. If you want online geocoding you will write
that adapter yourself; see [section 5](#5-what-you-still-have-to-do-yourself-honestly).

---

## 4. Running it

Once the three files and the config exist, the whole thing is one command:

```bash
# Full pipeline end to end: intake -> dedupe/geocode/snap/classify/quality -> analyze -> publish -> brief
nearmiss run --config config/your-city.toml
```

That writes the published GeoJSON to your `out_dir` as `<city-slug>.geojson` (e.g. `your-city.geojson`)
plus a content-hashed sidecar `<city-slug>.metadata.json`, and prints a summary. To also write the
advocacy brief to a file, add `--out`:

```bash
nearmiss run --config config/your-city.toml --out build/brief.md
```

Render the brief in **Spanish** instead of English with `--lang es` (the default is `en`):

```bash
nearmiss run   --config config/your-city.toml --lang es --out build/brief.es.md
nearmiss brief --config config/your-city.toml --lang es          # brief only, to stdout
```

The bilingual brief (via [`src/nearmiss/i18n.py`](../src/nearmiss/i18n.py)) carries a plain-language
glossary, a bottom-line sentence, the exposure unit you configured, and a bias counterweight, in
whichever of the two supported languages you choose; an unknown language falls back to English.

You can also run the stages individually for debugging:

```bash
nearmiss intake   reports.json --config config/your-city.toml    # validate into the private raw store
nearmiss pipeline --config config/your-city.toml --dump          # print the intermediate clean records
nearmiss analyze  --config config/your-city.toml                 # rates + CIs + bias + KDE + Getis-Ord
nearmiss publish  --config config/your-city.toml                 # build the open GeoJSON + metadata
```

Finally, serve the accessible map and its equivalent sortable data table (read-only) over the
published artifacts:

```bash
nearmiss serve                # serves the repo; open the web view in a browser
```

Reproducibility check: `make reproduce` rebuilds the published dataset and asserts a clean
`git diff` on `data/published/`. If your run is deterministic, re-running it changes nothing.

---

## 5. What you still have to do yourself (honestly)

Adapting nearmiss to a real city is mostly *data* work, not code work, and the hard parts are
genuinely hard. The tool will not paper over them, and this section is the honest list so you can plan
the effort.

- **Source real exposure data — this is the long pole.** The Davis demo ships *synthetic* exposure.
  For a real rate you need a real denominator per segment: a bike/pedestrian count program,
  manual or sensor counts, a travel-demand model, or a purchased exposure layer
  (Strava Metro, StreetLight, Replica). Acquiring, cleaning, and joining that to your `segment_id`s is
  the bulk of the work, and rule 1 means you cannot publish a risk rate for any segment you cannot
  give a denominator. Plan for partial coverage at first; the brief will report it honestly.
- **The default geocoder is an offline table, not a real geocoding service.** The
  `GazetteerGeocoder` only knows the addresses you put in its JSON. If your contributors type free-form
  addresses you have not pre-loaded, those reports go unplaced. A networked geocoder (Nominatim, etc.)
  is *not* provided; if you need one you will implement the `Geocoder` protocol yourself, and then you
  own its rate limits, network failure modes, and the privacy implications of sending addresses to a
  third party.
- **Get real street names.** The pipeline is only as legible as your `name` properties. Placeholder
  ids (`seg-01`) make an unreadable brief. Real block names (`"5th St (C–D)"`) are what make the output
  usable in front of a city council — and that mapping is yours to build for your street network.
- **Build the segment network itself.** Someone has to decide what a "segment" is for your city
  (block-by-block centerlines, with stable ids) and produce that GeoJSON. OSM or a city centerline
  file is a starting point, but segmenting and assigning durable ids is a real task.
- **Do the manual accessibility audit.** nearmiss runs an automated `axe-core` check (`make axe`) and
  a structural gate (`make verify`), and the data table is built for keyboard and zoom use. But
  automated checks are not a screen-reader pass. The **manual NVDA/VoiceOver review is still pending**
  for the project itself, and it would be pending for your deployment too. Do not claim full WCAG
  conformance on the strength of the automated run alone.
- **Own the privacy decision.** `min_publish_n` defaults to 3, but the right floor depends on your
  community's size and re-identification risk. Read [`docs/THREAT-MODEL.md`](THREAT-MODEL.md) before
  you publish, and treat raw reports as private data you are responsible for — they are never
  committed.

None of this is a reason not to start. It is a reason to start with eyes open: stand up the pipeline
on whatever exposure you can get, publish with honest coverage and caveats, and improve the inputs
over time. The statistics are built to tell the truth about thin data, not to hide it.

---

## 6. A minimal checklist

1. Copy `config/davis-demo.toml` → `config/your-city.toml`; set `city`, the three paths, `raw_dir`,
   `out_dir`, `ref_lat`/`ref_lon`, `exposure_unit`, and `dataset_note`.
2. Produce `streets.geojson` (`LineString` features with `segment_id` + real `name`).
3. Produce `exposure.json` keyed by the **same** `segment_id`s (`estimate`/`source`/`date`).
4. Collect `reports.json` (each with `lat`/`lon` **or** `address`); keep raw reports private.
5. If you accept addresses, add a `gazetteer.json` and set the `gazetteer` config key.
6. Review thresholds, especially `min_publish_n` (privacy floor) and `small_n`.
7. `nearmiss run --config config/your-city.toml [--lang es] [--out build/brief.md]`.
8. `nearmiss serve` to read the accessible map + table.
9. Read the brief's exposure-coverage and bias sections before you put a number in front of anyone.

When in doubt, diff your files against the committed Davis fixtures in
[`tests/fixtures/davis/`](../tests/fixtures/davis/) — they are the known-good shape.
