#!/usr/bin/env python3
"""Threshold-sensitivity and statistical-power note per city (R29 / R34).

Re-runs the published pipeline (dedupe -> geocode -> snap -> classify) and the
exposure-normalized ranking across a small grid of the snapping/dedupe
thresholds, and reports, per variant, how many reports were snapped / dropped /
deduped and how stable the published segment ranking is versus the baseline
config (top-5 overlap + a Kendall-tau-style pairwise agreement).

It also emits a "how many reports until rankable" power note: the small-n
publication gate (``min_publish_n``) and, using the *same* Byar / Poisson
confidence-interval method the published rates use (``stats/rates.py``), how
many reports a segment needs before its 95% interval clears the median
segment's — i.e. before it can be *distinguished* from the typical segment.

Everything here is pure-Python and deterministic (no RNG, no embedded date), so
``make sensitivity`` regenerates the notes byte-for-byte. It reuses the
production modules (``nearmiss.pipeline``, ``nearmiss.stats``,
``nearmiss.stats.rates``) rather than reimplementing them, consistent with
ADR-0003 (pure-python stats).

Usage:
    python tools/sensitivity_note.py --config config/davis-demo.toml
    python tools/sensitivity_note.py --config config/riverside-demo.toml --out data/published
"""

from __future__ import annotations

import argparse
import dataclasses
from pathlib import Path

from nearmiss.config import Config, load_config
from nearmiss.engine import CityInputs, load_city
from nearmiss.pipeline import run as run_pipeline
from nearmiss.publish import _slug
from nearmiss.stats import AnalysisResult, analyze
from nearmiss.stats.rates import poisson_ci

# Sensitivity grid. The baseline config's values are always among these so the
# baseline row is highlighted rather than special-cased.
SNAP_MAX_M: tuple[float, ...] = (15.0, 25.0, 40.0)
DEDUPE_DISTANCE_M: tuple[float, ...] = (10.0, 15.0, 25.0)
DEDUPE_WINDOW_S: tuple[int, ...] = (300, 600, 1200)

# Cap on the "reports needed" search — a segment that cannot be distinguished
# within this many reports is reported as ">cap" rather than looping forever.
_REPORTS_CAP = 2000


def _analyze_variant(config: Config, city: CityInputs) -> tuple[dict[str, int], AnalysisResult]:
    """Run the full pipeline + statistics for one threshold variant."""
    records, summary = run_pipeline(city.reports, city.segments, config)
    result = analyze(records, city.reports, city.segments, city.exposure, config)
    return summary, result


def _ranked_ids(result: AnalysisResult) -> list[str]:
    """Published ranking: publishable segments with a rate, high rate first.

    Ties break on ``segment_id`` so the ordering is deterministic (the published
    figure sorts on rate alone; a stable secondary key only matters here, where
    we compare orderings across variants)."""
    ranked = sorted(
        (s for s in result.segments if s.rate is not None and s.publishable),
        key=lambda s: (-(s.rate or 0.0), s.segment_id),
    )
    return [s.segment_id for s in ranked]


def _top_overlap(base: list[str], variant: list[str], k: int = 5) -> tuple[int, int]:
    """Count of shared ids in the top ``k`` of each ranking (out of the base's top-k)."""
    top_base = base[:k]
    top_variant = set(variant[:k])
    shared = sum(1 for sid in top_base if sid in top_variant)
    return shared, len(top_base)


def _pair_agreement(base: list[str], variant: list[str]) -> tuple[int, int]:
    """Kendall-tau-style concordance over ids ranked in *both* orderings.

    Returns (concordant_pairs, comparable_pairs). A pair is concordant when the
    two rankings agree on which of the two segments is higher."""
    in_variant = set(variant)
    common = [sid for sid in base if sid in in_variant]
    pos_base = {sid: i for i, sid in enumerate(base)}
    pos_variant = {sid: i for i, sid in enumerate(variant)}
    concordant = 0
    pairs = 0
    for i in range(len(common)):
        for j in range(i + 1, len(common)):
            a, b = common[i], common[j]
            pairs += 1
            order_base = pos_base[a] - pos_base[b]
            order_variant = pos_variant[a] - pos_variant[b]
            if order_base * order_variant > 0:
                concordant += 1
    return concordant, pairs


