# Potsdam: the first real-city run, and what its MAUP check actually found

**Date:** 2026-08-15. **Run performed:** 2026-07-15/16, with `nearmiss` 0.2.0.
**Re-verified:** 2026-08-15 against `main` at `c3ced50`; the rank-stability result below is
byte-identical on re-run, so the finding is a property of the method and the data, not of
the build that happened to produce it.

Every committed city dataset in this repository — `davis`, `riverside` — is synthetic, with
hotspots that were planted in the fixture and are therefore there to be found. This is the
one time the pipeline has been run end to end against a real city, and it is the only time
its answers were not arranged in advance.

## What was run

Potsdam, Germany, 2023-11-27 to 2023-12-31.

| Input | Source | Licence |
| --- | --- | --- |
| Streets, 8,129 segments | OpenStreetMap Brandenburg extract via Geofabrik, 2026-07-15 | ODbL 1.0 |
| Reports, 389 in the window | SimRa annotated bicycle near-misses, `Berllin_2023_12` | CC BY-NC 4.0 plus SimRa Terms of Use |
| Exposure, 124 segments | Distinct SimRa rides per segment, derived from 309 ride GPS traces, floored at 5 rides | CC BY-NC 4.0 plus SimRa Terms of Use |

The exposure layer is the part that had never existed before. It is built by snapping every
GPS point of every ride trace to the street network and counting *distinct rides* per
segment, then discarding any segment traversed by fewer than five distinct rides. Numerator
and denominator therefore come from the same rider pool, which is the right shape for a rate
and the wrong shape for generalising to all cyclists — SimRa riders are a self-selected app
population, and nothing here corrects for that.

### What is published here and what is not

No SimRa-derived file is committed, and this entry does not change that. `docs/DATA-CARD.md`
states that a dataset containing SimRa reports is not distributable under Apache-2.0 alone
and that aggregation does not dissolve the NonCommercial clause; the run's outputs
(`potsdam.geojson`, the exposure layer, the reports extract, the generated brief) stay
uncommitted for that reason.

What this entry does publish is the project's own analysis of its own method: unit counts,
coverage fractions, dispersion, Gi\* z-scores, re-segmentation results, and segment geometry
lengths. Those are facts about how the tool behaved, not a redistribution of SimRa records.
Where a rate appears below it carries its `n`, because publishing a rate without its count
would violate the project's second hard rule in order to satisfy a licence question — the
handful of segment-level counts here are aggregates over a 389-record extract, not a
substantial part of the SimRa database. OSM way identifiers and street names are ODbL facts
used as a produced work, with attribution above.

That is a judgment call, not a legal opinion, and it is the narrow version of the written
licensing decision this project still owes itself. If the decision comes out stricter, the
numbers to remove are the per-segment `n` values; everything else in this entry survives.

## Finding 1 — coverage is thin in segments and dense in reports

`exposure_coverage` is **0.0153**. Denominators exist for 124 of 8,129 segments, and 107 of
those clear publication, so the rate ranking rests on **1.3% of the network**.

That number reads like a disqualification and is not one, because reports are not spread
evenly over the network either:

- 387 of 389 reports snapped to a segment (1 unsnapped, 1 duplicate removed, 0 out of window).
- **351 of those 387 — 90.7% — landed on a segment that has a denominator.**
- 33 published segments carry at least one report. 25 more were withheld under the
  k-anonymity floor (`min_publish_n = 3`), carrying 27 reports between them.

So the correct statement is not "we can only see 1.5% of Potsdam." It is: the SimRa rider
pool concentrates on a small, heavily-ridden subnetwork, and that subnetwork is where both
the reports and the denominators are. Coverage is thin because the k≥5 ride floor is a
privacy control that most quiet residential blocks cannot clear, not because the denominator
derivation failed.

Two consequences that do bite:

- **The denominators are tiny.** Across the 124 rated segments the exposure ranges from 5 to
  34 distinct rides, median 8. A rate of "228.57 reports per 100 observed rides" is
  arithmetically sound and means more than two reported conflicts per traversal; it is not a
  per-traversal risk probability, and it is not stable against one more rider showing up.
- **Sparse denominators make a local statistic less local.** The rate field is defined on 124
  of 8,129 segments, so a Gi\* neighbourhood that looks well-populated on the street network
  is often nearly empty in the value field. This is the mechanism behind Finding 3.

