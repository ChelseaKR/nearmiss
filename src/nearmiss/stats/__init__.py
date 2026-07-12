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
from ..exposure import attach_exposure, corroboration, coverage, is_stale, is_usable
from ..geometry import haversine_m, polyline_centroid
from ..models import CleanRecord, ConfidenceLabel, Exposure, Report, Segment, SegmentStats
from ..util import round_stable
from .aggregate import _LOW_CONFIDENCE_RAW, SegmentAgg, aggregate
from .bias import BiasReport, characterize_bias
from .getis_ord import benjamini_hochberg, getis_ord_star, two_sided_p
from .kde import KdeResult, kde
from .maup import RankStability, rank_stability
from .rates import pearson_dispersion, rate_with_ci
from .temporal import TemporalBreakdown, WeatherDay, temporal_breakdown

__all__ = ["AnalysisResult", "analyze"]


@dataclass
class AnalysisResult:
    segments: list[SegmentStats]
    bias: BiasReport
    kde: KdeResult
    exposure_coverage: float
    kde_peak_segment: str | None
    temporal: TemporalBreakdown
    # Quasi-Poisson dispersion of the report counts (RR-02); ~1 is clean Poisson,
    # materially above 1 is overdispersion (clustered reporting), in which case the
    # per-segment Poisson intervals understate uncertainty by ~sqrt(dispersion).
    dispersion: float = 1.0
    # Whether the per-segment intervals were widened for that dispersion.
    overdispersion_adjusted: bool = False
    # MAUP rank-stability under re-segmentation (RR-05).
    rank_stability: RankStability | None = None
    # Fraction of snapped records excluded from the primary rate because they carry a
    # low-confidence flag (low_accuracy / far_snap): low_confidence_snapped / snapped.
    excluded_low_confidence_fraction: float = 0.0


def _published_quality_flags(
    usable: bool, count: int, small_n: int, raw_flags: set[str], stale: bool
) -> tuple[str, ...]:
    """Map internal pipeline flags + sample size to the published flag vocabulary."""
    flags: list[str] = []
    if not usable:
        flags.append("exposure_unknown")
    if 0 < count < small_n:
        flags.append("low_sample")
    if raw_flags & _LOW_CONFIDENCE_RAW:
        flags.append("geocode_low_confidence")
    if usable and stale:
        flags.append("exposure_stale")
    return tuple(sorted(set(flags)))


def _reference_date(records: list[CleanRecord], report_points: list[Report]) -> str | None:
    """The latest report date the pipeline retained — the temporary stand-in for a
    first-class analysis window (FIX-05), used only to detect a stale exposure
    vintage (METHODOLOGY §3.2). ``None`` when there is nothing to compare against.
    """
    dates = [r.occurred_at for r in records] or [r.occurred_at for r in report_points]
    return max(dates) if dates else None


def _estimate_dispersion(
    segments: list[Segment],
    attached: dict[str, Exposure | None],
    agg: dict[str, SegmentAgg],
) -> float:
    """Quasi-Poisson dispersion of report counts vs exposure over usable segments."""
    usable_counts: list[int] = []
    usable_exposures: list[float] = []
    for s in segments:
        exp = attached.get(s.id)
        if is_usable(exp):
            assert exp is not None
            a = agg.get(s.id)
            usable_counts.append(a.count if a else 0)
            usable_exposures.append(exp.estimate)
    return pearson_dispersion(usable_counts, usable_exposures)


def _rates_by_type(
    usable: bool,
    count: int,
    hazard_breakdown: dict[str, int],
    exposure_estimate: float | None,
    config: Config,
) -> dict[str, dict[str, float]]:
    """Per-hazard-type rate layers: for a usable, aggregated segment, each
    hazard type whose own count clears the small-sample threshold gets its
    own exposure-normalized rate + CI (against the same segment exposure).
    Types below the threshold are suppressed entirely (no entry). The
    top-level ``rate`` remains the pooled rate across all types (an
    explicit union). Aggregate-only: only counts and rates are stored.
    """
    rates_by_type: dict[str, dict[str, float]] = {}
    if not (usable and count >= config.small_n):
        return rates_by_type
    assert exposure_estimate is not None
    for hazard_type, type_count in hazard_breakdown.items():
        if type_count < config.small_n:
            continue
        t_rate, t_lo, t_hi = rate_with_ci(
            type_count, exposure_estimate, config.rate_per, config.confidence_z
        )
        r4, lo4, hi4 = (
            round_stable(t_rate, 4),
            round_stable(t_lo, 4),
            round_stable(t_hi, 4),
        )
        # rate_with_ci returns real floats, so the rounded values are never None.
        assert r4 is not None and lo4 is not None and hi4 is not None
        rates_by_type[hazard_type] = {
            "count": float(type_count),
            "rate": r4,
            "rate_ci_low": lo4,
            "rate_ci_high": hi4,
        }
    return rates_by_type


