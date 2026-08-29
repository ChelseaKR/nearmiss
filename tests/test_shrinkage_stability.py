"""Empirical-Bayes shrinkage as a re-ranking check (RE-02).

A sparse segment's rate is mostly Poisson noise, so the published order can rest
on which quiet block caught a lucky report. Shrinkage pulls each rate toward the
overall rate in proportion to how little its own count carries. This ships as a
check on the ranking, never as the published rate, and the tests here hold it to
the estimator's arithmetic, to its refusal, and to leaving the published numbers
alone.
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest

from honest_rates.rates import empirical_bayes_rates
from nearmiss.config import Config
from nearmiss.engine import AnalysisBundle
from nearmiss.figures import _shrinkage_note
from nearmiss.models import SegmentStats
from nearmiss.stats.shrinkage import (
    FRAGILE,
    NOT_EVALUATED,
    STABLE,
    shrinkage_stability,
    to_metadata,
)

ROOT = Path(__file__).resolve().parents[1]
PUBLISHED = ROOT / "data" / "published"
METHODOLOGY = ROOT / "docs" / "METHODOLOGY.md"
SCHEMA_DOC = ROOT / "schema" / "dataset.schema.md"


def test_a_sparse_unit_is_shrunk_further_than_a_dense_one() -> None:
    """The whole point of the estimator: information decides how far a rate moves.

    Two units with the same raw rate, one built on 2 events and one on 200, must
    not be treated as equally informative.
    """
    counts = [2, 200, 5, 6, 40]
    exposures = [20.0, 2000.0, 400.0, 500.0, 300.0]
    shrunk, global_rate, variance, weights = empirical_bayes_rates(counts, exposures)
    assert variance > 0.0
    sparse, dense = 0, 1
    assert counts[sparse] / exposures[sparse] == counts[dense] / exposures[dense]
    assert weights[sparse] < weights[dense]  # the sparse unit keeps less of its own rate
    raw_sparse = counts[sparse] / exposures[sparse]
    raw_dense = counts[dense] / exposures[dense]
    assert abs(shrunk[sparse] - global_rate) < abs(raw_sparse - global_rate)
    assert abs(shrunk[dense] - global_rate) < abs(raw_dense - global_rate)
    # ...and the sparse one lands closer to the overall rate than the dense one.
    assert abs(shrunk[sparse] - global_rate) < abs(shrunk[dense] - global_rate)


def test_shrunk_rates_lie_between_the_raw_rate_and_the_overall_rate() -> None:
    """A shrunk rate is a weighted average, so it can never overshoot either end."""
    counts = [1, 9, 30, 0, 4, 12]
    exposures = [50.0, 200.0, 900.0, 120.0, 340.0, 610.0]
    shrunk, global_rate, variance, weights = empirical_bayes_rates(counts, exposures)
    assert variance > 0.0
    for count, exposure, value, weight in zip(counts, exposures, shrunk, weights, strict=True):
        raw = count / exposure
        assert 0.0 <= weight <= 1.0
        assert min(raw, global_rate) - 1e-12 <= value <= max(raw, global_rate) + 1e-12
        assert abs(value - (global_rate + weight * (raw - global_rate))) < 1e-12


def test_no_between_unit_variance_shrinks_everything_to_the_overall_rate() -> None:
    """Marshall's convention: a negative variance estimate is clamped to zero.

    The spread is then no larger than Poisson noise alone would produce, and every
    unit collapses onto the overall rate. That must not read as a ranking.
    """
    shrunk, global_rate, variance, weights = empirical_bayes_rates([1, 1, 1], [10.0, 10.0, 10.0])
    assert variance == 0.0
    assert weights == [0.0, 0.0, 0.0]
    assert shrunk == [global_rate] * 3


def test_the_estimator_refuses_an_exposure_it_cannot_divide_by() -> None:
    with pytest.raises(ValueError):
        empirical_bayes_rates([1, 2], [0.0, 5.0])
    with pytest.raises(ValueError):
        empirical_bayes_rates([1, 2], [5.0])


def test_analysis_publishes_the_shrinkage_result(bundle: AnalysisBundle) -> None:
    """The Davis planted hotspot holds its rank, and the artifact says how narrowly.

    `top_segment_weight` is the number worth reading: the top segment keeps under
    two thirds of its own rate under the adjustment, so the published order is
    not resting on a segment that shrinkage would erase.
    """
    shrink = bundle.result.shrinkage_stability
    assert shrink is not None
    assert shrink.evaluated is True
    assert shrink.verdict == STABLE
    assert shrink.baseline_top_segment == "seg-06"
    assert shrink.shrunk_top_segment == "seg-06"
    assert shrink.shrunk_top_rank == 1
    assert shrink.top_segment_survives is True
    assert shrink.baseline_top_weight is not None and 0.0 < shrink.baseline_top_weight < 1.0
    assert 0.0 < shrink.mean_weight < 1.0
    assert shrink.between_segment_variance > 0.0


def _stat(sid: str, count: int, exposure: float) -> SegmentStats:
    """A rated, publishable segment whose rate is exactly count/exposure per 1000."""
    return SegmentStats(
        segment_id=sid,
        report_count=count,
        n=count,
        exposure_estimate=exposure,
        exposure_source="test",
        exposure_date="2026-01-01",
        rate=count / exposure * 1000.0,
        rate_ci_low=None,
        rate_ci_high=None,
        getis_ord_z=None,
        significant=False,
        confidence_label="certain",
    )


def test_a_lucky_sparse_segment_is_reported_as_fragile(config: Config) -> None:
    """When the published leader is the least informative segment, the check says so.

    `seg-lucky` has the highest raw rate in the city (200 per 1000) off a single
    report over an exposure of 5, and keeps 3% of its own rate under the
    adjustment. `seg-solid` has a lower raw rate off 60 reports over 3000 and
    keeps 97%, so it leads the shrunk ranking. The published order does not
    change; the artifact reports that it moved.
    """
    stats = [
        _stat("seg-lucky", 1, 5.0),
        _stat("seg-solid", 60, 3000.0),
        _stat("seg-a", 5, 1000.0),
        _stat("seg-b", 3, 900.0),
        _stat("seg-c", 8, 2000.0),
    ]
    counts = {s.segment_id: s.report_count for s in stats}
    result = shrinkage_stability(stats, counts, config, {})
    assert result.evaluated is True
    assert result.baseline_top_segment == "seg-lucky"
    assert result.verdict == FRAGILE
    assert result.top_segment_survives is False
    assert result.shrunk_top_segment == "seg-solid"
    assert result.shrunk_top_rank == 2
    # It kept almost none of its own rate, which is why it moved.
    assert result.baseline_top_weight is not None and result.baseline_top_weight < 0.2


def test_too_few_rated_segments_is_not_evaluated_never_stable(
    bundle: AnalysisBundle, config: Config
) -> None:
    """Below three rated segments there is no ranking to re-estimate."""
    rated = [s for s in bundle.result.segments if s.rate is not None and s.publishable][:2]
    result = shrinkage_stability(rated, {s.segment_id: 1 for s in rated}, config, {})
    assert result.evaluated is False
    assert result.verdict == NOT_EVALUATED
    assert result.verdict != STABLE
    assert result.top_segment_survives is None
    assert "not a passed check" in str(to_metadata(result)["reason"])


def test_no_variance_is_not_evaluated_and_says_which_reason(
    bundle: AnalysisBundle, config: Config
) -> None:
    """Identical rates leave nothing to rank, and the reason names the data."""
    rated = [s for s in bundle.result.segments if s.rate is not None and s.publishable][:4]
    flat = [
        dataclasses.replace(s, rate=10.0, exposure_estimate=100.0, report_count=1, n=1)
        for s in rated
    ]
    result = shrinkage_stability(flat, {s.segment_id: 1 for s in flat}, config, {})
    assert result.evaluated is False
    assert result.verdict == NOT_EVALUATED
    assert result.top_segment_survives is None
    reason = str(to_metadata(result)["reason"])
    assert "beyond Poisson noise" in reason
    assert "not a passed check" in reason


def test_published_metadata_carries_the_shrinkage_block() -> None:
    """Both committed demos publish the block, verdict and all."""
    for city in ("davis", "riverside"):
        metadata = json.loads((PUBLISHED / f"{city}.metadata.json").read_text(encoding="utf-8"))
        block = metadata["shrinkage_stability"]
        assert block["evaluated"] is True
        assert block["verdict"] == STABLE
        assert block["top_segment_survives"] is True
        assert 0.0 < block["top_segment_weight"] < 1.0
        assert block["global_rate"] > 0.0


def test_the_published_rates_and_order_are_not_changed_by_the_pass(
    bundle: AnalysisBundle,
) -> None:
    """The pass reads the ranking; it must never write it.

    The Davis top segment keeps under two thirds of its own rate under
    shrinkage, so if the shrunk value ever reached the published artifact the
    GeoJSON would show it.
    """
    shrink = bundle.result.shrinkage_stability
    assert shrink is not None and shrink.baseline_top_weight is not None
    assert shrink.baseline_top_weight < 0.7  # the adjustment really would move it
    geojson = json.loads((PUBLISHED / "davis.geojson").read_text(encoding="utf-8"))
    published = {
        f["properties"]["segment_id"]: f["properties"]["rate"] for f in geojson["features"]
    }
    # Withheld segments are absent from the GeoJSON (k-anonymity); every one that
    # is published must carry the raw rate, not the shrunk one.
    checked = 0
    for stat in bundle.result.segments:
        if stat.segment_id not in published:
            continue
        assert published[stat.segment_id] == stat.rate
        checked += 1
    assert checked > 0


def test_the_standalone_note_distinguishes_every_outcome(bundle: AnalysisBundle) -> None:
    shrink = bundle.result.shrinkage_stability
    assert shrink is not None
    held = _shrinkage_note(shrink)
    assert "stays rank 1" in held

    moved = _shrinkage_note(
        dataclasses.replace(shrink, top_segment_survives=False, shrunk_top_rank=3)
    )
    assert "falls to rank 3" in moved
    assert "unchanged" in moved

    refused = _shrinkage_note(dataclasses.replace(shrink, evaluated=False))
    assert "not evaluated" in refused
    assert "Not a passed check" in refused


def test_schema_documents_every_field_the_code_publishes(bundle: AnalysisBundle) -> None:
    """The schema's §10.5 table and the emitted block must not drift apart."""
    text = SCHEMA_DOC.read_text(encoding="utf-8")
    start = text.index("### 10.5 `shrinkage_stability`")
    section = text[start : text.index("## References", start)]
    shrink = bundle.result.shrinkage_stability
    assert shrink is not None
    ran = to_metadata(shrink)
    did_not_run = to_metadata(dataclasses.replace(shrink, evaluated=False))
    for key in set(ran) | set(did_not_run):
        assert f"`{key}`" in section, f"schema §10.5 does not document {key!r}"


