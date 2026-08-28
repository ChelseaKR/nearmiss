"""Overdispersion check wired into the analysis (RR-02).

The methodology flags that clustered report counts are overdispersed, so the
pure Poisson interval is too narrow. The analysis must (1) always estimate and
expose the dispersion, (2) leave the published Poisson intervals unchanged by
default (so enabling the widening is a deliberate, versioned choice), and (3)
widen every interval by ~sqrt(dispersion) when the adjustment is switched on.
"""

from __future__ import annotations

import dataclasses

import pytest

from nearmiss.config import Config
from nearmiss.engine import AnalysisBundle, build_analysis
from nearmiss.stats.aggregate import aggregate
from nearmiss.stats.rates import rate_with_ci


def test_fixture_is_overdispersed_and_reported(bundle: AnalysisBundle) -> None:
    # The planted hotspot makes the Davis counts strongly overdispersed.
    assert bundle.result.dispersion > 2.0
    assert bundle.result.overdispersion_adjusted is False  # default: not applied


def test_default_intervals_are_the_unwidened_poisson_intervals(bundle: AnalysisBundle) -> None:
    # With the adjustment off, each rated segment's CI is exactly the pure Poisson
    # (dispersion = 1) interval — so the published dataset is unchanged. The
    # published rate/CI is built from the PRIMARY (low-confidence-excluded,
    # FIX-07) count, so recompute the expectation from that count.
    per, z = 1000.0, 1.96
    agg = aggregate(bundle.records)
    for s in bundle.result.segments:
        if s.rate is None or s.exposure_estimate in (None, 0):
            continue
        assert s.exposure_estimate is not None
        a = agg.get(s.segment_id)
        count_primary = a.count_primary if a else 0
        _, lo, hi = rate_with_ci(count_primary, s.exposure_estimate, per, z, dispersion=1.0)
        assert s.rate_ci_low == round(lo, 4)
        assert s.rate_ci_high == round(hi, 4)


def test_adjustment_widens_every_interval_when_enabled(config: Config) -> None:
    off = build_analysis(config)
    on = build_analysis(dataclasses.replace(config, overdispersion_adjust=True))
    assert on.result.overdispersion_adjusted is True
    assert on.result.dispersion == off.result.dispersion  # same estimate either way

    off_by_id = {s.segment_id: s for s in off.result.segments}
    widened = 0
    for s in on.result.segments:
        base = off_by_id[s.segment_id]
        if s.rate is None or base.rate_ci_high is None or s.rate_ci_high is None:
            continue
        assert s.rate == base.rate  # the point estimate never moves
        if base.report_count > 0:
            assert s.rate_ci_high > base.rate_ci_high  # interval is wider
            assert s.rate_ci_low is not None and s.rate_ci_low >= 0.0
            widened += 1
    assert widened > 0


def test_per_hazard_type_intervals_are_widened_too(config: Config) -> None:
    """The per-type layers are published intervals, so the widening reaches them.

    METHODOLOGY §4 states the adjustment "widens **every published interval** by
    `sqrt(phi)`", and `schema/dataset.schema.md` §4.5 says each `rates_by_type`
    entry is computed "by the same method as the top-level `rate`". A per-type
    interval left at pure Poisson while the pooled interval beside it on the same
    feature is widened is a false-confidence claim on exactly the number a reader
    quotes for one hazard, such as the dooring rate on one block (issue #201).

    The check is the ratio of half-widths rather than a recomputed interval,
    because that is the property the documentation states: the same `sqrt(phi)`
    factor reaches the type layer that reaches the pooled rate it decomposes.
    """
    off = build_analysis(config)
    on = build_analysis(dataclasses.replace(config, overdispersion_adjust=True))
    assert on.result.dispersion > 1.0  # the fixture must be overdispersed
    off_by_id = {s.segment_id: s for s in off.result.segments}

    checked = 0
    for s in on.result.segments:
        base = off_by_id[s.segment_id]
        if not s.rates_by_type or s.rate is None or s.rate_ci_high is None:
            continue
        assert base.rate_ci_high is not None and base.rate is not None
        pooled_factor = (s.rate_ci_high - s.rate) / (base.rate_ci_high - base.rate)
        assert pooled_factor > 1.0  # the pooled interval is widened, as documented
        for hazard_type, layer in s.rates_by_type.items():
            was = base.rates_by_type[hazard_type]
            assert layer["rate"] == was["rate"]  # the point estimate never moves
            type_factor = (layer["rate_ci_high"] - layer["rate"]) / (
                was["rate_ci_high"] - was["rate"]
            )
            assert type_factor == pytest.approx(pooled_factor, rel=1e-4), (
                f"{s.segment_id}/{hazard_type} is not widened by the pooled factor"
            )
            checked += 1
    assert checked > 0  # the fixture must actually publish per-type layers
