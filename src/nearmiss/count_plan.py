"""Targeted manual-count plans for cities that have reports and no denominator.

The hard rule is *a denominator per rate, or no rate* (METHODOLOGY §3.3), and the
measured fact behind this module is that no open US dataset pairs near-miss
reports with the bicycle/pedestrian counts a rate needs. Today a city in that
position gets ``exposure unknown`` on every segment and an analysis that cannot
rank anything — a correct answer that leaves a group with nothing to do.

This module turns that refusal into a deliverable: **which segments to count
first, for how long, and what a count of that length would let anyone say.** It
never invents a denominator, never ranks danger, and never converts a report
volume into a risk statement. A plan is a work list, not a measurement.

Three things it deliberately refuses to do
------------------------------------------

1. **It will not guess a flow rate.** How many hours a segment needs depends on
   how many people pass it per hour, which is the very thing nobody has counted.
   With no ``assumed_flow_per_hour`` supplied the hours column is ``None`` with a
   stated reason, not a plausible number. An hours figure a group plans volunteer
   time around is a claim, and a claim needs an input.
2. **It will not hide the expansion factor.** A session count is not an annual
   denominator. When sessions differ in length, their counts are not even
   comparable to each other, so the factor that puts them on one basis is a
   per-row field of the plan (and of the count sheet), never a config default
   folded invisibly into a number.
3. **It will not present an empty plan as a finished city.** "Every segment that
   carries a report already has a denominator", "no report reached a segment" and
   "this city has no reports" are three different facts and get three different
   statuses.

The statistics
--------------

Write ``y`` for a segment's report count and ``N`` for the number of people a
volunteer would observe passing it during the planned session. The published
rate is ``y / E`` where ``E`` is proportional to ``N``, so on the log scale the
two sources of sampling error simply add::

    SE(log rate) = sqrt(1/y + 1/N)

Both terms are the Poisson relative standard error of a count. Two consequences
drive everything below.

**How long to count.** Volunteers cannot change ``y``; they can only stop the
denominator from being the limiting term. Requiring the denominator to
contribute at most a stated share ``f`` of the numerator's relative error --
``1/sqrt(N) <= f / sqrt(y)`` -- gives ``N >= y / f**2`` observations, and the
hours follow from the assumed flow. With the default ``f = 0.5`` a segment with
6 reports needs 24 observed users; past that point, counting longer buys very
little, because the six reports dominate.

**What that buys.** Against a reference rate treated as known (the city-wide
pooled rate, pooled over far more events than any one segment), the smallest
rate ratio distinguishable at level ``alpha`` with power ``1 - beta`` is::

    RR_min = exp((z_{1-alpha/2} + z_{1-beta}) * sqrt(1/y + 1/N))

That is a normal approximation on the log scale, and it is stated as an
assumption rather than a guarantee: it is the same approximation the power
column in METHODOLOGY §5.6 rests on, and it is optimistic exactly where this
project is most careful -- it treats the comparison rate as error-free and the
counts as Poisson, so overdispersion (RR-02) makes the true detectable ratio
larger, never smaller.

The expansion factor cancels out of both formulas, because it is a multiplicative
constant on ``E`` and these are log-scale standard errors. It changes the
denominator's *value*, not its *precision* -- which is precisely why it has to
travel as its own field rather than being absorbed into the hours.
"""

from __future__ import annotations

import csv
import io
import json
import math
import statistics
from dataclasses import asdict, dataclass
from typing import Literal

from .config import Config
from .engine import build_analysis
from .errors import ConfigError
from .geometry import haversine_m, point_to_polyline_m
from .models import Segment
from .network import SegmentGraph
from .util import reference_point, round_stable

#: Bumped whenever the artifact's shape changes; consumers pin it.
COUNT_PLAN_SCHEMA_VERSION = "1.0.0"

