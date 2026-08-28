"""Every published statistic says what the documents say it says.

This is the repository's own contract turned into a gate. `METHODOLOGY.md` and
`schema/dataset.schema.md` describe, in the present tense, how each published
number is computed; a reader who checks a claim has no way to know the code
stopped matching the sentence. The tests here read the **committed artifacts**
and the **committed prose** at test time and check them against each other, in
the pattern
`tests/test_exposure_sensitivity.py::test_methodology_describes_what_the_code_actually_computes`
established when the exposure-sensitivity pass landed.

The four properties checked correspond to the four defects of that class found
in the 0.4.0 tree: the per-hazard-type intervals that never inherited the
overdispersion widening, the MAUP coarse rate built from a numerator the
published rate does not use, the brief that reported a fallen rank as a held
one, and the bias audit whose top three were chosen before the k-anonymity
filter.
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import Any

import pytest

from nearmiss.config import Config
from nearmiss.engine import AnalysisBundle
from nearmiss.figures import _stability_note
from nearmiss.models import Segment
from nearmiss.stats.bias import to_metadata as bias_to_metadata
from nearmiss.stats.maup import (
    NO_RATED_UNIT,
    RANK_FELL,
    RANK_HELD_SIGNIFICANCE_LOST,
    SURVIVES,
    RankStability,
    _pair_segments,
    stability_outcome,
)

ROOT = Path(__file__).resolve().parents[1]
PUBLISHED = ROOT / "data" / "published"
METHODOLOGY = ROOT / "docs" / "METHODOLOGY.md"
SCHEMA_DOC = ROOT / "schema" / "dataset.schema.md"
CITIES = ("davis", "riverside")


def _artifacts(city: str) -> tuple[Any, Any]:
    geojson = json.loads((PUBLISHED / f"{city}.geojson").read_text(encoding="utf-8"))
    metadata = json.loads((PUBLISHED / f"{city}.metadata.json").read_text(encoding="utf-8"))
    return geojson, metadata


def _claim(doc: Path, claim_id: str) -> str:
    text = doc.read_text(encoding="utf-8")
    start = text.index(f"<!-- claim:{claim_id} -->")
    return text[start : text.index(f"<!-- /claim:{claim_id} -->")]


@pytest.mark.parametrize("city", CITIES)
def test_published_maup_block_ranks_the_units_the_published_rates_imply(city: str) -> None:
    """The committed coarse ranking is reproducible from the committed rates.

    `schema/dataset.schema.md` §10.1 says a coarse unit's rate is the sum of its
    members' primary counts over the sum of their exposures. The published
    per-feature `rate` *is* the primary count over that feature's exposure, so a
    reader with only the GeoJSON can rebuild every coarse rate and check the
    sidecar's `top_hotspot_coarse_rank` against it. That is done here from the
    files alone: the pairing, the numerator and the denominator all come back out
    of the published artifact, so a coarse rate quietly built from a different
    count would show up as a different rank.
    """
    geojson, metadata = _artifacts(city)
    block = metadata["maup_rank_stability"]
    assert isinstance(block, dict)
    top = block["top_hotspot_segment"]
    if top is None:  # pragma: no cover - both committed demos rate a top segment
        pytest.skip("no rated top segment in this dataset")

    features = [f for f in geojson["features"] if isinstance(f, dict)]
    segments = [
        Segment(
            id=f["properties"]["segment_id"],
            name=f["properties"]["segment_id"],
            coords=tuple((lat, lon) for lon, lat in f["geometry"]["coordinates"]),
        )
        for f in features
    ]
    coarse_of = _pair_segments(segments)

    # count_primary = rate * exposure / rate_per, recovered from the published pair.
    per = metadata["methods"]["rate_per"]
    numerator: dict[int, float] = {}
    denominator: dict[int, float] = {}
    floor = metadata["methods"]["exposure_floor"]
    for f in features:
        props = f["properties"]
        exposure, rate = props["exposure_estimate"], props["rate"]
        if exposure is None or rate is None or exposure <= floor:
            continue
        unit = coarse_of[props["segment_id"]]
        numerator[unit] = numerator.get(unit, 0.0) + rate * exposure / per
        denominator[unit] = denominator.get(unit, 0.0) + exposure

    coarse_rate = {u: numerator[u] / denominator[u] * per for u in denominator}
    ranked = sorted(coarse_rate, key=lambda u: coarse_rate[u], reverse=True)
    expected_rank = ranked.index(coarse_of[top]) + 1
    assert block["top_hotspot_coarse_rank"] == expected_rank, (
        f"{city}: the sidecar's coarse rank does not match the rank the published "
        "rates imply, so the coarse units were rated on a different numerator"
    )


def test_published_bias_audit_is_the_top_of_the_publishable_ranking(
    bundle: AnalysisBundle,
) -> None:
    """The committed bias block names as many segments as the ranking can fill.

    `schema/dataset.schema.md` §2 calls this block "the reporting-bias audit over
    publishable segment ids" and METHODOLOGY §6.2 says the k-anonymity filter runs
    before the top-three cut. Both are checked against the committed artifact: the
    published lists must be exactly the recomputed publishable top three, which is
    only true if the filter precedes the cut.
    """
    metadata: Any = json.loads((PUBLISHED / "davis.metadata.json").read_text(encoding="utf-8"))
    publishable = {s.segment_id for s in bundle.result.segments if s.publishable}
    expected = bias_to_metadata(bundle.result.bias, publishable)
    assert metadata["bias"] == expected

    published_over = expected["over_represented"]
    assert isinstance(published_over, list)
    eligible = [
        f
        for f in bundle.result.bias.findings
        if f.over_representation > 0 and f.segment_id in publishable
    ]
    assert len(published_over) == min(3, len(eligible))


def test_methodology_binds_the_widening_to_the_per_type_layers() -> None:
    """METHODOLOGY §4's absolute claim names the artifact it is absolute about.

    "Widens every published interval" was true of the pooled interval and false of
    the type layers for as long as the sentence stood. The claim block now names
    `rates_by_type` and its witness, so the sentence and the code are checked
    together by `make claims` rather than only by a reader's goodwill.
    """
    claim = _claim(METHODOLOGY, "overdispersion-widens-every-published-interval")
    for token in (
        "rates_by_type",
        "overdispersion_adjust",
        "quasi_poisson_ci",
        "test_per_hazard_type_intervals_are_widened_too",
    ):
        assert token in claim, f"METHODOLOGY §4 does not name {token!r}"


def test_methodology_states_what_the_maup_check_holds_fixed() -> None:
    """METHODOLOGY §8.3 names the numerator, the floor, and the two failure modes.

    The re-segmentation check is only a MAUP result if the units are the only
    thing that moved, so the paragraph has to say which numerator and which
    exposure rule the coarse units use, and it has to say that
    `top_hotspot_survives` collapses two different findings.
    """
    claim = _claim(METHODOLOGY, "maup-varies-only-the-units")
    for token in (
        "primary",
        "exposure_floor",
        "rank_stability",
        "stability_outcome",
        "top_hotspot_survives",
    ):
        assert token in claim, f"METHODOLOGY §8.3 does not name {token!r}"
    assert "primary counts as a required argument" in claim


def _stability(
    *,
    top_hotspot_id: str | None = "seg-01",
    survives: bool = False,
    coarse_rank: int | None = 1,
    still_significant: bool = False,
) -> RankStability:
    return RankStability(
        fine_units=10,
        coarse_units=5,
        k=5,
        top_hotspot_id=top_hotspot_id,
        top_hotspot_survives=survives,
        top_hotspot_coarse_rank=coarse_rank,
        top_hotspot_still_significant=still_significant,
        topk_overlap=0.5,
    )


def test_both_maup_renderers_agree_on_which_outcome_happened(
    bundle: AnalysisBundle, config: Config
) -> None:
    """The brief and the standalone ranked table describe the same result the same way.

    They are two renderings of one `RankStability` read by different audiences,
    and they disagreed: `figures._stability_note` distinguished a fallen rank from
    a lost significance, and the brief called both "stays the highest-rate unit".
    Both now switch on `maup.stability_outcome`, so this walks the four outcomes
    and asserts neither renderer claims a rank the result does not have.
    """
    from nearmiss.brief import render_brief

    cases = {
        SURVIVES: _stability(survives=True, still_significant=True),
        RANK_HELD_SIGNIFICANCE_LOST: _stability(),
        RANK_FELL: _stability(coarse_rank=3),
        NO_RATED_UNIT: _stability(top_hotspot_id=None),
    }
    for expected_outcome, stability in cases.items():
        assert stability_outcome(stability) == expected_outcome
        note = _stability_note(stability)
        doctored = dataclasses.replace(
            bundle,
            result=dataclasses.replace(bundle.result, rank_stability=stability),
        )
        brief = render_brief(doctored, config, "en")
        held_rank_1 = expected_outcome in (SURVIVES, RANK_HELD_SIGNIFICANCE_LOST)
        assert ("stays rank 1" in note) is held_rank_1
        assert ("the highest-rate" in brief) is held_rank_1
        if expected_outcome == RANK_FELL:
            assert "falls to rank 3" in note
            assert "falls to rank 3" in brief
