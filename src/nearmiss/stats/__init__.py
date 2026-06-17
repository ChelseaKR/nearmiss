"""The statistics layer: where counts become honest, exposure-normalized claims.

``analyze`` turns clean records plus exposure into per-segment
:class:`~nearmiss.models.SegmentStats` — rates with confidence intervals,
Getis-Ord Gi* hotspot z-scores computed on the rate with a Benjamini-Hochberg
false-discovery-rate adjustment for multiple comparisons, a report-intensity KDE
surface, and a reporting-bias characterization. Segments with too few reports to
publish safely are flagged not-publishable (k-anonymity).
"""

from __future__ import annotations

from dataclasses import dataclass

from ..config import Config
from ..exposure import attach_exposure, coverage, is_usable
from ..geometry import haversine_m, polyline_centroid
from ..models import CleanRecord, ConfidenceLabel, Exposure, Report, Segment, SegmentStats
from ..util import round_stable
from .aggregate import aggregate
from .bias import BiasReport, characterize_bias
from .getis_ord import benjamini_hochberg, getis_ord_star, two_sided_p
from .kde import KdeResult, kde
from .rates import rate_with_ci

__all__ = ["AnalysisResult", "analyze"]

# Raw pipeline quality flags that map to the published "geocode_low_confidence" flag.
_LOW_CONFIDENCE_RAW = frozenset(("low_accuracy", "far_snap"))


@dataclass
class AnalysisResult:
    segments: list[SegmentStats]
    bias: BiasReport
    kde: KdeResult
    exposure_coverage: float
    kde_peak_segment: str | None


def _published_quality_flags(
    usable: bool, count: int, small_n: int, raw_flags: set[str]
) -> tuple[str, ...]:
    """Map internal pipeline flags + sample size to the published flag vocabulary."""
    flags: list[str] = []
    if not usable:
        flags.append("exposure_unknown")
    if 0 < count < small_n:
        flags.append("low_sample")
    if raw_flags & _LOW_CONFIDENCE_RAW:
        flags.append("geocode_low_confidence")
    return tuple(sorted(set(flags)))


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
        usable = is_usable(exp)
        rate: float | None
        lo: float | None
        hi: float | None
        conf: ConfidenceLabel
        if usable:
            assert exp is not None
            rate, lo, hi = rate_with_ci(count, exp.estimate, config.rate_per, config.confidence_z)
            rate_values[s.id] = rate
            conf = "uncertain" if count < config.small_n else "certain"
        else:
            rate = lo = hi = None
            conf = "exposure_unknown"
        # Hazard breakdown is suppressed below the small-sample threshold.
        breakdown = dict(a.hazard_breakdown) if (a and count >= config.small_n) else {}
        raw_flags = set(a.quality_flags) if a else set()
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
                # k-anonymity: withhold segments with a non-zero count below the floor.
                publishable=not (0 < count < config.min_publish_n),
                hazard_breakdown=breakdown,
                quality_flags=_published_quality_flags(usable, count, config.small_n, raw_flags),
            )
        )

    # Getis-Ord Gi* on the exposure-normalized rate, with a Benjamini-Hochberg
    # FDR adjustment so a "significant" cluster is not a multiple-comparison fluke.
    z = getis_ord_star(rate_values, {sid: centroids[sid] for sid in rate_values}, config.gi_band_m)
    pvals = {sid: two_sided_p(zi) for sid, zi in z.items()}
    rejected = benjamini_hochberg(pvals, config.fdr_alpha)
    for st in stats:
        if st.segment_id in z:
            zi = z[st.segment_id]
            st.getis_ord_z = round_stable(zi, 4)
            st.significant = st.segment_id in rejected and zi > 0.0

    seg_counts = {s.id: (agg[s.id].count if s.id in agg else 0) for s in segments}
    bias = characterize_bias(seg_counts, exposure_map)
    surface = kde([(r.lat, r.lon) for r in report_points], config.kde_grid, config.kde_bandwidth_m)

    # Report the KDE peak only as the nearest PUBLISHABLE segment id — never as a
    # raw or near-raw coordinate (privacy).
    peak_segment: str | None = None
    peak_cell = surface.peak
    if peak_cell is not None:
        publishable = [s for s in stats if s.publishable]
        if publishable:
            peak_segment = min(
                publishable,
                key=lambda s: haversine_m(peak_cell.lat, peak_cell.lon, *centroids[s.segment_id]),
            ).segment_id

    return AnalysisResult(
        segments=stats,
        bias=bias,
        kde=surface,
        exposure_coverage=coverage(attached),
        kde_peak_segment=peak_segment,
    )
