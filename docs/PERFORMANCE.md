# Performance

nearmiss is built for city-scale data (hundreds to low-thousands of segments,
thousands of reports), not for national datasets, and the implementation reflects
that: it is pure, typed standard-library Python with no native dependencies (see
[ADR-0003](adr/0003-pure-python-statistics-and-planar-geometry.md)). This page
gives real numbers rather than a claim, and is honest about the known scaling
limits.

## Benchmark

Run it yourself:

```bash
make bench                       # 300 segments, 6000 reports (defaults)
python tools/benchmark.py 800 20000   # a larger run
```

`tools/benchmark.py` generates a deterministic synthetic city in memory and times
the pipeline, the statistics (including the O(M²) Getis-Ord step), and the GeoJSON
build.

Representative figures (300 segments, 6,000 reports, on a developer laptop;
your numbers will differ):

| Stage | Time |
| --- | ---: |
| Pipeline (dedupe / geocode / snap / classify / quality) | ~3.8 s |
| Statistics (rates + CIs, bias, KDE, Getis-Ord Gi\*) | ~1.7 s |
| Build GeoJSON | <0.01 s |
| **Total** | **~5.5 s** (~1,100 reports/s) |

For a real city this is comfortably fast: a rebuild is seconds, well within the
scheduled-rebuild budget, and the analysis runs anywhere with no install beyond
`jsonschema`.

## Known scaling limits (honest)

- **Deduplication is O(n²) in the number of reports.** Each report is compared
  against the kept set. At a few thousand reports this is fine (most of the
  benchmark's pipeline time); at tens of thousands it would dominate. A spatial
  index (grid hash on the dedupe radius) would make it near-linear and is the
  obvious first optimization if a city outgrows the current approach.
- **Getis-Ord Gi\* is O(M²) in the number of segments** (a dense pairwise distance
  pass to build the distance-band weights). At a few hundred segments this is
  sub-second; for very large networks, precomputing a sparse spatial-weights
  matrix once would remove the repeated distance work.
- **No parallelism.** The pipeline and statistics run single-threaded. City-scale
  data does not need more; a much larger deployment would.

These are not yet bottlenecks at the scale nearmiss targets, but they are stated
here rather than discovered later — and the benchmark exists so a regression or a
too-large dataset shows up as a number, not a surprise.
