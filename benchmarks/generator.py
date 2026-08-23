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
    a good method MUST find). Laid out as a plus-shaped 5-segment cluster (one
    strongly elevated centre avenue block + its north, south, east, and west
    neighbours) so a neighbourhood statistic (Getis-Ord Gi*) has real
    street-network spatial support, not an isolated cell — see "The street
    grid" below for how that support is actually wired up.
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

The street grid
----------------

Issue #196: through 2026-08-19 this generator laid every city out as short,
mutually non-touching stubs (~122 m gaps against a 5 m node-snap tolerance),
so the adjacency graph ``nearmiss.network.SegmentGraph`` builds from
``streets.geojson`` had no edges at all — every segment was a singleton
neighbourhood (ADR-0015, issue #193), and every "Gi* z" this suite ever
scored was actually the plain global z-score.

Cities are now a real, connected two-layer grid:

  * **Avenue segments** (east-west) — one per grid cell ``(row, col)``, same
    role/rate/exposure planting as before. Cell ``(r, c)``'s avenue block
    spans from the intersection boundary just west of it to the one just
    east (``_boundary_lon``), not a fixed pad around its own point, so
    consecutive avenue blocks in a row share an exact endpoint and the row is
    one connected street. ``merge_cols`` merges ``merge_cols`` adjacent cells'
    blocks into one wider published segment (the MAUP regime pair) by moving
    the shared endpoint outward; the outer endpoints of a merge group are
    still real boundary nodes, so a merged block still meets its row
    neighbours exactly.
  * **Cross-street segments** (north-south) — one per intersection boundary
    column, connecting every pair of adjacent avenue rows, always at full
    (unmerged) granularity regardless of ``merge_cols``. These carry no
    planted signal (always ``background``, baseline rate) — they exist to
    give the grid real intersections. Every avenue segment's own two
    endpoints are boundary nodes, so it always has a cross-street touching
    each end, reaching the same-column avenue block one row north or south in
    two hops. That is what gives the plus-shaped hotspot cluster (and every
    other segment) genuine street-network neighbours: the centre and its
    east/west neighbours touch directly; the north/south neighbours are two
    hops away via a cross-street, both comfortably inside the default
    ``gi_band_m`` (300 m) at this grid's ~100 m block spacing (see ``DLAT``
    / ``DLON`` below).

    A cross-street at a boundary a coarse (``merge_cols`` > 1) avenue group
    has swallowed loses its link to the avenue layer at that column — its two
    ends no longer coincide with any avenue segment's endpoint — while
    staying connected to its own north-south neighbours. That is not routed
    around: re-drawing published segment boundaries at a coarser grain is
    exactly what the MAUP regime pair is testing, and the scorer measures
    whatever topology that produces rather than assuming the fine city's
    connectivity survives intact.

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
this file and diffing (``make bench-suite-verify``). Cross-street cells are
sampled in a fixed order strictly AFTER every avenue cell, and their
existence and count never depend on ``merge_cols`` (only avenue grouping
does) — so ``maup_fine`` and ``maup_coarse``, which share a seed, still share
byte-identical ``reports.json``.

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

SUITE_VERSION = "2.0.0"
T0 = datetime(2026, 6, 1, 7, 0, 0, tzinfo=timezone(timedelta(hours=-7)))
REPORT_SPACING_MIN = 15  # global minutes between successive reports; keeps every
# report pair well outside any plausible dedupe_window_s (default 600s = 10min),
# so the observed report count always equals the sampled count -- no incidental
# dedupe -- and the ground-truth manifest stays exactly checkable.

# Grid origin and spacing. Each block (one avenue segment, or one row-gap of
# one cross-street) is ~100 m, so the 2-hop network path a plus-shape cluster
# neighbour must clear -- half the centre block + one cross-street + half the
# neighbour block, ~200 m at merge_cols=1 -- comfortably clears the default
# gi_band_m (300 m, nearmiss.config.DEFAULT gi_band_m) with real margin, while
# a 3-hop path (two blocks away) sits around 300-350 m and mostly does not.
# DLON is shorter in degrees than DLAT because a degree of longitude is
# ~cos(LAT0) times a degree of latitude at this latitude.
LAT0 = 38.5
LON0 = -121.7
DLAT = 0.0009  # ~100.2 m of latitude
DLON = 0.00115  # ~100.4 m of longitude at LAT0 (1 deg lon ~ 111_320*cos(38.5deg) m)

# Report-location jitter, scaled off the block spacing so a report always sits
# well inside its owning segment and clear of the shared boundary node with
# the next one (never ambiguous between two segments that happen to touch
# there). The small perpendicular offset (alternating +/-) is a fixed, tiny
# amount of simulated GPS noise, independent of block size.
_LON_JITTER_HALF_WIDTH = 0.35 * DLON
_LAT_JITTER_HALF_WIDTH = 0.35 * DLAT
_PERP_JITTER = 0.00003


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
    # Filled in by _sample_one(): the ONE random draw per cell, independent of
    # merge_cols. This is what makes maup_fine and maup_coarse (same seed) share
    # byte-identical reports.json -- sampling happens at the finest grain first,
    # and merging (see _build_avenue_segments) only re-buckets already-sampled cells.
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


