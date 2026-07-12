# Mutation testing (advisory)

Line and branch coverage prove a line *ran*; they do not prove a test would
*notice* if that line were wrong. For the correctness-critical spatial statistics
in nearmiss — where a silent numerical bug does not crash, it just quietly
mislabels which street is a hotspot — that gap matters. Mutation testing closes
it: [mutmut](https://mutmut.readthedocs.io/) systematically introduces small
faults ("mutants") into the code and reports which ones the test suite fails to
catch ("survivors"). A surviving mutant is a concrete, reproducible bug your
tests would ship.

This is **advisory only** (backlog #15). It is **never** a merge gate, never runs
per-PR, and never blocks. The blocking correctness gate stays `make test` (the
known-answer fixtures under a branch-coverage floor). Mutation score is a slow
health signal we watch weekly.

## Scope

Deliberately narrow, aimed at the highest-stakes numerical routines:

| Module | What it computes | Why it is in scope |
| --- | --- | --- |
| `src/nearmiss/stats/getis_ord.py` | Getis-Ord Gi\* local hotspot z-score + Benjamini-Hochberg FDR control | The hotspot verdict itself. A sign flip or off-by-one here corrupts a published hotspot without failing a coarse test. |
| `src/nearmiss/stats/rates.py` | Byar Poisson and Wilson confidence intervals | Produces the exposure-normalized rate the hotspot runs on. |
| `src/nearmiss/network.py` | Street-network adjacency graph + band-bounded Dijkstra deciding Gi\*'s neighbor map (FIX-02) | An off-by-one in the node-snap tolerance or the network-distance band cutoff silently redraws which segments count as neighbors, without failing a coarse test. |

Configuration lives in `[tool.mutmut]` in `pyproject.toml`. mutmut reuses the
existing pytest suite (`test_hotspot.py`, `test_fdr.py`, `test_rates.py`,
`test_stats_numerics.py`, `test_network.py`, `test_getis_ord_differential.py`)
as the kill oracle — there is no separate mutation-only test harness to
maintain.

mutmut is kept in its **own** optional-dependency group (`.[mutation]`), *not* in
`dev`, so the `make verify` merge gate — and in particular the blocking
`pip-audit --strict` scan — audits exactly the dependency surface it did before.
mutmut's large transitive tree (libcst, textual, …) never enters the gated path.

## Running it

```bash
make mutation          # installs .[mutation] on demand, runs mutmut, prints results
```

Or directly:

```bash
pip install -e ".[mutation]"
python -m mutmut run           # generates + tests mutants (writes ./mutants/, gitignored)
python -m mutmut results       # list survivors
python -m mutmut show <id>     # show the exact diff of one surviving mutant
```

The `mutants/` working copy and `mutmut-*.json` stats are regenerated every run
and are gitignored — never commit them.

CI runs the same thing weekly and on demand via
`.github/workflows/mutation.yml` (`workflow_dispatch` + a Monday cron), with
`continue-on-error` so a score dip surfaces in the run summary without ever
turning a required check red.

## Baseline

Recorded on 2026-06-30 (Python 3.12, mutmut 3.6.0), before `network.py` existed.

| Module | Baseline (existing suite) | After `test_stats_numerics.py` |
| --- | --- | --- |
| `getis_ord.py` | 61 / 116 killed — **52.6%** | 106 / 116 killed — **91.4%** |
| `rates.py` | 59 / 114 killed — **51.8%** | 59 / 114 killed — **51.8%** |
| **Total** | 120 / 230 — **52.2%** | 165 / 230 — **71.7%** |

`network.py` (added by FIX-02) is in scope as of this change (see the table above) but has **no
recorded mutation-score baseline yet** — that requires an actual `make mutation` run, which this
advisory, non-blocking process has not had a scheduled/manual trigger for since the module landed.
`tests/test_network.py` includes a differential test against an independent brute-force oracle
(`test_dijkstra_matches_a_brute_force_relaxation_oracle_on_random_grids`) and 100% line/branch
coverage of `network.py`, but that is not a substitute for an actual mutation run; do not treat this
paragraph as one. The next `make mutation` (weekly cron or manual `workflow_dispatch`) will record a
real baseline for it.

### Notable baseline survivors (real bugs the old tests missed)

The known-answer fixtures only pinned coarse properties (seg-06 is the hottest,
and significant), so mutations that perturbed the z-scores without changing the
*ranking* slipped through. Three examples inside `getis_ord_star`:

1. **Sign flip in the Gi\* numerator** — `wx_sum - mean * w_sum` → `wx_sum + mean * w_sum`.
   A hot cluster and a cold gap become numerically indistinguishable in sign.
2. **`*`/`/` slip in the standard error** — `s * math.sqrt(...)` → `s / math.sqrt(...)`.
   Every z-score is scaled by the wrong factor; significance thresholds move.
3. **Off-by-one in the variance term** — `(n - 1)` → `(n + 1)` in the Gi\*
   denominator (the degrees-of-freedom correction).

Also surviving in the baseline: the `n < 3` guard weakened to `n <= 3` (a
three-segment city would silently return all-zero hotspots), and in
`benjamini_hochberg`, `m == 0` weakened to `m == 1` and the sort key dropped
(FDR ranking by insertion order instead of p-value).

### Tests added to kill them

`tests/test_stats_numerics.py` (three focused tests):

- `test_getis_ord_star_pins_exact_zscores` — pins the Gi\* z-scores of a tiny,
  fully hand-computable four-segment layout to their exact closed form
  (`±sqrt(3)`), with the standardization factor deliberately `4/3` (not 1) so a
  `*`/`/` slip cannot hide. Kills the numerator sign flip, the denominator swap,
  the `(n - 1)` off-by-one, and the mean/variance mutants at once.
- `test_getis_ord_star_boundary_and_degenerate_inputs` — the `n == 3` minimum
  computes a real hotspot (`±sqrt(2)`), while `n < 3`, and zero-variance inputs
  return exactly `0.0` for every id (never `None`).
- `test_benjamini_hochberg_ranks_by_pvalue_and_handles_edges` — single-test
  rejection (`m == 1`), an empty result when nothing clears its threshold, and
  ranking by p-value rather than key order.

### Remaining survivors (equivalent / measure-zero — left intentionally)

The 10 residual `getis_ord.py` survivors are not defects:

- **Equivalent mutants.** `w = 1.0` → `w = 2.0`: Gi\* is invariant to a uniform
  scaling of the weights, so the z-scores are unchanged. `max(0.0, F)` →
  `max(1.0, F)`: the factor `F = k(n-k)/(n-1)` is provably `>= 1` for any binary
  neighborhood, so the floor never binds. `variance > 0` → `variance >= 0`: the
  zero case is already caught by the `s == 0` guard.
- **Measure-zero boundaries.** `d <= band_m` → `d < band_m`, `p <= thr` →
  `p < thr`, and the `== 0.0` guards flipped to `== 1.0`/`!= 1.0` differ only when
  a distance, p-value, or standard error lands on an exact boundary — not
  reachable with ordinary floating-point inputs and not worth a contrived test.

`rates.py` remains at its baseline (~52%): its CI bounds are asserted with loose
approximate ranges, so many arithmetic mutants survive. Tightening those is
tracked as follow-up advisory work; it is not a correctness regression, and
mutation testing is advisory by design.
