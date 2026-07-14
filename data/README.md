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

### Annual public FARS context

The nationwide evidence ledger uses a separate aggregate-only release set:

- `fars-YYYY-state-mode.json` is the immutable revision-1 artifact; a later reviewed revision uses
  `fars-YYYY-state-mode-rN.json`. Every one of
  the 51 jurisdictions carries all six canonical modes. A cell below the publication floor, or a
  true zero, has only `status: "suppressed_or_zero"`; it never carries a numeric value.
- `fars-state-mode-index-v2.json` is the current canonical allowlist of released years. Each entry
  pins the
  annual artifact's exact byte length and SHA-256 plus the reviewed NHTSA archive, revision, and
  fixed-year geography crosswalk. It also binds the exact annual source-contract digest, semantic
  regime, crash/person mapping versions, and state-code system so cross-year comparisons cannot
  silently assume that classification stayed unchanged.
- `fars-state-mode-index.json` and `fars-2024-state-mode.json` retain the immutable first publication.
  `fars-release-corrections.json` pins those exact bytes and their replacements after the 2024 source
  stage was corrected from `final` to NHTSA's `annual_report_file` classification.

The checked-in index contains the independently reviewed **2020–2024** annual release set. Pinned
source archives or private activation proofs alone do not make a public result available. A year
enters the index only after its canonical public artifact has been generated from the exact verified
annual snapshot and independently reviewed.

Rebuild the index from an explicit set of reviewed annual artifacts (never by directory discovery):

```bash
python tools/build_fars_public_index.py \
  --artifact data/published/fars-2020-state-mode.json \
  --artifact data/published/fars-2021-state-mode.json \
  --artifact data/published/fars-2022-state-mode.json \
  --artifact data/published/fars-2023-state-mode.json \
  --artifact data/published/fars-2024-state-mode-r2.json \
  --out data/published/fars-state-mode-index-v2.json
```

Repeat `--artifact` exactly once for every reviewed production artifact. The Pages build rejects
digest drift, noncanonical JSON, any unindexed FARS-namespaced JSON, missing files,
private/unexpected fields, source-contract mismatches, and symlinks before copying published data.

For the 2024 provenance correction, rebuild the exact ledger only from both immutable generations:

```bash
python tools/build_fars_correction_ledger.py \
  --prior-artifact data/published/fars-2024-state-mode.json \
  --replacement-artifact data/published/fars-2024-state-mode-r2.json \
  --prior-index data/published/fars-state-mode-index.json \
  --replacement-index data/published/fars-state-mode-index-v2.json \
  --out data/published/fars-release-corrections.json
```
