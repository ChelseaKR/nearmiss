"""Benjamini-Hochberg FDR correction for hotspot significance."""

from __future__ import annotations

import pytest

from nearmiss.engine import AnalysisBundle
from nearmiss.stats.getis_ord import benjamini_hochberg, two_sided_p


def test_two_sided_p_of_196_is_about_005() -> None:
    assert two_sided_p(1.959963984540054) == pytest.approx(0.05, abs=1e-3)
    assert two_sided_p(0.0) == pytest.approx(1.0)


def test_bh_rejects_only_small_p_under_correction() -> None:
    # One clearly-significant test among nine noise tests: BH should reject only it.
    pvals = {"hot": 0.0005}
    for i in range(9):
        pvals[f"noise{i}"] = 0.4 + i * 0.05
    rejected = benjamini_hochberg(pvals, 0.05)
    assert rejected == {"hot"}


def test_bh_is_more_conservative_than_uncorrected() -> None:
    # A raw 0.05 cut would reject both "a" and "b"; BH rejects only "a", because
    # "b" does not clear its rank-adjusted threshold.
    pvals = {"a": 0.001, "b": 0.04, "c": 0.06, "d": 0.2, "e": 0.5}
    raw = {k for k, p in pvals.items() if p <= 0.05}
    bh = benjamini_hochberg(pvals, 0.05)
    assert bh < raw  # proper subset
    assert bh == {"a"}


def test_significant_field_is_fdr_corrected_in_analysis(bundle: AnalysisBundle) -> None:
    sig = [s.segment_id for s in bundle.result.segments if s.significant]
    assert sig == ["seg-06"]