PlanStatus = Literal[
    "counts_needed",
    "no_counts_needed",
    "no_snapped_reports",
    "no_reports",
]
ExposureLayerState = Literal["absent", "partial", "complete"]
CountPointState = Literal["on_segment", "ambiguous"]

#: Default share of the numerator's relative standard error that the denominator
#: is allowed to contribute. 0.5 means "the counting must not be the limiting
#: term"; it is an analyst choice and is recorded in every artifact.
DEFAULT_DENOMINATOR_SHARE = 0.5
DEFAULT_ALPHA = 0.05
DEFAULT_POWER = 0.8


@dataclass(frozen=True)
class PlanAssumptions:
    """Every number the plan's columns depend on, stated where a reader can see it."""

    alpha: float
    power: float
    z_total: float
    denominator_share: float
    assumed_flow_per_hour: float | None
    expansion_period_hours: float | None
    exposure_floor: float
    min_publish_n: int

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class CountTarget:
    """One segment a group would go and count, and what that count would buy."""

    priority_rank: int
    segment_id: str
    segment_name: str
    report_count: int
    network_degree: int
    count_point: CountPointState
    lat: float | None
    lon: float | None
    observations_required: int
    observation_hours_target: float | None
    observations_at_target_hours: float | None
    exposure_expansion_factor: float | None
    minimum_detectable_rate_ratio: float | None

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class CountPlan:
    """A count-collection plan. Not a ranking, not a rate, not a danger score."""

    schema_version: str
    artifact_kind: str
    city: str
    status: PlanStatus
    exposure_layer: ExposureLayerState
    segments_total: int
    segments_with_usable_exposure: int
    segments_needing_counts: int
    segments_without_exposure_and_without_reports: int
    reports_total: int
    reports_on_targets: int
    assumptions: PlanAssumptions
    targets: tuple[CountTarget, ...] = ()
    caveats: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["assumptions"] = self.assumptions.as_dict()
        data["targets"] = [target.as_dict() for target in self.targets]
        data["caveats"] = list(self.caveats)
        return data


# --------------------------------------------------------------------------- #
# Statistics
# --------------------------------------------------------------------------- #


def z_for_two_sided_alpha_and_power(alpha: float, power: float) -> float:
    """``z_{1-alpha/2} + z_{1-beta}``, the constant in the detectable-ratio formula."""
    if not 0.0 < alpha < 1.0:
        raise ConfigError("count plan: alpha must be in (0, 1)")
    if not 0.0 < power < 1.0:
        raise ConfigError("count plan: power must be in (0, 1)")
    normal = statistics.NormalDist()
    return normal.inv_cdf(1.0 - alpha / 2.0) + normal.inv_cdf(power)


def observations_required(report_count: int, denominator_share: float) -> int:
    """Observed users needed so the denominator is not the limiting error term.

    ``N >= y / f**2``. Rounded up, and floored at 1 so a segment is never told to
    count nobody.
    """
    if report_count < 1:
        raise ConfigError("count plan: a target needs at least one report")
    if not 0.0 < denominator_share <= 1.0:
        raise ConfigError("count plan: denominator-share must be in (0, 1]")
    return max(1, math.ceil(report_count / (denominator_share * denominator_share)))


def minimum_detectable_rate_ratio(report_count: int, observations: float, z_total: float) -> float:
    """``exp(z_total * sqrt(1/y + 1/N))`` — see the module docstring."""
    if report_count < 1:
        raise ConfigError("count plan: a detectable ratio needs at least one report")
    if observations <= 0:
        raise ConfigError("count plan: a detectable ratio needs a positive observation count")
    return math.exp(z_total * math.sqrt(1.0 / report_count + 1.0 / observations))


# --------------------------------------------------------------------------- #
# Geometry: where a volunteer actually stands
# --------------------------------------------------------------------------- #


