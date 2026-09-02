"""How much of the published significance rests on the dependence assumption? (RR-08)

Published Getis-Ord Gi\\* significance is decided with a Benjamini-Hochberg
false-discovery-rate correction across the many per-segment tests
([METHODOLOGY](../../../docs/METHODOLOGY.md) §5.5). BH controls the FDR when the
tests are independent or positively regression dependent. **Local spatial
statistics are neither, by construction:** two neighbouring segments share the
values inside their overlapping Gi\\* neighborhoods, so their test statistics are
dependent, and nothing guarantees the sign of that dependence.

RR-08 asks this project to "justify (or move to) a spatial-dependence-aware FDR
... rather than vanilla Benjamini-Hochberg", citing Caldas de Castro & Singer
(2006). **That method is not implemented here and this module does not claim it
is.** What is computed is Benjamini-Yekutieli (2001), whose control of the FDR
under *arbitrary* dependence is exactly the property the concern is about and
whose definition is fully specified in a source this project has: the same
step-up procedure at ``alpha / c(m)``, with ``c(m)`` the m-th harmonic number.
Choosing a method whose definition can be reproduced from the citation, over one
whose text this project does not hold, is the same rule the rest of the
repository follows about never inventing a specification.

The published decision does not change. BH remains what
``getis_ord_significant`` means; the BY rejection set is always a subset of it,
and what is published here is **how much of the published significance survives
dropping the dependence assumption**. On the committed ``davis`` demo, one of the
five BH-significant clusters does. That is a large difference and it is published
rather than withheld, because the alternative is a reader assuming the five are
five independent findings.

Reference: Benjamini & Yekutieli, *The control of the false discovery rate in
multiple testing under dependency*, Annals of Statistics 29(4), 2001; Caldas de
Castro & Singer, *Controlling the False Discovery Rate: A New Application to
Account for Multiple and Dependent Tests in Local Statistics of Spatial
Association*, Geographical Analysis 38(2), 2006 (cited as the concern, not as the
implemented method).
"""

from __future__ import annotations

from dataclasses import dataclass

from honest_rates.hotspot import benjamini_yekutieli, harmonic

from ..config import Config
from ..models import SegmentStats
from ..util import round_stable

#: Verdicts. ``not_evaluated`` is a first-class outcome, not an error state.
NOT_EVALUATED = "not_evaluated"
ROBUST = "robust"
NOT_ROBUST = "not_robust"

#: Why the comparison could not run, published verbatim so a reader never has to
#: guess whether "no result" meant "nothing was lost".
NO_SIGNIFICANT_SEGMENTS_REASON = (
    "the dataset publishes no significant cluster, so there was no significance claim whose "
    "dependence assumption could be dropped; this is an unanswered question, not a passed check"
)


@dataclass(frozen=True)
class DependenceRobustness:
    """How the published significance set changes under arbitrary-dependence FDR."""

    #: False when the dataset publishes no significant cluster to re-test.
    evaluated: bool
    #: ``not_evaluated`` / ``robust`` / ``not_robust``.
    verdict: str
    #: Simultaneous tests the correction is applied across (the rated segments).
    tests: int
    #: The harmonic penalty ``c(m)`` Benjamini-Yekutieli divides the level by.
    harmonic_penalty: float
    #: ``fdr_alpha`` (the published Benjamini-Hochberg level).
    alpha: float
    #: ``fdr_alpha / c(m)`` (the Benjamini-Yekutieli level).
    dependence_robust_alpha: float
    #: Segments the published dataset flags as significant clusters.
    published_significant: int
    #: Of those, how many survive the arbitrary-dependence correction.
    dependence_robust_significant: int
    #: The surviving segment ids, sorted.
    dependence_robust_segments: tuple[str, ...]


def _not_evaluated(tests: int, config: Config) -> DependenceRobustness:
    """The honest empty result: the question was asked and could not be answered."""
    penalty = harmonic(tests)
    return DependenceRobustness(
        evaluated=False,
        verdict=NOT_EVALUATED,
        tests=tests,
        harmonic_penalty=round_stable(penalty, 4) or 0.0,
        alpha=config.fdr_alpha,
        dependence_robust_alpha=(round_stable(config.fdr_alpha / penalty, 6) or 0.0)
        if penalty
        else 0.0,
        published_significant=0,
        dependence_robust_significant=0,
        dependence_robust_segments=(),
    )


def dependence_robustness(
    stats: list[SegmentStats],
    pvalues: dict[str, float],
    config: Config,
) -> DependenceRobustness:
    """Re-decide significance under arbitrary dependence and report what is lost.

    ``pvalues`` is the same per-segment two-sided p-value map the published
    Benjamini-Hochberg decision was made from, so the two answers differ only in
    the correction. Returns a :class:`DependenceRobustness`; ``verdict`` is
    ``"not_evaluated"`` when the dataset publishes no significant cluster, and is
    never ``"robust"`` by default.
    """
    published = {s.segment_id for s in stats if s.significant}
    if not published or not pvalues:
        return _not_evaluated(len(pvalues), config)

    penalty = harmonic(len(pvalues))
    rejected = benjamini_yekutieli(pvalues, config.fdr_alpha)
    # A published significant segment is one that cleared BH *and* the positivity
    # and non-degeneracy rules in `analyze`; intersecting rather than re-deriving
    # keeps this comparison about the correction and nothing else.
    survivors = tuple(sorted(published & rejected))
    return DependenceRobustness(
        evaluated=True,
        verdict=ROBUST if len(survivors) == len(published) else NOT_ROBUST,
        tests=len(pvalues),
        harmonic_penalty=round_stable(penalty, 4) or 0.0,
        alpha=config.fdr_alpha,
        dependence_robust_alpha=round_stable(config.fdr_alpha / penalty, 6) or 0.0,
        published_significant=len(published),
        dependence_robust_significant=len(survivors),
        dependence_robust_segments=survivors,
    )


def to_metadata(robustness: DependenceRobustness) -> dict[str, object]:
    """A JSON-serializable view of the dependence-robustness artifact (RR-08).

    Segment ids, counts and levels only: never a coordinate, a timestamp, or a
    forbidden key. When the comparison did not run, ``evaluated`` is ``false`` and
    ``reason`` says why, so a consumer can never read silence as robustness.
    """
    meta: dict[str, object] = {
        "basis": (
            "Benjamini-Yekutieli false-discovery-rate control under arbitrary dependence, "
            "published beside the Benjamini-Hochberg decision and never replacing it"
        ),
        "not_implemented": (
            "this is not the spatially-aware FDR of Caldas de Castro & Singer (2006), whose text "
            "this project does not hold; it is the arbitrary-dependence correction of Benjamini & "
            "Yekutieli (2001), whose definition is reproducible from its citation"
        ),
        "evaluated": robustness.evaluated,
        "verdict": robustness.verdict,
        "tests": robustness.tests,
        "harmonic_penalty": robustness.harmonic_penalty,
        "alpha": robustness.alpha,
        "dependence_robust_alpha": robustness.dependence_robust_alpha,
        "published_significant": robustness.published_significant,
        "dependence_robust_significant": robustness.dependence_robust_significant,
        "dependence_robust_segments": list(robustness.dependence_robust_segments),
    }
    if not robustness.evaluated:
        meta["reason"] = NO_SIGNIFICANT_SEGMENTS_REASON
    return meta
