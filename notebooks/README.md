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

## Teaching module — *"How to lie with heat maps"*

[`teaching/`](teaching/README.md) is a hands-on workshop for journalism and civic-data audiences: three
bilingual (EN/ES), deterministic notebooks built entirely on the synthetic Davis decoy fixtures, plus a
90-minute [facilitator guide](../docs/teaching/FACILITATOR-GUIDE.md). It shows how a raw-count heat map
misleads (the busy decoy `seg-03`), how exposure normalization corrects it, and how re-segmentation can
manufacture or dissolve a "significant" hotspot. Run them with `make teach`; a CI job executes them on
every push.