def midpoint_on_polyline(coords: tuple[tuple[float, float], ...]) -> tuple[float, float]:
    """The point at half the polyline's own length — guaranteed *on* the line.

    ``geometry.polyline_centroid`` is a length-weighted average of segment
    midpoints, which for a curved street is not a point of the street. A count
    location that is not on the segment can snap to a different one, which would
    put a volunteer on the wrong corner and attach their count to the wrong
    denominator.
    """
    if not coords:
        raise ConfigError("count plan: a segment with no coordinates has no count point")
    if len(coords) == 1:
        return coords[0]
    lengths = [
        haversine_m(coords[i][0], coords[i][1], coords[i + 1][0], coords[i + 1][1])
        for i in range(len(coords) - 1)
    ]
    total = sum(lengths)
    if total == 0.0:
        return coords[0]
    remaining = total / 2.0
    for index, length in enumerate(lengths):
        if length >= remaining:
            fraction = remaining / length if length > 0 else 0.0
            (lat_a, lon_a), (lat_b, lon_b) = coords[index], coords[index + 1]
            return (lat_a + (lat_b - lat_a) * fraction, lon_a + (lon_b - lon_a) * fraction)
        remaining -= length
    return coords[-1]


def _count_point(
    segment: Segment, segments: list[Segment], lat0: float, lon0: float
) -> tuple[CountPointState, float | None, float | None]:
    """The count location, plus whether it unambiguously identifies its own segment.

    Uses the same ``point_to_polyline_m`` the pipeline snaps reports with, so a
    point this accepts is a point the pipeline would attribute to this segment.
    A tie (another segment at least as close) is reported as ``ambiguous`` with no
    coordinates rather than a coordinate that sends someone to the wrong street.
    """
    lat, lon = midpoint_on_polyline(segment.coords)
    own = point_to_polyline_m(lat, lon, segment.coords, lat0, lon0)
    for other in segments:
        if other.id == segment.id:
            continue
        if point_to_polyline_m(lat, lon, other.coords, lat0, lon0) <= own:
            return "ambiguous", None, None
    return "on_segment", round_stable(lat, 6), round_stable(lon, 6)


# --------------------------------------------------------------------------- #
# The plan
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class _Candidate:
    segment: Segment
    report_count: int
    degree: int


def _caveats(
    *,
    status: PlanStatus,
    assumed_flow_per_hour: float | None,
    expansion_period_hours: float | None,
    excluded_without_reports: int,
    ambiguous_points: int,
) -> tuple[str, ...]:
    notes: list[str] = [
        "This is a data-collection plan, not a measurement. It states no rate, no ranking "
        "and no danger score. Priority order is by how much has been reported, which "
        "records where people chose to report, not where risk is.",
    ]
    if status != "counts_needed":
        return tuple(notes)
    notes.append(
        "Counting only the segments listed here yields denominators only where reports "
        "already are. That supports each listed segment's own rate; it does not support a "
        "city-wide ranking, which needs denominators on a comparison set that includes "
        "segments with few or no reports."
    )
    if assumed_flow_per_hour is None:
        notes.append(
            "No assumed flow per hour was supplied, so observation hours could not be "
            "computed and are reported as unknown rather than estimated. Supply "
            "--assumed-flow-per-hour once a pilot session has measured one."
        )
    if expansion_period_hours is None:
        notes.append(
            "No expansion period was supplied, so every count stays on its own session "
            "basis. Sessions of different lengths are not comparable to each other until "
            "an expansion factor puts them on one; this tool computes the mechanical "
            "hours ratio only and does not estimate day-of-week or seasonal factors."
        )
    if excluded_without_reports:
        notes.append(
            f"{excluded_without_reports} segment(s) have no usable exposure and no reports. "
            "They are outside this plan because nothing has been reported on them, which is "
            "not the same as nothing having happened there."
        )
    if ambiguous_points:
        notes.append(
            f"{ambiguous_points} segment(s) have no unambiguous count point: their midpoint is "
            "at least as close to another segment, so a count taken there could not be "
            "attributed. Site them by hand."
        )
    return tuple(notes)


