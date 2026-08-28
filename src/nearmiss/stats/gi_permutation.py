"""Does the published hotspot survive an empirical reference distribution? (RR-09)

Getis-Ord Gi\\* significance in this project comes from the **analytic**
normal-approximation z-score: the statistic is read against an asymptotic normal
reference, and the resulting p-values go through Benjamini-Hochberg
([METHODOLOGY](../../../docs/METHODOLOGY.md) §5.5, §8.2). That reference is an
approximation, and it is least comfortable exactly where this project operates:
sparse, skewed, exposure-normalized rates over small street-network
neighborhoods. METHODOLOGY §8.2 has named the alternative as future work and been
explicit that it "is **not** what is computed today".

This module is that alternative, computed and published as a **robustness check
beside the published decision, never as a replacement for it**. For each segment
the dataset makes a significance claim about, it holds the segment's own rate
fixed, redistributes the other rates at random across the other segments,
recomputes Gi\\*, and reads the observed statistic against that empirical
reference (``honest_rates.hotspot.conditional_permutation_p``; Anselin 1995).
The published ``getis_ord_significant`` flag does not move. Changing what
"significant" means in a published dataset is a methodology change with a
statistician's sign-off attached, not something a robustness pass does on its own
authority.

**Multiplicity is deliberately not re-run here, and that is a limit, not an
oversight.** A pseudo p-value from ``m`` permutations cannot go below
``1 / (m + 1)``. Benjamini-Hochberg over ``t`` simultaneous tests compares the
smallest p-value against ``alpha / t``, which for a city with hundreds of rated
segments is far below that floor. Feeding permutation p-values into BH at any
feasible ``m`` would therefore reject nothing, and publishing "no segment is
significant under permutation" would be an artifact of the permutation count
rather than a finding. What is published instead is the per-segment comparison:
each tested segment's analytic p-value beside its pseudo p-value, and whether the
two agree at ``fdr_alpha`` read as a single-test level. The pass refuses to run
at all when ``1 / (permutations + 1) > alpha``, because then the empirical test
could not have detected significance even in principle.

**Scope.** The tested set is the segments whose significance the dataset
publishes as a claim: the FDR-significant clusters, plus the top ``k`` by rate,
which are the segments a reader acts on. It cannot promote a segment the analytic
test did not flag, and the artifact says so rather than leaving a reader to infer
that an untested segment was tested and passed. Segments whose Gi\\*
neighbourhood is a singleton are excluded, because Gi\\* there is a global
z-score and not a cluster statistic (ADR-0015).

Reference: Anselin, *Local Indicators of Spatial Association (LISA)*,
Geographical Analysis 27(2), 1995; Ord & Getis (1995); North, Curtis & Sham,
*A note on the calculation of empirical P values from Monte Carlo procedures*,
American Journal of Human Genetics 71(2), 2002.
"""

from __future__ import annotations

from dataclasses import dataclass

from honest_rates.hotspot import conditional_permutation_p, two_sided_p

from ..config import Config
from ..models import SegmentStats
from ..util import round_stable

#: Verdicts. ``not_evaluated`` is a first-class outcome, not an error state.
NOT_EVALUATED = "not_evaluated"
CORROBORATED = "corroborated"
NOT_CORROBORATED = "not_corroborated"

#: Why the pass could not run, published verbatim so a reader never has to guess
#: whether "no result" meant "nothing disagreed".
NO_TESTABLE_SEGMENTS_REASON = (
    "no segment carried a testable Gi* neighbourhood, so no published significance claim was "
    "re-tested against an empirical reference; this is an unanswered question, not a passed check"
)
RESOLUTION_REASON = (
    "the permutation count is too small for a pseudo p-value to reach the significance level, so "
    "the empirical test could not have detected significance even in principle; no segment was "
    "re-tested"
)


@dataclass(frozen=True)
class PermutationSegment:
    """One segment's analytic result beside its empirical one."""

    segment_id: str
    #: Whether the published dataset flags this segment as a significant cluster.
    published_significant: bool
    #: Two-sided p of the published analytic Gi* z-score.
    analytic_p: float
    #: Two-sided pseudo p from the conditional-permutation reference.
    permutation_p: float
    #: Whether the two references agree about this segment at the single-test level.
    agrees: bool


@dataclass(frozen=True)
class PermutationInference:
    """The Gi* permutation-reference result for one published dataset."""

    #: False when nothing was testable, or the permutation count was too small.
    evaluated: bool
    #: ``not_evaluated`` / ``corroborated`` / ``not_corroborated``.
    verdict: str
    permutations: int
    seed: int
    #: The single-test level the two references are compared at (``fdr_alpha``).
    alpha: float
    tested_segments: int
    #: Of those, how many the published dataset flags as significant clusters.
    published_significant_tested: int
    #: Published significant clusters whose empirical reference does not agree.
    unsupported_segments: int
    segments: tuple[PermutationSegment, ...]