def _node_lat(r: int) -> float:
    return LAT0 + r * DLAT


def _node_lon(c: int) -> float:
    return LON0 + c * DLON


def _boundary_lon(c: int) -> float:
    """Longitude of the intersection boundary immediately WEST of grid column
    ``c`` (``c`` in ``0..cols`` is valid: ``0`` is half a block west of the
    first column, ``cols`` is half a block east of the last). An avenue
    segment covering columns ``[c, end)`` spans ``_boundary_lon(c)`` to
    ``_boundary_lon(end)``; every cross-street at boundary ``c`` shares that
    exact point, which is what makes them touch (issue #196)."""
    return LON0 + (c - 0.5) * DLON


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

    cells: dict[tuple[int, int], Cell] = {}
    for r in range(cfg.rows):
        for c in range(cfg.cols):
            role, lam, exp_, rep_mult = roles.get(
                (r, c), ("background", cfg.baseline_lambda, cfg.baseline_exposure, 1.0)
            )
            cells[(r, c)] = Cell(
                row=r,
                col=c,
                lat=round(_node_lat(r), 6),
                lon=round(_node_lon(c), 6),
                role=role,
                true_lambda=lam,
                true_exposure=exp_,
                reporting_multiplier=rep_mult,
            )
    return cells


def _build_connector_cells(cfg: RegimeConfig) -> dict[tuple[int, int], Cell]:
    """One 'cell' per cross-street: the north-south block connecting avenue
    row ``r`` to row ``r + 1`` at intersection boundary column ``b``. These
    carry no planted signal (always ``background``, baseline rate/exposure)
    -- they exist purely to give the grid real intersections, so the
    plus-shaped hotspot cluster (and every other segment) has genuine
    street-network neighbours instead of the isolated stubs issue #196
    found. Keyed by ``(row_gap, boundary_col)``, a disjoint index space from
    ``_build_cells``'s ``(row, col)`` so the two dicts never collide, and
    positioned at each cross-street's own midpoint -- clear of the shared
    endpoints with the avenue layer, for the same snapping reason
    ``_boundary_lon`` gives avenue blocks their span rather than a pad."""
    connectors: dict[tuple[int, int], Cell] = {}
    for r in range(cfg.rows - 1):
        mid_lat = round((_node_lat(r) + _node_lat(r + 1)) / 2.0, 6)
        for b in range(cfg.cols + 1):
            connectors[(r, b)] = Cell(
                row=r,
                col=b,
                lat=mid_lat,
                lon=round(_boundary_lon(b), 6),
                role="background",
                true_lambda=cfg.baseline_lambda,
                true_exposure=cfg.baseline_exposure,
                reporting_multiplier=1.0,
            )
    return connectors


_ROLE_PRECEDENCE = ("hotspot", "decoy_reporting_bias", "decoy_exposure", "background")


def _merge_role(roles: list[str]) -> str:
    for r in _ROLE_PRECEDENCE:
        if r in roles:
            return r
    return "background"


def _sample_one(cfg: RegimeConfig, cell: Cell, rng: random.Random) -> None:
    """Draw the ONE random outcome for a cell (grid cell or connector),
    mutating it in place. Called in a fixed order that does not depend on
    merge_cols -- see _sample_cells / _sample_connectors -- which is what
    lets maup_fine and maup_coarse (same seed) share byte-identical
    reports.json."""
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


def _sample_cells(
    cfg: RegimeConfig, cells: dict[tuple[int, int], Cell], rng: random.Random
) -> None:
    """Sample every grid cell, row-major, ahead of any connector -- see
    _sample_one."""
    for r in range(cfg.rows):
        for c in range(cfg.cols):
            _sample_one(cfg, cells[(r, c)], rng)


def _sample_connectors(
    cfg: RegimeConfig, connectors: dict[tuple[int, int], Cell], rng: random.Random
) -> None:
    """Sample every cross-street connector, row-gap-major, strictly AFTER
    every grid cell (see _sample_cells) and independent of merge_cols -- so
    the connector draws are identical between maup_fine and maup_coarse too."""
    for r in range(cfg.rows - 1):
        for b in range(cfg.cols + 1):
            _sample_one(cfg, connectors[(r, b)], rng)


def _report_record(i: int, lat: float, lon: float) -> dict[str, object]:
    return {
        "schema_version": "1.0.0",
        "id": f"00000000-0000-4000-8000-{i:012x}",
        "occurred_at": (T0 + timedelta(minutes=REPORT_SPACING_MIN * i)).isoformat(),
        "location": {"lat": round(lat, 6), "lon": round(lon, 6)},
        "mode": ["cyclist", "cyclist", "pedestrian", "scooter"][i % 4],
        "hazard_type": ["close_pass", "surface_hazard", "dooring"][i % 3],
        "severity": ["near_miss", "near_miss", "minor"][i % 3],
    }


