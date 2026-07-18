# `nearmiss` — package source

The analysis engine. Each stage is a pure, recorded transform that emits plain, inspectable data, so
any stage can be piped, checked, or replaced independently.

| Module | Responsibility |
| --- | --- |
| `intake.py` | Validate incoming reports against [`schema/report.schema.json`](../../schema/report.schema.json) and land them in the private raw store. |
| `pipeline/` | `dedupe.py`, `geocode.py`, `snap.py`, `classify.py`, `quality.py` — clean and structure raw reports. `geocode.py` is currently a pass-through adapter seam for coordinate-bearing reports; real address geocoder adapters are still pending. |
| `exposure.py` | Attach an exposure denominator per segment (counts, demand model, or exposure layer), recording source and date. |
| `stats/` | `rates.py` (rates + confidence intervals), `bias.py` (reporting-bias characterization), `kde.py`, `getis_ord.py` (Getis-Ord Gi\*). |
| `publish.py` | Build the open GeoJSON and the segment-aggregated public dataset; enforce the k-anonymity withholding and coordinate-leak invariants (no jitter — privacy comes from snap-to-segment aggregation and withholding, see [`docs/RE-IDENTIFICATION.md`](../../docs/RE-IDENTIFICATION.md)). |
| `brief.py` | Render advocacy briefs (ranked locations, intervals, plain-language prose). |
| `dossier.py` | Render a deterministic, controlled-claim corridor dossier with a named decision request and evidence-readiness record. |
| `server.py` | Serve the accessible, read-only map and its equivalent sortable list/table view. |
| `config.py` | Cities, exposure sources, and privacy/analysis thresholds (snap distance, `min_publish_n`, `small_n`) as versioned, checked-in configuration. |

> Status: **beta.** Every module above is implemented in pure, typed Python (the only runtime dependency
> is `jsonschema`) and covered by the known-answer test suite. The one pending piece in this package is
> the geocode stage: `pipeline/geocode.py` is a pass-through adapter seam for reports that already carry
> coordinates, and real address geocoder adapters have not landed yet. See the
> [roadmap](../../README.md#roadmap) for what each phase delivers. The
> [methodology](../../docs/METHODOLOGY.md) is the authority for every statistical choice made here.
