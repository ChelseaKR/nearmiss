"""Does the ranking survive borrowing strength across segments? (RE-02)

A rate on a sparse, low-exposure block is mostly Poisson noise. One extra report
moves it a long way, and the segment that happens to catch that report lands at
the top of the table. [LIMITATIONS](../../../docs/LIMITATIONS.md) names this
plainly ("small numbers are loud") and the published interval admits it, but the
published *ranking* is still by the point estimate, so a segment with a wide
interval and a lucky report can still be rank 1.

Empirical-Bayes shrinkage is the standard answer to that: pull each unit's rate
toward the overall rate in proportion to how little information the unit carries,
so a rate resting on two reports moves a long way and a rate resting on two
hundred barely moves (Marshall 1991; Clayton & Kaldor 1987). This module runs it
as a **robustness pass, not a published rate**. It is the third sibling of
``stats/maup.py`` (re-draw the units) and ``stats/exposure_sensitivity.py``
(re-pick the denominator): re-estimate the *rate* and ask whether the same
segment is still on top.

**The published rate stays the raw one, deliberately.** METHODOLOGY §6.3 already
states this repository's rule for a model-based adjustment: a smoothed number
looks authoritative and can launder a modelling assumption into a fact, so an
adjustment that cannot be defended in the published number is offered as a
labelled sensitivity analysis instead. Shrinkage is exactly such an adjustment.
It assumes the segments are exchangeable draws from one distribution, which is a
strong assumption on a street network where a corridor is not a random sample of
the city, and it deliberately pulls the extremes in, which is the wrong default
for a tool whose job is to find extremes.

**It can refuse.** The between-segment variance is estimated by the method of
moments and can come out at or below zero, meaning the spread across segments is
no larger than Poisson noise alone would produce. Every segment then shrinks all
the way to the overall rate, every shrunk rate is identical, and there is no
ranking to compare: the pass reports ``not_evaluated`` with that reason, which is
itself a statement about how little the counts distinguish the segments, rather
than a verdict it did not earn.

Reference: Marshall, *Mapping disease and mortality rates using empirical Bayes
estimators*, Applied Statistics 40(2), 1991; Clayton & Kaldor, *Empirical Bayes
estimates of age-standardized relative risks*, Biometrics 43(3), 1987.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from honest_rates.rates import empirical_bayes_rates

from ..config import Config
from ..models import SegmentStats
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

#: Why the pass could not run, published verbatim so a reader never has to guess
#: whether "no result" meant "nothing moved".
NO_VARIANCE_REASON = (
    "the between-segment variance estimate is zero, so every rate shrinks to the overall rate and "
    "there is no shrunk ranking to compare; the counts do not distinguish these segments beyond "
    "Poisson noise, which is a finding about the data and not a passed check"
)
TOO_FEW_REASON = (
    "fewer than three rated, publishable segments, so there is no ranking to re-estimate; this is "
    "an unanswered question, not a passed check"
)


@dataclass(frozen=True)
class ShrinkageStability:
    """Whether the published ranking survives empirical-Bayes shrinkage."""

    #: False when there was no ranking to re-estimate.
    evaluated: bool
    #: ``not_evaluated`` / ``stable`` / ``fragile``.
    verdict: str
    rated_segments: int
    #: The overall rate every segment is shrunk toward, in published rate units.
    global_rate: float
    #: Method-of-moments between-segment variance, on the raw count/exposure scale.
    between_segment_variance: float
    #: Mean weight on a segment's own rate. 1 keeps the raw rate, 0 discards it.
    mean_weight: float
    k: int
    baseline_top_segment: str | None
    baseline_top_significant: bool
    #: Where the published top segment lands once every rate is shrunk.
    shrunk_top_rank: int | None
    #: The highest-rate segment after shrinkage.
    shrunk_top_segment: str | None
    #: Weight the published top segment keeps on its own rate.
    baseline_top_weight: float | None
    #: Whether it is still an FDR-significant Gi* cluster on the shrunk rates.
    shrunk_top_significant: bool
    #: Jaccard overlap of the published top-k against the shrunk top-k.
    topk_overlap: float
    #: ``None`` when the pass did not run. Never ``True`` by default.
    top_segment_survives: bool | None


def _not_evaluated(rated: int, k: int, variance: float, global_rate: float) -> ShrinkageStability:
    """The honest empty result: the question was asked and could not be answered."""
    return ShrinkageStability(
        evaluated=False,
        verdict=NOT_EVALUATED,
        rated_segments=rated,
        global_rate=global_rate,
        between_segment_variance=variance,
        mean_weight=0.0,
        k=k,
        baseline_top_segment=None,
        baseline_top_significant=False,
        shrunk_top_rank=None,
        shrunk_top_segment=None,
        baseline_top_weight=None,
        shrunk_top_significant=False,
        topk_overlap=0.0,
        top_segment_survives=None,
    )


def shrinkage_stability(
    stats: list[SegmentStats],
    primary_counts: Mapping[str, int],
    config: Config,
    neighbor_map: dict[str, set[str]],
    k: int = 5,
) -> ShrinkageStability:
    """Re-rank on empirical-Bayes shrunk rates and report whether the top holds.

    ``primary_counts`` is the numerator the published rate is built from (the
    primary, low-confidence-excluded count), for the same reason
    :func:`nearmiss.stats.maup.rank_stability` requires it: a check that changes
    the numerator as well as the estimator is not measuring the estimator.

    Returns a :class:`ShrinkageStability`. ``verdict`` is ``"not_evaluated"``
    when there is no ranking to re-estimate or when the between-segment variance
    estimate is zero; it is never ``"stable"`` by default.
    """
    ranked_stats = [
        s for s in stats if s.rate is not None and s.exposure_estimate is not None and s.publishable
    ]
    baseline = sorted(ranked_stats, key=lambda s: s.rate or 0.0, reverse=True)
    ids = [s.segment_id for s in baseline]
    if len(ids) < 3:
        return _not_evaluated(len(ids), k, 0.0, 0.0)

    exposures = [s.exposure_estimate or 0.0 for s in baseline]
    counts = [primary_counts.get(sid, 0) for sid in ids]
    shrunk, global_rate, variance, weights = empirical_bayes_rates(counts, exposures)
    published_global = global_rate * config.rate_per
    if variance <= 0.0:
        return _not_evaluated(len(ids), k, 0.0, round_stable(published_global, 6) or 0.0)

    # Back to published rate units, so the block reads on the same scale as `rate`.
    shrunk_rates = {sid: value * config.rate_per for sid, value in zip(ids, shrunk, strict=True)}
    weight_of = dict(zip(ids, weights, strict=True))

    shrunk_ranked = sorted(ids, key=lambda sid: shrunk_rates[sid], reverse=True)
    baseline_top = ids[0]
    baseline_top_k = ids[:k]
    shrunk_top_k = shrunk_ranked[:k]
    union = set(baseline_top_k) | set(shrunk_top_k)
    overlap = len(set(baseline_top_k) & set(shrunk_top_k)) / len(union) if union else 0.0

    # Gi* + FDR + ADR-0015 suppression on the shrunk rates, exactly as published,
    # so "significant" means the same thing in this scenario as in the dataset.
    z = getis_ord_star(shrunk_rates, neighbor_map)
    rejected = benjamini_hochberg({sid: two_sided_p(zi) for sid, zi in z.items()}, config.fdr_alpha)
    degenerate = singleton_neighborhoods(shrunk_rates, neighbor_map)
    significant = {sid for sid in rejected if z.get(sid, 0.0) > 0.0} - degenerate

    baseline_significant = baseline_top in {s.segment_id for s in stats if s.significant}
    shrunk_top_significant = baseline_top in significant
    rank = shrunk_ranked.index(baseline_top) + 1
    # Significance can only be lost here, never demanded: a top segment that was
    # not a significant cluster to begin with is not called fragile for failing to
    # become one under an estimator it never had.
    survives = rank == 1 and (shrunk_top_significant or not baseline_significant)
    return ShrinkageStability(
        evaluated=True,
        verdict=STABLE if survives else FRAGILE,
        rated_segments=len(ids),
        global_rate=round_stable(published_global, 6) or 0.0,
        between_segment_variance=round_stable(variance, 10) or 0.0,
        mean_weight=round_stable(sum(weights) / len(weights), 4) or 0.0,
        k=k,
        baseline_top_segment=baseline_top,
        baseline_top_significant=baseline_significant,
        shrunk_top_rank=rank,
        shrunk_top_segment=shrunk_ranked[0],
        baseline_top_weight=round_stable(weight_of[baseline_top], 4),
        shrunk_top_significant=shrunk_top_significant,
        topk_overlap=round(overlap, 4),
        top_segment_survives=survives,
    )


def to_metadata(stability: ShrinkageStability) -> dict[str, object]:
    """A JSON-serializable view of the shrinkage-stability artifact (RE-02).

    Segment ids, counts, ranks and scalar summaries only: never a coordinate, a
    timestamp, or a forbidden key. When the pass did not run, ``evaluated`` is
    ``false``, ``top_segment_survives`` is ``null``, and ``reason`` says why, so a
    consumer can never read silence as stability.
    """
    meta: dict[str, object] = {
        "basis": (
            "Marshall global empirical-Bayes shrinkage of every rate toward the overall rate, "
            "published as a re-ranking check and never as the published rate"
        ),
        "evaluated": stability.evaluated,
        "verdict": stability.verdict,
        "rated_segments": stability.rated_segments,
        "global_rate": stability.global_rate,
        "between_segment_variance": stability.between_segment_variance,
        "mean_weight": stability.mean_weight,
        "k": stability.k,
        "top_segment": stability.baseline_top_segment,
        "top_segment_significant": stability.baseline_top_significant,
        "top_segment_weight": stability.baseline_top_weight,
        "shrunk_top_segment": stability.shrunk_top_segment,
        "shrunk_top_rank": stability.shrunk_top_rank,
        "shrunk_top_significant": stability.shrunk_top_significant,
        "topk_overlap": stability.topk_overlap,
        "top_segment_survives": stability.top_segment_survives,
    }
    if not stability.evaluated:
        meta["reason"] = TOO_FEW_REASON if stability.rated_segments < 3 else NO_VARIANCE_REASON
    return meta
