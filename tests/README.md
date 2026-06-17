# Tests

Every deterministic component — intake, each pipeline stage, and every statistic — is tested with
`pytest`. The defining feature of this suite is that the **answers are known**: `fixtures/` holds
synthetic report sets with **planted hotspots**, so the pipeline and the spatial statistics can be
validated against ground truth rather than against themselves.

- **Known-answer fixtures.** Recovering the planted hotspots (and only those) is the pass condition for
  the hotspot statistics. Interval-coverage checks validate the confidence intervals.
- **No real data, ever.** Fixtures are synthetic. No precise raw report is committed (hard rule #4);
  `data/raw/` is gitignored. See [`CONTRIBUTING.md`](../CONTRIBUTING.md).
- **Run them.** `make test` (or `pytest`). The full merge gate is `make verify`.

Determinism is a requirement: seeded pipelines and analyses produce the same dataset and figures every
run, which is what makes `make reproduce` a meaningful proof.
