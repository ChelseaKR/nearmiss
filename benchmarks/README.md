# nearmiss planted-truth benchmark suite

**Version 1.0.0.** A versioned, seeded, public benchmark suite for
hotspot-detection methods: synthetic cities with a KNOWN answer (which
segments are truly elevated risk, which are decoys, which are statistical
traps) that any tool — not just nearmiss — can run itself against, in the
spirit of `docs/ideation/03-expansions.md` EXP-09.

`tools/make_fixtures.py` and `tools/benchmark.py` already generate one
hand-tuned synthetic city each (a fixed known-answer test fixture, and a
size-scalable timing benchmark). This suite generalizes that idea: one
generator, several regimes, each varying exactly one honesty-relevant axis,
plus a scorer that turns "did the tool find the planted hotspot" into
numbers.

## Why

A heat map of raw report counts lies in at least four well-understood ways:
it can't tell "dangerous" from "busy" (needs exposure normalization), it
can't tell "dangerous" from "more reported" (reporting bias — exposure
normalization does NOT fix this), its confidence intervals silently assume
Poisson variance (overdispersion breaks that), and its answer can change
depending on how you draw segment boundaries (MAUP) without the underlying
risk changing at all. Each is a controlled regime in this suite. nearmiss
scores itself and publishes the result in [SCORECARD.md](SCORECARD.md),
including where it does NOT come out perfect — the point of a benchmark
suite is to be the referee, not just a contestant with a home-field
advantage.

## Layout

```
benchmarks/
  generator.py           seeded, parameterized synthetic-city generator
  scorer.py               scores nearmiss OR any other tool's results against ground truth
  configs/*.json           one regime config per city (the generator's input)
  schema/results.schema.json   common format for "bring your own tool" scoring
  cities/<regime>/          FROZEN generated output (committed) -- the benchmark itself
    streets.geojson           public street network
    exposure.json              per-segment exposure denominators
    reports.json                synthetic report records (same shape as a real intake)
    ground_truth.json           the known answer: role + true rate per segment (NEVER given to a tool being scored)
    config.toml                 ready-to-use nearmiss Config for this city
    scorecard.json               nearmiss's own score on this city (see scorer.py)
  SCORECARD.md              nearmiss's published scorecard, human-readable, with commentary
```

## Regimes

| Regime | Varies (vs. `baseline`) | Tests |
|---|---|---|
| `baseline` | nothing — pure Poisson, no bias, no exposure error | control |
| `reporting_bias` | a subset of segments report 5x as often per incident, same true risk | risk vs. reporting-propensity confound |
| `overdispersion` | incident counts drawn Gamma-Poisson (negative binomial, φ=0.6) | confidence-interval honesty under non-Poisson variance |
| `exposure_error` | published exposure is true exposure × mean-1 lognormal noise (σ=0.35) | sensitivity to imperfect real-world exposure estimates |
| `maup_fine` / `maup_coarse` | identical report locations, republished at 1-cell vs. 3-cell-merged segment granularity | Modifiable Areal Unit Problem: does the signal survive a change of spatial units |

Every city plants, out of an R×C grid of street segments:

- a **true hotspot** cluster (a plus-shape of 5 segments: 1 strongly elevated
  centre + 4 moderately elevated neighbors, so a spatial-clustering statistic
  like Getis-Ord Gi* has neighborhood support — an isolated single hot cell
  is a much weaker, less realistic test),
- a few **exposure decoys** (very high exposure, baseline rate — many raw
  reports, unremarkable once normalized),
- a few **reporting-bias decoys** (baseline true rate AND baseline exposure,
  but inflated reporting propensity — elevated observed rate that exposure
  normalization structurally cannot see through), and
- **background** everywhere else (baseline rate, no trap — should almost
  never be flagged).

`ground_truth.json` records the role, true incident rate, true exposure,
published exposure, reporting multiplier, and the resulting mean/observed
report count for every segment. It is never given to a tool being scored —
only to the scorer, after the fact.

## Running it

Regenerate every city (deterministic — re-running always produces
byte-identical output; that's what makes the "known answer" claim
checkable):

```
python benchmarks/generator.py
git diff --exit-code -- benchmarks/cities   # should be empty if nothing drifted
```

Or via `make`:

```
make bench-suite            # regenerate + score nearmiss on every city
make bench-suite-verify      # regenerate + fail if the committed cities changed
```

Score nearmiss itself on one or all cities:

```
python benchmarks/scorer.py                    # every city
python benchmarks/scorer.py --city baseline     # one city
```

## Scoring your own tool

1. Read `benchmarks/cities/<regime>/streets.geojson`, `exposure.json`, and
   `reports.json` (three boring, documented formats — see
   `docs/METHODOLOGY.md` and `schema/report.schema.json` in the repo root)
   with your own tool. Do **not** read `ground_truth.json` before producing
   your verdict — it is the answer key.
2. For every segment, decide whether your tool calls it a statistically
   significant hotspot, and (if your method produces one) its rate estimate
   and confidence/credible interval.
3. Write that out as JSON matching
   [`schema/results.schema.json`](schema/results.schema.json):
   ```json
   {
     "tool": "your-tool-name",
     "segments": {
       "seg-04-04": { "significant": true, "rate": 53.3, "rate_ci_low": 31.2, "rate_ci_high": 82.1 },
       "seg-01-01": { "significant": false }
     }
   }
   ```
4. Score it:
   ```
   python benchmarks/scorer.py --city baseline --tool your-tool-name --results path/to/your-results.json
   ```
5. Send a PR adding your tool's `scorecard.json` output (or a row in the
   table below) plus a link to your tool/method. Scores are regime-by-regime
   on purpose — a tool that's strong on `baseline` but collapses on
   `reporting_bias` or `overdispersion` is a more useful, more honest data
   point than one aggregate number.

### Community results

| Tool | Regime | Recall | Precision | Decoy FP | Bias trap | CI coverage | Link |
|---|---|---|---|---|---|---|---|
| nearmiss | (all) | see [SCORECARD.md](SCORECARD.md) | | | | | this repo |

_(No external submissions yet — see step 5 above to add yours.)_

## Versioning and drift

`SUITE_VERSION` in `generator.py` (currently `1.0.0`) is bumped whenever a
regime's parameters, the grid layout, or the ground-truth format changes in a
way that would change a previously-computed scorecard's meaning — treat it
like SemVer for a dataset: a patch/minor bump for additive changes (a new
regime), a major bump for anything that invalidates old scorecards
(different grid, different planted multipliers, different report format).
Old scorecards should always say which suite version they were computed
against (`ground_truth.json["suite_version"]`, copied into every
`scorecard.json`), so a stale scorecard is visibly stale rather than silently
wrong.

**Held-out regime note (overfitting risk):** the ideation doc flags that a
benchmark a tool's author also builds against risks overfitting nearmiss's
own thresholds to these exact regimes. Mitigation: the regime *parameters*
(multipliers, φ, σ) are declared in `configs/*.json`, separate from
`generator.py`'s mechanics, specifically so new regimes/parameter values can
be added or rotated without touching how cities are built — a genuinely
held-out regime is one whose config a maintainer adds without re-tuning
`src/nearmiss/stats/` against it first.