def analyze(
    records: list[CleanRecord],
    report_points: list[Report],
    segments: list[Segment],
    exposure_map: dict[str, Exposure],
    config: Config,
    weather: dict[str, WeatherDay] | None = None,
    weather_source: str | None = None,
) -> AnalysisResult:
    """Turn clean records + exposure into per-segment published statistics.

    ``report_count``/``n`` on each :class:`~nearmiss.models.SegmentStats` stay the
    total observed (all-records) count. The *published* ``rate``/CI is the PRIMARY
    rate: it excludes low-confidence records (``low_accuracy`` / ``far_snap``) and is
    also what feeds Getis-Ord hotspot detection. Each segment carries a
    ``rate_sensitivity_delta`` when the all-records rate falls outside the primary CI,
    and :class:`AnalysisResult` carries the overall
    ``excluded_low_confidence_fraction``.
    """
    agg = aggregate(records)
    seg_ids = [s.id for s in segments]
    attached = attach_exposure(seg_ids, exposure_map)
    centroids = {s.id: polyline_centroid(s.coords) for s in segments}
    # corroboration() returns an AGREEMENT ratio (1.0 = perfect agreement); the
    # published exposure_disagreement is its complement so higher = more disagreement.
    agreement = corroboration(exposure_map)
    reference_date = _reference_date(records, report_points)

    # RR-02: estimate the quasi-Poisson dispersion of the report counts against
    # exposure. Clustered reporting makes counts more variable than Poisson, which
    # makes the pure Poisson interval too narrow; when overdispersion is present we
    # can widen every per-segment interval by sqrt(dispersion). The dispersion is
    # always computed and reported (the brief surfaces it); whether it is applied
    # to the published intervals is an explicit, versioned config choice so the
    # published methodology is never silently changed under a consumer.
    dispersion = _estimate_dispersion(segments, attached, agg)
    ci_dispersion = dispersion if config.overdispersion_adjust else 1.0

    rate_values: dict[str, float] = {}
    stats: list[SegmentStats] = []
    for s in segments:
        a = agg.get(s.id)
        count = a.count if a else 0
        count_primary = a.count_primary if a else 0
        exp = attached.get(s.id)
        usable = is_usable(exp, config.exposure_floor)
        rate: float | None
        lo: float | None
        hi: float | None
        sensitivity_delta: float | None = None
        conf: ConfidenceLabel
        if usable:
            assert exp is not None
            # The PRIMARY published rate excludes low-confidence records; it is what
            # SegmentStats.rate/CI reports and what feeds Getis-Ord hotspot detection.
            rate, lo, hi = rate_with_ci(
                count_primary, exp.estimate, config.rate_per, config.confidence_z, ci_dispersion
            )
            rate_values[s.id] = rate
            # Sensitivity: the all-records rate (including low-confidence reports).
            # Report a delta only when it falls OUTSIDE the primary CI — i.e. when
            # including the excluded reports would materially move the published rate.
            if count != count_primary:
                rate_all, _, _ = rate_with_ci(
                    count, exp.estimate, config.rate_per, config.confidence_z, ci_dispersion
                )
                if rate_all < lo or rate_all > hi:
                    sensitivity_delta = round_stable(rate_all - rate, 4)
            conf = "uncertain" if count < config.small_n else "certain"
        else:
            rate = lo = hi = None
            conf = "exposure_unknown"
        # Hazard breakdown is suppressed below the small-sample threshold.
        breakdown = dict(a.hazard_breakdown) if (a and count >= config.small_n) else {}
        rates_by_type = _rates_by_type(
            usable,
            count,
            a.hazard_breakdown if a else {},
            exp.estimate if exp else None,
            config,
        )
        raw_flags = set(a.quality_flags) if a else set()
        stale = (
            usable
            and exp is not None
            and reference_date is not None
            and is_stale(exp.date, reference_date, config.exposure_stale_days)
        )
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
                rates_by_type=rates_by_type,
                quality_flags=_published_quality_flags(
                    usable, count, config.small_n, raw_flags, stale
                ),
                rate_sensitivity_delta=sensitivity_delta,
                exposure_tier=(exp.tier if exp else "unknown"),
                exposure_disagreement=(
                    round_stable(1.0 - agreement[s.id], 4) if s.id in agreement else None
                ),
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

    temporal = temporal_breakdown(records, config, weather, weather_source)

    # RR-05: re-segment the network and report whether the top hotspots survive.
    stability = rank_stability(stats, segments, exposure_map, config)

    # Overall excluded fraction: low-confidence snapped records / all snapped records.
    snapped_total = sum(a.count for a in agg.values())
    snapped_primary = sum(a.count_primary for a in agg.values())
    excluded_fraction = (
        round((snapped_total - snapped_primary) / snapped_total, 4) if snapped_total else 0.0
    )

    return AnalysisResult(
        segments=stats,
        bias=bias,
        kde=surface,
        exposure_coverage=coverage(attached, config.exposure_floor),
        kde_peak_segment=peak_segment,
        temporal=temporal,
        dispersion=round(dispersion, 4),
        overdispersion_adjusted=config.overdispersion_adjust,
        rank_stability=stability,
        excluded_low_confidence_fraction=excluded_fraction,
    )
