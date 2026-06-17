# `nearmiss` — package source

The analysis engine. Each stage is a pure, recorded transform that emits plain, inspectable data, so
any stage can be piped, checked, or replaced independently.

| Module | Responsibility |
| --- | --- |
| `intake.py` | Validate incoming reports against [`schema/report.schema.json`](../../schema/report.schema.json) and land them in the private raw store. |
| `pipeline/` | `dedupe.py`, `geocode.py`, `snap.py`, `classify.py`, `quality.py` — clean and structure raw reports. |
| `exposure.py` | Attach an exposure denominator per segment (counts, demand model, or exposure layer), recording source and date. |
| `stats/` | `rates.py` (rates + confidence intervals), `bias.py` (reporting-bias characterization), `kde.py`, `getis_ord.py` (Getis-Ord Gi\*). |
| `publish.py` | Build the open GeoJSON and the aggregated, jittered public dataset; apply privacy fuzzing. |
| `brief.py` | Render advocacy briefs (ranked locations, intervals, plain-language prose). |
| `server.py` | Serve the accessible, read-only map and its equivalent sortable list/table view. |
| `config.py` | Cities, exposure sources, thresholds, and jitter as versioned, checked-in configuration. |

> Status: **beta.** Module surfaces and contracts are documented; see the [roadmap](../../README.md#roadmap)
> for what each phase delivers. The [methodology](../../docs/METHODOLOGY.md) is the authority for every
> statistical choice made here.
