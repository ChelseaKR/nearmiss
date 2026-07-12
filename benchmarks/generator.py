#!/usr/bin/env python3
"""Generate the planted-truth benchmark cities (EXP-09).

``tools/make_fixtures.py`` and ``tools/benchmark.py`` each hand-roll one
synthetic city: a fixed known-answer grid for tests, and a size-scalable grid
for timing. This generator is the generalization the ideation doc
(``docs/ideation/03-expansions.md``, EXP-09) asked for: a single, seeded,
regime-parameterized generator that plants KNOWN ground truth — true hotspots,
two kinds of decoys, and a controllable set of statistical traps — into a
street grid, so ANY hotspot-detection tool (not just nearmiss) can be scored
against a known answer.

Ground truth per segment falls into four roles:

  * ``hotspot``               — genuinely elevated incident rate (planted signal
    a good method MUST find). Laid out as a plus-shaped 5-cell cluster so a
    neighborhood statistic (Getis-Ord Gi*) has spatial support, not an
    isolated cell.
  * ``decoy_exposure``        — high exposure -> high RAW report count, but a
    baseline (non-elevated) rate once normalized. A method that ranks by raw
    count instead of a normalized rate fails this one (the classic
    heat-map-lie decoy, generalizing ``tests/fixtures/davis`` seg-03).
  * ``decoy_reporting_bias``  — baseline true incident rate AND baseline
    exposure, but an elevated REPORTING probability. Because reports (not
    incidents) are the only observable signal, this decoy inflates the
    observed rate even after honest exposure normalization — exposure
    normalization cannot fix a reporting-propensity confound. Nearmiss's own
    Getis-Ord layer does not correct for this (see ``stats/bias.py``): scoring
    it is meant to make that known limitation visible and measurable, not to
    make nearmiss look flawless. That is the point of a benchmark suite that
    is a referee, not just a contestant.
  * ``background``            — everything else: baseline rate, baseline
    exposure, no trap. Should almost never be flagged significant.

Four regimes stress different honesty properties, each varying exactly ONE
axis from the ``baseline`` regime (see ``benchmarks/configs/*.json``):

  * ``baseline``          — control: pure Poisson, no bias, no exposure error.
  * ``reporting_bias``    — ``decoy_reporting_bias`` cells get an elevated
    reporting multiplier (tests whether a tool distinguishes risk from
    reporting propensity).
  * ``overdispersion``    — incident counts are drawn Gamma-Poisson (negative
    binomial) instead of pure Poisson, so the variance exceeds the Poisson
    assumption (tests whether Poisson confidence intervals stay honest, i.e.
    interval coverage, under overdispersion).
  * ``exposure_error``    — the PUBLISHED exposure is a noisy (lognormal)
    version of the true exposure used to generate incidents (tests
    sensitivity to imperfect exposure denominators, which is the normal case
    in the real world).
  * ``maup_fine`` / ``maup_coarse`` — the identical underlying report
    locations, published at two different street-segment granularities (tests
    the Modifiable Areal Unit Problem: does the same signal survive a change
    of spatial units?).

Everything is deterministic and seeded (stdlib ``random`` only, no extra
dependency): the same config always produces byte-identical output, so the
"known answers" claim in the README is independently checkable by re-running
this file and diffing (``make bench-suite-verify``).

Run from the repo root:
    python benchmarks/generator.py                    # regenerate every city
    python benchmarks/generator.py --config baseline   # regenerate one city
"""

from __future__ import annotations

import argparse
import json
import math
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import cast

ROOT = Path(__file__).resolve().parents[1]
CONFIGS_DIR = Path(__file__).resolve().parent / "configs"
CITIES_DIR = Path(__file__).resolve().parent / "cities"

SUITE_VERSION = "1.0.0"
T0 = datetime(2026, 6, 1, 7, 0, 0, tzinfo=timezone(timedelta(hours=-7)))
REPORT_SPACING_MIN = 15  # global minutes between successive reports; keeps every
# report pair well outside any plausible dedupe_window_s (default 600s = 10min),
# so the observed report count always equals the sampled count -- no incidental
# dedupe -- and the ground-truth manifest stays exactly checkable.


