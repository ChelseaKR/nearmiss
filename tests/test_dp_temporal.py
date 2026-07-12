"""EXP-05 prototype tests: epsilon-DP segment x part-of-day release.

These guard the contract the ideation doc (docs/ideation/03-expansions.md,
EXP-05) and the design doc (docs/privacy/exp-05-dp-segment-time-bands.md)
require: disabled by default (strict no-op), a hard SME sign-off gate that
raises rather than silently shipping unreviewed, calibrated Laplace noise
tied to a stated epsilon/sensitivity, and a metadata view that never leaks
the true pre-noise count.
"""

from __future__ import annotations

import dataclasses
import json
import random

import pytest

from nearmiss.config import Config
from nearmiss.errors import NearmissError
from nearmiss.models import CleanRecord
from nearmiss.publish import _FORBIDDEN_KEYS
from nearmiss.stats.dp_temporal import (
    DPSignoffMissingError,
    dp_segment_time_release,
    to_metadata,
    true_segment_time_counts,
)


def _rec(occurred_at: str, segment_id: str | None = "seg-01") -> CleanRecord:
    return CleanRecord(
        report_id="r-" + occurred_at + "-" + str(id(occurred_at)),
        occurred_at=occurred_at,
        segment_id=segment_id,
        hazard_type="close_pass",
        severity="near_miss",
        mode="cyclist",
        snapped_distance_m=1.0,
    )


def test_disabled_by_default_is_a_strict_no_op(config: Config) -> None:
    assert config.dp_segment_time_enabled is False
    records = [_rec("2026-06-10T08:00:00-07:00")]
    release = dp_segment_time_release(records, config)
    assert release.enabled is False
    assert release.epsilon is None
    assert release.cells == ()
    assert to_metadata(release) == {"enabled": False}


def test_enabled_without_signoff_raises(config: Config) -> None:
    cfg = dataclasses.replace(
        config, dp_segment_time_enabled=True, dp_segment_time_sme_signoff_ref=None
    )
    with pytest.raises(DPSignoffMissingError):
        dp_segment_time_release([_rec("2026-06-10T08:00:00-07:00")], cfg)


def test_enabled_with_signoff_and_nonpositive_epsilon_raises(config: Config) -> None:
    cfg = dataclasses.replace(
        config,
        dp_segment_time_enabled=True,
        dp_segment_time_sme_signoff_ref="reviewed by J. Doe 2026-07-07",
        dp_segment_time_epsilon=0.0,
    )
    with pytest.raises(NearmissError):
        dp_segment_time_release([_rec("2026-06-10T08:00:00-07:00")], cfg)


def test_true_segment_time_counts_buckets_by_segment_and_part() -> None:
    records = [
        _rec("2026-06-10T07:00:00-07:00", "seg-01"),  # am_peak
        _rec("2026-06-10T08:00:00-07:00", "seg-01"),  # am_peak
        _rec("2026-06-10T12:00:00-07:00", "seg-02"),  # midday
        _rec("2026-06-10T12:00:00-07:00", None),  # unsnapped -- excluded
        _rec("not-a-date", "seg-01"),  # unparseable -- excluded
    ]
    counts = true_segment_time_counts(records)
    assert counts == {("seg-01", "am_peak"): 2, ("seg-02", "midday"): 1}


def test_a_single_report_add_changes_exactly_one_cell_by_one() -> None:
    """Sensitivity check: adding one report changes exactly one cell, by exactly 1."""
    base = [_rec("2026-06-10T07:00:00-07:00", "seg-01")]
    plus_one = [*base, _rec("2026-06-10T08:00:00-07:00", "seg-01")]
    c0 = true_segment_time_counts(base)
    c1 = true_segment_time_counts(plus_one)
    changed = {k: c1.get(k, 0) - c0.get(k, 0) for k in set(c0) | set(c1)}
    changed = {k: v for k, v in changed.items() if v != 0}
    assert changed == {("seg-01", "am_peak"): 1}