def test_methodology_describes_what_the_shrinkage_pass_actually_computes() -> None:
    """METHODOLOGY §5.4's claim block is checked against the code and the artifacts.

    Including the figures it quotes about the committed demos, so the paragraph
    cannot drift away from the numbers it describes.
    """
    text = METHODOLOGY.read_text(encoding="utf-8")
    start = text.index("<!-- claim:shrinkage-is-a-check-not-the-published-rate -->")
    claim = text[start : text.index("<!-- /claim:shrinkage-is-a-check-not-the-published-rate -->")]
    flat = " ".join(claim.split())

    for token in (
        "stats/shrinkage.py",
        "empirical_bayes_rates",
        "shrinkage_stability",
        "not_evaluated",
        "Marshall 1991",
    ):
        assert token in flat, f"METHODOLOGY §5.4 does not name {token!r}"

    davis = json.loads((PUBLISHED / "davis.metadata.json").read_text(encoding="utf-8"))
    block = davis["shrinkage_stability"]
    assert f"keeping `{block['top_segment_weight']}` of its own rate" in flat
    assert f"mean weight of `{block['mean_weight']}` across {block['rated_segments']}" in flat
    riverside = json.loads((PUBLISHED / "riverside.metadata.json").read_text(encoding="utf-8"))
    assert (
        f"`riverside` publishes `stable` at a mean weight of "
        f"`{riverside['shrinkage_stability']['mean_weight']}`" in flat
    )
