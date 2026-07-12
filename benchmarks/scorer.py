#!/usr/bin/env python3
"""Score a hotspot-detection tool's output against a planted-truth city (EXP-09).

Two ways to score a city:

1. ``--tool nearmiss`` (the default): runs nearmiss's own pipeline + Getis-Ord
   statistics (``nearmiss.engine.build_analysis``) against the city's
   ``config.toml`` and scores the result. This is how nearmiss scores itself
   (see ``benchmarks/SCORECARD.md``).

2. ``--results PATH``: scores a JSON file any OTHER hotspot tool produced,
   validated against ``benchmarks/schema/results.schema.json``. This is the
   "any hotspot tool can run" path the ideation doc (EXP-09) asks for: a tool
   reads ``streets.geojson`` + ``exposure.json`` + ``reports.json`` from a
   city directory, decides which segments are statistically significant
   hotspots, and writes its verdict in the common results format.

Metrics computed against ``ground_truth.json`` (all in [0, 1] except counts):

  * ``hotspot_recall``            -- share of TRUE hotspot segments flagged significant.
  * ``hotspot_precision``         -- share of ALL flagged-significant segments that are
                                      true hotspots.
  * ``decoy_exposure_fp_rate``    -- share of high-exposure/normal-rate decoys flagged
                                      significant (should be LOW: a rate-based method should
                                      not be fooled by raw volume).
  * ``reporting_bias_trap_rate``  -- share of reporting-bias decoys flagged significant
                                      (documents, rather than penalizes -- see generator.py's
                                      module docstring: exposure normalization structurally
                                      cannot detect this).
  * ``background_fp_rate``        -- share of background (no-signal) segments flagged
                                      significant.
  * ``interval_coverage``         -- share of non-reporting-bias segments (hotspot /
                                      decoy_exposure / background, where the observed rate
                                      targets the true incident rate) whose published
                                      confidence interval contains the true rate.

Run from the repo root:
    python benchmarks/scorer.py                          # score nearmiss on every city
    python benchmarks/scorer.py --city baseline           # score nearmiss on one city
    python benchmarks/scorer.py --city baseline \\
        --tool other --results path/to/other-tool.json    # score a third-party tool
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import cast

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

CITIES_DIR = Path(__file__).resolve().parent / "cities"
SCHEMA_PATH = Path(__file__).resolve().parent / "schema" / "results.schema.json"

_ROLES_SCORED_FOR_COVERAGE = ("hotspot", "decoy_exposure", "background")


@dataclass
class SegmentVerdict:
    """The one thing every tool's output boils down to, for scoring purposes."""

    significant: bool
    rate: float | None = None
    rate_ci_low: float | None = None
    rate_ci_high: float | None = None


def _run_nearmiss(city_dir: Path) -> dict[str, SegmentVerdict]:
    from nearmiss.config import load_config
    from nearmiss.engine import build_analysis

    config = load_config(city_dir / "config.toml")
    bundle = build_analysis(config)
    return {
        s.segment_id: SegmentVerdict(
            significant=bool(s.significant),
            rate=s.rate,
            rate_ci_low=s.rate_ci_low,
            rate_ci_high=s.rate_ci_high,
        )
        for s in bundle.result.segments
    }


def _load_external_results(path: Path) -> dict[str, SegmentVerdict]:
    import jsonschema

    data = json.loads(path.read_text(encoding="utf-8"))
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator(schema).validate(data)
    out: dict[str, SegmentVerdict] = {}
    for sid, row in data["segments"].items():
        out[sid] = SegmentVerdict(
            significant=bool(row["significant"]),
            rate=row.get("rate"),
            rate_ci_low=row.get("rate_ci_low"),
            rate_ci_high=row.get("rate_ci_high"),
        )
    return out


