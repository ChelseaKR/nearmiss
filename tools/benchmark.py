#!/usr/bin/env python3
"""Performance benchmark for the nearmiss pipeline + statistics.

Generates a city-scale synthetic dataset in memory and times the pipeline,
the exposure-normalized statistics (including the O(M^2) Getis-Ord step), and
the GeoJSON build. Deterministic generation, no RNG. Run:
    python tools/benchmark.py [n_segments] [n_reports]
    python tools/benchmark.py --json            # machine-readable, to stdout
    python tools/benchmark.py --json out.json   # ... or to a file

Two kinds of number come out of this file, and they are not interchangeable.

**Seconds** are what the human tables in ``docs/PERFORMANCE.md`` report. They
depend on the machine, so they can be compared against yesterday's laptop and
never against a shared CI runner: a wall-clock budget on a noisy runner either
flaps or gets muted, and a muted gate is the thing this project treats as a
defect.

**Work units** are the counts under ``ops``: how many times the pipeline, the
statistics, and the GeoJSON build call into nearmiss/honest_rates code at all,
and how many times they call the four geometry primitives that every
distance-based pass runs through. The input is deterministic, so these are
*exact* — measured identical on CPython 3.11.16 and 3.12.14 — which makes them
the half of the benchmark a merge gate can actually hold a budget against.
``tools/perf_budget.py`` compares them to ``perf/baseline.json``.

The work-unit counts are what the documented scaling story is *about*: snap,
dedupe, KDE and Gi* are near-linear because a uniform grid index prunes their
candidate sets, and losing that index turns these counts quadratic long before
anyone notices seconds on a 300-segment demo city. They cannot see a constant
factor (a slower expression inside an unchanged number of calls); that limit is
stated in ``perf/README.md`` rather than papered over.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from importlib import import_module
from pathlib import Path
from types import FrameType

import honest_rates
import nearmiss
from nearmiss import pipeline
from nearmiss.config import Config
from nearmiss.models import Exposure, Report, Segment
from nearmiss.publish import build_geojson
from nearmiss.stats import analyze

BASE_LAT = 38.5
BASE_LON = -121.7

#: Default workload: the city-scale row of `docs/PERFORMANCE.md`.
DEFAULT_SEGMENTS = 300
DEFAULT_REPORTS = 6000

#: The distance/projection primitives every spatial pass funnels through, as
#: (module, function). Counting these is the quadratic tripwire: remove the grid
#: index from snap, dedupe, KDE or Gi* and the count explodes by orders of
#: magnitude while a 300-segment demo still finishes in seconds. Nested calls are
#: counted (``point_to_polyline_m`` calls ``project``), because nesting is work.
GEOMETRY_PRIMITIVES: tuple[tuple[str, str], ...] = (
    ("nearmiss.geometry", "point_to_polyline_m"),
    ("nearmiss.geometry", "_point_seg_dist_xy"),
    ("honest_rates.geometry", "haversine_m"),
    ("honest_rates.geometry", "project"),
)

#: Comprehension bodies get their own code object on CPython 3.11 and are inlined
#: on 3.12 (PEP 709). Counting them would make the same tree measure differently
#: on the two interpreters this project supports, so they are excluded and the
#: counts hold across both. Generator expressions and lambdas still make a frame
#: on both, and are counted.
_INLINED_ON_312 = frozenset({"<listcomp>", "<setcomp>", "<dictcomp>"})


def _config() -> Config:
    return Config(
        city="bench",
        streets_path=Path("x"),
        reports_path=Path("x"),
        exposure_path=Path("x"),
        raw_dir=Path("/tmp/nm-bench-raw"),
        out_dir=Path("/tmp/nm-bench-pub"),
    )


def _segments(m: int) -> list[Segment]:
    cols = max(1, int(m**0.5))
    out: list[Segment] = []
    for n in range(m):
        row, col = divmod(n, cols)
        lat = BASE_LAT + row * 0.0025
        lon = BASE_LON + col * 0.0030
        out.append(
            Segment(
                id=f"seg-{n}", name=f"Street {n}", coords=((lat, lon - 0.0008), (lat, lon + 0.0008))
            )
        )
    return out


def _exposure(segs: list[Segment]) -> dict[str, Exposure]:
    return {
        s.id: Exposure(s.id, 100.0 + (i % 50) * 30.0, "synthetic", "2026-05-01")
        for i, s in enumerate(segs)
    }


def _reports(n: int, segs: list[Segment]) -> list[Report]:
    out: list[Report] = []
    for i in range(n):
        s = segs[i % len(segs)]
        lat = s.coords[0][0] + 0.00003
        # Spread reports along the segment by report index so within-segment
        # reports are distinct (not collapsed by dedupe).
        lon = (s.coords[0][1] + s.coords[1][1]) / 2 + ((i // len(segs)) - 10) * 0.00006
        # Distinct timestamps per report (h:m:s derived from i) -> no dedupe.
        h, mn, sc = (i // 3600) % 24, (i // 60) % 60, i % 60
        out.append(
            Report(
                id=f"00000000-0000-4000-8000-{i:012x}",
                occurred_at=f"2026-06-01T{h:02d}:{mn:02d}:{sc:02d}-07:00",
                lat=round(lat, 6),
                lon=round(lon, 6),
                mode="cyclist",
                hazard_type="close_pass",
                severity="near_miss",
            )
        )
    return out


def _feature_count(geojson: dict[str, object]) -> int:
    features = geojson["features"]
    if not isinstance(features, list):
        # `build_geojson` is typed `dict[str, object]`; refuse to report a feature
        # count guessed from something that is not a feature list.
        raise TypeError("build_geojson did not return a list of features")
    return len(features)


# ---------------------------------------------------------------------------
# Work units: an exactly reproducible measure of how much the pipeline does.
# ---------------------------------------------------------------------------


def _path_forms(path: Path) -> set[str]:
    """A path as written and as symlink-resolved; often the same string."""
    return {str(path), str(path.resolve())}


class _Tally:
    """Counts calls into nearmiss/honest_rates code, and into the geometry primitives.

    A ``sys.setprofile`` hook rather than ``cProfile``: the same numbers, no
    ``pstats`` round trip, and every value it produces is typed.
    """

    def __init__(self) -> None:
        # Both the raw and the symlink-resolved forms of every path: `co_filename` is
        # whatever the module was compiled with, which need not be the resolved path
        # (an editable install, a worktree under a symlinked temp dir). A mismatch
        # would make this count nothing, and counting nothing is the failure mode a
        # tripwire must never have.
        roots: set[str] = set()
        for package in (nearmiss, honest_rates):
            roots |= _path_forms(Path(package.__file__ or "").parent)
        self.roots = tuple(sorted(roots))
        self.primitives: dict[tuple[str, str], tuple[str, str]] = {}
        for module_name, function in GEOMETRY_PRIMITIVES:
            source = Path(import_module(module_name).__file__ or "")
            for form in _path_forms(source):
                self.primitives[form, function] = (module_name, function)
        self.calls = 0
        self.geometry = 0
        self.by_primitive: dict[tuple[str, str], int] = dict.fromkeys(GEOMETRY_PRIMITIVES, 0)

    def __call__(self, frame: FrameType, event: str, arg: object) -> None:
        if event != "call":
            return
        code = frame.f_code
        if code.co_name in _INLINED_ON_312:
            return
        filename = code.co_filename
        if not filename.startswith(self.roots):
            return
        self.calls += 1
        primitive = self.primitives.get((filename, code.co_name))
        if primitive is not None:
            self.geometry += 1
            self.by_primitive[primitive] += 1


@contextmanager
def _tallying() -> Iterator[_Tally]:
    """Count calls made inside the block. Nothing else may be profiling."""
    tally = _Tally()
    sys.setprofile(tally)
    try:
        yield tally
    finally:
        sys.setprofile(None)


def measure(segments: int, reports: int) -> dict[str, object]:
    """Time one benchmark run, then count the work units of an identical run.

    Two runs on purpose: the profiler hook roughly triples wall-clock, so timing a
    tallied run would publish seconds that describe the measurement rather than the
    code. The generated city is deterministic, so the second run does the same work
    as the first.
    """
    config = _config()
    segs = _segments(segments)
    exposure = _exposure(segs)
    reps = _reports(reports, segs)

    t0 = time.perf_counter()
    records, _summary = pipeline.run(reps, segs, config)
    t1 = time.perf_counter()
    result = analyze(records, reps, segs, exposure, config)
    t2 = time.perf_counter()
    geojson = build_geojson(result.segments, segs)
    t3 = time.perf_counter()

    with _tallying() as pipeline_tally:
        tallied_records, _tallied_summary = pipeline.run(reps, segs, config)
    with _tallying() as stats_tally:
        tallied_result = analyze(tallied_records, reps, segs, exposure, config)
    with _tallying() as publish_tally:
        build_geojson(tallied_result.segments, segs)

    seen = dict.fromkeys(GEOMETRY_PRIMITIVES, 0)
    for tally in (pipeline_tally, stats_tally, publish_tally):
        for primitive, count in tally.by_primitive.items():
            seen[primitive] += count
    unseen = sorted(f"{module}.{function}" for (module, function), n in seen.items() if n == 0)
    if unseen:
        # A tripwire that counts a primitive nothing calls reports zero for ever, and
        # zero looks like a pass. Renaming or moving one of these is a change to the
        # measurement, and has to be made deliberately in GEOMETRY_PRIMITIVES.
        raise RuntimeError(
            "benchmark: these geometry primitives were never called, so the work-unit "
            f"tripwire measures nothing: {unseen}. Update GEOMETRY_PRIMITIVES."
        )

    return {
        "workload": {"segments": segments, "reports": reports},
        "features": _feature_count(geojson),
        "seconds": {
            "pipeline": t1 - t0,
            "statistics": t2 - t1,
            "publish": t3 - t2,
            "total": t3 - t0,
        },
        "ops": {
            "pipeline_calls": pipeline_tally.calls,
            "pipeline_geometry_ops": pipeline_tally.geometry,
            "statistics_calls": stats_tally.calls,
            "statistics_geometry_ops": stats_tally.geometry,
            "publish_calls": publish_tally.calls,
            "publish_geometry_ops": publish_tally.geometry,
        },
    }


def _print_human(run: dict[str, object]) -> None:
    workload = run["workload"]
    seconds = run["seconds"]
    ops = run["ops"]
    assert isinstance(workload, dict) and isinstance(seconds, dict) and isinstance(ops, dict)
    n = workload["reports"]
    print(f"benchmark: {workload['segments']} segments, {n} reports")
    print(f"  pipeline (dedupe/geocode/snap/classify/quality): {seconds['pipeline']:7.3f} s")
    print(f"  statistics (rates+CIs, bias, KDE, Getis-Ord):     {seconds['statistics']:7.3f} s")
    print(f"  build geojson:                                    {seconds['publish']:7.3f} s")
    print(f"  TOTAL:                                            {seconds['total']:7.3f} s")
    print(f"  throughput: {n / seconds['total']:,.0f} reports/s; features: {run['features']}")
    print("  work units (exact, machine-independent; the budgeted half):")
    for name, value in ops.items():
        print(f"    {name:24s} {value:>12,}")
    print("  budget: make perf-budget  (compares the work units to perf/baseline.json)")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Benchmark the nearmiss pipeline + statistics.")
    parser.add_argument("segments", nargs="?", type=int, default=DEFAULT_SEGMENTS)
    parser.add_argument("reports", nargs="?", type=int, default=DEFAULT_REPORTS)
    parser.add_argument(
        "--json",
        nargs="?",
        const="-",
        metavar="PATH",
        help="emit the run as JSON to PATH ('-' or omitted: stdout) instead of a table",
    )
    args = parser.parse_args(argv)

    run = measure(args.segments, args.reports)
    if args.json is None:
        _print_human(run)
        return
    text = json.dumps(run, indent=2, sort_keys=True) + "\n"
    if args.json == "-":
        sys.stdout.write(text)
    else:
        Path(args.json).write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
