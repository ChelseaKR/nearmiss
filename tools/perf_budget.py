#!/usr/bin/env python3
"""PERF-03: hold the benchmark to the committed baseline, and fail the merge if it drifts.

`make bench` has timed the pipeline since v0.1 and `docs/PERFORMANCE.md` has published
the numbers, but nothing compared a run to anything: the benchmark measured and no gate
could notice a regression. That is the same shape this repository names everywhere else
-- a published figure with no mechanism behind it -- and the README said so in its own
Standards Conformance table ("a merge-blocking regression budget remains open", #236).

This is that budget. `docs/standards/PERFORMANCE-STANDARD.md` §2 fixes the mechanics: a
committed `perf/baseline.json` carrying `meta` / `metrics` / `direction`, and a run fails
when any non-null metric is more than 10% worse in its declared direction.

    python tools/perf_budget.py                 # measure, then compare (the gate)
    python tools/perf_budget.py --measurement run.json   # compare an emitted run
    python tools/perf_budget.py --update        # ratchet: rewrite the baseline

Exit: 0 when every budgeted metric is inside the band; 1 otherwise. No network.

Why the budgeted metrics are work units and not seconds
-------------------------------------------------------

The obvious gate -- assert the wall-clock total against a committed number -- cannot be
merge-blocking here and be honest at the same time. GitHub's shared runners vary by far
more than 10% run to run, so a seconds budget is either muted (`continue-on-error`, which
the standard forbids outright) or it is red for reasons that have nothing to do with the
diff, and a gate people learn to re-run is a gate that has stopped gating.

So the budgeted metrics are the *work units* `tools/benchmark.py` counts: how many calls
each stage makes into nearmiss/honest_rates code, and how many of those are the four
geometry primitives every distance-based pass funnels through. The benchmark city is
generated deterministically, so those counts are exact -- byte-identical across repeated
runs and across CPython 3.11 and 3.12 -- and a budget on them flags a real regression and
nothing else.

They are also the numbers the documented scaling story is actually about. Snap, dedupe,
KDE and Gi* are near-linear because a uniform grid index prunes their candidate sets;
delete that index and the geometry-op counts go quadratic while the demo city still
finishes in a couple of seconds and every existing test still passes.

**What this cannot see, stated plainly:** a constant-factor slowdown inside an unchanged
number of calls -- a costlier expression in an inner loop, a slower `json` encoder --
moves seconds and not work units, and no gate here will fail on it. `make bench` still
prints seconds for a human to read, `docs/PERFORMANCE.md` still publishes them, and that
remains a review responsibility rather than an automated one. Naming the gap is the point;
a budget that claimed to cover it would be the defect this file exists to remove.

The band is symmetric on purpose
--------------------------------

§2's rule is "more than 10% worse fails". Applied alone to an exact metric it leaves the
ratchet half-built: a change that improves a metric by 60% and leaves the baseline alone
silently buys the next change a 60% regression for free, and the budget quietly stops
being one. §2 answers that with a REVIEW gate ("update `baseline.json` in the same PR that
improved them"), which works when a human is reading every diff. Since these numbers are
exact rather than noisy, the same 10% -- no new threshold, no second number to keep in
step -- can be enforced in both directions: a metric more than 10% *better* than the
baseline fails too, and says to ratchet the file forward with `make perf-baseline`.
"""

from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
BASELINE = ROOT / "perf" / "baseline.json"

#: §2's rule, as one number. A metric outside +-`TOLERANCE` of the baseline fails: over,
#: because that is a regression; under, because an un-ratcheted improvement loosens the
#: budget by exactly as much as it improved.
TOLERANCE = 0.10

#: §2's required top-level keys.
REQUIRED_TOP_LEVEL = ("meta", "metrics", "direction")

#: §2's required provenance. `workload` and `not_applicable` are this repository's
#: additions: the first because a work-unit count means nothing without the input size it
#: was measured on, the second because §2 requires an inapplicable metric to be a declared
#: null rather than a silent absence -- and a null with no reason beside it is closer to
#: silent than to declared.
REQUIRED_META = ("commit", "date", "environment", "tools", "workload", "not_applicable")

DIRECTIONS = ("lower_is_better", "higher_is_better")

# Imported by the one name that is true in every context -- run as a script, imported by a
# test, and read by `mypy --strict` (which covers `tools/`). Same reasoning, and the same
# shape, as `tools/conformance_sweep.py`'s import of the dataset verifier.
_ROOT_STRING = str(ROOT)
if _ROOT_STRING not in sys.path:
    sys.path.insert(0, _ROOT_STRING)