@dataclass(frozen=True)
class RegimeConfig:
    """One benchmark regime: everything needed to regenerate its city."""

    name: str
    seed: int
    rows: int = 9
    cols: int = 9
    rate_per: float = 1000.0
    baseline_lambda: float = 10.0  # true incidents per rate_per exposure units
    baseline_exposure: float = 300.0
    hotspot_core_multiplier: float = 6.0  # centre of the planted cluster
    hotspot_cluster_multiplier: float = 3.0  # the 4 plus-shape neighbours
    decoy_exposure_multiplier: float = 10.0  # exposure multiplier for exposure decoys
    decoy_reporting_multiplier: float = 1.0  # >1.0 activates the reporting-bias trap
    overdispersion_phi: float = 0.0  # 0 = pure Poisson; >0 = Gamma-Poisson dispersion
    exposure_error_sigma: float = 0.0  # 0 = published exposure == true exposure
    merge_cols: int = 1  # >1 aggregates that many adjacent columns into one segment (MAUP)
    n_decoy_exposure: int = 3
    n_decoy_reporting_bias: int = 3
    notes: str = ""

    @staticmethod
    def from_json(path: Path) -> RegimeConfig:
        data = json.loads(path.read_text(encoding="utf-8"))
        return RegimeConfig(**data)


@dataclass
class Cell:
    row: int
    col: int
    lat: float
    lon: float
    role: str  # "hotspot" | "decoy_exposure" | "decoy_reporting_bias" | "background"
    true_lambda: float
    true_exposure: float
    reporting_multiplier: float
    # Filled in by _sample_cells(): the ONE random draw per cell, independent of
    # merge_cols. This is what makes maup_fine and maup_coarse (same seed) share
    # byte-identical reports.json -- sampling happens at the finest grain first,
    # and merging (see _build_segments) only re-buckets already-sampled cells.
    mean_reports: float = 0.0
    observed_reports: int = 0
    published_exposure: float = 0.0


@dataclass
class Segment:
    segment_id: str
    name: str
    coords: tuple[tuple[float, float], tuple[float, float]]
    role: str
    true_lambda: float
    true_exposure: float
    published_exposure: float
    reporting_multiplier: float
    mean_reports: float
    observed_reports: int
    cell_ids: list[str] = field(default_factory=list)


def _poisson(rng: random.Random, mean: float) -> int:
    """Knuth's algorithm. Stdlib-only (no numpy dependency in this project)."""
    if mean <= 0:
        return 0
    # For the means used here (well under a few hundred) this is fast and exact;
    # a more elaborate transformed-rejection sampler is unnecessary at this scale.
    limit = math.exp(-mean)
    k = 0
    p = 1.0
    while True:
        k += 1
        p *= rng.random()
        if p <= limit:
            return k - 1


def _cluster_offsets() -> list[tuple[int, int, str]]:
    """Plus-shape: (row_off, col_off, sub-role). Mirrors tools/make_fixtures.py's
    proven pattern of a hot centre with hot cross-street neighbours, which is what
    gives Getis-Ord Gi* spatial support to call the cluster significant."""
    return [
        (0, 0, "core"),
        (-1, 0, "cluster"),
        (1, 0, "cluster"),
        (0, -1, "cluster"),
        (0, 1, "cluster"),
    ]