def score_city(city_dir: Path, verdicts: dict[str, SegmentVerdict], tool: str) -> dict[str, object]:
    ground_truth = json.loads((city_dir / "ground_truth.json").read_text(encoding="utf-8"))
    truth_segments: dict[str, dict[str, object]] = ground_truth["segments"]

    def flagged(ids: list[str]) -> int:
        return sum(1 for sid in ids if verdicts.get(sid, SegmentVerdict(False)).significant)

    hotspots = ground_truth["true_hotspot_segments"]
    decoy_exposure = ground_truth["decoy_exposure_segments"]
    decoy_bias = ground_truth["decoy_reporting_bias_segments"]
    background = ground_truth["background_segments"]

    total_flagged = sum(1 for v in verdicts.values() if v.significant)
    true_positive = flagged(hotspots)

    coverage_hits = 0
    coverage_total = 0
    for sid, truth in truth_segments.items():
        if truth["role"] not in _ROLES_SCORED_FOR_COVERAGE:
            continue
        v = verdicts.get(sid)
        if v is None or v.rate_ci_low is None or v.rate_ci_high is None:
            continue
        coverage_total += 1
        true_rate = float(cast(float, truth["true_incident_rate_per"]))
        if v.rate_ci_low <= true_rate <= v.rate_ci_high:
            coverage_hits += 1

    result = {
        "regime": ground_truth["regime"],
        "suite_version": ground_truth["suite_version"],
        "tool": tool,
        "n_segments": len(truth_segments),
        "n_flagged_significant": total_flagged,
        "hotspot_recall": _safe_div(true_positive, len(hotspots)),
        "hotspot_precision": _safe_div(true_positive, total_flagged),
        "decoy_exposure_fp_rate": _safe_div(flagged(decoy_exposure), len(decoy_exposure)),
        "reporting_bias_trap_rate": _safe_div(flagged(decoy_bias), len(decoy_bias)),
        "background_fp_rate": _safe_div(flagged(background), len(background)),
        "interval_coverage": _safe_div(coverage_hits, coverage_total),
        "counts": {
            "true_hotspots": len(hotspots),
            "hotspots_flagged": true_positive,
            "decoy_exposure": len(decoy_exposure),
            "decoy_exposure_flagged": flagged(decoy_exposure),
            "decoy_reporting_bias": len(decoy_bias),
            "decoy_reporting_bias_flagged": flagged(decoy_bias),
            "background": len(background),
            "background_flagged": flagged(background),
            "coverage_checked": coverage_total,
            "coverage_hits": coverage_hits,
        },
    }
    return result


def _safe_div(n: int, d: int) -> float | None:
    return round(n / d, 4) if d else None


def _print_row(r: dict[str, object]) -> None:
    def pct(key: str) -> str:
        v = r[key]
        return "n/a" if v is None else f"{v:.0%}"

    print(
        f"  {r['regime']:<16} recall={pct('hotspot_recall'):>5} "
        f"precision={pct('hotspot_precision'):>5} "
        f"decoy_fp={pct('decoy_exposure_fp_rate'):>5} "
        f"bias_trap={pct('reporting_bias_trap_rate'):>5} "
        f"bg_fp={pct('background_fp_rate'):>5} "
        f"ci_coverage={pct('interval_coverage'):>5}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--city",
        action="append",
        help="city name under benchmarks/cities/ (repeatable); default: all",
    )
    parser.add_argument(
        "--tool", default="nearmiss", help="label recorded in the scorecard (default: nearmiss)"
    )
    parser.add_argument(
        "--results",
        type=Path,
        help="score an external tool's results JSON (see benchmarks/schema/results.schema.json) "
        "against exactly one --city, instead of running nearmiss itself",
    )
    parser.add_argument(
        "--out",
        type=Path,
        help="write per-city scorecards as JSON to this directory (default: <city>/scorecard.json)",
    )
    args = parser.parse_args()

    names = args.city or sorted(
        p.name for p in CITIES_DIR.iterdir() if (p / "ground_truth.json").is_file()
    )
    if args.results and len(names) != 1:
        parser.error("--results requires exactly one --city")

    print(f"benchmarks/scorer.py -- tool={args.tool}")
    scorecards = []
    for name in names:
        city_dir = CITIES_DIR / name
        if not city_dir.is_dir():
            parser.error(f"unknown city: {name} (looked in {CITIES_DIR})")
        verdicts = _load_external_results(args.results) if args.results else _run_nearmiss(city_dir)
        card = score_city(city_dir, verdicts, args.tool)
        _print_row(card)
        scorecards.append(card)
        out_dir = args.out or city_dir
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "scorecard.json").write_text(
            json.dumps(card, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