from tools.benchmark import measure  # noqa: E402


def _relative(path: Path) -> str:
    """Repo-relative if it is inside the repo, absolute otherwise.

    Falls back rather than raising: `--baseline` can name a file anywhere, and a
    message that raises while being formatted is a gate that cannot report.
    """
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def load_baseline(path: Path) -> dict[str, Any]:
    parsed: Any = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(parsed, dict):
        raise ValueError(f"{path}: the baseline must be a JSON object")
    return parsed


def _check_direction(metrics: dict[str, Any], direction: dict[str, Any]) -> list[str]:
    """`direction` has to cover `metrics` exactly.

    A metric with no direction cannot be compared mechanically, and a direction for a
    metric that no longer exists is a leftover that makes the file look like it budgets
    more than it does.
    """
    problems = [
        f"perf/baseline.json: metric {name!r} has no entry in 'direction'"
        for name in sorted(set(metrics) - set(direction))
    ]
    problems += [
        f"perf/baseline.json: 'direction' names {name!r}, which is not a metric"
        for name in sorted(set(direction) - set(metrics))
    ]
    problems += [
        f"perf/baseline.json: direction[{name!r}] must be one of {DIRECTIONS}"
        for name, value in sorted(direction.items())
        if value not in DIRECTIONS
    ]
    return problems


def _check_values(metrics: dict[str, Any], declared: dict[str, Any]) -> list[str]:
    """Every metric is a number, or a null with a written reason. Never a bare blank."""
    problems: list[str] = []
    for name, value in sorted(metrics.items()):
        if value is None:
            if not str(declared.get(name, "")).strip():
                problems.append(
                    f"perf/baseline.json: metric {name!r} is null with no reason in "
                    "meta.not_applicable. An inapplicable metric is a declared N/A, "
                    "never a blank."
                )
            continue
        if name in declared:
            problems.append(
                f"perf/baseline.json: metric {name!r} has a value and an "
                "meta.not_applicable reason; it cannot be both measured and N/A"
            )
        if isinstance(value, bool) or not isinstance(value, int | float):
            problems.append(f"perf/baseline.json: metric {name!r} must be a number or null")
    return problems


def check_schema(baseline: dict[str, Any]) -> list[str]:
    """Hold `perf/baseline.json` to the schema PERFORMANCE-STANDARD §2 fixes."""
    problems = [
        f"perf/baseline.json: missing {k!r}" for k in REQUIRED_TOP_LEVEL if k not in baseline
    ]
    if problems:
        return problems

    meta, metrics, direction = baseline["meta"], baseline["metrics"], baseline["direction"]
    problems += [
        f"perf/baseline.json: {name!r} must be an object"
        for name, value in (("meta", meta), ("metrics", metrics), ("direction", direction))
        if not isinstance(value, dict)
    ]
    if problems:
        return problems

    problems += [
        f"perf/baseline.json: meta is missing {k!r}" for k in REQUIRED_META if k not in meta
    ]
    problems += _check_direction(metrics, direction)

    declared = meta.get("not_applicable", {})
    if not isinstance(declared, dict):
        return [*problems, "perf/baseline.json: meta.not_applicable must be an object"]
    return problems + _check_values(metrics, declared)


def compare(baseline: dict[str, Any], measured: dict[str, float]) -> list[str]:
    """Every budgeted metric against the run, direction-aware, both sides of the band."""
    problems: list[str] = []
    metrics, direction = baseline["metrics"], baseline["direction"]
    budgeted = {name: value for name, value in metrics.items() if value is not None}

    # Enumerate rather than list, the way `reproduce-check` and `bench-check` do: a
    # measured number the baseline does not budget is invisible to this gate, and a
    # budgeted number the run stopped producing would otherwise pass by being absent.
    for name in sorted(set(budgeted) - set(measured)):
        problems.append(
            f"{name}: budgeted in perf/baseline.json and not produced by the benchmark. "
            "A metric that stops being measured must not pass by disappearing."
        )
    for name in sorted(set(measured) - set(budgeted)):
        problems.append(
            f"{name}: the benchmark measures it and perf/baseline.json does not budget it. "
            "Add it (run `make perf-baseline`), so a new hot path cannot regress unwatched."
        )

    for name in sorted(set(budgeted) & set(measured)):
        expected, actual = float(budgeted[name]), float(measured[name])
        lower_is_better = direction[name] == "lower_is_better"
        worse = actual > expected if lower_is_better else actual < expected
        moved = abs(actual - expected) > abs(expected) * TOLERANCE
        if not moved:
            continue
        if worse:
            problems.append(
                f"{name}: {actual:,.0f} against a baseline of {expected:,.0f} "
                f"({_percent(actual, expected)} worse, budget is {TOLERANCE:.0%}). Fix the "
                "regression; the baseline does not move to make red turn green. An "
                "intentional cost needs owner sign-off in this PR and the baseline updated "
                "in it -- PERFORMANCE-STANDARD §2."
            )
        else:
            problems.append(
                f"{name}: {actual:,.0f} against a baseline of {expected:,.0f} "
                f"({_percent(actual, expected)} better). Ratchet it forward in this PR "
                "(`make perf-baseline`): an un-ratcheted improvement leaves the budget "
                "loose by exactly the amount it improved."
            )
    return problems


