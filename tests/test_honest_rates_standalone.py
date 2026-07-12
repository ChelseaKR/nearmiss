"""honest_rates (EXP-08) must be usable completely independently of nearmiss.

Every test in this module imports ONLY from ``honest_rates`` — never from
``nearmiss`` — to prove the extraction is real, not aspirational: the README's
"usable on any point-event dataset" claim is checked here, not just asserted.
See src/honest_rates/README.md (roadmap item EXP-08).
"""

from __future__ import annotations

import pytest

from honest_rates import SimpleUnit, analyze
from honest_rates.bias import characterize_bias
from honest_rates.fixtures import planted_cluster_fixture
from honest_rates.hotspot import band_neighbors, benjamini_hochberg, getis_ord_star, two_sided_p
from honest_rates.rates import poisson_ci, rate_with_ci, wilson_ci


def test_rate_with_ci_scales_by_exposure() -> None:
    rate, low, high = rate_with_ci(6, 300.0, per=1000.0)
    assert rate == pytest.approx(20.0)
    assert low < rate < high


def test_poisson_ci_zero_count_is_uncertain_not_zero_risk() -> None:
    low, high = poisson_ci(0)
    assert low == 0.0
    assert high > 0.0


def test_wilson_ci_bounds() -> None:
    low, high = wilson_ci(3, 10)
    assert 0.0 <= low < 0.3 < high <= 1.0


def test_getis_ord_and_fdr_flag_a_tight_synthetic_cluster() -> None:
    # Three tight-together high-value units plus nine scattered, near-uniform
    # "noise" units -- large enough (n=12) for the Benjamini-Hochberg
    # correction to have real rank-adjusted thresholds to work with.
    values = {"a": 10.0, "b": 10.0, "c": 10.0}
    centroids = {
        "a": (38.0, -121.0),
        "b": (38.0005, -121.0),
        "c": (38.0, -121.0005),
    }
    noise_values = [1.0, 1.2, 0.8, 1.1, 0.9, 1.3, 0.7, 1.0, 1.05]
    for i, v in enumerate(noise_values):
        uid = f"noise-{i}"
        values[uid] = v
        centroids[uid] = (38.5 + i * 0.05, -121.5 - i * 0.03)

    z = getis_ord_star(values, band_neighbors(centroids, 200.0))
    pvals = {k: two_sided_p(v) for k, v in z.items()}
    rejected = benjamini_hochberg(pvals, alpha=0.05)
    assert rejected == {"a", "b", "c"}  # exactly the planted cluster is flagged


def test_characterize_bias_over_and_under_representation() -> None:
    counts = {"x": 90, "y": 10}
    exposure = {"x": 10.0, "y": 90.0}
    report = characterize_bias(counts, exposure)
    assert report.over_represented[0].unit_id == "x"
    assert report.under_represented[0].unit_id == "y"


def test_analyze_with_plain_units_ranks_rate_over_raw_count() -> None:
    units = [
        SimpleUnit(id="quiet-hot", lat=38.5, lon=-121.5),
        SimpleUnit(id="busy-decoy", lat=39.0, lon=-122.0),
    ]
    counts = {"quiet-hot": 8, "busy-decoy": 40}
    exposure = {"quiet-hot": 50.0, "busy-decoy": 8000.0}
    results = {r.unit_id: r for r in analyze(units, counts, exposure, band_m=500.0)}
    assert results["busy-decoy"].count > results["quiet-hot"].count
    assert (results["busy-decoy"].rate or 0.0) < (results["quiet-hot"].rate or 0.0)


def test_planted_cluster_fixture_recovers_known_ground_truth() -> None:
    """The core honesty test: a pipeline built on this library must recover a
    truth it is handed, not just run without crashing."""
    fx = planted_cluster_fixture()
    results = {
        r.unit_id: r for r in analyze(list(fx.units), fx.counts, fx.exposure, band_m=fx.band_m)
    }

    ranked = sorted(results.values(), key=lambda r: r.rate or 0.0, reverse=True)
    top_ids = {r.unit_id for r in ranked[: len(fx.hotspot_ids)]}
    assert top_ids == fx.hotspot_ids, "the planted cluster must rank first by rate"

    decoy = results[fx.decoy_id]
    assert decoy.count == max(r.count for r in results.values()), (
        "the decoy is planted to have the most raw events"
    )
    assert not decoy.significant, "the busy decoy must not be flagged as a hotspot"
    assert any(results[uid].significant for uid in fx.hotspot_ids), (
        "the planted cluster must be flagged significant"
    )


def test_planted_cluster_fixture_is_deterministic() -> None:
    a = planted_cluster_fixture()
    b = planted_cluster_fixture()
    assert a.counts == b.counts
    assert a.exposure == b.exposure
    assert [u.id for u in a.units] == [u.id for u in b.units]
