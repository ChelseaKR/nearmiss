"""The performance regression budget, and the proof that it can fail (#236).

`make bench` has timed the pipeline since v0.1 and `docs/PERFORMANCE.md` has published the
numbers, but nothing compared a run to anything: the benchmark measured, and no gate could
notice a regression. The README's own Standards Conformance table said so.

`tools/perf_budget.py` closes it against `perf/baseline.json`, per
`docs/standards/PERFORMANCE-STANDARD.md` §2. A budget is only worth the failures it can
produce, so this module is mostly failure cases:

* the comparison fails on a real regression, passes inside the band, and fails on an
  un-ratcheted improvement too (the band is symmetric — see the tool's docstring);
* a metric that stops being measured, and a metric that starts being measured and is not
  budgeted, both fail rather than passing by absence;
* a `null` metric with no written reason fails, so an inapplicable metric stays a declared
  N/A rather than a silent skip;
* **the tripwire actually applies.** The last test removes the spatial index's pruning —
  the regression the whole design is aimed at — and asserts the measured work units move
  far enough to fail the gate. A negative control that silently no-ops reads exactly like
  a pass, so the sabotage is asserted to have landed before its effect is measured.

And the wiring, because a gate nothing runs is not a gate: `make verify` has to depend on
it and CI has to invoke it.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest
from tools import benchmark, perf_budget

ROOT = Path(__file__).resolve().parents[1]
BASELINE_PATH = ROOT / "perf" / "baseline.json"
MAKEFILE = ROOT / "Makefile"
CI_WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"

#: A workload small enough to run inside the unit-test suite and large enough that the
#: spatial index is doing something. The committed baseline is measured at 300/6,000.
TINY = (12, 60)


@pytest.fixture
def baseline() -> dict[str, Any]:
    return perf_budget.load_baseline(BASELINE_PATH)


def _budgeted(baseline: dict[str, Any]) -> dict[str, float]:
    return {n: float(v) for n, v in baseline["metrics"].items() if v is not None}


# --- the committed file -----------------------------------------------------------


def test_the_committed_baseline_matches_the_standards_schema(baseline: dict[str, Any]) -> None:
    """PERFORMANCE-STANDARD §2: meta + metrics + direction, every null with a reason."""
    assert perf_budget.check_schema(baseline) == []


def test_the_committed_baseline_budgets_exactly_what_the_benchmark_measures() -> None:
    """Enumerate, do not list: no measured work unit sits outside the budget.

    The failure this prevents is quiet in both directions — a renamed metric drops out of
    the comparison, and a newly measured one is never added — so `compare` reports each,
    and the committed pair has to agree today.
    """
    committed = perf_budget.load_baseline(BASELINE_PATH)
    run = benchmark.measure(*TINY)
    measured = perf_budget.measured_ops(run)
    assert sorted(measured) == sorted(_budgeted(committed))


def test_every_null_metric_names_the_reason_it_is_not_applicable(
    baseline: dict[str, Any],
) -> None:
    declared = baseline["meta"]["not_applicable"]
    for name, value in baseline["metrics"].items():
        if value is None:
            assert len(declared[name]) > 40, f"{name}: a one-word N/A is not a declared one"


# --- the comparison ---------------------------------------------------------------


def test_a_regression_beyond_the_band_fails(baseline: dict[str, Any]) -> None:
    measured = _budgeted(baseline)
    measured["pipeline_geometry_ops"] *= 1.11
    problems = perf_budget.compare(baseline, measured)
    assert len(problems) == 1
    assert "pipeline_geometry_ops" in problems[0]
    assert "worse" in problems[0]


def test_a_change_inside_the_band_passes(baseline: dict[str, Any]) -> None:
    measured = _budgeted(baseline)
    measured["pipeline_geometry_ops"] *= 1.09
    measured["statistics_calls"] *= 0.92
    assert perf_budget.compare(baseline, measured) == []


def test_an_unratcheted_improvement_fails_and_says_to_ratchet(baseline: dict[str, Any]) -> None:
    """The other half of the band: a big improvement that never reaches the file would
    otherwise leave the budget loose by exactly the amount it improved."""
    measured = _budgeted(baseline)
    measured["statistics_geometry_ops"] *= 0.5
    problems = perf_budget.compare(baseline, measured)
    assert len(problems) == 1
    assert "better" in problems[0]
    assert "make perf-baseline" in problems[0]


def test_a_zero_baseline_refuses_any_work_at_all(baseline: dict[str, Any]) -> None:
    """`publish_geometry_ops` is 0: building the GeoJSON does no distance work, and a
    single call would mean it had started to."""
    assert baseline["metrics"]["publish_geometry_ops"] == 0
    measured = _budgeted(baseline)
    measured["publish_geometry_ops"] = 1
    assert any("publish_geometry_ops" in p for p in perf_budget.compare(baseline, measured))


def test_a_higher_is_better_metric_is_compared_the_other_way_round() -> None:
    """Direction is read off the file, not assumed: a score falling by 20% is a
    regression, and the same drop in a lower-is-better metric is an improvement."""
    synthetic: dict[str, Any] = {
        "meta": {},
        "metrics": {"score": 90.0},
        "direction": {"score": "higher_is_better"},
    }
    problems = perf_budget.compare(synthetic, {"score": 72.0})
    assert len(problems) == 1 and "worse" in problems[0]
    assert perf_budget.compare(synthetic, {"score": 99.0}) == []


def test_a_metric_that_stops_being_measured_does_not_pass_by_disappearing(
    baseline: dict[str, Any],
) -> None:
    measured = _budgeted(baseline)
    del measured["statistics_calls"]
    problems = perf_budget.compare(baseline, measured)
    assert any("statistics_calls" in p and "not produced" in p for p in problems)


def test_a_newly_measured_metric_must_be_budgeted(baseline: dict[str, Any]) -> None:
    measured = _budgeted(baseline)
    measured["a_new_hot_path_ops"] = 1_000.0
    problems = perf_budget.compare(baseline, measured)
    assert any("a_new_hot_path_ops" in p and "does not budget it" in p for p in problems)


# --- the schema gate --------------------------------------------------------------


def test_a_null_metric_without_a_reason_fails_the_schema(baseline: dict[str, Any]) -> None:
    baseline["metrics"]["p95_ms"] = None
    del baseline["meta"]["not_applicable"]["p95_ms"]
    problems = perf_budget.check_schema(baseline)
    assert any("p95_ms" in p and "never a blank" in p for p in problems)


def test_a_metric_with_no_direction_fails_the_schema(baseline: dict[str, Any]) -> None:
    del baseline["direction"]["pipeline_calls"]
    problems = perf_budget.check_schema(baseline)
    assert any("pipeline_calls" in p and "direction" in p for p in problems)


def test_the_report_entry_point_fails_on_a_regressing_measurement(tmp_path: Path) -> None:
    """End to end through `report()`, on a recorded run rather than a live one, so the
    exit status the Makefile depends on is the thing under test."""
    run = benchmark.measure(*TINY)
    ops = run["ops"]
    assert isinstance(ops, dict)
    ops["pipeline_calls"] = int(ops["pipeline_calls"] * 3)

    committed = perf_budget.load_baseline(BASELINE_PATH)
    committed["metrics"] = {**committed["metrics"], **perf_budget.measured_ops(run)}
    committed["metrics"]["pipeline_calls"] = float(ops["pipeline_calls"]) / 3
    baseline_path = tmp_path / "baseline.json"
    baseline_path.write_text(json.dumps(committed), encoding="utf-8")
    measurement_path = tmp_path / "run.json"
    measurement_path.write_text(json.dumps(run), encoding="utf-8")

    argv = ["--baseline", str(baseline_path), "--measurement", str(measurement_path)]
    assert perf_budget.report(argv) == 1


def test_the_ratchet_rewrites_the_baseline_and_the_result_passes(tmp_path: Path) -> None:
    """`make perf-baseline` has to produce a file the gate then accepts, and a diff a
    reviewer can read: counts stay integers rather than widening to `654172.0`, which
    would make every ratchet look like a change of type as well as of value."""
    run = benchmark.measure(*TINY)
    measurement_path = tmp_path / "run.json"
    measurement_path.write_text(json.dumps(run), encoding="utf-8")
    baseline_path = tmp_path / "baseline.json"
    baseline_path.write_text(BASELINE_PATH.read_text(encoding="utf-8"), encoding="utf-8")

    argv = ["--baseline", str(baseline_path), "--measurement", str(measurement_path)]
    assert perf_budget.report([*argv, "--update"]) == 0

    written = perf_budget.load_baseline(baseline_path)
    assert perf_budget.check_schema(written) == []
    for name, value in perf_budget.measured_ops(run).items():
        assert written["metrics"][name] == value
        assert isinstance(written["metrics"][name], int)
    assert perf_budget.report(argv) == 0


# --- the negative control: the tripwire has to actually apply ----------------------


def test_losing_the_spatial_index_moves_the_work_units_far_enough_to_fail(
    monkeypatch: pytest.MonkeyPatch, baseline: dict[str, Any]
) -> None:
    """Remove the grid pruning and measure what the budget sees.

    This is the regression the design is aimed at: without the index, snap, dedupe, KDE
    and Gi* fall back to comparing everything against everything, which no existing test
    notices and which a 60-segment demo still finishes in seconds. A sabotage that
    silently failed to apply would read as a pass, so the un-pruned run is asserted to
    differ from the pruned one before its effect on the gate is checked.
    """
    from honest_rates.spatial_index import SpatialIndex

    pruned = benchmark.measure(*TINY)
    pruned_ops = perf_budget.measured_ops(pruned)

    def brute_force(
        self: SpatialIndex, x: float, y: float, radius_m: float
    ) -> list[tuple[str, float, float]]:
        seen: set[str] = set()
        out: list[tuple[str, float, float]] = []
        for cell in self.cells.values():
            for item in cell:
                if item[0] not in seen:
                    seen.add(item[0])
                    out.append(item)
        out.sort(key=lambda item: item[0])
        return out

    monkeypatch.setattr(SpatialIndex, "neighbors_in_radius", brute_force)
    unpruned_ops = perf_budget.measured_ops(benchmark.measure(*TINY))

    assert unpruned_ops["pipeline_calls"] > pruned_ops["pipeline_calls"], (
        "the sabotage did not change what the benchmark measured, so this test proves "
        "nothing about the tripwire"
    )

    # And the gate says so, against the baseline the pruned code produced.
    synthetic = {**baseline, "metrics": {**baseline["metrics"], **pruned_ops}}
    problems = perf_budget.compare(synthetic, unpruned_ops)
    assert any("worse" in problem for problem in problems), problems


# --- the wiring -------------------------------------------------------------------


def test_make_verify_runs_the_perf_budget_gate() -> None:
    """The claim the README's Performance row makes: this is in the merge gate."""
    text = MAKEFILE.read_text(encoding="utf-8")
    verify = next(line for line in text.splitlines() if line.startswith("verify:"))
    prerequisites = verify.split(":", 1)[1].split("##")[0].split()
    assert "perf-budget" in prerequisites, verify
    recipe = re.search(r"^perf-budget:.*?\n((?:\t.*\n|\n)*)", text, re.MULTILINE)
    assert recipe is not None and "tools/perf_budget.py" in recipe.group(1)


def test_ci_runs_the_perf_budget_gate_in_a_job_that_can_block_a_merge() -> None:
    """A performance gate that cannot block a merge is the unenforced number #236 is
    about, so the step lives in a job whose name is a required status check."""
    workflow = CI_WORKFLOW.read_text(encoding="utf-8")
    assert "run: make perf-budget" in workflow
    reproducibility = workflow.split("  reproducibility:", 1)
    assert len(reproducibility) == 2, "the reproducibility job was renamed"
    job = reproducibility[1].split("\n  build-pages:", 1)[0]
    assert "run: make perf-budget" in job