def _build_target(
    candidate: _Candidate,
    *,
    rank: int,
    segments: list[Segment],
    lat0: float,
    lon0: float,
    denominator_share: float,
    assumed_flow_per_hour: float | None,
    expansion_period_hours: float | None,
    z_total: float,
) -> CountTarget:
    """One row of the plan: how much to count here, and what that would buy."""
    required = observations_required(candidate.report_count, denominator_share)
    hours: float | None = None
    at_hours: float | None = None
    factor: float | None = None
    mde: float | None = None
    if assumed_flow_per_hour is not None:
        hours = float(math.ceil(required / assumed_flow_per_hour))
        at_hours = hours * assumed_flow_per_hour
        mde = minimum_detectable_rate_ratio(candidate.report_count, at_hours, z_total)
        if expansion_period_hours is not None:
            factor = expansion_period_hours / hours
    state, lat, lon = _count_point(candidate.segment, segments, lat0, lon0)
    return CountTarget(
        priority_rank=rank,
        segment_id=candidate.segment.id,
        segment_name=candidate.segment.name,
        report_count=candidate.report_count,
        network_degree=candidate.degree,
        count_point=state,
        lat=lat,
        lon=lon,
        observations_required=required,
        observation_hours_target=round_stable(hours, 2),
        observations_at_target_hours=round_stable(at_hours, 2),
        exposure_expansion_factor=round_stable(factor, 4),
        minimum_detectable_rate_ratio=round_stable(mde, 3),
    )


def build_count_plan(
    config: Config,
    *,
    assumed_flow_per_hour: float | None = None,
    expansion_period_hours: float | None = None,
    alpha: float = DEFAULT_ALPHA,
    power: float = DEFAULT_POWER,
    denominator_share: float = DEFAULT_DENOMINATOR_SHARE,
) -> CountPlan:
    """Build the count plan for ``config``'s city.

    A target is a segment that carries at least one snapped report and has no
    usable exposure. Priority is lexicographic and therefore free of any invented
    weighting: report count descending, then network degree descending (a junction
    a group can watch is worth more than a cul-de-sac), then segment id ascending
    so the order is stable.
    """
    if assumed_flow_per_hour is not None and assumed_flow_per_hour <= 0:
        raise ConfigError("count plan: --assumed-flow-per-hour must be positive")
    if expansion_period_hours is not None and expansion_period_hours <= 0:
        raise ConfigError("count plan: --expansion-period-hours must be positive")
    z_total = z_for_two_sided_alpha_and_power(alpha, power)

    bundle = build_analysis(config)
    segments = bundle.segments
    by_id = {segment.id: segment for segment in segments}

    # Read "how many reports landed here" and "is there a usable denominator" from
    # the analysis itself rather than re-deriving either. `exposure_unknown` is the
    # pipeline's own verdict (`exposure.is_usable` against `config.exposure_floor`),
    # so a plan can never disagree with the analysis it exists to unblock.
    counts = {stat.segment_id: stat.report_count for stat in bundle.result.segments}
    usable = {
        stat.segment_id
        for stat in bundle.result.segments
        if stat.confidence_label != "exposure_unknown"
    }

    graph = SegmentGraph.build(segments, node_snap_m=config.gi_node_snap_m)
    candidates = [
        _Candidate(
            segment=by_id[segment_id],
            report_count=count,
            degree=len(graph.adjacency.get(segment_id, [])),
        )
        for segment_id, count in counts.items()
        if count > 0 and segment_id not in usable and segment_id in by_id
    ]
    candidates.sort(key=lambda c: (-c.report_count, -c.degree, c.segment.id))

    lat0, lon0 = (
        reference_point(
            (coord for segment in segments for coord in segment.coords),
            config.ref_lat,
            config.ref_lon,
        )
        if segments
        else (0.0, 0.0)
    )

    targets = tuple(
        _build_target(
            candidate,
            rank=rank,
            segments=segments,
            lat0=lat0,
            lon0=lon0,
            denominator_share=denominator_share,
            assumed_flow_per_hour=assumed_flow_per_hour,
            expansion_period_hours=expansion_period_hours,
            z_total=z_total,
        )
        for rank, candidate in enumerate(candidates, start=1)
    )
    ambiguous = sum(1 for target in targets if target.count_point == "ambiguous")

    exposure_state: ExposureLayerState
    if not usable:
        exposure_state = "absent"
    elif len(usable) >= len(segments):
        exposure_state = "complete"
    else:
        exposure_state = "partial"

    snapped_total = sum(counts.values())
    status: PlanStatus
    if not bundle.records:
        status = "no_reports"
    elif snapped_total == 0:
        status = "no_snapped_reports"
    elif targets:
        status = "counts_needed"
    else:
        status = "no_counts_needed"

    excluded = sum(
        1 for segment in segments if segment.id not in usable and counts.get(segment.id, 0) == 0
    )
    return CountPlan(
        schema_version=COUNT_PLAN_SCHEMA_VERSION,
        artifact_kind="collection_plan",
        city=config.city,
        status=status,
        exposure_layer=exposure_state,
        segments_total=len(segments),
        segments_with_usable_exposure=len(usable),
        segments_needing_counts=len(targets),
        segments_without_exposure_and_without_reports=excluded,
        reports_total=len(bundle.records),
        reports_on_targets=sum(target.report_count for target in targets),
        assumptions=PlanAssumptions(
            alpha=alpha,
            power=power,
            z_total=round(z_total, 6),
            denominator_share=denominator_share,
            assumed_flow_per_hour=assumed_flow_per_hour,
            expansion_period_hours=expansion_period_hours,
            exposure_floor=config.exposure_floor,
            min_publish_n=config.min_publish_n,
        ),
        targets=targets,
        caveats=_caveats(
            status=status,
            assumed_flow_per_hour=assumed_flow_per_hour,
            expansion_period_hours=expansion_period_hours,
            excluded_without_reports=excluded,
            ambiguous_points=ambiguous,
        ),
    )