def _decoy_positions(
    rows: int, cols: int, count: int, taken: set[tuple[int, int]]
) -> list[tuple[int, int]]:
    """Deterministically pick `count` cell positions spread across the grid,
    away from anything already taken. No RNG -- placement is a fixed function of
    grid size, only the report COUNTS are randomized."""
    out: list[tuple[int, int]] = []
    r, c = 1, 1
    step_r, step_c = max(1, rows // 4), max(1, cols // 4)
    while len(out) < count:
        pos = (r % rows, c % cols)
        if pos not in taken:
            out.append(pos)
            taken.add(pos)
        c += step_c
        if c >= cols:
            c = c % max(cols, 1)
            r += step_r
    return out


def _build_cells(cfg: RegimeConfig) -> dict[tuple[int, int], Cell]:
    center = (cfg.rows // 2, cfg.cols // 2)
    taken: set[tuple[int, int]] = set()
    roles: dict[tuple[int, int], tuple[str, float, float, float]] = {}

    for dr, dc, sub in _cluster_offsets():
        pos = (center[0] + dr, center[1] + dc)
        mult = cfg.hotspot_core_multiplier if sub == "core" else cfg.hotspot_cluster_multiplier
        roles[pos] = ("hotspot", cfg.baseline_lambda * mult, cfg.baseline_exposure, 1.0)
        taken.add(pos)

    for pos in _decoy_positions(cfg.rows, cfg.cols, cfg.n_decoy_exposure, taken):
        roles[pos] = (
            "decoy_exposure",
            cfg.baseline_lambda,
            cfg.baseline_exposure * cfg.decoy_exposure_multiplier,
            1.0,
        )

    for pos in _decoy_positions(cfg.rows, cfg.cols, cfg.n_decoy_reporting_bias, taken):
        roles[pos] = (
            "decoy_reporting_bias",
            cfg.baseline_lambda,
            cfg.baseline_exposure,
            cfg.decoy_reporting_multiplier,
        )

    lat0, lon0 = 38.5, -121.7
    dlat, dlon = 0.0025, 0.0030  # ~ meets gi_band_m default (300m) between neighbours
    cells: dict[tuple[int, int], Cell] = {}
    for r in range(cfg.rows):
        for c in range(cfg.cols):
            role, lam, exp_, rep_mult = roles.get(
                (r, c), ("background", cfg.baseline_lambda, cfg.baseline_exposure, 1.0)
            )
            cells[(r, c)] = Cell(
                row=r,
                col=c,
                lat=round(lat0 + r * dlat, 6),
                lon=round(lon0 + c * dlon, 6),
                role=role,
                true_lambda=lam,
                true_exposure=exp_,
                reporting_multiplier=rep_mult,
            )
    return cells


_ROLE_PRECEDENCE = ("hotspot", "decoy_reporting_bias", "decoy_exposure", "background")


def _merge_role(roles: list[str]) -> str:
    for r in _ROLE_PRECEDENCE:
        if r in roles:
            return r
    return "background"


def _sample_cells(
    cfg: RegimeConfig, cells: dict[tuple[int, int], Cell], rng: random.Random
) -> None:
    """Draw the ONE random outcome per cell, in a fixed row-major order that
    does not depend on merge_cols. This is what lets maup_fine and maup_coarse
    (same seed) share byte-identical reports.json -- sampling always happens at
    the finest grain; merging (_build_segments) only re-buckets afterwards."""
    for r in range(cfg.rows):
        for c in range(cfg.cols):
            cell = cells[(r, c)]
            mean_incidents = cell.true_lambda * cell.true_exposure / cfg.rate_per
            mean_reports = mean_incidents * cell.reporting_multiplier
            if cfg.overdispersion_phi > 0:
                # Gamma-Poisson mixture: per-cell Gamma(shape=1/phi, scale=phi) has
                # mean 1, so E[reports] is unchanged but Var(reports) > mean
                # (negative binomial), i.e. overdispersed relative to the Poisson
                # assumption the published confidence interval makes.
                g = rng.gammavariate(1.0 / cfg.overdispersion_phi, cfg.overdispersion_phi)
                mean_reports *= g
            cell.mean_reports = mean_reports
            cell.observed_reports = _poisson(rng, mean_reports)
            if cfg.exposure_error_sigma > 0:
                # Lognormal, mean-1 multiplicative noise: the published exposure a
                # tool sees differs from the true exposure used to generate
                # incidents (mirrors a real, imperfect exposure survey).
                mu = -(cfg.exposure_error_sigma**2) / 2.0
                cell.published_exposure = cell.true_exposure * math.exp(
                    rng.gauss(mu, cfg.exposure_error_sigma)
                )
            else:
                cell.published_exposure = cell.true_exposure


def _cell_reports(cfg: RegimeConfig, cells: dict[tuple[int, int], Cell]) -> list[dict[str, object]]:
    """Render each cell's already-sampled report count into report records,
    placed on a short local line around the cell's own point -- independent of
    how cells are later grouped into published segments."""
    reports: list[dict[str, object]] = []
    i = 0
    half_width = 0.0006
    for r in range(cfg.rows):
        for c in range(cfg.cols):
            cell = cells[(r, c)]
            k = cell.observed_reports
            for j in range(k):
                i += 1
                t = (j + 0.5) / max(k, 1)
                lat = cell.lat + (0.00003 if i % 2 == 0 else -0.00003)
                lon = cell.lon - half_width + t * (2 * half_width)
                reports.append(
                    {
                        "schema_version": "1.0.0",
                        "id": f"00000000-0000-4000-8000-{i:012x}",
                        "occurred_at": (T0 + timedelta(minutes=REPORT_SPACING_MIN * i)).isoformat(),
                        "location": {"lat": round(lat, 6), "lon": round(lon, 6)},
                        "mode": ["cyclist", "cyclist", "pedestrian", "scooter"][i % 4],
                        "hazard_type": ["close_pass", "surface_hazard", "dooring"][i % 3],
                        "severity": ["near_miss", "near_miss", "minor"][i % 3],
                    }
                )
    return reports


def _build_segments(cfg: RegimeConfig, cells: dict[tuple[int, int], Cell]) -> list[Segment]:
    """Group already-sampled cells into published segments, merging
    `merge_cols` adjacent columns per row into one segment. merge_cols=1 is a
    no-op (one cell each), used by every non-MAUP regime; merge_cols>1 is the
    MAUP "coarse" variant. No RNG here -- pure deterministic aggregation of the
    per-cell draws _sample_cells already made."""
    segments: list[Segment] = []
    for r in range(cfg.rows):
        c = 0
        while c < cfg.cols:
            group = [cells[(r, cc)] for cc in range(c, min(c + cfg.merge_cols, cfg.cols))]
            c += cfg.merge_cols
            sid = f"seg-{r:02d}-{group[0].col:02d}"
            lat = group[0].lat
            lon_lo = min(g.lon for g in group) - 0.0008
            lon_hi = max(g.lon for g in group) + 0.0008
            true_exposure = sum(g.true_exposure for g in group)
            # Weighted-average true incident rate across the merged cells, weighted
            # by each cell's own exposure (so a merged segment's "true rate" is the
            # exposure-weighted rate an honest observer would recover).
            true_lambda = (
                sum(g.true_lambda * g.true_exposure for g in group) / true_exposure
                if true_exposure > 0
                else 0.0
            )
            # A merged segment's effective reporting multiplier is likewise the
            # exposure-weighted average of its cells' multipliers.
            reporting_multiplier = (
                sum(g.reporting_multiplier * g.true_exposure for g in group) / true_exposure
                if true_exposure > 0
                else 1.0
            )
            role = _merge_role([g.role for g in group])
            segments.append(
                Segment(
                    segment_id=sid,
                    name=f"Row {r} Ave {group[0].col}-{group[-1].col}",
                    coords=((lat, lon_lo), (lat, lon_hi)),
                    role=role,
                    true_lambda=true_lambda,
                    true_exposure=true_exposure,
                    published_exposure=sum(g.published_exposure for g in group),
                    reporting_multiplier=reporting_multiplier,
                    mean_reports=sum(g.mean_reports for g in group),
                    observed_reports=sum(g.observed_reports for g in group),
                    cell_ids=[f"cell-{g.row:02d}-{g.col:02d}" for g in group],
                )
            )
    return segments


def generate(
    cfg: RegimeConfig,
) -> tuple[dict[str, object], dict[str, object], dict[str, object], dict[str, object]]:
    """Return (streets_geojson, exposure_json, reports_json, ground_truth_json)."""
    rng = random.Random(cfg.seed)
    cells = _build_cells(cfg)
    _sample_cells(cfg, cells, rng)
    reports = _cell_reports(cfg, cells)
    segments = _build_segments(cfg, cells)

    streets: dict[str, object] = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {
                    "type": "LineString",
                    "coordinates": [
                        [seg.coords[0][1], seg.coords[0][0]],
                        [seg.coords[1][1], seg.coords[1][0]],
                    ],
                },
                "properties": {"segment_id": seg.segment_id, "name": seg.name},
            }
            for seg in segments
        ],
    }
    exposure: dict[str, object] = {
        "segments": [
            {
                "segment_id": seg.segment_id,
                "estimate": round(seg.published_exposure, 3),
                "source": "benchmark_synthetic",
                "date": "2026-05-01",
            }
            for seg in segments
        ]
    }
    by_role: dict[str, list[str]] = {r: [] for r in _ROLE_PRECEDENCE}
    seg_truth: dict[str, object] = {}
    for seg in segments:
        by_role[seg.role].append(seg.segment_id)
        seg_truth[seg.segment_id] = {
            "role": seg.role,
            "true_lambda": round(seg.true_lambda, 6),
            "true_incident_rate_per": round(seg.true_lambda, 6),
            "true_exposure": round(seg.true_exposure, 3),
            "published_exposure": round(seg.published_exposure, 3),
            "reporting_multiplier": round(seg.reporting_multiplier, 6),
            "mean_reports": round(seg.mean_reports, 6),
            "observed_reports": seg.observed_reports,
        }
    ground_truth: dict[str, object] = {
        "suite_version": SUITE_VERSION,
        "regime": cfg.name,
        "seed": cfg.seed,
        "rate_per": cfg.rate_per,
        "true_hotspot_segments": sorted(by_role["hotspot"]),
        "decoy_exposure_segments": sorted(by_role["decoy_exposure"]),
        "decoy_reporting_bias_segments": sorted(by_role["decoy_reporting_bias"]),
        "background_segments": sorted(by_role["background"]),
        "segments": dict(sorted(seg_truth.items())),
    }
    return streets, exposure, {"reports": reports}, ground_truth


