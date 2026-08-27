"""Exposure-sensitivity: does the ranking survive a different denominator? (RR-03 / R28)

The denominator is the shakiest input in this pipeline, and the published
interval does not cover it: the 95% interval on a rate is a Poisson interval on
the *count*, with exposure treated as a known constant
([METHODOLOGY](../../../docs/METHODOLOGY.md) §5.2). Two published decisions say
what happens instead of propagating that uncertainty into the interval:

    "an exposure-sensitivity pass re-runs the ranking under plausible
    alternative denominators and reports how much the conclusion moves. A
    ranking that survives only one choice of exposure source is reported as
    fragile."
    — METHODOLOGY §3.3, and ADR 0002 ("Degraded exposure does not produce a
      fabricated rate")

This module is that pass. It is the exposure twin of ``stats/maup.py``: where
the MAUP check re-draws the *units* and asks whether the top hotspot survives,
this one re-picks the *denominator* and asks the same question.

**The alternatives are declared, never invented.** The only denominators
considered are the corroborating readings a segment's exposure record already
carries (``Exposure.sources`` — METHODOLOGY §3.1: "when two or more sources
cover the same segment they can corroborate the denominator"). There is no
perturbation model, no tier-derived multiplier, no assumed error bar. A
plausible alternative denominator here means a denominator someone actually
published for that segment.

The direct consequence is that this check often **cannot run**, and it says so.
Where no rated segment declares a second reading there is nothing to re-rank
under, and the result is ``verdict="not_evaluated"`` with
``top_segment_survives=None`` — never ``"stable"``. A robustness check that
reports success when it had nothing to test is not a robustness check.
``alternative_coverage`` reports what share of the rated segments the pass could
vary at all, so a "stable" verdict is always readable against how much of the
network it actually exercised.

Two scenarios bracket what the declared readings support:

``declared_low``
    every segment with alternatives takes the *smallest* usable reading it
    declares — the smallest denominator, so the highest rate.
``declared_high``
    the *largest* usable reading — the lowest rate.

The minimum and maximum are taken over the primary estimate together with its
corroborating readings, so a scenario never moves a segment outside the range
its own sources published. Segments with no declared alternative keep their
published denominator in both scenarios.

Rates are re-derived by scaling: ``rate_alt = rate * (E_base / E_alt)``, which
is exact for a count over an offset and leaves the numerator untouched, so the
scenario ranking is the published ranking with only the denominator swapped.
Getis-Ord Gi\\* is then re-run on the scenario rates over the same
street-network neighborhoods, at the same Benjamini-Hochberg FDR level and with
the same singleton-neighborhood suppression (ADR-0015), so "significant" means
in a scenario exactly what it means in the published dataset.

Reference: FHWA, *Methods for estimating pedestrian and bicyclist exposure*;
Elvik & Bjornskau (2019), on how much a safety conclusion can rest on the
exposure choice alone.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..config import Config
from ..models import Exposure, Segment, SegmentStats
from ..network import SegmentGraph
from ..util import round_stable
from .getis_ord import (
    benjamini_hochberg,
    getis_ord_star,
    singleton_neighborhoods,
    two_sided_p,
)

#: Verdicts. ``not_evaluated`` is a first-class outcome, not an error state.
NOT_EVALUATED = "not_evaluated"
STABLE = "stable"
FRAGILE = "fragile"

#: Why the pass could not run, published verbatim so a reader of the artifact
#: never has to guess whether "no result" meant "nothing moved".
NO_ALTERNATIVES_REASON = (
    "no rated segment declares an alternative exposure reading, so the ranking was never "
    "re-run under a different denominator; this is an unanswered question, not a passed check"
)

_LOW = "declared_low"
_HIGH = "declared_high"
_BASIS = {
    _LOW: "smallest denominator this segment's own sources declare (highest rate)",
    _HIGH: "largest denominator this segment's own sources declare (lowest rate)",
}


@dataclass(frozen=True)
class ExposureScenario:
    """What the published ranking looks like under one alternative denominator."""

    name: str
    basis: str
    #: Rated segments whose denominator actually differs from the published one here.
    substituted_segments: int
    #: Highest-rate publishable segment under this denominator.
    top_segment_id: str | None
    #: Where the *published* top segment lands in this scenario (1 = still first).
    baseline_top_rank: int | None
    #: Whether the published top segment is still an FDR-significant Gi* cluster here.
    baseline_top_significant: bool
    #: How many segments' significance flags differ from the published dataset's.
    significance_flips: int
    #: Jaccard overlap of the published top-k against this scenario's top-k.
    topk_overlap: float


@dataclass(frozen=True)
class ExposureSensitivity:
    """The exposure-sensitivity result for one published dataset."""

    #: False when no rated segment declared an alternative denominator to test.
    evaluated: bool
    #: ``not_evaluated`` / ``stable`` / ``fragile``.
    verdict: str
    #: Segments carrying a rate (the Gi* population).
    rated_segments: int
    #: Of those, how many declare at least one usable alternative reading.
    segments_with_alternatives: int
    #: ``segments_with_alternatives / rated_segments`` — how much of the network
    #: this pass could vary at all. A "stable" verdict is only as strong as this.
    alternative_coverage: float
    k: int
    baseline_top_segment: str | None
    baseline_top_significant: bool
    #: ``None`` when the pass did not run. Never ``True`` by default.
    top_segment_survives: bool | None
    scenarios: tuple[ExposureScenario, ...]


def _usable_readings(exp: Exposure, floor: float) -> list[float]:
    """Every denominator this exposure record declares that clears the floor.

    The primary estimate plus each corroborating reading, filtered by the same
    rule :func:`nearmiss.exposure.is_usable` applies to the primary: an estimate
    at or below the exposure floor is not a denominator (METHODOLOGY §3.3), so
    it cannot be an alternative denominator either.
    """
    return [e for e in (exp.estimate, *(r.estimate for r in exp.sources)) if e > floor]


def _alternatives(
    rated_ids: set[str], exposure_map: dict[str, Exposure], floor: float
) -> dict[str, tuple[float, float]]:
    """Rated segment id -> (smallest, largest) usable declared denominator.

    Only segments that declare at least one *corroborating* reading appear: with
    a single reading there is no alternative to re-rank under, and pretending
    otherwise would let the pass report a result it did not earn.
    """
    out: dict[str, tuple[float, float]] = {}
    for sid in sorted(rated_ids):
        exp = exposure_map.get(sid)
        if exp is None or not exp.sources:
            continue
        readings = _usable_readings(exp, floor)
        if len(readings) < 2:
            continue
        out[sid] = (min(readings), max(readings))
    return out


def _scenario_rates(
    published: dict[str, float],
    denominators: dict[str, float],
    alternatives: dict[str, tuple[float, float]],
    pick_low: bool,
) -> dict[str, float]:
    """Published rates with the chosen alternative denominators substituted in.

    ``rate = count / E``, so swapping the denominator is exactly
    ``rate * (E_base / E_alt)`` — the numerator, and every filter that produced
    it, is left untouched.
    """
    out: dict[str, float] = {}
    for sid, rate in published.items():
        alt = alternatives.get(sid)
        if alt is None:
            out[sid] = rate
            continue
        chosen = alt[0] if pick_low else alt[1]
        out[sid] = rate * (denominators[sid] / chosen)
    return out


def _significant(
    rates: dict[str, float], neighbor_map: dict[str, set[str]], fdr_alpha: float
) -> set[str]:
    """Gi* + Benjamini-Hochberg + ADR-0015 suppression, exactly as published."""
    z = getis_ord_star(rates, neighbor_map)
    rejected = benjamini_hochberg({sid: two_sided_p(zi) for sid, zi in z.items()}, fdr_alpha)
    degenerate = singleton_neighborhoods(rates, neighbor_map)
    return {sid for sid in rejected if z.get(sid, 0.0) > 0.0} - degenerate


def _rank(ranked_stats: list[SegmentStats], rates: dict[str, float]) -> list[str]:
    """Publishable rated segment ids, highest rate first.

    Sorted from the analysis' own segment order with a stable sort, so ties break
    exactly as they do in the brief and in the MAUP check rather than by a
    different rule in each artifact.
    """
    ordered = sorted(ranked_stats, key=lambda s: rates[s.segment_id], reverse=True)
    return [s.segment_id for s in ordered]


def _build_scenario(
    name: str,
    rates: dict[str, float],
    ranked_stats: list[SegmentStats],
    baseline: tuple[list[str], str, set[str]],
    neighbor_map: dict[str, set[str]],
    config: Config,
    substituted: int,
) -> ExposureScenario:
    """Rank, re-test, and compare one scenario against the published dataset."""
    baseline_top_k, baseline_top, baseline_sig = baseline
    ranked = _rank(ranked_stats, rates)
    sig = _significant(rates, neighbor_map, config.fdr_alpha)
    top_k = set(ranked[: len(baseline_top_k)])
    union = set(baseline_top_k) | top_k
    overlap = len(set(baseline_top_k) & top_k) / len(union) if union else 0.0
    return ExposureScenario(
        name=name,
        basis=_BASIS[name],
        substituted_segments=substituted,
        top_segment_id=ranked[0] if ranked else None,
        baseline_top_rank=(ranked.index(baseline_top) + 1) if baseline_top in ranked else None,
        baseline_top_significant=baseline_top in sig,
        significance_flips=len(sig ^ baseline_sig),
        topk_overlap=round(overlap, 4),
    )


def _survives(scenarios: tuple[ExposureScenario, ...], baseline_significant: bool) -> bool:
    """Did the published top segment hold up under every alternative denominator?

    It survives when it is still rank 1 in every scenario **and**, if it was a
    significant Gi* cluster in the published dataset, it still is. Significance
    can only be lost here, never demanded: a top segment that was not a
    significant cluster to begin with is not called fragile for failing to
    become one under a denominator it never had.
    """
    ranks_hold = all(s.baseline_top_rank == 1 for s in scenarios)
    if not baseline_significant:
        return ranks_hold
    return ranks_hold and all(s.baseline_top_significant for s in scenarios)


def _not_evaluated(rated: int, with_alternatives: int, k: int) -> ExposureSensitivity:
    """The honest empty result: the question was asked and could not be answered."""
    return ExposureSensitivity(
        evaluated=False,
        verdict=NOT_EVALUATED,
        rated_segments=rated,
        segments_with_alternatives=with_alternatives,
        alternative_coverage=0.0,
        k=k,
        baseline_top_segment=None,
        baseline_top_significant=False,
        top_segment_survives=None,
        scenarios=(),
    )


def exposure_sensitivity(
    stats: list[SegmentStats],
    segments: list[Segment],
    exposure_map: dict[str, Exposure],
    config: Config,
    k: int = 5,
    neighbor_map: dict[str, set[str]] | None = None,
) -> ExposureSensitivity:
    """Re-run the published ranking under each segment's declared alternative denominators.

    Returns an :class:`ExposureSensitivity`. ``verdict`` is ``"not_evaluated"``
    whenever no rated segment declares a corroborating exposure reading: there is
    then nothing to substitute, and the pass reports an unanswered question
    rather than a passed check.
    """
    rated_rates: dict[str, float] = {}
    denominators: dict[str, float] = {}
    for s in stats:
        if s.rate is None or s.exposure_estimate is None:
            continue
        rated_rates[s.segment_id] = s.rate
        denominators[s.segment_id] = s.exposure_estimate
    alternatives = _alternatives(set(rated_rates), exposure_map, config.exposure_floor)

    # The ranked population is the published one: rated AND past the k-anonymity
    # floor, so this check ranks exactly what a reader sees ranked.
    ranked_stats = [s for s in stats if s.segment_id in rated_rates and s.publishable]
    baseline_ranked = _rank(ranked_stats, rated_rates)
    if not alternatives or not baseline_ranked:
        return _not_evaluated(len(rated_rates), len(alternatives), k)

    baseline_top = baseline_ranked[0]
    baseline_sig = {s.segment_id for s in stats if s.significant}
    baseline = (baseline_ranked[:k], baseline_top, baseline_sig)

    if neighbor_map is None:
        graph = SegmentGraph.build(segments, node_snap_m=config.gi_node_snap_m)
        neighbor_map = graph.neighbors_within(config.gi_band_m)

    scenarios: list[ExposureScenario] = []
    for name, pick_low in ((_LOW, True), (_HIGH, False)):
        rates = _scenario_rates(rated_rates, denominators, alternatives, pick_low)
        substituted = sum(1 for sid in alternatives if rates[sid] != rated_rates[sid])
        scenarios.append(
            _build_scenario(name, rates, ranked_stats, baseline, neighbor_map, config, substituted)
        )

    frozen = tuple(scenarios)
    baseline_significant = baseline_top in baseline_sig
    survives = _survives(frozen, baseline_significant)
    return ExposureSensitivity(
        evaluated=True,
        verdict=STABLE if survives else FRAGILE,
        rated_segments=len(rated_rates),
        segments_with_alternatives=len(alternatives),
        alternative_coverage=round(len(alternatives) / len(rated_rates), 4),
        k=k,
        baseline_top_segment=baseline_top,
        baseline_top_significant=baseline_significant,
        top_segment_survives=survives,
        scenarios=frozen,
    )


def to_metadata(sensitivity: ExposureSensitivity) -> dict[str, object]:
    """A JSON-serializable view of the exposure-sensitivity artifact (RR-03).

    Segment ids, counts, ranks, and boolean/scalar summaries only — never a
    coordinate, a timestamp, or a forbidden key — so it is safe to embed in the
    published metadata sidecar. When the pass did not run, ``evaluated`` is
    ``false``, ``top_segment_survives`` is ``null``, and ``reason`` says why, so
    a consumer can never read silence as success.
    """
    meta: dict[str, object] = {
        "basis": "re-ranking under the alternative denominators each segment's sources declare",
        "evaluated": sensitivity.evaluated,
        "verdict": sensitivity.verdict,
        "rated_segments": sensitivity.rated_segments,
        "segments_with_alternatives": sensitivity.segments_with_alternatives,
        "alternative_coverage": sensitivity.alternative_coverage,
        "k": sensitivity.k,
        "top_segment": sensitivity.baseline_top_segment,
        "top_segment_significant": sensitivity.baseline_top_significant,
        "top_segment_survives": sensitivity.top_segment_survives,
        "scenarios": [
            {
                "name": s.name,
                "basis": s.basis,
                "substituted_segments": s.substituted_segments,
                "top_segment": s.top_segment_id,
                "top_segment_rank": s.baseline_top_rank,
                "top_segment_significant": s.baseline_top_significant,
                "significance_flips": s.significance_flips,
                "topk_overlap": round_stable(s.topk_overlap, 4),
            }
            for s in sensitivity.scenarios
        ],
    }
    if not sensitivity.evaluated:
        meta["reason"] = NO_ALTERNATIVES_REASON
    return meta
