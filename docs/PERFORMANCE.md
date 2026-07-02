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
```

`tools/benchmark.py` generates a deterministic synthetic city in memory and times
the pipeline, the statistics (including the O(M²) Getis-Ord step), and the GeoJSON
build.

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
