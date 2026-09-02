"""Significance re-decided under arbitrary dependence (RR-08).

Benjamini-Hochberg, the published correction, needs the tests to be independent
or positively regression dependent. Local Gi\\* tests on overlapping
neighbourhoods are neither. This pass re-decides under Benjamini-Yekutieli, which
holds under arbitrary dependence, and publishes how much of the significance
survives. It never changes the published decision, and the tests here hold it to
that as much as to the arithmetic.
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

from honest_rates.hotspot import benjamini_hochberg, benjamini_yekutieli, harmonic
from nearmiss.config import Config
from nearmiss.engine import AnalysisBundle, build_analysis
from nearmiss.figures import _dependence_note
from nearmiss.models import SegmentStats
from nearmiss.stats.multiplicity import (
    NOT_EVALUATED,
    NOT_ROBUST,
    ROBUST,
    dependence_robustness,
    to_metadata,
)

ROOT = Path(__file__).resolve().parents[1]
PUBLISHED = ROOT / "data" / "published"
METHODOLOGY = ROOT / "docs" / "METHODOLOGY.md"
SCHEMA_DOC = ROOT / "schema" / "dataset.schema.md"


def test_harmonic_penalty_is_the_harmonic_number() -> None:
    """The published `harmonic_penalty` has to be recomputable by hand."""
    assert harmonic(1) == 1.0
    assert harmonic(2) == 1.5
    assert abs(harmonic(12) - 3.103210678210678) < 1e-12
    assert harmonic(0) == 0.0


def test_yekutieli_rejects_a_subset_of_hochberg() -> None:
    """The comparison is only meaningful because it can only ever lose claims.

    Benjamini-Yekutieli is Benjamini-Hochberg at `alpha / c(m)` and `c(m) >= 1`,
    so its rejection set is a subset. A published cluster can be reported as
    resting on the dependence assumption; one can never be *added* here.
    """
    pvalues = {f"s{i:02d}": p for i, p in enumerate([0.001, 0.008, 0.012, 0.02, 0.3, 0.6, 0.9])}
    bh = benjamini_hochberg(pvalues, 0.05)
    by = benjamini_yekutieli(pvalues, 0.05)
    assert by <= bh
    assert by != bh  # this p-value set actually separates the two

    # The level really is alpha / c(m), not something else that happens to be smaller.
    assert by == benjamini_hochberg(pvalues, 0.05 / harmonic(len(pvalues)))


def test_single_test_is_unpenalised() -> None:
    """With one test there is no multiplicity, so `c(1) = 1` and nothing changes."""
    pvalues = {"only": 0.04}
    assert benjamini_yekutieli(pvalues, 0.05) == benjamini_hochberg(pvalues, 0.05) == {"only"}


def test_analysis_publishes_how_much_significance_is_lost(bundle: AnalysisBundle) -> None:
    """Four of the five Davis clusters rest on the independence assumption.

    That is the result worth publishing, and the reason the pass exists: a reader
    who sees five stars would otherwise read them as five independent findings.
    """
    dep = bundle.result.dependence_robustness
    assert dep is not None
    assert dep.evaluated is True
    assert dep.verdict == NOT_ROBUST
    assert dep.published_significant == 5
    assert dep.dependence_robust_significant == 1
    assert dep.tests == 12
    assert abs(dep.dependence_robust_alpha - 0.05 / harmonic(12)) < 1e-5
    # Every surviving segment is one the published dataset already flagged.
    published = {s.segment_id for s in bundle.result.segments if s.significant}
    assert set(dep.dependence_robust_segments) <= published


def test_no_significant_cluster_is_not_evaluated_never_robust(config: Config) -> None:
    """A dataset with nothing to lose has not proved its significance is robust."""
    empty: list[SegmentStats] = []
    result = dependence_robustness(empty, {"a": 0.4, "b": 0.9}, config)
    assert result.evaluated is False
    assert result.verdict == NOT_EVALUATED
    assert result.verdict != ROBUST
    assert result.dependence_robust_significant == 0
    meta = to_metadata(result)
    assert "not a passed check" in str(meta["reason"])
    # The harmonic penalty is still published, so the level is checkable either way.
    assert meta["tests"] == 2


def test_riverside_publishes_the_refusal() -> None:
    """The committed Riverside sidecar carries the unanswered question, not silence."""
    metadata = json.loads((PUBLISHED / "riverside.metadata.json").read_text(encoding="utf-8"))
    block = metadata["dependence_robustness"]
    assert block["evaluated"] is False
    assert block["verdict"] == NOT_EVALUATED
    assert "not a passed check" in block["reason"]


def test_published_metadata_carries_the_dependence_block_and_names_what_it_is_not() -> None:
    """The committed Davis sidecar publishes the loss, and says which method it used.

    RR-08 cites Caldas de Castro & Singer (2006). That method is not implemented
    here, and the artifact has to say so in the file rather than in a commit
    message a consumer will never read.
    """
    metadata = json.loads((PUBLISHED / "davis.metadata.json").read_text(encoding="utf-8"))
    block = metadata["dependence_robustness"]
    assert block["evaluated"] is True
    assert block["verdict"] == NOT_ROBUST
    assert block["published_significant"] == 5
    assert block["dependence_robust_significant"] == 1
    assert "Caldas de Castro & Singer" in block["not_implemented"]
    assert "Yekutieli" in block["not_implemented"]
    # The level is recomputable from the published fields alone.
    assert abs(block["alpha"] / block["harmonic_penalty"] - block["dependence_robust_alpha"]) < 1e-5


def test_the_published_significance_flags_are_not_changed_by_the_comparison(
    bundle: AnalysisBundle,
) -> None:
    """The pass reads `significant`; it must never write it.

    The Benjamini-Yekutieli survivors are a strict subset here, so if the pass
    ever wrote back, four Davis features would lose their star.
    """
    dep = bundle.result.dependence_robustness
    assert dep is not None
    published = {s.segment_id for s in bundle.result.segments if s.significant}
    assert len(published) == 5
    assert len(dep.dependence_robust_segments) == 1
    geojson = json.loads((PUBLISHED / "davis.geojson").read_text(encoding="utf-8"))
    flagged = {
        f["properties"]["segment_id"]
        for f in geojson["features"]
        if f["properties"]["getis_ord_significant"]
    }
    assert flagged == published


def test_the_standalone_note_distinguishes_every_outcome(bundle: AnalysisBundle) -> None:
    dep = bundle.result.dependence_robustness
    assert dep is not None
    lost = _dependence_note(dep)
    assert "1 of 5 significant cluster(s) survive" in lost
    assert "unchanged" in lost

    refused = _dependence_note(dataclasses.replace(dep, evaluated=False))
    assert "not evaluated" in refused
    assert "Not a passed check" in refused


def test_schema_documents_every_field_the_code_publishes(bundle: AnalysisBundle) -> None:
    """The schema's §10.4 table and the emitted block must not drift apart."""
    text = SCHEMA_DOC.read_text(encoding="utf-8")
    start = text.index("### 10.4 `dependence_robustness`")
    section = text[start : text.index("## References", start)]
    dep = bundle.result.dependence_robustness
    assert dep is not None
    ran = to_metadata(dep)
    did_not_run = to_metadata(dataclasses.replace(dep, evaluated=False))
    for key in set(ran) | set(did_not_run):
        assert f"`{key}`" in section, f"schema §10.4 does not document {key!r}"


