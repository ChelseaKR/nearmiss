"""Publish-time null calibration: "we attacked our own dataset."

Section 9.3 of ``docs/METHODOLOGY.md`` runs a null/no-signal fixture at *test*
time, on synthetic geometry we invented — it proves the method behaves on a
network we control, not on any particular published city. This module runs the
analogous check at *publish* time, on the city's own real network, geometry,
and exposure surface: it repeatedly relabels which segment each observed
report count belongs to (a seeded permutation), holding the exposure estimate
at every segment and the spatial structure completely fixed, and re-runs the
exact same rate + Getis-Ord Gi* + Benjamini-Hochberg pipeline the real
analysis uses. Because a label shuffle destroys any genuine spatial signal
while preserving this city's real exposure heterogeneity, count distribution,
and geometry, anything the method calls "significant" on a shuffle is by
construction a false positive. The empirical rate of that across many shuffles
is a per-dataset calibration statement — "on N shuffles of this exact network
and exposure, the method flagged a mean of X spurious hotspots at
fdr_alpha=Y" — that a skeptic can inspect beside the dataset, distinct from:

- the fixture-time null test (Section 9.3: one synthetic network, a build-time
  regression guard, not published per city), and
- ``RR-09`` permutation inference for the statistic itself (a different
  question: the reference distribution for one z-score, not the whole
  pipeline's empirical false-positive behavior on real geometry).

Privacy-safe by construction: the input is already the city's published
per-segment counts and exposure estimates (aggregates of aggregates), and the
output is a handful of summary numbers, never a per-report or per-shuffle
per-segment listing.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from ..config import Config
from ..geometry import polyline_centroid
from ..models import Segment, SegmentStats
from ..util import round_stable
from .getis_ord import benjamini_hochberg, getis_ord_star, two_sided_p
from .rates import rate_with_ci

__all__ = ["CalibrationResult", "run_null_calibration", "shuffled_count_sequences"]

# Fixed default so `make reproduce` and CI are byte-for-byte deterministic
# (docs/ideation/03-expansions.md EXP-01: "deterministic seeds for the
# reproduce gate"). Override with an explicit seed for a fresh Monte-Carlo draw.
DEFAULT_SEED = 20260101
DEFAULT_N_SHUFFLES = 200


@dataclass(frozen=True)
class CalibrationResult:
    """Empirical false-positive behavior of the hotspot method on one city's
    own geometry and exposure, measured by label-shuffling its own counts."""

    city: str
    n_shuffles: int
    seed: int
    n_segments: int
    fdr_alpha: float
    gi_band_m: float
    false_positive_counts: tuple[int, ...]  # significant segments found, one entry per shuffle
    mean_false_positives: float
    max_false_positives: int
    false_positive_rate: float  # mean_false_positives / n_segments
    shuffle_with_any_false_positive_rate: float  # fraction of shuffles with >= 1 flagged segment

    def to_metadata(self) -> dict[str, object]:
        """The published, privacy-safe calibration artifact (no per-shuffle detail)."""
        return {
            "schema_version": "1.0.0",
            "city": self.city,
            "method": (
                "label-shuffle null calibration: seeded permutation of this city's own "
                "segment report counts, exposure and geometry held fixed, re-run through the "
                "same rate + Getis-Ord Gi* + Benjamini-Hochberg FDR pipeline used to publish"
            ),
            "n_shuffles": self.n_shuffles,
            "seed": self.seed,
            "n_segments_tested": self.n_segments,
            "fdr_alpha": self.fdr_alpha,
            "getis_ord_band_m": self.gi_band_m,
            "mean_false_positives_per_shuffle": round_stable(self.mean_false_positives, 4),
            "max_false_positives_in_a_shuffle": self.max_false_positives,
            "false_positive_rate": round_stable(self.false_positive_rate, 6),
            "shuffle_with_any_false_positive_rate": round_stable(
                self.shuffle_with_any_false_positive_rate, 6
            ),
            "interpretation": self.sentence(),
        }

    def sentence(self) -> str:
        """One human-readable sentence, suitable for the brief and the data card."""
        return (
            f"On {self.n_shuffles} label-shuffles of {self.city}'s own reports across its own "
            f"{self.n_segments} tested segments (exposure and geometry held fixed), the hotspot "
            f"method flagged a mean of {round(self.mean_false_positives, 2)} spurious "
            f"significant segment(s) per shuffle at fdr_alpha={self.fdr_alpha} — a false-positive "
            f"rate of {round(self.false_positive_rate * 100, 2)}% of tested segments."
        )


def shuffled_count_sequences(
    count_values: list[int], n_shuffles: int, seed: int
) -> list[list[int]]:
    """Deterministically generate ``n_shuffles`` seeded permutations of ``count_values``.

    A small, directly-testable seam: the same ``(count_values, seed)`` always
    yields the same sequence of permutations (the reproduce-gate guarantee), and
    a different seed yields a different sequence of permutations of the *same*
    multiset of counts.
    """
    rng = random.Random(seed)
    out: list[list[int]] = []
    for _ in range(n_shuffles):
        shuffled = count_values[:]
        rng.shuffle(shuffled)
        out.append(shuffled)
    return out


def run_null_calibration(
    stats: list[SegmentStats],
    segments: list[Segment],
    config: Config,
    n_shuffles: int = DEFAULT_N_SHUFFLES,
    seed: int = DEFAULT_SEED,
) -> CalibrationResult:
    """Run the published hotspot method against seeded label-shuffles of this
    city's own report counts, holding exposure and geometry fixed.

    ``stats`` and ``segments`` are exactly what the real analysis and publish
    step already computed (:class:`~nearmiss.stats.AnalysisResult.segments` and
    :class:`~nearmiss.engine.AnalysisBundle.segments`) — no separate load or
    re-aggregation, so calibration can never silently diverge from what was
    actually published.
    """
    centroid_by_id = {s.id: polyline_centroid(s.coords) for s in segments}
    # Only segments with a usable exposure denominator entered the real rate/Gi*
    # computation (see stats/__init__.py's rate_values); mirror that exactly so
    # the null distribution is calibrated against the same segment set.
    usable_ids = sorted(
        st.segment_id
        for st in stats
        if st.exposure_estimate is not None and st.segment_id in centroid_by_id
    )
    n = len(usable_ids)
    if n == 0:
        return CalibrationResult(
            city=config.city,
            n_shuffles=n_shuffles,
            seed=seed,
            n_segments=0,
            fdr_alpha=config.fdr_alpha,
            gi_band_m=config.gi_band_m,
            false_positive_counts=(),
            mean_false_positives=0.0,
            max_false_positives=0,
            false_positive_rate=0.0,
            shuffle_with_any_false_positive_rate=0.0,
        )

    by_id = {st.segment_id: st for st in stats}
    exposures = {sid: by_id[sid].exposure_estimate for sid in usable_ids}
    centroids = {sid: centroid_by_id[sid] for sid in usable_ids}
    count_values = [by_id[sid].report_count for sid in usable_ids]

    false_positive_counts: list[int] = []
    for shuffled_counts in shuffled_count_sequences(count_values, n_shuffles, seed):
        rate_values = {
            sid: rate_with_ci(
                shuffled_counts[i], exposures[sid] or 0.0, config.rate_per, config.confidence_z
            )[0]
            for i, sid in enumerate(usable_ids)
        }
        z = getis_ord_star(rate_values, centroids, config.gi_band_m)
        pvalues = {sid: two_sided_p(zi) for sid, zi in z.items()}
        rejected = benjamini_hochberg(pvalues, config.fdr_alpha)
        false_positives = sum(1 for sid in rejected if z[sid] > 0.0)
        false_positive_counts.append(false_positives)

    mean_fp = sum(false_positive_counts) / n_shuffles
    any_fp_rate = sum(1 for c in false_positive_counts if c > 0) / n_shuffles

    return CalibrationResult(
        city=config.city,
        n_shuffles=n_shuffles,
        seed=seed,
        n_segments=n,
        fdr_alpha=config.fdr_alpha,
        gi_band_m=config.gi_band_m,
        false_positive_counts=tuple(false_positive_counts),
        mean_false_positives=mean_fp,
        max_false_positives=max(false_positive_counts),
        false_positive_rate=mean_fp / n,
        shuffle_with_any_false_positive_rate=any_fp_rate,
    )
