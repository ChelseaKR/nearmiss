# Notebooks — the reproducibility backbone

Every figure and number in an advocacy brief is produced by a notebook here, from the raw inputs.
`make reproduce` runs them end to end; a claim no notebook can regenerate is not published.

The notebooks are **deterministic** (seeded) and cover:

- **Hotspots** — kernel density surfaces (labeled as report intensity unless exposure-normalized) and
  Getis-Ord Gi\* significant clusters.
- **Trends** — change over time, with intervals.
- **Exposure sensitivity** — how conclusions shift under different exposure denominators, stated openly
  rather than hidden.

Each notebook records its inputs, the exposure source and date, and the thresholds used, so a figure
traces back through statistic → cleaned dataset → raw reports. See
[`docs/METHODOLOGY.md`](../docs/METHODOLOGY.md).
