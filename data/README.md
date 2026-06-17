# Data

Two strictly separated worlds, because contributor privacy is hard rule #4.

## `raw/` — private, never committed

Precise, un-jittered reports as they arrive. This directory is **gitignored** and must never be added
to version control (not even with `git add -f`). Precise coordinates plus timing can identify a
person's routine, so they stay private. See [`docs/THREAT-MODEL.md`](../docs/THREAT-MODEL.md).

## `published/` — open and committed

The aggregated, **jittered** public dataset: open GeoJSON aligned to
[`schema/dataset.schema.md`](../schema/dataset.schema.md), plus the
[data card](../docs/DATA-CARD.md). Every rate here is exposure-normalized and carries a confidence
interval and an `n`. Home-end coordinates are fuzzed; no record is published at a precision that could
expose an individual.

`publish.py` is the only path from `raw/` to `published/`, and it applies the aggregation and jitter.
If you change publication precision, aggregation, or jitter, you are editing a **privacy control** —
flag it explicitly in your pull request.
