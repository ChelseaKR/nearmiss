# `perf/` — the performance regression budget

`docs/standards/PERFORMANCE-STANDARD.md` §2 says the ">10% regression fails" rule is
meaningless without a defined comparand, and names the comparand: a committed
`perf/baseline.json`. This directory is that file, plus the reasoning a reader needs to
decide whether the gate is worth trusting.

| File | What it is |
| --- | --- |
| `baseline.json` | The committed comparand: `meta` (provenance), `metrics` (flat map, inapplicable ones an explicit `null`), `direction` (per-metric, so the comparison is mechanical). |
| `README.md` | This file. |

There is no `k6-smoke.js` and no `lighthouserc.json`. §4's file contract assumes a hosted
route and a shipped bundle; nearmiss is a CLI and library that publishes a static
artifact, and the two files' absence is recorded as a declared N/A in
`baseline.json`'s `meta.not_applicable`, with the reason, rather than left as a gap a
reader has to notice.

## What is budgeted, and why it is not seconds

`make bench` times the pipeline, the statistics and the GeoJSON build, and
`docs/PERFORMANCE.md` publishes those numbers. Seconds are not what this gate compares.

A wall-clock budget cannot be both merge-blocking and honest on a shared CI runner:
GitHub's runners vary by far more than 10% between runs of identical code, so the gate is
either muted — and `PERFORMANCE-STANDARD.md` §3 forbids `|| true` and
`continue-on-error` outright — or it goes red for reasons that have nothing to do with the
diff, which is how a team learns to re-run a gate instead of reading it.

So the budgeted metrics are **work units**: how many calls each stage makes into
`nearmiss`/`honest_rates` code, and how many of those are the four geometry primitives
every distance-based pass funnels through (`haversine_m`, `project`,
`point_to_polyline_m`, `_point_seg_dist_xy`). The benchmark city is generated
deterministically with no RNG, so those counts are **exact**: identical between runs on
one machine, and measured identical on CPython 3.11.16 and 3.12.14, the two interpreters
the CI test matrix runs. A budget on an exact number can be tight without flapping.

They are also the numbers `docs/PERFORMANCE.md`'s scaling story is actually about. Snap,
dedupe, KDE and Getis-Ord Gi\* are near-linear because a uniform grid index prunes their
candidate sets. Remove that pruning and the counts explode — measured, on a deliberately
sabotaged index at 60 segments / 1,200 reports: `pipeline_calls` 105,718 → 2,331,736 and
`statistics_geometry_ops` 178,393 → 722,976 — while the demo city still finishes in a
couple of seconds and every existing test still passes. That is the regression this gate
exists to catch, and `tests/test_perf_budget.py` runs that same sabotage so the tripwire
is demonstrated rather than asserted.

## What this gate cannot see

A **constant-factor slowdown inside an unchanged number of calls** — a costlier expression
in an inner loop, a slower serializer, a `sleep` — moves seconds and leaves every work
unit exactly where it was. No gate here will fail on it.

That limit is stated rather than closed. `make bench` still prints seconds,
`docs/PERFORMANCE.md` still publishes them against a dated machine, and noticing a
constant-factor regression remains a review responsibility (the `City-scale performance`
REVIEW row in `docs/ROADMAP.md`). A budget that implied otherwise would be the same defect
this directory exists to remove: a number published with nothing behind it.

The work-unit counts also stop at the boundary of the profiled functions. Work done
*inside* one call — widening the grid's cell scan, say, without changing how many
candidates come back — is invisible here for the same reason.

## Running it

```bash
make perf-budget        # the gate: measure, then compare (also runs inside `make verify`)
make bench              # the human table, seconds included
python tools/benchmark.py --json run.json          # emit one run, machine-readable
python tools/perf_budget.py --measurement run.json # compare an already-emitted run
```

## Updating the baseline

`PERFORMANCE-STANDARD.md` §2's ritual, unchanged:

| Case | Who | How |
| --- | --- | --- |
| **Improvement** | PR author | `make perf-baseline` in the same PR that improved it. Ratchet forward; no sign-off needed. |
| **Intentional regression** | PR author + owner | Owner sign-off recorded in the PR that names the regression, and the baseline updated **in that same PR**. The diff is the audit trail. |
| **Unintentional regression** | — | Not an update case. Fix the code. The baseline does not move to make red turn green. |
| **Environment/tool change** | PR author | Re-measure and update `meta.tools` / `meta.environment` together with the metrics, in one PR titled as a re-baseline, with before/after numbers in the description. |

`make perf-budget` fails on a metric more than 10% **better** than the baseline as well as
one more than 10% worse. §2 leaves the improvement side to review (PERF-04), which is the
right call for a noisy measurement and the wrong one for an exact one: a 60% improvement
that never reaches the file silently buys the next change a 60% regression, and the budget
stops being a budget. Enforcing the same 10% in both directions closes that with no second
threshold to keep in step — the failure message says to run `make perf-baseline`.

A baseline edited outside these cases, or in a separate "fix CI" PR after the regressing
change has already merged, is a defect in its own right.