def _testable(stats: list[SegmentStats], k: int) -> list[str]:
    """The segments a reader acts on: significant clusters, plus the top k by rate."""
    rated = [s for s in stats if s.rate is not None and s.publishable]
    top = sorted(rated, key=lambda s: s.rate or 0.0, reverse=True)[:k]
    ids = {s.segment_id for s in top} | {s.segment_id for s in stats if s.significant}
    return sorted(ids)


def _not_evaluated(config: Config) -> PermutationInference:
    """The honest empty result: the question was asked and could not be answered."""
    return PermutationInference(
        evaluated=False,
        verdict=NOT_EVALUATED,
        permutations=config.gi_permutations,
        seed=config.gi_permutation_seed,
        alpha=config.fdr_alpha,
        tested_segments=0,
        published_significant_tested=0,
        unsupported_segments=0,
        segments=(),
    )


def permutation_inference(
    stats: list[SegmentStats],
    rate_values: dict[str, float],
    neighbor_map: dict[str, set[str]],
    config: Config,
    k: int = 5,
) -> PermutationInference:
    """Re-test the published significance claims against an empirical reference.

    Returns a :class:`PermutationInference`. ``verdict`` is ``"not_evaluated"``
    when nothing could be tested or when the configured permutation count could
    not resolve the significance level; it is never ``"corroborated"`` by
    default. The published ``getis_ord_significant`` flags are read, never
    written.
    """
    alpha = config.fdr_alpha
    if 1.0 / (config.gi_permutations + 1) > alpha:
        return _not_evaluated(config)

    wanted = _testable(stats, k)
    pseudo = conditional_permutation_p(
        rate_values, neighbor_map, wanted, config.gi_permutations, config.gi_permutation_seed
    )
    if not pseudo:
        return _not_evaluated(config)

    by_id = {s.segment_id: s for s in stats}
    tested: list[PermutationSegment] = []
    for segment_id in sorted(pseudo):
        stat = by_id[segment_id]
        # The analytic p of the published z, so the two references are compared on
        # the same statistic rather than on two differently-computed ones.
        analytic = two_sided_p(stat.getis_ord_z) if stat.getis_ord_z is not None else 1.0
        permutation = pseudo[segment_id]
        tested.append(
            PermutationSegment(
                segment_id=segment_id,
                published_significant=stat.significant,
                analytic_p=round_stable(analytic, 6) or 0.0,
                permutation_p=round_stable(permutation, 6) or 0.0,
                agrees=(analytic <= alpha) == (permutation <= alpha),
            )
        )

    published_significant = [t for t in tested if t.published_significant]
    # A published significant cluster is unsupported when its own empirical
    # reference does not put it past the level. A segment the analytic test did
    # NOT flag is not called unsupported for failing to become significant here:
    # this pass does not promote, and it does not demand promotion either.
    unsupported = [t for t in published_significant if t.permutation_p > alpha]
    return PermutationInference(
        evaluated=True,
        verdict=NOT_CORROBORATED if unsupported else CORROBORATED,
        permutations=config.gi_permutations,
        seed=config.gi_permutation_seed,
        alpha=alpha,
        tested_segments=len(tested),
        published_significant_tested=len(published_significant),
        unsupported_segments=len(unsupported),
        segments=tuple(tested),
    )


def to_metadata(inference: PermutationInference) -> dict[str, object]:
    """A JSON-serializable view of the Gi* permutation artifact (RR-09).

    Segment ids, counts and p-values only: never a coordinate, a timestamp, or a
    forbidden key, so it is safe to embed in the published metadata sidecar. When
    the pass did not run, ``evaluated`` is ``false`` and ``reason`` says why, so a
    consumer can never read silence as corroboration.
    """
    meta: dict[str, object] = {
        "basis": (
            "conditional-permutation reference distribution for Gi*, published beside the "
            "analytic normal-approximation decision and never replacing it"
        ),
        "evaluated": inference.evaluated,
        "verdict": inference.verdict,
        "permutations": inference.permutations,
        "seed": inference.seed,
        "alpha": inference.alpha,
        "scope": (
            "the segments the dataset makes a claim about: FDR-significant clusters plus the "
            "top-ranked segments by rate; a segment the analytic test did not flag cannot be "
            "promoted here"
        ),
        "multiplicity": (
            "not re-run: a pseudo p-value cannot go below 1/(permutations+1), which is above the "
            "Benjamini-Hochberg critical values at this many tests, so each segment is compared "
            "at the single-test level alpha"
        ),
        "tested_segments": inference.tested_segments,
        "published_significant_tested": inference.published_significant_tested,
        "unsupported_segments": inference.unsupported_segments,
        "segments": [
            {
                "segment_id": s.segment_id,
                "published_significant": s.published_significant,
                "analytic_p": s.analytic_p,
                "permutation_p": s.permutation_p,
                "agrees": s.agrees,
            }
            for s in inference.segments
        ],
    }
    if not inference.evaluated:
        meta["reason"] = (
            RESOLUTION_REASON
            if 1.0 / (inference.permutations + 1) > inference.alpha
            else NO_TESTABLE_SEGMENTS_REASON
        )
    return meta
