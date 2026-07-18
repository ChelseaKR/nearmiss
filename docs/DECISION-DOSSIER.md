# Decision Dossier generator

`nearmiss dossier` turns one already-published corridor into a deterministic Markdown
artifact for a specific decision. It is the first executable part of the local-first
Decision Dossier workflow; it is not a new risk score, reporting queue, or treatment
recommender.

```bash
nearmiss dossier \
  --config config/davis-demo.toml \
  --corridor corridor-dd8fbf5922ba \
  --decision-request "Schedule a daylight field review before the next capital-program cycle." \
  --out build/davis-5th-st-dossier.md
```

The command requires both a published `--corridor` id and a named `--decision-request`.
It rejects unknown corridor ids rather than selecting a location on the operator's behalf.
It can render in English or Spanish with `--lang en|es`.

## What it contains

- The one corridor’s exposure-normalized reported near-miss rate, interval, count, and
  constituent-block count.
- The analysis window, exposure provenance, corridor id, and a command to repeat the
  artifact from the same inputs.
- Declared source/evidence readiness when the city config names a source registry,
  including source freshness and missing-core-source warnings.
- A claim boundary and a next-review prompt.

## What it does not claim

The generator does not establish danger, fault, causation, an intervention’s likely
effect, or conditions for any individual trip. A corridor is only an aggregate of
already publishable, FDR-screened block results; it does not create another hotspot
test or disclose a withheld segment.

If no source registry is configured, the dossier says so explicitly. It does not infer
an evidence tier from report volume or silently label a city as measured or partner
reviewed.

For the manual companion structure and meeting fields, see the
[Decision Dossier template](DECISION-DOSSIER-TEMPLATE.md). For the staged product and
validation plan, see the [product expansion plan](PRODUCT-EXPANSION-PLAN.md).