def test_enabled_release_adds_calibrated_noise_and_reports_accounting(config: Config) -> None:
    cfg = dataclasses.replace(
        config,
        dp_segment_time_enabled=True,
        dp_segment_time_sme_signoff_ref="reviewed by J. Doe 2026-07-07, see docs/privacy/...",
        dp_segment_time_epsilon=0.5,
    )
    records = [_rec(f"2026-06-10T{h:02d}:00:00-07:00", "seg-01") for h in (7, 8, 9)]
    rng = random.Random(1234)
    release = dp_segment_time_release(records, cfg, rng=rng)

    assert release.enabled is True
    assert release.epsilon == 0.5
    assert release.sensitivity == 1.0
    assert release.mechanism == "laplace"
    assert release.noise_scale == pytest.approx(1.0 / 0.5)
    assert release.sme_signoff_ref is not None
    assert len(release.cells) == 1  # single (segment, part) cell in this fixture
    cell = release.cells[0]
    assert cell.segment_id == "seg-01"
    assert cell.part_of_day == "am_peak"
    assert cell.true_count == 3
    # Noise was actually applied (deterministic under the seeded rng).
    assert cell.noisy_count != cell.true_count
    assert cell.published_count >= 0
    assert release.composed_epsilon_upper_bound == pytest.approx(0.5 * 1)


def test_published_count_never_negative_even_with_large_noise(config: Config) -> None:
    cfg = dataclasses.replace(
        config,
        dp_segment_time_enabled=True,
        dp_segment_time_sme_signoff_ref="reviewed by J. Doe",
        dp_segment_time_epsilon=0.001,  # huge noise scale
    )
    records = [_rec("2026-06-10T07:00:00-07:00", "seg-01")]
    rng = random.Random(7)
    release = dp_segment_time_release(records, cfg, rng=rng)
    assert all(c.published_count >= 0 for c in release.cells)


def test_low_epsilon_flags_utility_theater_risk(config: Config) -> None:
    cfg = dataclasses.replace(
        config,
        dp_segment_time_enabled=True,
        dp_segment_time_sme_signoff_ref="reviewed by J. Doe",
        dp_segment_time_epsilon=0.01,  # very noisy relative to a count of 1
    )
    records = [_rec("2026-06-10T07:00:00-07:00", "seg-01")]
    release = dp_segment_time_release(records, cfg, rng=random.Random(1))
    assert release.utility_theater_risk is True


def test_metadata_never_leaks_true_count_or_forbidden_keys(config: Config) -> None:
    cfg = dataclasses.replace(
        config,
        dp_segment_time_enabled=True,
        dp_segment_time_sme_signoff_ref="reviewed by J. Doe",
        dp_segment_time_epsilon=1.0,
    )
    records = [_rec(f"2026-06-10T{h:02d}:00:00-07:00", "seg-01") for h in (7, 8, 9, 10, 11)]
    release = dp_segment_time_release(records, cfg, rng=random.Random(42))
    md = to_metadata(release)
    text = json.dumps(md)
    assert '"true_count"' not in text
    for key in _FORBIDDEN_KEYS:
        assert f'"{key}"' not in text, f"DP metadata leaked forbidden key {key}"
    assert md["enabled"] is True
    assert md["epsilon_per_cell"] == 1.0
    assert md["sensitivity_per_cell"] == 1.0
    cells = md["cells"]
    assert isinstance(cells, list)
    first_cell = cells[0]
    assert isinstance(first_cell, dict)
    assert first_cell["published_count"] == release.cells[0].published_count
    status = md["status"]
    assert isinstance(status, str)
    assert "PROTOTYPE" in status


def test_publish_metadata_carries_disabled_dp_release(bundle) -> None:  # type: ignore[no-untyped-def]
    from nearmiss.stats.dp_temporal import to_metadata as dp_to_metadata

    assert dp_to_metadata(bundle.result.dp_segment_time) == {"enabled": False}
