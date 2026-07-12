# EXP-05 — Privacy-budgeted segment × time-band release (design doc + SME sign-off gate)

**Status: PROTOTYPE. Not approved for a real (non-synthetic) publication.**
**Implements:** the EXP-05 ideation item ("Privacy-budgeted segment × time-band release
(differential privacy)"), catalogued in `docs/ideation/03-expansions.md` on the roadmap branches
that track it (that catalogue predates this branch's history; not reproduced here to keep this
change scoped to the mechanism itself).
**Code:** [`src/nearmiss/stats/dp_temporal.py`](../../src/nearmiss/stats/dp_temporal.py).
**Gate:** a privacy-SME sign-off is a hard requirement before `dp_segment_time.enabled = true`
is ever set on a config pointed at real reports — see [§6](#6-the-sme-sign-off-gate).

> **Honesty note.** This document is written by the maintainer, not by a privacy or
> differential-privacy specialist, in the same spirit as [`docs/DPIA.md`](../DPIA.md): it follows
> the standard shape of a DP mechanism writeup (mechanism, sensitivity, epsilon rationale,
> composition, threat interaction, open questions) so it is checkable against that shape, and it
> says plainly where it has *not* been reviewed rather than implying a rigor it doesn't have. It
> exists to give an actual SME reviewer a concrete artifact to check, not to substitute for that
> review.

## 1. The problem this unlocks

[`docs/LIMITATIONS.md`](../LIMITATIONS.md) states plainly: *"No time dimension is published... the
public dataset cannot answer 'dangerous at the 3pm school bell.'"* `stats/temporal.py` only ever
publishes a **city-wide** time-of-day breakdown — never a per-segment one — because a
(segment, hour) cell is exactly the kind of low-count cell that can re-identify a contributor's
commute (a report on Elm St. every weekday at 7:45am is a routine, not a data point). The current
mitigation is all-or-nothing: k-anonymity suppression (`min_publish_n`, hard rule #4) withholds
the whole breakdown below a floor, and per-segment time bands are never computed at all.

This blocks a real advocacy use case named in the panel personas: Safe-Routes-to-School advocacy
(P2) wants "is this specific corridor dangerous at school-bell time," not "is this city dangerous
sometime." The ideation doc asks whether calibrated noise can answer that question where blunt
suppression cannot.

## 2. Mechanism: epsilon-differential privacy, Laplace mechanism

For each cell `c = (segment_id, part_of_day)` (the same five commute-aware parts of day
`stats/temporal.py` already uses — `overnight`, `am_peak`, `midday`, `pm_peak`, `evening` — chosen
over 24 hourly bins because they are more robust to small samples), the true report count `n_c` is
released as:

```
published_c = max(0, round(n_c + Lap(0, sensitivity / epsilon)))
```

`Lap(0, b)` is a zero-mean Laplace random variable with scale `b`. This is the textbook Laplace
mechanism for epsilon-DP counting queries (Dwork & Roth, *The Algorithmic Foundations of
Differential Privacy*). Clamping the noised value to a non-negative integer for publication is
standard practice but is **not** an unbiased transform — it slightly over-estimates true counts
that are at or near zero, since negative noise draws get truncated up to 0 while positive draws
pass through unchanged. The prototype documents this rather than hiding it; an SME reviewer should
confirm the bias is acceptable at the epsilon chosen, or suggest a truncated-Laplace / smooth
variant instead.

## 3. Sensitivity

Each clean, snapped report contributes to **exactly one** `(segment_id, part_of_day)` cell (one
segment from spatial snapping, one part-of-day bucket from its timestamp — see
`true_segment_time_counts` in the code). Adding or removing a single report therefore changes
exactly one cell's true count by exactly 1. Global sensitivity for a single-report add/remove is
**1**, per cell. `tests/test_dp_temporal.py::test_a_single_report_add_changes_exactly_one_cell_by_one`
pins this as a regression test on the bucketing logic itself, not just an assertion in prose.

**This is event-level DP, not user-level DP.** The mechanism bounds the influence of one *report*
on the release. It does **not** bound how many reports a single contributor may have filed — a
contributor who reports the same close pass five times (or genuinely experiences five distinct
near-misses on their commute) spends five times the per-report privacy loss on their own routine,
concentrated on the cells that describe that routine. This is the single biggest open question for
the SME sign-off (see §6): either (a) argue event-level DP is an acceptable bound given
`stats/rates.py`'s existing dedupe window already collapses near-duplicate reports from the same
person in the same place/time, or (b) require a per-reporter contribution cap (clamp each
`reporter_token`'s influence on a given cell to some bound `k` before computing sensitivity, i.e.
user-level DP with sensitivity `k`) before this ships. The prototype does not implement (b).

## 4. Composition across cells

A release publishes one noised value per `(segment_id, part_of_day)` cell that clears the *report
count* floor for computing at all — potentially dozens of cells per city. Each cell spends the same
stated `epsilon`. By basic (sequential) composition, publishing `C` cells in the same release costs
**at most `C × epsilon`** in total privacy loss; the prototype reports this as
`composed_epsilon_upper_bound` in the metadata so nobody has to reconstruct it by hand. This is a
worst-case bound, not a tight one — advanced composition (Dwork, Rothblum & Vadhan) or a
per-cell-budget allocation (e.g. `epsilon / C` per cell, holding total loss to a stated target)
would give a tighter guarantee at the cost of more noise per cell. The prototype does **not**
implement either refinement; it reports the worst case honestly instead of asserting a bound it
hasn't earned. **A privacy SME should decide the actual epsilon-per-cell vs. epsilon-total target
before any real release**, not this document.

This DP release also composes with the *existing* GeoJSON publication (segment rate + CI,
Getis-Ord z, hazard breakdown) from the same underlying reports. That existing release is not
itself expressed in DP terms (it uses k-anonymity suppression, not noise), so a combined epsilon
accounting across both isn't well-defined without translating the existing mechanism into DP terms
too — flagged here as a known gap for the SME to weigh in on, not resolved by this prototype.

## 5. Utility, and the "utility-theater" risk

The ideation doc names the risk explicitly: *"noise so large the bands are meaningless — measure
and say so."* The prototype computes `mean_absolute_noise` (the average magnitude of the injected
noise across published cells) against the mean true count, and sets `utility_theater_risk = true`
when the average noise is at least as large as the average signal — a cheap, honest, city-agnostic
smoke test, not a substitute for the SME's own utility analysis on real data. At nearmiss's typical
sample sizes (single- and low-double-digit counts per city-wide part-of-day bucket, per
`tests/fixtures/davis`), per-segment cells will often be much smaller still, which is exactly the
regime where Laplace noise at any reasonable epsilon risks drowning the signal. **Either outcome —
the bands survive noise at a defensible epsilon, or they don't — is a publishable finding**, per
the ideation doc; this prototype is built to measure that finding, not to assume the answer.

## 6. The SME sign-off gate

This is a **hard gate**, enforced as code, not just as policy prose:

- `dp_segment_time.enabled` defaults to `false`. Every existing config remains a strict no-op —
  `stats/dp_temporal.dp_segment_time_release()` returns immediately with `enabled: False` and
  produces no cells, no noise draws, and no change to any existing published artifact.
- If `enabled = true` but `dp_segment_time.sme_signoff_ref` (a free-text field — e.g. a reviewer
  name, date, and a pointer to their review notes) is **not** set, the mechanism raises
  `DPSignoffMissingError` rather than silently proceeding. This applies even to a first `analyze()`
  call in tests or a demo — there is no "just try it once" path that skips the gate.
- The `sme_signoff_ref` string is carried into the published metadata verbatim next to the epsilon
  and noise scale, so a published release under this mechanism is self-documenting about who
  reviewed it.

**What a reviewer needs to check before setting that field on a config pointed at real (not
synthetic-demo) data:**

1. Is event-level DP (§3) an acceptable privacy bound for this deployment, or does it need a
   per-reporter contribution cap first?
2. Is the composition accounting in §4 (worst-case `C × epsilon`) the right target, or should the
   budget be split per-cell instead?
3. At the epsilon actually chosen, does §5's utility check pass on the *real* city's data (not just
   the synthetic fixtures), and is the round-to-nonnegative-integer bias (§2) acceptable?
4. Does this interact with [`docs/THREAT-MODEL.md`](../THREAT-MODEL.md)'s T1 (deanonymization via
   precise coordinates/timing, RR-1) in a way the existing mitigation table doesn't already cover?
   T1 currently reasons about the *aggregated, city-wide* release; a segment-level time band is a
   materially different linkage surface and T1/RR-1 should be revisited alongside any real
   deployment of this mechanism, not assumed already covered.
5. Should this be gated per-city (a sparse city might never clear the utility bar at any reasonable
   epsilon) rather than as a single global on/off switch?

Until those are answered and `sme_signoff_ref` is set by someone who actually did that review, this
mechanism ships noise math and tests — not a claim that any real dataset should use it.

## 7. What ships in this PR, and what doesn't

**Ships:** the mechanism (`stats/dp_temporal.py`), the config surface
(`dp_segment_time.{enabled,epsilon,sme_signoff_ref}`), the hard sign-off gate, wiring into
`AnalysisResult`/`publish.py` metadata (`segment_time_bands_dp`, `{"enabled": false}` for every
existing config), and unit tests covering the no-op default, the gate, the sensitivity claim, the
noise mechanics, the utility-theater signal, and the privacy-metadata leak check.

**Does not ship:** an enabled config for any real city, a per-reporter contribution cap, advanced
composition, a brief.md rendering of the DP bands, or a claim that any privacy SME has reviewed
this. Those are the next steps once §6 is actually satisfied.
