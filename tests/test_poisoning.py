"""Red-team: a low-confidence report flood cannot move the published hotspot ranking.

The primary published rate is built only from high-confidence records (the
quality-tier split, docs/METHODOLOGY.md §2 step 4). This test models an adversary
who tries to manufacture a hotspot on a *non*-hotspot segment by injecting a large
batch of deliberately vague (``low_accuracy``) reports. Because those records are
excluded from the primary rate, the top segment and the significant cluster must be
byte-identical to the un-poisoned run — while the poison remains fully visible as a
raised all-records count, a per-segment sensitivity delta, and a higher excluded
fraction (honest, not hidden).
"""

from __future__ import annotations

from nearmiss.config import Config
from nearmiss.engine import AnalysisBundle, load_city
from nearmiss.models import CleanRecord
from nearmiss.stats import analyze

# A segment that is NOT the planted hotspot (seg-06): the busy decoy with the most
# raw reports but a low rate, and a large exposure denominator to dilute honest counts.
TARGET_SEGMENT = "seg-03"
POISON_BATCH = 200  # enough that, if counted, seg-03's rate would exceed the real hotspot


def _poison(report_id: str) -> CleanRecord:
    return CleanRecord(
        report_id=report_id,
        occurred_at="2026-06-10T12:00:00-07:00",
        segment_id=TARGET_SEGMENT,
        hazard_type="close_pass",
        severity="near_miss",
        mode="cyclist",
        snapped_distance_m=1.0,
        quality_flags=("low_accuracy",),  # deliberately vague -> low-confidence tier
    )


def test_low_confidence_flood_does_not_change_primary_ranking(
    bundle: AnalysisBundle, config: Config
) -> None:
    city = load_city(config)

    baseline = bundle.result  # analyze() over the clean fixture records
    baseline_rates = {s.segment_id: s.rate for s in baseline.segments}
    baseline_significant = {s.segment_id for s in baseline.segments if s.significant}
    baseline_top = max(
        (s for s in baseline.segments if s.rate is not None), key=lambda s: s.rate or 0.0
    ).segment_id
    assert baseline_top == "seg-06"  # sanity: the planted hotspot leads before the attack

    poisoned_records = list(bundle.records) + [_poison(f"poison-{i}") for i in range(POISON_BATCH)]
    poisoned = analyze(poisoned_records, city.reports, bundle.segments, city.exposure, config)
    poisoned_rates = {s.segment_id: s.rate for s in poisoned.segments}
    poisoned_significant = {s.segment_id for s in poisoned.segments if s.significant}
    poisoned_top = max(
        (s for s in poisoned.segments if s.rate is not None), key=lambda s: s.rate or 0.0
    ).segment_id

    # The attack does NOT move the published (primary) surface at all.
    assert poisoned_top == baseline_top
    assert poisoned_significant == baseline_significant
    assert poisoned_rates == baseline_rates  # every per-segment primary rate is unchanged

    # ...but the poison is not silently dropped: it is visible as a raised all-records
    # count, a reported sensitivity delta on the targeted segment, and a higher
    # excluded fraction. Honesty over concealment.
    by_id = {s.segment_id: s for s in poisoned.segments}
    target = by_id[TARGET_SEGMENT]
    baseline_target = {s.segment_id: s for s in baseline.segments}[TARGET_SEGMENT]
    assert target.report_count == baseline_target.report_count + POISON_BATCH
    assert target.rate_sensitivity_delta is not None
    assert target.rate_sensitivity_delta > 0.0
    assert poisoned.excluded_low_confidence_fraction > baseline.excluded_low_confidence_fraction