def _percent(actual: float, expected: float) -> str:
    if expected == 0:
        return "from zero"
    return f"{abs(actual - expected) / abs(expected):.1%}"


def measured_ops(run: dict[str, Any]) -> dict[str, float]:
    ops = run["ops"]
    if not isinstance(ops, dict):
        raise ValueError("the benchmark run has no 'ops' object")
    return {name: float(value) for name, value in ops.items()}


def _run(baseline: dict[str, Any], measurement: Path | None) -> dict[str, Any]:
    if measurement is not None:
        loaded: Any = json.loads(measurement.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            raise ValueError(f"{measurement}: the measurement must be a JSON object")
        return loaded
    workload = baseline["meta"]["workload"]
    return measure(int(workload["segments"]), int(workload["reports"]))


def update(baseline: dict[str, Any], run: dict[str, Any], path: Path) -> None:
    """Ratchet: write the measured work units into the baseline, with fresh provenance."""
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.strip()
    measured = measured_ops(run)
    metrics: dict[str, float | int | None] = dict(baseline["metrics"])
    for name, value in measured.items():
        # Work units are counts. `measured_ops` widens them to float for the
        # comparison arithmetic; writing them back as `654172.0` would make every
        # ratchet's diff look like a change of type as well as of value.
        metrics[name] = int(value) if value.is_integer() else value
        baseline["direction"].setdefault(name, "lower_is_better")
    baseline["metrics"] = {name: metrics[name] for name in sorted(metrics)}
    baseline["direction"] = {name: baseline["direction"][name] for name in sorted(metrics)}
    baseline["meta"]["commit"] = commit
    baseline["meta"]["date"] = datetime.now(UTC).date().isoformat()
    baseline["meta"]["tools"]["python"] = platform.python_version()
    path.write_text(json.dumps(baseline, indent=2) + "\n", encoding="utf-8")
    print(f"perf-baseline: rewrote {_relative(path)} at {commit[:12]}.")
    print("               Read the diff before committing it -- a baseline moved without")
    print("               a reason is how a budget stops being one.")


def report(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Compare a benchmark run to perf/baseline.json (PERF-03)."
    )
    parser.add_argument("--baseline", type=Path, default=BASELINE)
    parser.add_argument(
        "--measurement", type=Path, default=None, help="compare an already-emitted run JSON"
    )
    parser.add_argument(
        "--update", action="store_true", help="ratchet the baseline to the measured numbers"
    )
    args = parser.parse_args(argv)

    baseline = load_baseline(args.baseline)
    problems = check_schema(baseline)
    if problems:
        return _fail(problems)

    run = _run(baseline, args.measurement)
    if args.update:
        update(baseline, run, args.baseline)
        return 0

    measured = measured_ops(run)
    if not measured:
        return _fail(["the benchmark produced no work units; an empty run must not pass"])
    problems = compare(baseline, measured)
    if problems:
        return _fail(problems)

    workload = baseline["meta"]["workload"]
    print(
        f"perf-budget: {len(measured)} work-unit metrics measured on "
        f"{workload['segments']} segments / {workload['reports']} reports, all within "
        f"{TOLERANCE:.0%} of perf/baseline.json (measured at {baseline['meta']['commit'][:12]})."
    )
    for name in sorted(measured):
        print(
            f"  {name:24s} {measured[name]:>12,.0f}  baseline {baseline['metrics'][name]:>12,.0f}"
        )
    return 0


def _fail(problems: list[str]) -> int:
    print("\nperf-budget FAILED:", file=sys.stderr)
    for problem in problems:
        print(f"  - {problem}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(report())