def _cell_reports(
    cells_in_order: list[Cell], start_i: int = 0
) -> tuple[list[dict[str, object]], int]:
    """Render each already-sampled avenue cell's report count into report
    records, on a short local line straddling the cell's own point along the
    avenue's east-west axis -- independent of how cells are later grouped
    into published segments, and kept well clear of the shared boundary node
    with the next cell (_LON_JITTER_HALF_WIDTH) so a report always snaps to
    the intended segment, never a neighbour it happens to touch."""
    reports: list[dict[str, object]] = []
    i = start_i
    for cell in cells_in_order:
        k = cell.observed_reports
        for j in range(k):
            i += 1
            t = (j + 0.5) / max(k, 1)
            lat = cell.lat + (_PERP_JITTER if i % 2 == 0 else -_PERP_JITTER)
            lon = cell.lon - _LON_JITTER_HALF_WIDTH + t * (2 * _LON_JITTER_HALF_WIDTH)
            reports.append(_report_record(i, lat, lon))
    return reports, i


def _connector_reports(
    cells_in_order: list[Cell], start_i: int
) -> tuple[list[dict[str, object]], int]:
    """Same idea as _cell_reports, but jittered along the connector's own
    north-south axis, since a cross-street runs perpendicular to an avenue."""
    reports: list[dict[str, object]] = []
    i = start_i
    for cell in cells_in_order:
        k = cell.observed_reports
        for j in range(k):
            i += 1
            t = (j + 0.5) / max(k, 1)
            lon = cell.lon + (_PERP_JITTER if i % 2 == 0 else -_PERP_JITTER)
            lat = cell.lat - _LAT_JITTER_HALF_WIDTH + t * (2 * _LAT_JITTER_HALF_WIDTH)
            reports.append(_report_record(i, lat, lon))
    return reports, i


def _build_avenue_segments(cfg: RegimeConfig, cells: dict[tuple[int, int], Cell]) -> list[Segment]:
    """Group already-sampled cells into published east-west segments, merging
    `merge_cols` adjacent columns per row into one segment. merge_cols=1 is a
    no-op (one cell each), used by every non-MAUP regime; merge_cols>1 is the
    MAUP "coarse" variant. No RNG here -- pure deterministic aggregation of the
    per-cell draws _sample_cells already made. A segment's endpoints are the
    shared intersection boundaries either side of its cell group
    (_boundary_lon), not a pad around the cells -- so consecutive avenue
    segments, and every cross-street at a surviving boundary, meet exactly."""
    segments: list[Segment] = []
    for r in range(cfg.rows):
        c = 0
        while c < cfg.cols:
            group = [cells[(r, cc)] for cc in range(c, min(c + cfg.merge_cols, cfg.cols))]
            c += cfg.merge_cols
            sid = f"seg-{r:02d}-{group[0].col:02d}"
            lat = round(_node_lat(r), 6)
            lon_lo = round(_boundary_lon(group[0].col), 6)
            lon_hi = round(_boundary_lon(group[-1].col + 1), 6)
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


def _build_cross_street_segments(
    cfg: RegimeConfig, connectors: dict[tuple[int, int], Cell]
) -> list[Segment]:
    """One published north-south segment per connector cell, always at full
    (unmerged) granularity regardless of `merge_cols` -- MAUP coarsening
    (_build_avenue_segments) only re-buckets avenue segments, never these.
    See the module docstring's "The street grid" section for what that does
    and does not preserve under coarsening."""
    segments: list[Segment] = []
    for r in range(cfg.rows - 1):
        lat_lo = round(_node_lat(r), 6)
        lat_hi = round(_node_lat(r + 1), 6)
        for b in range(cfg.cols + 1):
            cell = connectors[(r, b)]
            lon = round(_boundary_lon(b), 6)
            segments.append(
                Segment(
                    segment_id=f"xst-{r:02d}-{b:02d}",
                    name=f"Cross St {b} Row {r}-{r + 1}",
                    coords=((lat_lo, lon), (lat_hi, lon)),
                    role=cell.role,
                    true_lambda=cell.true_lambda,
                    true_exposure=cell.true_exposure,
                    published_exposure=cell.published_exposure,
                    reporting_multiplier=cell.reporting_multiplier,
                    mean_reports=cell.mean_reports,
                    observed_reports=cell.observed_reports,
                    cell_ids=[f"xcell-{r:02d}-{b:02d}"],
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
    connectors = _build_connector_cells(cfg)
    _sample_connectors(cfg, connectors, rng)

    cell_order = [cells[(r, c)] for r in range(cfg.rows) for c in range(cfg.cols)]
    connector_order = [connectors[(r, b)] for r in range(cfg.rows - 1) for b in range(cfg.cols + 1)]
    cell_reports, next_i = _cell_reports(cell_order)
    connector_reports, _next_i = _connector_reports(connector_order, next_i)
    reports = cell_reports + connector_reports

    segments = _build_avenue_segments(cfg, cells) + _build_cross_street_segments(cfg, connectors)

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