def test_methodology_describes_what_the_correction_actually_computes() -> None:
    """METHODOLOGY §5.5's claim block is checked against the code and the artifacts.

    Including the part that says what is *not* implemented: RR-08 cites a method
    this project does not hold, and a paragraph that let a reader think it did
    would be the defect ADR 0017 exists to prevent.
    """
    text = METHODOLOGY.read_text(encoding="utf-8")
    start = text.index("<!-- claim:dependence-robust-fdr-published-beside-bh -->")
    claim = text[start : text.index("<!-- /claim:dependence-robust-fdr-published-beside-bh -->")]
    flat = " ".join(claim.split())

    for token in (
        "stats/multiplicity.py",
        "benjamini_yekutieli",
        "dependence_robustness",
        "getis_ord_significant",
        "not_evaluated",
        "not_implemented",
        "Caldas de Castro & Singer",
    ):
        assert token in flat, f"METHODOLOGY §5.5 does not name {token!r}"

    davis = json.loads((PUBLISHED / "davis.metadata.json").read_text(encoding="utf-8"))
    block = davis["dependence_robustness"]
    assert block["dependence_robust_significant"] == 1 and block["published_significant"] == 5
    assert "**one of the five** FDR-significant clusters survives" in flat
    assert f"level of {block['dependence_robust_alpha']:.4f} instead of {block['alpha']:g}" in flat
    assert f"across {block['tests']} simultaneous tests" in flat

    riverside = json.loads((PUBLISHED / "riverside.metadata.json").read_text(encoding="utf-8"))
    assert riverside["dependence_robustness"]["verdict"] == NOT_EVALUATED
    assert "committed `riverside`\ndemo does" in claim


def test_turning_the_level_down_cannot_add_a_published_cluster(config: Config) -> None:
    """A stricter published alpha cannot make the dependence check report more.

    The invariant is structural, not incidental: the arbitrary-dependence
    rejection set is always inside the published one, whatever `fdr_alpha` is.
    """
    for alpha in (0.01, 0.05, 0.1):
        result = build_analysis(dataclasses.replace(config, fdr_alpha=alpha)).result
        dep = result.dependence_robustness
        assert dep is not None
        published = {s.segment_id for s in result.segments if s.significant}
        assert set(dep.dependence_robust_segments) <= published