# --------------------------------------------------------------------------- #
# Renderers
# --------------------------------------------------------------------------- #

#: The columns ``tools/build_exposure.py`` reads by default (``--lat-field``,
#: ``--lon-field``, ``--count-field``), plus the fields a volunteer needs and the
#: expansion factor that puts unequal sessions on one basis. ``count`` ships
#: empty: a pre-filled denominator is the thing this whole module refuses.
COUNT_SHEET_COLUMNS: tuple[str, ...] = (
    "segment_id",
    "segment_name",
    "lat",
    "lon",
    "observation_hours_target",
    "observations_required",
    "exposure_expansion_factor",
    "count",
)


def render_count_sheet_csv(plan: CountPlan) -> str:
    """A count sheet in ``tools/build_exposure.py``'s CSV input shape.

    Rows are emitted only for targets with an unambiguous count point, because a
    row with no coordinate cannot be loaded and would silently become an
    unsnapped observation.
    """
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(COUNT_SHEET_COLUMNS), lineterminator="\n")
    writer.writeheader()
    for target in plan.targets:
        if target.count_point != "on_segment":
            continue
        writer.writerow(
            {
                "segment_id": target.segment_id,
                "segment_name": target.segment_name,
                "lat": target.lat,
                "lon": target.lon,
                "observation_hours_target": (
                    ""
                    if target.observation_hours_target is None
                    else target.observation_hours_target
                ),
                "observations_required": target.observations_required,
                "exposure_expansion_factor": (
                    ""
                    if target.exposure_expansion_factor is None
                    else target.exposure_expansion_factor
                ),
                "count": "",
            }
        )
    return buffer.getvalue()


