# Teaching module — *"How to lie with heat maps"* (EXP-12)

A short, hands-on workshop for journalism and civic-data audiences on how a
raw-count heat map misleads, and how exposure normalization, confidence
intervals, and honest hotspot statistics put it right. Everything runs on the
project's **synthetic Davis fixtures** — a known-answer street grid with a
planted hotspot and a *busy decoy* — so there is no real, sensitive data
anywhere in the exercise.

Every notebook is **bilingual** (English + Spanish prose in each markdown cell,
matching the repo's i18n discipline), **seeded / deterministic** (no RNG, no
network — the executed notebooks are byte-identical across runs), and imports
**only** `nearmiss.*` and `IPython.display`: the figures are hand-built SVG, the
same no-plotting-dependency approach as [`src/nearmiss/figures.py`](../../src/nearmiss/figures.py).

## The notebooks

1. **[`01-the-naive-map.ipynb`](01-the-naive-map.ipynb) — The naive map.**
   Renders the same reports twice: a raw report-count heat map (*the lie*) and
   the exposure-normalized rate map (*the honest reading*). The busy decoy
   `seg-03` burns brightest on the left and dissolves on the right; the planted
   `seg-06` corridor emerges as the real hotspot. This is threat-model **T4** —
   a naive consumer misreading a raw-count map as danger — made visible.

2. **[`02-find-the-decoy.ipynb`](02-find-the-decoy.ipynb) — Find the decoy *(exercise)*.**
   Participants rank the twelve analyzed blocks by raw count, compute
   exposure-normalized rates with 95% Poisson confidence intervals using the
   real pipeline function (`nearmiss.stats.rates.rate_with_ci`), and identify the
   segment that falls furthest between the two rankings. The *Solution* section
   at the end confirms `seg-03` as the decoy and `seg-06` as the true hotspot,
   cross-checked against the pipeline.

3. **[`03-break-the-ci.ipynb`](03-break-the-ci.ipynb) — Break the CI *(re-segmentation)*.**
   The modifiable areal unit problem (MAUP): *split* a borderline segment to
   **manufacture** a "significant" Getis-Ord Gi\* hotspot, then *merge* the real
   corridor to **dissolve** the genuine one — same reports, opposite findings.
   Uses the exact hotspot API the tests exercise (`getis_ord_star`,
   `two_sided_p`, `benjamini_hochberg`; see
   [`tests/test_fdr.py`](../../tests/test_fdr.py) and
   [`tests/test_hotspot.py`](../../tests/test_hotspot.py)) and shows why FDR
   control cannot save you from a rigged unit of analysis.

## Running them

```bash
make teach            # execute all three into notebooks/_build/ (gitignored)
```

`make teach` installs the isolated `.[teaching]` extra (Jupyter execution stack,
kept out of `dev` so the `pip-audit` security gate is unchanged) on demand and
runs `nbconvert --execute` with per-cell timestamps stripped, so the output is
deterministic. A dedicated CI job (`teaching`) runs the same command on every
push, so a red cell — meaning the analysis API or the fixtures drifted — blocks
the merge. `make clean` removes `notebooks/_build/`.

## Facilitator guide

A 90-minute workshop plan, learning objectives, discussion prompts keyed to
threat-model **T4**, and an answer key are in
[`docs/teaching/FACILITATOR-GUIDE.md`](../../docs/teaching/FACILITATOR-GUIDE.md)
(English) and its parallel Spanish translation
[`FACILITATOR-GUIDE.es.md`](../../docs/teaching/FACILITATOR-GUIDE.es.md).
