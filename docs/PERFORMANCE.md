# Performance

nearmiss is built for city-scale data (hundreds to low-thousands of segments,
thousands to tens-of-thousands of reports), not for national datasets, and the
implementation reflects that: it is pure, typed standard-library Python with no
native dependencies (see [ADR-0003](adr/0003-pure-python-statistics-and-planar-geometry.md)).
This page gives real numbers rather than a claim, and is honest about the known scaling limits.

## Benchmark

Run it yourself:

```bash
make bench                            # 300 segments, 6000 reports (defaults)
python tools/benchmark.py 800 20000   # larger city
python tools/benchmark.py 5000 100000 # very large city
python tools/benchmark.py --json      # the same run, machine-readable
```

`tools/benchmark.py` generates a deterministic synthetic city in memory and times
the pipeline, the statistics (including the O(M²) Getis-Ord step), and the GeoJSON
build. It also counts the **work units** each stage performs, which is the half of
the benchmark a merge gate can hold a budget against — see
[The regression budget](#the-regression-budget) below.

Representative figures (on a developer laptop; your numbers will differ):

### City-scale (300 segments, 6,000 reports)

| Stage | Time |
| --- | ---: |
| Pipeline (dedupe / geocode / snap / classify / quality) | ~4.5 s |
| Statistics (rates + CIs, bias, KDE, Getis-Ord Gi\*) | ~2.8 s |
| Build GeoJSON | <0.01 s |
| **Total** | **~7.3 s** (~821 reports/s) |

### Large city (800 segments, 20,000 reports)

| Stage | Time |
| --- | ---: |
| Pipeline (dedupe / geocode / snap / classify / quality) | ~44 s |
| Statistics (rates + CIs, bias, KDE, Getis-Ord Gi\*) | ~10 s |
| Build GeoJSON | <0.01 s |
| **Total** | **~54 s** (~374 reports/s) |

The pipeline and statistics are accelerated by spatial indexing: snap, dedupe, KDE,
and Getis-Ord now use a uniform grid index to avoid O(n²) and O(M²) brute-force
distance passes. Results are identical to pre-indexed code.

For a real city this is comfortably fast: a rebuild is seconds to tens of seconds
depending on scale, well within the scheduled-rebuild budget, and the analysis
runs anywhere with no install beyond `jsonschema`.

## The regression budget

Every table above is a measurement with nothing behind it: they were taken on a
laptop, on a date, and until now no gate compared a new run to them. That is the
shape this project treats as a defect elsewhere, and the README's own Standards
Conformance table said so — "a merge-blocking regression budget remains open".

It is no longer open. `make perf-budget` runs inside `make verify` and inside CI's
required `reproducibility` job; it re-measures the 300-segment / 6,000-report
workload and fails when any budgeted metric is more than 10% off the committed
comparand, [`perf/baseline.json`](../perf/baseline.json), in that metric's declared
direction. The schema, the 10% rule and the baseline-update ritual are
[`docs/standards/PERFORMANCE-STANDARD.md`](standards/PERFORMANCE-STANDARD.md) §2.

**The budgeted numbers are work units, not the seconds above.** How many calls each
stage makes into `nearmiss`/`honest_rates` code, and how many of those are the four
geometry primitives every distance-based pass runs through. The synthetic city is
deterministic, so those counts are exact — identical between runs, and measured
identical on CPython 3.11.16 and 3.12.14 — whereas a wall-clock budget on a shared
CI runner would have to be either muted or accepted as intermittently red, and a
gate people re-run is a gate that has stopped gating.

Work units are also what the scaling limits below are about. Every acceleration on
this page is a spatial index pruning a candidate set; losing one takes the counts
quadratic while a 300-segment demo still finishes in seconds and every existing
test still passes. Measured, on a deliberately un-pruned index at 60 segments /
1,200 reports: `pipeline_calls` 105,718 → 2,331,736.

**What the budget cannot see:** a constant-factor slowdown inside an unchanged
number of calls moves the seconds in the tables above and leaves every work unit
where it was. Nothing here will fail on it. That stays a review responsibility —
the `City-scale performance (wall clock)` REVIEW row in
[`ROADMAP.md`](ROADMAP.md) — and [`perf/README.md`](../perf/README.md) is where the
whole design, including this gap, is written down.

```bash
make perf-budget     # the gate
make perf-baseline   # ratchet the baseline after an improvement (review the diff)
```

## Known scaling limits (honest)

- **Deduplication uses spatial bucketing** on the `dedupe_distance_m` grid.
  At tens of thousands of reports, this makes the stage near-linear.
- **Getis-Ord Gi\* uses spatial indexing** to prune the pairwise distance pass
  from O(M²) to near-linear in typical city networks. At a few thousand segments
  this is sub-second; for very large networks (>10k segments), precomputing a
  sparse graph-based weights matrix once would offer further speedup.
- **Snap and KDE both use spatial indexing** to accelerate candidate queries,
  lifting the practical ceiling from ~10³ to ~10⁴–10⁵ segments without breaking
  ADR-0003's no-native-deps rule.
- **No parallelism.** The pipeline and statistics run single-threaded. City-scale
  data does not need more; a much larger deployment would.

These spatial indexes are internal accelerators: all output is numerically identical
to the pre-indexed code, so correctness and reproducibility are maintained.