_STATUS_HEADLINE: dict[PlanStatus, str] = {
    "counts_needed": "Segments to count, highest priority first.",
    "no_counts_needed": (
        "Nothing to collect: every segment carrying a report already has a usable exposure "
        "denominator."
    ),
    "no_snapped_reports": (
        "Nothing to collect: reports exist but none of them snapped to a street segment, so "
        "there is no segment to count. Check the snapping distance and the street network "
        "before reading this as coverage."
    ),
    "no_reports": (
        "Nothing to collect: this city has no reports, so nothing points at a segment to "
        "count. That is an empty input, not a finished city."
    ),
}


def render_count_plan_markdown(plan: CountPlan) -> str:
    """Operator-facing Markdown. English only, like every other operator surface."""
    lines: list[str] = [
        f"# Count-collection plan — {plan.city}",
        "",
        _STATUS_HEADLINE[plan.status],
        "",
        "| | |",
        "|---|---|",
        f"| Status | `{plan.status}` |",
        f"| Exposure layer | `{plan.exposure_layer}` |",
        f"| Segments | {plan.segments_total} |",
        f"| Segments with a usable denominator | {plan.segments_with_usable_exposure} |",
        f"| Segments in this plan | {plan.segments_needing_counts} |",
        f"| Reports on segments in this plan | {plan.reports_on_targets} of {plan.reports_total} |",
        "",
    ]
    if plan.targets:
        flow = plan.assumptions.assumed_flow_per_hour
        lines += [
            "## Priority order",
            "",
            "Report count descending, then street-network degree, then segment id. "
            "Report count is a measure of what has been reported, not of risk.",
            "",
            "| # | Segment | Reports | Degree | Observations needed | Hours | "
            "Expansion factor | Smallest detectable rate ratio |",
            "|---:|---|---:|---:|---:|---:|---:|---:|",
        ]
        for target in plan.targets:
            hours = (
                "unknown"
                if target.observation_hours_target is None
                else (f"{target.observation_hours_target:g}")
            )
            factor = (
                "session basis"
                if target.exposure_expansion_factor is None
                else (f"{target.exposure_expansion_factor:g}")
            )
            mde = (
                "unknown"
                if target.minimum_detectable_rate_ratio is None
                else (f"{target.minimum_detectable_rate_ratio:.2f}x")
            )
            lines.append(
                f"| {target.priority_rank} | {target.segment_name} (`{target.segment_id}`) "
                f"| {target.report_count} | {target.network_degree} "
                f"| {target.observations_required} | {hours} | {factor} | {mde} |"
            )
        lines += [
            "",
            "## What the columns mean",
            "",
            "- **Observations needed** — people passing the segment, so that the denominator "
            f"contributes at most {plan.assumptions.denominator_share:g} of the report count's "
            "own relative sampling error. Counting past this buys very little.",
            "- **Hours** — observations needed divided by the assumed flow per hour"
            + (
                f" ({flow:g} per hour), rounded up to a whole hour."
                if flow is not None
                else ", which is unknown because no flow was assumed."
            ),
            "- **Expansion factor** — what a session count is multiplied by to reach the "
            "requested denominator period. Sessions of different lengths are not comparable "
            "until this is applied.",
            "- **Smallest detectable rate ratio** — how far this segment's rate would have to "
            f"sit from the city-wide rate to be distinguishable at alpha "
            f"{plan.assumptions.alpha:g} with power {plan.assumptions.power:g}, once the "
            "count is in. It is a normal approximation on the log scale that treats the "
            "city-wide rate as known and the counts as Poisson; overdispersion makes the "
            "true figure larger, never smaller.",
            "",
        ]
    lines += ["## Caveats", ""]
    lines += [f"- {caveat}" for caveat in plan.caveats]
    lines.append("")
    return "\n".join(lines)


def render_count_plan_json(plan: CountPlan) -> str:
    """Deterministic JSON: sorted keys, no timestamp, newline-terminated."""
    return json.dumps(plan.as_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
