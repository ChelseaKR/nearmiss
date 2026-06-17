"""The statistics layer: where counts become honest, exposure-normalized claims.

``analyze`` turns clean records plus exposure into per-segment
:class:`~nearmiss.models.SegmentStats` — rates with confidence intervals,
Getis-Ord Gi* hotspot z-scores computed on the rate, a report-intensity KDE
surface, and a reporting-bias characterization.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..config import Config
from ..exposure import attach_exposure, coverage
from ..geometry import polyline_centroid
from ..models import CleanRecord, ConfidenceLabel, Exposure, Report, Segment, SegmentStats
from ..util import round_stable
from .aggregate import aggregate
from .bias import BiasReport, characterize_bias
from .getis_ord import getis_ord_star
from .kde import KdeResult, kde
from .rates import rate_with_ci

__all__ = ["AnalysisResult", "analyze"]


@dataclass
class AnalysisResult:
    segments: list[SegmentStats]
    bias: BiasReport
    kde: KdeResult
    exposure_coverage: float


def analyze(
    records: list[CleanRecord],
    report_points: list[Report],
    segments: list[Segment],
    exposure_map: dict[str, Exposure],
    config: Config,
) -> AnalysisResult:
    agg = aggregate(records)
    seg_ids = [s.id for s in segments]
    attached = attach_exposure(seg_ids, exposure_map)
    centroids = {s.id: polyline_centroid(s.coords) for s in segments}

    rate_values: dict[str, float] = {}
    stats: list[SegmentStats] = []
    for s in segments:
        a = agg.get(s.id)
        count = a.count if a else 0
        exp = attached.get(s.id)
        rate: float | None
        lo: float | None
        hi: float | None
        conf: ConfidenceLabel
        if exp is not None and exp.estimate > 0:
            rate, lo, hi = rate_with_ci(count, exp.estimate, config.rate_per, config.confidence_z)
            rate_values[s.id] = rate
            conf = "uncertain" if count < config.small_n else "certain"
        else:
            rate = lo = hi = None
            conf = "exposure_unknown"
        # Suppress the hazard breakdown on small-n segments (privacy / safety).
        breakdown = dict(a.hazard_breakdown) if (a and count >= config.small_n) else {}
        stats.append(
            SegmentStats(
                segment_id=s.id,
                report_count=count,
                n=count,
                exposure_estimate=(exp.estimate if exp else None),
                exposure_source=(exp.source if exp else None),
                exposure_date=(exp.date if exp else None),
                rate=round_stable(rate, 4),
                rate_ci_low=round_stable(lo, 4),
                rate_ci_high=round_stable(hi, 4),
                getis_ord_z=None,
                significant=False,
                confidence_label=conf,
                hazard_breakdown=breakdown,
                quality_flags=tuple(sorted(a.quality_flags)) if a else (),
            )
        )

    z = getis_ord_star(rate_values, {sid: centroids[sid] for sid in rate_values}, config.gi_band_m)
    for st in stats:
        if st.segment_id in z:
            st.getis_ord_z = round_stable(z[st.segment_id], 4)
            st.significant = z[st.segment_id] > config.confidence_z

    seg_counts = {s.id: (agg[s.id].count if s.id in agg else 0) for s in segments}
    bias = characterize_bias(seg_counts, exposure_map)
    surface = kde([(r.lat, r.lon) for r in report_points], config.kde_grid, config.kde_bandwidth_m)
    return AnalysisResult(
        segments=stats,
        bias=bias,
        kde=surface,
        exposure_coverage=coverage(attached),
    )