def _write_config_toml(city_dir: Path, cfg: RegimeConfig) -> None:
    toml_text = f'''# Generated by benchmarks/generator.py, regime "{cfg.name}". Do not hand-edit;
# re-run the generator instead. Lets any tool run nearmiss itself against this
# city via:
#   nearmiss analyze --config benchmarks/cities/{cfg.name}/config.toml
city = "benchmark-{cfg.name}"
streets = "streets.geojson"
reports = "reports.json"
exposure = "exposure.json"
raw_dir = "/tmp/nm-bench-{cfg.name}-raw"
out_dir = "/tmp/nm-bench-{cfg.name}-pub"
exposure_unit = "synthetic exposure units"
dataset_note = "SYNTHETIC benchmark city (planted-truth suite v{SUITE_VERSION}, regime={cfg.name})."

[thresholds]
rate_per = {cfg.rate_per}
'''
    (city_dir / "config.toml").write_text(toml_text, encoding="utf-8")


def write_city(cfg: RegimeConfig) -> Path:
    city_dir = CITIES_DIR / cfg.name
    city_dir.mkdir(parents=True, exist_ok=True)
    streets, exposure, reports, ground_truth = generate(cfg)
    (city_dir / "streets.geojson").write_text(
        json.dumps(streets, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (city_dir / "exposure.json").write_text(
        json.dumps(exposure, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (city_dir / "reports.json").write_text(
        json.dumps(reports, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (city_dir / "ground_truth.json").write_text(
        json.dumps(ground_truth, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    _write_config_toml(city_dir, cfg)
    n_segments = len(cast(list[object], exposure["segments"]))
    n_reports = len(cast(list[object], reports["reports"]))
    print(
        f"wrote {cfg.name}: {n_segments} segments, "
        f"{n_reports} reports -> {city_dir.relative_to(ROOT)}"
    )
    return city_dir


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--config",
        action="append",
        help="regime name (file stem under benchmarks/configs/) to regenerate; "
        "repeatable. Default: regenerate every config.",
    )
    args = parser.parse_args()
    names = args.config or sorted(p.stem for p in CONFIGS_DIR.glob("*.json"))
    for name in names:
        cfg = RegimeConfig.from_json(CONFIGS_DIR / f"{name}.json")
        write_city(cfg)


if __name__ == "__main__":
    main()