def _reports_to_distinguish(
    exposure: float, per: float, z: float, reference_ci_high: float
) -> int | None:
    """Smallest report count whose Poisson rate-CI lower bound clears ``reference_ci_high``.

    Uses the published Byar/Poisson interval (``poisson_ci``) at a fixed exposure
    denominator, mirroring the CI method in docs/METHODOLOGY.md 5.2. Returns
    ``None`` if the cap is reached without separation."""
    if exposure <= 0:
        return None
    scale = per / exposure
    for count in range(_REPORTS_CAP + 1):
        low, _ = poisson_ci(count, z)
        if low * scale > reference_ci_high:
            return count
    return None


def _median(values: list[float]) -> float:
    ordered = sorted(values)
    n = len(ordered)
    mid = n // 2
    if n % 2 == 1:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2.0


def _fmt(value: float | None, places: int = 2) -> str:
    return "—" if value is None else f"{value:.{places}f}"


def _sensitivity_rows(config: Config, city: CityInputs) -> list[str]:
    baseline_ids = _ranked_ids(_analyze_variant(config, city)[1])
    rows: list[str] = []
    for snap in SNAP_MAX_M:
        for dist in DEDUPE_DISTANCE_M:
            for window in DEDUPE_WINDOW_S:
                variant = dataclasses.replace(
                    config,
                    snap_max_m=snap,
                    dedupe_distance_m=dist,
                    dedupe_window_s=window,
                )
                summary, result = _analyze_variant(variant, city)
                ids = _ranked_ids(result)
                shared, base_k = _top_overlap(baseline_ids, ids)
                concordant, pairs = _pair_agreement(baseline_ids, ids)
                agreement = "n/a" if pairs == 0 else f"{concordant / pairs:.2f}"
                is_baseline = (
                    snap == config.snap_max_m
                    and dist == config.dedupe_distance_m
                    and window == config.dedupe_window_s
                )
                marker = " **(baseline)**" if is_baseline else ""
                rows.append(
                    f"| {snap:g}{marker} | {dist:g} | {window} | "
                    f"{summary['duplicates_removed']} | {summary['snapped']} | "
                    f"{summary['unsnapped']} | {shared}/{base_k} | {agreement} |"
                )
    return rows


def _power_note(config: Config, result: AnalysisResult, names: dict[str, str]) -> list[str]:
    published = [s for s in result.segments if s.rate is not None and s.publishable]
    out: list[str] = []
    out.append("## Statistical power — how many reports until rankable")
    out.append("")
    out.append(
        f"**Publication gate (k-anonymity).** A segment is withheld while it has "
        f"`0 < reports < min_publish_n`. With `min_publish_n = {config.min_publish_n}`, a segment "
        f"needs **{config.min_publish_n} reports** before it is published at all (segments with "
        f"exactly 0 reports are published as a true zero)."
    )
    out.append("")

    if not published:
        out.append(
            "_No segment is currently publishable, so no distinguish-from-median power note "
            "can be computed for this dataset._"
        )
        out.append("")
        return out

    rates = [s.rate or 0.0 for s in published]
    median_rate = _median(rates)
    # The reference segment is the published segment whose rate is nearest the
    # median rate (deterministic tie-break on id); its interval is the bar a
    # candidate must clear to be "distinguishable from the typical segment".
    reference = min(
        published,
        key=lambda s: (abs((s.rate or 0.0) - median_rate), s.segment_id),
    )
    ref_high = reference.rate_ci_high or 0.0
    per = config.rate_per
    z = config.confidence_z

    out.append(
        f"**Distinguishing a segment from the median.** The published rates use the Byar/Poisson "
        f"interval (`stats/rates.py`, docs/METHODOLOGY.md 5.2). Two segments are reported as "
        f"*distinguishable* only when their 95% intervals do not overlap. The reference here is "
        f"the median published segment, rate **{_fmt(reference.rate)}/{per:g}** "
        f"(95% CI {_fmt(reference.rate_ci_low)}–{_fmt(reference.rate_ci_high)}, "
        f"n={reference.report_count}). A candidate segment must lift its interval's lower bound "
        f"above **{_fmt(ref_high)}/{per:g}** to clear it."
    )
    out.append("")

    exposures = [s.exposure_estimate for s in published if s.exposure_estimate]
    if exposures:
        levels = [
            ("lowest", min(exposures)),
            ("median", _median(exposures)),
            ("highest", max(exposures)),
        ]
        out.append(
            "The count needed depends on the segment's exposure denominator (a busier segment "
            "needs more reports to reach the same rate). At the published exposure spread:"
        )
        out.append("")
        out.append("| Exposure level | Exposure | Reports to clear the median's CI |")
        out.append("| --- | ---: | ---: |")
        for label, exp in levels:
            need = _reports_to_distinguish(exp, per, z, ref_high)
            need_str = f">{_REPORTS_CAP}" if need is None else str(need)
            out.append(f"| {label} | {exp:g} | {need_str} |")
        out.append("")

    out.append(
        "Per published segment, its observed count and whether its 95% interval already clears the "
        "median reference (non-overlapping intervals):"
    )
    out.append("")
    out.append("| Segment | n | Rate | 95% CI | Distinguishable from median? |")
    out.append("| --- | ---: | ---: | --- | --- |")
    for s in sorted(published, key=lambda s: (-(s.rate or 0.0), s.segment_id)):
        ci = f"{_fmt(s.rate_ci_low)}–{_fmt(s.rate_ci_high)}"
        # Non-overlap in either direction counts as distinguishable.
        low = s.rate_ci_low or 0.0
        high = s.rate_ci_high or 0.0
        distinguishable = low > ref_high or high < (reference.rate_ci_low or 0.0)
        mark = "yes" if distinguishable else "no"
        if s.segment_id == reference.segment_id:
            mark = "— (reference)"
        name = names.get(s.segment_id, s.segment_id)
        out.append(f"| {name} | {s.report_count} | {_fmt(s.rate)} | {ci} | {mark} |")
    out.append("")
    return out


