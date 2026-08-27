"""Exposure-sensitivity: does the ranking survive a different denominator? (RR-03)

METHODOLOGY §3.3 and ADR 0002 both promise that the published ranking is re-run
"under plausible alternative denominators" and that a ranking resting on one
choice of exposure source is "reported as fragile". These tests hold the code to
that sentence, and hold the sentence to the code.

The load-bearing one is
:func:`test_no_declared_alternative_is_not_evaluated_never_stable`. The whole
design rests on the pass refusing to report success when it had nothing to test,
and a robustness check that cannot fail is worth less than no check at all.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from nearmiss.config import Config
from nearmiss.engine import AnalysisBundle, build_analysis, load_city
from nearmiss.figures import _exposure_note
from nearmiss.models import Exposure, ExposureReading, Segment, SegmentStats
from nearmiss.stats.exposure_sensitivity import (
    FRAGILE,
    NOT_EVALUATED,
    STABLE,
    ExposureSensitivity,
    exposure_sensitivity,
    to_metadata,
)

ROOT = Path(__file__).resolve().parents[1]
PUBLISHED = ROOT / "data" / "published"
METHODOLOGY = ROOT / "docs" / "METHODOLOGY.md"
SCHEMA_DOC = ROOT / "schema" / "dataset.schema.md"


# --------------------------------------------------------------------------- #
# Synthetic builders. Segments are placed far apart unless a neighbor map is
# supplied, so Gi* degeneracy is explicit rather than accidental.
# --------------------------------------------------------------------------- #
def _seg(sid: str, lat: float, lon: float = -121.7400) -> Segment:
    return Segment(id=sid, name=sid, coords=((lat, lon), (lat, lon + 0.0002)))


def _stat(
    sid: str,
    count: int,
    exposure: float,
    rate: float,
    *,
    publishable: bool = True,
    significant: bool = False,
) -> SegmentStats:
    return SegmentStats(
        segment_id=sid,
        report_count=count,
        n=count,
        exposure_estimate=exposure,
        exposure_source="test",
        exposure_date="2026-01-01",
        rate=rate,
        rate_ci_low=None,
        rate_ci_high=None,
        getis_ord_z=None,
        significant=significant,
        confidence_label="certain",
        publishable=publishable,
    )


def _exposure(sid: str, estimate: float, *alternatives: float) -> Exposure:
    return Exposure(
        segment_id=sid,
        estimate=estimate,
        source="primary-count",
        date="2026-01-01",
        tier="observed",
        sources=tuple(
            ExposureReading(estimate=a, source=f"alt-{i}", date="2026-01-01", tier="modeled")
            for i, a in enumerate(alternatives)
        ),
    )


# --------------------------------------------------------------------------- #
# The check must refuse to pass when it had nothing to test.
# --------------------------------------------------------------------------- #
def test_no_declared_alternative_is_not_evaluated_never_stable(
    bundle: AnalysisBundle, config: Config
) -> None:
    """Davis declares no corroborating exposure reading anywhere.

    The pass therefore cannot run, and must say so. The failure this test exists
    to catch is the tempting one: returning ``stable`` (or ``top_segment_survives
    = True``) because nothing moved, when nothing was moved.
    """
    exposure = load_city(config).exposure
    assert not any(e.sources for e in exposure.values()), "fixture drifted: davis gained sources"

    sens = exposure_sensitivity(bundle.result.segments, bundle.segments, exposure, config)

    assert sens.evaluated is False
    assert sens.verdict == NOT_EVALUATED
    assert sens.verdict != STABLE
    assert sens.top_segment_survives is None
    assert sens.top_segment_survives is not True
    assert sens.scenarios == ()
    assert sens.segments_with_alternatives == 0
    assert sens.alternative_coverage == 0.0
    assert sens.rated_segments > 0, "davis does rate segments; the pass had a population"

    meta = to_metadata(sens)
    assert meta["evaluated"] is False
    assert meta["top_segment_survives"] is None
    assert "unanswered question" in str(meta["reason"])


def test_the_analysis_result_carries_the_pass(bundle: AnalysisBundle) -> None:
    sens = bundle.result.exposure_sensitivity
    assert sens is not None
    assert sens.verdict == NOT_EVALUATED


def test_riverside_actually_exercises_an_alternative_denominator() -> None:
    """The other demo declares one alternative reading, and the pass uses it."""
    from nearmiss.config import load_config

    cfg = load_config(ROOT / "config" / "riverside-demo.toml")
    result = build_analysis(cfg).result
    sens = result.exposure_sensitivity
    assert sens is not None
    assert sens.evaluated is True
    assert sens.verdict == STABLE
    assert sens.segments_with_alternatives == 1
    assert sens.rated_segments == 6
    # The substitution is real: one scenario actually swapped a denominator.
    assert max(s.substituted_segments for s in sens.scenarios) == 1


# --------------------------------------------------------------------------- #
# It must be able to report fragile — for either reason.
# --------------------------------------------------------------------------- #
def _two_segment_case(
    config: Config, alt_for_top: float, *, significant: bool = False
) -> ExposureSensitivity:
    segments = [_seg("s-hot", 38.5500), _seg("s-cool", 38.6000)]
    stats = [
        _stat("s-hot", 10, 1000.0, 10.0, significant=significant),
        _stat("s-cool", 8, 1000.0, 8.0),
    ]
    exposure_map = {
        "s-hot": _exposure("s-hot", 1000.0, alt_for_top),
        "s-cool": _exposure("s-cool", 1000.0),
    }
    return exposure_sensitivity(stats, segments, exposure_map, config, k=2)


def test_a_denominator_that_flips_the_ranking_is_reported_fragile(config: Config) -> None:
    """The top segment's own second reading says its exposure is 2x larger.

    Under that denominator its rate halves and it is no longer first. That is the
    exact situation ADR 0002 says must be "reported as fragile, not as settled".
    """
    sens = _two_segment_case(config, alt_for_top=2000.0)
    assert sens.evaluated is True
    assert sens.verdict == FRAGILE
    assert sens.top_segment_survives is False
    assert sens.baseline_top_segment == "s-hot"
    high = next(s for s in sens.scenarios if s.name == "declared_high")
    assert high.baseline_top_rank == 2
    assert high.top_segment_id == "s-cool"
    # Top-k overlap is a SET measure: with two segments and k=2 both sets are the
    # same pair, so it cannot see the swap. That is precisely why the verdict
    # rests on the rank field and not on the overlap.
    assert high.topk_overlap == 1.0
    # The low scenario keeps the published denominator (it is already the minimum).
    low = next(s for s in sens.scenarios if s.name == "declared_low")
    assert low.baseline_top_rank == 1
    assert low.substituted_segments == 0


def test_a_denominator_that_does_not_flip_the_ranking_is_reported_stable(
    config: Config,
) -> None:
    """Same shape, an alternative too small to dislodge rank 1: stable."""
    sens = _two_segment_case(config, alt_for_top=1100.0)
    assert sens.verdict == STABLE
    assert sens.top_segment_survives is True
    assert all(s.baseline_top_rank == 1 for s in sens.scenarios)
    assert sens.alternative_coverage == 0.5  # 1 of 2 rated segments had an alternative


def test_losing_significance_alone_is_fragile(config: Config) -> None:
    """Rank can hold while the ★ does not, and that still counts as fragile.

    Baseline significance is read from the published dataset; the scenario's is
    recomputed by Gi*. These two segments are far apart, so no scenario can
    produce a significant cluster: a top segment that WAS starred loses it.
    """
    sens = _two_segment_case(config, alt_for_top=1100.0, significant=True)
    assert sens.baseline_top_significant is True
    assert all(s.baseline_top_rank == 1 for s in sens.scenarios)
    assert all(s.baseline_top_significant is False for s in sens.scenarios)
    assert sens.verdict == FRAGILE
    assert sens.top_segment_survives is False


def test_significance_is_only_lost_never_demanded(config: Config) -> None:
    """The mirror image, and the reason the rule is asymmetric.

    Identical inputs except the published top segment was never significant. It
    cannot be called fragile for failing to *become* a significant cluster under
    a denominator it never had, so the rank result stands on its own.
    """
    sens = _two_segment_case(config, alt_for_top=1100.0, significant=False)
    assert sens.baseline_top_significant is False
    assert all(s.baseline_top_significant is False for s in sens.scenarios)
    assert sens.verdict == STABLE


# --------------------------------------------------------------------------- #
# Alternatives are declared, never invented — and never fabricated from a
# denominator the pipeline itself would refuse.
# --------------------------------------------------------------------------- #
def test_scenario_rate_scales_exactly_with_the_declared_denominator(config: Config) -> None:
    """``rate_alt = rate * (E_base / E_alt)`` — the numerator is never touched."""
    segments = [_seg("s-a", 38.5500), _seg("s-b", 38.6000)]
    stats = [_stat("s-a", 10, 1000.0, 10.0), _stat("s-b", 1, 1000.0, 1.0)]
    exposure_map = {
        "s-a": _exposure("s-a", 1000.0, 4000.0),
        "s-b": _exposure("s-b", 1000.0),
    }
    sens = exposure_sensitivity(stats, segments, exposure_map, config, k=2)
    # 10.0 * (1000 / 4000) = 2.5, which is below s-b's 1.0? No: 2.5 > 1.0, so rank holds.
    high = next(s for s in sens.scenarios if s.name == "declared_high")
    assert high.baseline_top_rank == 1
    assert sens.verdict == STABLE
    # Push the alternative past the point where the arithmetic must flip the order.
    exposure_map["s-a"] = _exposure("s-a", 1000.0, 20000.0)  # 10.0 * 1000/20000 = 0.5 < 1.0
    flipped = exposure_sensitivity(stats, segments, exposure_map, config, k=2)
    assert flipped.verdict == FRAGILE


def test_a_reading_at_or_below_the_exposure_floor_is_not_an_alternative(
    config: Config,
) -> None:
    """A zero-exposure reading is not a denominator, so it is not an alternative.

    Using it would divide by zero, or manufacture an enormous rate from an
    estimate the pipeline itself refuses (METHODOLOGY §3.3). The pass must fall
    back to "not evaluated" rather than invent a scenario.
    """
    segments = [_seg("s-a", 38.5500), _seg("s-b", 38.6000)]
    stats = [_stat("s-a", 10, 1000.0, 10.0), _stat("s-b", 1, 1000.0, 1.0)]
    exposure_map = {
        "s-a": _exposure("s-a", 1000.0, 0.0),
        "s-b": _exposure("s-b", 1000.0),
    }
    sens = exposure_sensitivity(stats, segments, exposure_map, config, k=2)
    assert sens.verdict == NOT_EVALUATED
    assert sens.segments_with_alternatives == 0

    # And the same rule applies to a configured, non-zero floor.
    floored = replace(config, exposure_floor=500.0)
    exposure_map["s-a"] = _exposure("s-a", 1000.0, 400.0)
    sens_floored = exposure_sensitivity(stats, segments, exposure_map, floored, k=2)
    assert sens_floored.verdict == NOT_EVALUATED


def test_only_publishable_segments_are_ranked_but_all_rated_ones_count(
    config: Config,
) -> None:
    """A withheld (k-anonymity) segment is not ranked, but it is still a rated
    segment: it shapes the Gi* population and the coverage denominator, exactly
    as it does in the published analysis."""
    segments = [_seg("s-a", 38.5500), _seg("s-b", 38.6000), _seg("s-c", 38.7000)]
    stats = [
        _stat("s-a", 10, 1000.0, 10.0),
        _stat("s-b", 1, 1000.0, 1.0),
        _stat("s-c", 2, 1000.0, 99.0, publishable=False),  # withheld: highest rate, not ranked
    ]
    exposure_map = {
        "s-a": _exposure("s-a", 1000.0, 1100.0),
        "s-b": _exposure("s-b", 1000.0),
        "s-c": _exposure("s-c", 1000.0),
    }
    sens = exposure_sensitivity(stats, segments, exposure_map, config, k=3)
    assert sens.baseline_top_segment == "s-a"  # not the withheld s-c
    assert sens.rated_segments == 3
    assert sens.alternative_coverage == round(1 / 3, 4)


def test_no_publishable_rated_segment_is_not_evaluated(config: Config) -> None:
    """Alternatives with nothing to rank is still an unanswered question."""
    segments = [_seg("s-a", 38.5500)]
    stats = [_stat("s-a", 1, 1000.0, 10.0, publishable=False)]
    exposure_map = {"s-a": _exposure("s-a", 1000.0, 2000.0)}
    sens = exposure_sensitivity(stats, segments, exposure_map, config)
    assert sens.verdict == NOT_EVALUATED
    assert sens.top_segment_survives is None


def test_a_supplied_neighbor_map_drives_the_scenario_significance(config: Config) -> None:
    """Gi* is re-run on the caller's street-network neighborhoods, not re-derived.

    A planted three-segment cluster, each unit neighboring only its immediate
    chain neighbors. All three declare a denominator 30x larger, which flattens
    their rates into the background: the cluster the published dataset starred
    does not exist under that denominator, and `significance_flips` counts it.
    """
    ids = [f"s-{i}" for i in range(8)]
    segments = [_seg(sid, 38.55 + i * 0.01) for i, sid in enumerate(ids)]
    rates = [30.0, 30.0, 30.0, 1.0, 1.0, 1.0, 1.0, 1.0]
    hot = {"s-0", "s-1", "s-2"}
    stats = [
        _stat(sid, 5, 1000.0, r, significant=sid in hot) for sid, r in zip(ids, rates, strict=True)
    ]
    exposure_map = {
        sid: (_exposure(sid, 1000.0, 30000.0) if sid in hot else _exposure(sid, 1000.0))
        for sid in ids
    }
    neighbors = {
        sid: {ids[j] for j in (i - 1, i, i + 1) if 0 <= j < len(ids)} for i, sid in enumerate(ids)
    }
    sens = exposure_sensitivity(stats, segments, exposure_map, config, k=3, neighbor_map=neighbors)
    high = next(s for s in sens.scenarios if s.name == "declared_high")
    assert high.substituted_segments == 3
    assert high.baseline_top_rank == 1  # rank survives; the star does not
    assert high.baseline_top_significant is False
    assert high.significance_flips == len(hot)
    assert sens.verdict == FRAGILE
    # The low scenario is the published denominator itself: nothing substituted.
    low = next(s for s in sens.scenarios if s.name == "declared_low")
    assert low.substituted_segments == 0


# --------------------------------------------------------------------------- #
# What is published, and whether the docs describe it.
# --------------------------------------------------------------------------- #
def test_metadata_is_json_serializable_and_carries_no_geometry(config: Config) -> None:
    sens = _two_segment_case(config, alt_for_top=2000.0)
    meta = to_metadata(sens)
    text = json.dumps(meta)
    for forbidden in ("lat", "lon", "coordinates", "occurred_at", "reporter"):
        assert forbidden not in text
    assert "reason" not in meta  # only present when the pass did not run
    scenario = meta["scenarios"]
    assert isinstance(scenario, list) and len(scenario) == 2


@pytest.mark.parametrize(
    ("slug", "verdict"),
    [("davis", NOT_EVALUATED), ("riverside", STABLE)],
)
def test_published_metadata_carries_the_block(slug: str, verdict: str) -> None:
    meta = json.loads((PUBLISHED / f"{slug}.metadata.json").read_text(encoding="utf-8"))
    block = meta["exposure_sensitivity"]
    assert block["verdict"] == verdict
    if verdict == NOT_EVALUATED:
        assert block["evaluated"] is False
        assert block["top_segment_survives"] is None
        assert "reason" in block
    else:
        assert block["evaluated"] is True
        assert block["scenarios"]


def test_the_ranked_artifact_states_the_verdict_even_when_it_did_not_run() -> None:
    """A reader of the standalone ranked table must not infer a passed check from
    a missing line."""
    davis = (PUBLISHED / "davis-ranked.md").read_text(encoding="utf-8")
    riverside = (PUBLISHED / "riverside-ranked.md").read_text(encoding="utf-8")
    assert "**Exposure-sensitivity check:** not evaluated" in davis
    assert "not a passed check" in davis
    assert "**Exposure-sensitivity check:** the top-rate segment stays rank 1" in riverside


def test_ranked_note_distinguishes_all_four_outcomes(config: Config) -> None:
    """Each outcome reads differently in the artifact, because each is a different
    finding — and "did not run" is one of them, not an omission."""
    not_run = _exposure_note(exposure_sensitivity([], [], {}, config))
    assert "not evaluated" in not_run
    assert "not a passed check" in not_run

    stable = _exposure_note(_two_segment_case(config, alt_for_top=1100.0))
    assert "stays rank 1 under every alternative denominator" in stable
    assert "1 of 2 rated segments" in stable

    fell = _exposure_note(_two_segment_case(config, alt_for_top=2000.0))
    assert "falls to rank 2" in fell

    lost = _exposure_note(_two_segment_case(config, alt_for_top=1100.0, significant=True))
    assert "no longer" in lost
    assert "falls to rank" not in lost


def test_schema_documents_every_field_the_code_publishes(config: Config) -> None:
    """The schema's §10.2 table and the emitted block must not drift apart.

    A published key the contract does not describe is a number nobody can check.
    """
    text = SCHEMA_DOC.read_text(encoding="utf-8")
    start = text.index("### 10.2 `exposure_sensitivity`")
    section = text[start : text.index("## References", start)]

    ran = to_metadata(_two_segment_case(config, alt_for_top=2000.0))
    did_not_run = to_metadata(exposure_sensitivity([], [], {}, config))
    keys = set(ran) | set(did_not_run)
    for key in keys:
        assert f"`{key}`" in section, f"schema §10.2 does not document {key!r}"

    scenario = ran["scenarios"]
    assert isinstance(scenario, list)
    for key in scenario[0]:
        assert f"`{key}`" in section, f"schema §10.2 does not document scenario key {key!r}"


def test_methodology_describes_what_the_code_actually_computes() -> None:
    """The claim block in METHODOLOGY §3.3 is checked against the shipped code and
    the committed artifacts, number by number.

    This is the whole contract of the repository applied to one paragraph: a
    published number has to match what the methodology says it computes.
    """
    text = METHODOLOGY.read_text(encoding="utf-8")
    start = text.index("<!-- claim:exposure-sensitivity-declared-only -->")
    claim = text[start : text.index("<!-- /claim:exposure-sensitivity-declared-only -->")]

    # The names the code uses, not paraphrases of them.
    for token in (
        "stats/exposure_sensitivity.py",
        "declared_low",
        "declared_high",
        "not_evaluated",
        "top_segment_survives: null",
        "alternative_coverage",
        "Exposure.sources",
    ):
        assert token in claim, f"METHODOLOGY §3.3 does not name {token!r}"

    # And the two figures it quotes about the committed demos.
    riverside = json.loads((PUBLISHED / "riverside.metadata.json").read_text(encoding="utf-8"))
    block = riverside["exposure_sensitivity"]
    assert f"alternative_coverage: {block['alternative_coverage']}" in claim
    covered, rated = block["segments_with_alternatives"], block["rated_segments"]
    assert f"`{covered} of {rated} rated segments`" in claim
    assert block["verdict"] == STABLE and "publishes `stable`" in claim

    davis = json.loads((PUBLISHED / "davis.metadata.json").read_text(encoding="utf-8"))
    assert davis["exposure_sensitivity"]["verdict"] == NOT_EVALUATED
    assert "publishes `not_evaluated`" in claim