The tool's own coverage tiering got this right without being asked. `nearmiss coverage
--config potsdam.toml` returns `evidence_tier: modeled_city`, not `measured_city`: the
registry declares `measured_min_coverage = 0.8` and observed coverage is 0.0153, so promotion
is refused and the run is labelled as one where "segment rates are possible, but observed
exposure is incomplete." That is the honest-coverage machinery working at its limit, on real
data, unprompted.

## Finding 2 — the MAUP check reported a failure, and "failure" here means something specific

From `potsdam.metadata.json`:

| Field | Value |
| --- | --- |
| `fine_units` | 8,129 |
| `coarse_units` | 4,065 |
| `top_hotspot_segment` | `osm-w4782819-2` (Kaiser-Friedrich-Straße) |
| `top_hotspot_coarse_rank` | **1** |
| `top_hotspot_still_significant` | **false** |
| `top_hotspot_survives` | **false** |
| `topk_overlap` | 0.6667 |

`stats/maup.py` defines `survives` as `coarse_rank == 1 and still_significant`. Here the first
conjunct holds and the second does not. **The top hotspot did not dissolve. It kept its rank
and lost its significance.** Anyone reporting this run as "the top hotspot disappeared under
re-segmentation" would be overstating it in the direction that flatters the check.

What actually changed, at the coarser scale:

- Kaiser-Friedrich-Straße stays the highest-rate unit (228.57 per 100 rides, unchanged,
  because its re-segmentation partner has no denominator and contributes nothing to either
  side of the ratio), but its Gi\* z falls from **5.407 to 2.258** (p = 0.0240). With
  Benjamini-Hochberg over 89 rated coarse units its critical value at that rank is 0.0039, so
  it is not rejected.
- The second fine-scale hotspot, `osm-w4782819-1`, misses by a hair: p = 0.0023367 against a
  BH critical value of 0.0022472. Four parts in a hundred thousand.
- Three coarse units *are* significant, and all three are the Amundsenstraße group. The
  highest coarse z in the whole run, 3.584, belongs to a unit that was not the fine-scale
  leader at all.

So the check did not return "nothing survives." It returned **"a different thing survives
than the one at the top of your table"** — which is the more useful answer and the harder one
to get from a synthetic fixture.

## Finding 3 — why it lost significance, and why that is a tool defect rather than a fact about Potsdam

This is the part worth the write-up.

Gi\* neighbours in this pipeline are street-network neighbours within `gi_band_m` (300 m).
`network.py` builds the graph by joining segments that share an endpoint, and weights each
edge as **half of each segment's length**, because `polyline_centroid` puts a segment's
representative point at its midpoint. A band-bounded Dijkstra then collects everything within
300 m.

That construction has an arithmetic consequence nothing in the repository currently states:

> **A segment longer than twice the band can never reach any neighbour.** Its own half-length
> already exceeds the band, so every edge out of it is over budget before the neighbour's
> half-length is added.

Measured on this network: 87 of 8,129 segments are ≥ 600 m, and **all 87 have a Gi\*
neighbourhood consisting of themselves alone.** In total 148 segments (1.82%) get a singleton
neighbourhood, of which only 20 are genuinely disconnected in the graph; the other 128 have
real street adjacency and are excluded purely by this arithmetic. Their median length is 675 m.

`osm-w4782819-2` is **597.1 m long**. It shares an *exact* endpoint with `osm-w4782819-1`
— both polylines contain the coordinate (52.4052507, 13.0074463) — so the two are adjacent in
the graph. The edge between them weighs 597.1/2 + 449.6/2 = **523.4 m**, well over the 300 m
band, so neither appears in the other's neighbourhood.

When a unit's neighbourhood is just itself, Gi\* is not a cluster statistic. With binary
weights and `w_sum = 1`, the formula collapses to (x_i − mean) / population SD over the value
set. For this run the 124 rated segments have mean 18.6435 and population SD 38.8214, so:

- (228.5714 − 18.6435) / 38.8214 = **5.4075**, the reported z of 5.407.
- `osm-w4782819-1` has three network neighbours, but neither of the other two has a
  denominator, and `honest_rates.hotspot.getis_ord_star` ignores neighbour ids absent from the
  value map. Its neighbourhood is effectively singleton too:
  (171.4286 − 18.6435) / 38.8214 = **3.9356**, the reported 3.936.

**Two of the four fine-scale "significant clusters," including the top one, are not cluster
statistics at all — they are global z-scores of a single segment, presented with a Gi\* label
and a ★.** Only 3 of the 124 rated segments have a degenerate neighbourhood, so this is rare;
it just happens to have hit the two segments at the top of the table.

Re-segmentation is what exposed it. Pairing `osm-w4782819-2` with a shorter neighbour gave the
merged unit reachable neighbours for the first time — rates of 0.00, 0.00, and 41.67 — and the
statistic reverted to measuring what it claims to measure. The z of 2.258 is the honest one.
The 5.407 was an artefact of the band-versus-length interaction.

The clusters that survived are the ones that had genuine neighbourhoods all along:
Amundsenstraße `osm-w220883650-2` had five rated neighbours at the block scale (z = 3.437) and
remains significant at the coarser scale (z = 3.220).

## What this run supports, and what it does not

**Supported.**

1. The MAUP rank-stability check works, and it earned its place. Run once against reality it
   separated a scale-robust cluster from an artefact, and it did so on the project's own
   headline result rather than on a convenient one.
2. `evidence_tier` correctly refused to call Potsdam a measured city at 1.5% coverage.
3. The exposure derivation from ride traces is viable: 91% of snapped reports landed on a
   segment with a denominator, which is a far better join rate than the segment-coverage
   figure suggests.
4. There is a real defect: Gi\* is reported for units whose neighbourhood is a singleton,
   where it is a global z-score wearing a local statistic's name, and long segments fall into
   that state deterministically rather than by accident.

**Not supported.**

1. *"The method finds nothing on real data."* False. Three significant clusters survive
   re-segmentation.
2. *"The top hotspot dissolves."* False, and it is the specific overstatement this entry
   exists to prevent. Rank 1 held; significance did not.
3. *"1.5% coverage means the result is uninterpretable."* Too strong. Coverage is thin in
   segments and dense in reports. What thin coverage genuinely costs is neighbourhood density
   for the spatial statistic, which is Finding 3, not the rate ranking itself.
4. Anything about Potsdam's actual street safety. A 389-report, one-month, self-selected
   sample with denominators on 1.3% of the network is a method test, not a safety assessment.
   Kaiser-Friedrich-Straße is not hereby called dangerous, and Amundsenstraße is not hereby
   called the most dangerous street in Potsdam.

## Follow-on work this generates

- Surface the singleton-neighbourhood case in the output instead of silently emitting a z.
  Either suppress `significant` for a unit whose Gi\* neighbourhood is a singleton, or flag it
  in `quality_flags` so a ★ in the brief always means a cluster. Filed as
  [#193](https://github.com/ChelseaKR/nearmiss/issues/193), which also records why neither
  committed fixture catches this: `davis`'s longest segment is 178 m, under a third of the
  600 m at which the arithmetic below starts to bite, so the case is structurally unreachable
  there; `riverside` is 6 segments that are *all* singletons, so every Gi\* z it publishes is
  already a global z-score, and it ships no ★ only because Benjamini-Hochberg rejected them.
- Reconsider the `gi_band_m`-versus-segment-length interaction — same issue. A band that cannot
  span the units it is applied to is a configuration error the tool should detect and say so,
  since the affected segments are exactly the long arterials most likely to carry reports.
- Commit the two derivation tools (`build_simra_exposure.py`, `extract_osm_pbf.py`). They are
  code, not data, and they are the only working implementation of ride-trace exposure that
  exists.
- Correct the licence stamp in the metadata writer. `potsdam.metadata.json` records
  `license: "Apache-2.0"` while its own `dataset_note` says the inputs are CC BY-NC 4.0 plus
  ODbL 1.0. A derived artifact should record the most restrictive inherited terms.
- Answer the licensing question in writing, per the checklist `CONTRIBUTING.md` points at,
  rather than resolving it case by case as this entry has had to.

## Reproducing this

The inputs are not committed and cannot be. To rebuild the run from scratch: fetch the SimRa
`Berllin_2023_12` release and a Geofabrik Brandenburg extract, clip both to
12.95–13.15 E / 52.35–52.50 N, derive the exposure layer with the ride-trace aggregator at a
minimum of five distinct rides, and run the pipeline against a config with the thresholds
recorded in the run manifest (`snap_max_m = 30`, `min_publish_n = 3`, `small_n = 5`,
`rate_per = 100`, `fdr_alpha = 0.05`, `gi_band_m = 300`, `overdispersion_adjust = true`).

Overdispersion for the record: quasi-Poisson Pearson φ = 7.7192, so the Poisson intervals were
widened by up to 2.78×, and that factor is an upper bound because genuine between-segment
variation inflates φ too.