def render_note(config: Config, city: CityInputs) -> str:
    _, baseline_result = _analyze_variant(config, city)
    names = {s.id: s.name for s in city.segments}
    per = config.rate_per
    lines: list[str] = []
    lines.append(f"# Threshold sensitivity & statistical power — {config.city}")
    lines.append("")
    lines.append(
        "Generated by `tools/sensitivity_note.py` (R29 / R34). Deterministic and byte-stable — "
        "regenerate with `make sensitivity`. No embedded date, so `make reproduce` can diff it."
    )
    lines.append("")
    lines.append(
        f"Baseline thresholds: `snap_max_m={config.snap_max_m:g}`, "
        f"`dedupe_distance_m={config.dedupe_distance_m:g}`, "
        f"`dedupe_window_s={config.dedupe_window_s}`, "
        f"`min_publish_n={config.min_publish_n}`, `small_n={config.small_n}`."
    )
    lines.append("")

    lines.append("## Snapping / dedupe threshold sensitivity")
    lines.append("")
    lines.append(
        "Each row re-runs the whole pipeline and the exposure-normalized ranking under one "
        "combination of the snapping/dedupe thresholds. **Dropped** is reports left unsnapped "
        "(no street within `snap_max_m`); **Deduped** is near-duplicate reports removed. "
        "**Top-5** is how many of the baseline's top-5 ranked segments survive in the variant's "
        "top-5; **Pair agree** is the Kendall-tau-style fraction of segment pairs the variant "
        "orders the same way as the baseline (1.00 = identical order). A ranking that holds across "
        "the grid is robust to the threshold choice; one that swings is fragile and is read with "
        "that caveat."
    )
    lines.append("")
    lines.append(
        "| snap_max_m | dedupe_dist_m | dedupe_win_s | Deduped | Snapped | Dropped | "
        "Top-5 | Pair agree |"
    )
    lines.append("| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")
    lines.extend(_sensitivity_rows(config, city))
    lines.append("")

    lines.extend(_power_note(config, baseline_result, names))

    lines.append("---")
    lines.append("")
    lines.append(
        f"Rates are per {per:g} {config.exposure_unit}. See docs/METHODOLOGY.md "
        "§5 (rates & intervals) and §3 (snapping/dedupe) for the underlying method."
    )
    lines.append("")
    return "\n".join(lines)


def write_note(config: Config, out_dir: Path) -> Path:
    city = load_city(config)
    note = render_note(config, city)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{_slug(config.city)}-sensitivity.md"
    path.write_text(note, encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Emit a per-city threshold-sensitivity + statistical-power note (R29/R34).",
    )
    parser.add_argument("--config", required=True, help="path to a city config TOML/JSON")
    parser.add_argument(
        "--out",
        default=None,
        help="output directory (default: the config's out_dir, i.e. data/published)",
    )
    args = parser.parse_args(argv)

    config = load_config(args.config)
    out_dir = Path(args.out) if args.out else config.out_dir
    path = write_note(config, out_dir)
    print(f"sensitivity: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
