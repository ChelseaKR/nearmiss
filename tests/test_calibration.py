"""Publish-time null calibration: "we attacked our own dataset" (EXP-01).

Label-shuffling a city's own report counts (exposure and geometry held fixed)
and re-running the real rate + Getis-Ord Gi* + Benjamini-Hochberg pipeline must
produce a reproducible, privacy-safe, and honestly bounded false-positive
estimate — the whole point of a *calibration* artifact is that it is trustworthy
on its own terms.
"""

from __future__ import annotations

from nearmiss.config import Config
from nearmiss.engine import AnalysisBundle
from nearmiss.stats.calibration import run_null_calibration, shuffled_count_sequences


def test_calibration_is_deterministic_for_a_fixed_seed(
    bundle: AnalysisBundle, config: Config
) -> None:
    first = run_null_calibration(
        bundle.result.segments, bundle.segments, config, n_shuffles=25, seed=7
    )
    second = run_null_calibration(
        bundle.result.segments, bundle.segments, config, n_shuffles=25, seed=7
    )
    assert first.false_positive_counts == second.false_positive_counts
    assert first.mean_false_positives == second.mean_false_positives
    assert first.false_positive_rate == second.false_positive_rate


def test_seed_deterministically_drives_the_permutation() -> None:
    counts = list(range(12))
    same_a = shuffled_count_sequences(counts, n_shuffles=10, seed=1)
    same_b = shuffled_count_sequences(counts, n_shuffles=10, seed=1)
    different = shuffled_count_sequences(counts, n_shuffles=10, seed=2)
    assert same_a == same_b  # fixed seed -> reproducible (the reproduce-gate guarantee)
    assert same_a != different  # a different seed -> a different sequence of permutations
    # Every permutation is of the SAME multiset (a relabeling, not a resample).
    for shuffle in same_a:
        assert sorted(shuffle) == counts


def test_result_shape_matches_requested_shuffle_count(
    bundle: AnalysisBundle, config: Config
) -> None:
    result = run_null_calibration(
        bundle.result.segments, bundle.segments, config, n_shuffles=30, seed=42
    )
    assert result.n_shuffles == 30
    assert len(result.false_positive_counts) == 30
    assert result.n_segments > 0
    # Only segments with a usable exposure estimate are tested, exactly like the
    # real analysis's rate_values (stats/__init__.py).
    usable = sum(1 for s in bundle.result.segments if s.exposure_estimate is not None)
    assert result.n_segments == usable


def test_false_positive_rate_is_a_bounded_fraction(bundle: AnalysisBundle, config: Config) -> None:
    result = run_null_calibration(
        bundle.result.segments, bundle.segments, config, n_shuffles=50, seed=99
    )
    assert 0.0 <= result.false_positive_rate <= 1.0
    assert 0.0 <= result.shuffle_with_any_false_positive_rate <= 1.0
    assert result.max_false_positives <= result.n_segments
    assert 0.0 <= result.mean_false_positives <= result.max_false_positives + 1e-9


def test_calibration_never_flags_more_than_fdr_alpha_would_predict_loosely(
    bundle: AnalysisBundle, config: Config
) -> None:
    # A calibration artifact that "finds" hotspots in shuffled noise at a rate wildly
    # beyond the nominal fdr_alpha would mean the method is miscalibrated on this
    # city's real geometry -- this is the honesty check the artifact exists to make.
    # We use a loose multiple of fdr_alpha (not an exact equality) because BH's
    # finite-sample behavior on a handful of segments is not asymptotic.
    result = run_null_calibration(
        bundle.result.segments, bundle.segments, config, n_shuffles=200, seed=20260101
    )
    assert result.false_positive_rate <= max(config.fdr_alpha * 5, 0.25)


def test_to_metadata_is_privacy_safe_and_carries_no_per_shuffle_detail(
    bundle: AnalysisBundle, config: Config
) -> None:
    result = run_null_calibration(
        bundle.result.segments, bundle.segments, config, n_shuffles=10, seed=3
    )
    metadata = result.to_metadata()
    assert metadata["n_shuffles"] == 10
    assert metadata["seed"] == 3
    assert metadata["city"] == config.city
    assert "false_positive_rate" in metadata
    assert "interpretation" in metadata
    # Only aggregate summary numbers -- never a per-shuffle or per-segment listing.
    assert "false_positive_counts" not in metadata


def test_sentence_mentions_city_and_shuffle_count(bundle: AnalysisBundle, config: Config) -> None:
    result = run_null_calibration(
        bundle.result.segments, bundle.segments, config, n_shuffles=15, seed=5
    )
    sentence = result.sentence()
    assert config.city in sentence
    assert "15" in sentence


def test_empty_input_yields_a_zeroed_result(config: Config) -> None:
    result = run_null_calibration([], [], config, n_shuffles=10, seed=1)
    assert result.n_segments == 0
    assert result.false_positive_rate == 0.0
    assert result.mean_false_positives == 0.0
    assert result.false_positive_counts == ()
