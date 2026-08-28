"""Gi\\* significance re-tested against a conditional-permutation reference (RR-09).

The published significance decision is the analytic normal-approximation z-score
with a Benjamini-Hochberg correction. This pass reads the same statistic against
an empirical reference built by re-shuffling the rates, and publishes the
disagreement without changing the published flag. The tests here hold it to the
three things that make such a pass worth publishing: it recovers a planted
cluster, it refuses to run rather than reporting a pass it did not earn, and it
is deterministic enough for `make reproduce`.
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest

from honest_rates.hotspot import conditional_permutation_p, getis_ord_star, two_sided_p
from nearmiss.config import Config
from nearmiss.engine import AnalysisBundle, build_analysis
from nearmiss.figures import _permutation_note
from nearmiss.models import SegmentStats
from nearmiss.stats.gi_permutation import (
    CORROBORATED,
    NOT_CORROBORATED,
    NOT_EVALUATED,
    permutation_inference,
    to_metadata,
)

ROOT = Path(__file__).resolve().parents[1]
PUBLISHED = ROOT / "data" / "published"


def _line_values(hot: float, cold: float, n: int = 24) -> dict[str, float]:
    """A chain of units where the first three are hot and the rest are cold."""
    return {f"u{i:02d}": (hot if i < 3 else cold) for i in range(n)}


def _chain_neighbors(n: int = 24) -> dict[str, set[str]]:
    return {f"u{i:02d}": {f"u{j:02d}" for j in (i - 1, i + 1) if 0 <= j < n} for i in range(n)}


def test_planted_cluster_is_extreme_under_the_permutation_reference() -> None:
    """The unit inside a planted cluster is rare in its own reference distribution.

    Nothing about a pseudo p-value is meaningful unless it can recover a cluster
    that is really there. `u01` sits in the middle of three adjacent hot units in
    a field of cold ones; `u12` sits in the cold field.
    """
    values, neighbors = _line_values(10.0, 1.0), _chain_neighbors()
    p = conditional_permutation_p(values, neighbors, ["u01", "u12"], 999, seed=1)
    assert p["u01"] <= 0.01
    assert p["u12"] > 0.05
    # It is answering about the same statistic the published z-score reports.
    z = getis_ord_star(values, neighbors)
    assert z["u01"] > 0 and two_sided_p(z["u01"]) < 0.05


def test_pseudo_p_is_deterministic_and_never_zero() -> None:
    """`make reproduce` needs the same bytes twice, and a p-value of 0 is a lie.

    The reference draws are seeded per unit, so the answer does not depend on
    iteration order, and the observed arrangement counts as one of its own
    draws, so the smallest reportable value is 1/(permutations+1).
    """
    values, neighbors = _line_values(10.0, 1.0), _chain_neighbors()
    ids = sorted(values)
    first = conditional_permutation_p(values, neighbors, ids, 199, seed=7)
    second = conditional_permutation_p(values, neighbors, list(reversed(ids)), 199, seed=7)
    assert first == second
    assert min(first.values()) >= 1.0 / 200
    # A different seed is allowed to differ; the point is that each is stable.
    assert conditional_permutation_p(values, neighbors, ids, 199, seed=8) != first


def test_singleton_neighborhoods_are_omitted_not_reported_as_passing() -> None:
    """ADR-0015: Gi* on a lone unit is a global z, so it has no cluster to test.

    Such a unit must be absent from the result rather than carrying a p-value a
    caller could read as corroboration.
    """
    values = {"a": 5.0, "b": 1.0, "c": 1.0, "d": 1.0}
    neighbors: dict[str, set[str]] = {"a": set(), "b": {"c"}, "c": {"b"}, "d": set()}
    p = conditional_permutation_p(values, neighbors, sorted(values), 99, seed=1)
    assert "a" not in p and "d" not in p
    assert "b" in p and "c" in p


def test_permutation_count_must_be_positive() -> None:
    values, neighbors = _line_values(10.0, 1.0), _chain_neighbors()
    with pytest.raises(ValueError):
        conditional_permutation_p(values, neighbors, ["u01"], 0, seed=1)


def test_analysis_publishes_the_permutation_result(bundle: AnalysisBundle) -> None:
    """The Davis fixture's planted clusters are re-tested, and not all of them hold.

    This is the result worth having: three of the five clusters the analytic test
    flags do not clear the level against their own empirical reference. The
    published `significant` flags are unchanged by that, which is checked here so
    the pass can never quietly become the decision.
    """
    perm = bundle.result.gi_permutation
    assert perm is not None
    assert perm.evaluated is True
    assert perm.verdict == NOT_CORROBORATED
    assert perm.published_significant_tested == 5
    assert perm.unsupported_segments == 3
    published_significant = {s.segment_id for s in bundle.result.segments if s.significant}
    assert {s.segment_id for s in perm.segments if s.published_significant} == published_significant


def test_a_refused_pass_never_reports_corroboration(config: Config) -> None:
    """Two refusals, and neither may read as a pass.

    A pseudo p-value cannot go below 1/(permutations+1). With too few
    permutations the empirical test could not detect significance even in
    principle, so the pass must decline rather than report that nothing
    disagreed. The same applies when no segment has a testable neighbourhood.
    """
    too_few = dataclasses.replace(config, gi_permutations=5)  # 1/6 > 0.05
    stats: list[SegmentStats] = []
    refused = permutation_inference(stats, {}, {}, too_few)
    assert refused.evaluated is False
    assert refused.verdict == NOT_EVALUATED
    assert refused.tested_segments == 0
    assert "could not have detected significance" in str(to_metadata(refused)["reason"])

    nothing_testable = permutation_inference([], {}, {}, config)
    assert nothing_testable.verdict == NOT_EVALUATED
    assert "not a passed check" in str(to_metadata(nothing_testable)["reason"])
    assert to_metadata(nothing_testable)["verdict"] != CORROBORATED


def test_riverside_cannot_run_the_check_and_says_so() -> None:
    """Every Riverside segment is a Gi* singleton, so there is nothing to re-test.

    The committed artifact publishes that as `not_evaluated` with a reason,
    rather than omitting the block, so a reader comparing the two demos sees an
    unanswered question rather than an absence.
    """
    metadata = json.loads((PUBLISHED / "riverside.metadata.json").read_text(encoding="utf-8"))
    block = metadata["gi_permutation"]
    assert block["evaluated"] is False
    assert block["verdict"] == NOT_EVALUATED
    assert block["tested_segments"] == 0
    assert "not a passed check" in block["reason"]
    assert "top_segment_survives" not in block  # not this artifact's vocabulary


def test_published_metadata_carries_the_permutation_block() -> None:
    """The committed Davis sidecar publishes the disagreement, not only the pass.

    A robustness check whose result is only published when it passes is not a
    robustness check, so the number that does not flatter the dataset has to be
    in the file.
    """
    metadata = json.loads((PUBLISHED / "davis.metadata.json").read_text(encoding="utf-8"))
    block = metadata["gi_permutation"]
    assert block["evaluated"] is True
    assert block["verdict"] == NOT_CORROBORATED
    assert block["unsupported_segments"] > 0
    assert block["permutations"] == 999
    # Every tested segment carries both p-values, so a reader can check the verdict.
    for entry in block["segments"]:
        assert set(entry) == {
            "segment_id",
            "published_significant",
            "analytic_p",
            "permutation_p",
            "agrees",
        }


def test_the_published_significance_flags_are_not_changed_by_the_pass(config: Config) -> None:
    """Turning the permutation count up and down must not move a published flag.

    The pass reads `significant`; it must never write it. If it ever did, the
    published dataset would depend on a Monte Carlo seed.
    """
    base = build_analysis(config)
    other = build_analysis(dataclasses.replace(config, gi_permutations=199, gi_permutation_seed=42))
    assert {s.segment_id: s.significant for s in base.result.segments} == {
        s.segment_id: s.significant for s in other.result.segments
    }
    assert {s.segment_id: s.rate_ci_high for s in base.result.segments} == {
        s.segment_id: s.rate_ci_high for s in other.result.segments
    }
    # ...and the robustness verdict itself is allowed to move with the count.
    assert other.result.gi_permutation is not None
    assert other.result.gi_permutation.permutations == 199


def test_the_standalone_note_distinguishes_every_outcome(bundle: AnalysisBundle) -> None:
    """Each outcome reads differently, because each is a different finding."""
    perm = bundle.result.gi_permutation
    assert perm is not None
    disagreed = _permutation_note(perm)
    assert "do not clear" in disagreed
    assert "unchanged" in disagreed

    agreed = _permutation_note(dataclasses.replace(perm, unsupported_segments=0))
    assert "also clear" in agreed

    no_claims = _permutation_note(dataclasses.replace(perm, published_significant_tested=0))
    assert "no significance claim to corroborate" in no_claims

    refused = _permutation_note(dataclasses.replace(perm, evaluated=False))
    assert "not evaluated" in refused
    assert "Not a passed check" in refused


SCHEMA_DOC = ROOT / "schema" / "dataset.schema.md"
METHODOLOGY = ROOT / "docs" / "METHODOLOGY.md"


def test_schema_documents_every_field_the_code_publishes(bundle: AnalysisBundle) -> None:
    """The schema's §10.3 table and the emitted block must not drift apart.

    A published key the contract does not describe is a number nobody can check.
    """
    text = SCHEMA_DOC.read_text(encoding="utf-8")
    start = text.index("### 10.3 `gi_permutation`")
    section = text[start : text.index("## References", start)]

    perm = bundle.result.gi_permutation
    assert perm is not None
    ran = to_metadata(perm)
    did_not_run = to_metadata(dataclasses.replace(perm, evaluated=False, segments=()))
    for key in set(ran) | set(did_not_run):
        assert f"`{key}`" in section, f"schema §10.3 does not document {key!r}"
    segments = ran["segments"]
    assert isinstance(segments, list)
    for key in segments[0]:
        assert f"`{key}`" in section, f"schema §10.3 does not document segment key {key!r}"


def test_methodology_describes_what_the_permutation_pass_actually_computes() -> None:
    """METHODOLOGY §8.2's claim block is checked against the code and the artifacts.

    The paragraph it replaced said a conditional-permutation reference "is **not**
    what is computed today", which was true. The paragraph that replaces it says
    what does run, and the figures it quotes about the committed demos are checked
    against those demos here, number by number.
    """
    text = METHODOLOGY.read_text(encoding="utf-8")
    start = text.index("<!-- claim:gi-permutation-beside-not-instead -->")
    claim = text[start : text.index("<!-- /claim:gi-permutation-beside-not-instead -->")]

    for token in (
        "stats/gi_permutation.py",
        "conditional_permutation_p",
        "gi_permutation",
        "getis_ord_significant",
        "not_evaluated",
        "1 / (m + 1)",
        "ADR-0015",
    ):
        assert token in claim, f"METHODOLOGY §8.2 does not name {token!r}"

    # Line wrapping is not part of the claim, so compare on normalised whitespace.
    flat = " ".join(claim.split())
    davis = json.loads((PUBLISHED / "davis.metadata.json").read_text(encoding="utf-8"))
    block = davis["gi_permutation"]
    assert block["unsupported_segments"] == 3 and block["published_significant_tested"] == 5
    assert "three of the five FDR-significant clusters do **not** clear" in flat

    riverside = json.loads((PUBLISHED / "riverside.metadata.json").read_text(encoding="utf-8"))
    assert riverside["gi_permutation"]["verdict"] == NOT_EVALUATED
    assert "`riverside` demo every segment is such a singleton" in flat


def test_the_permutation_seed_and_count_are_live_config_not_decoration(config: Config) -> None:
    """Both new config keys change the artifact, so neither is a dead knob."""
    base = build_analysis(config).result.gi_permutation
    fewer = build_analysis(dataclasses.replace(config, gi_permutations=199)).result.gi_permutation
    reseeded = build_analysis(
        dataclasses.replace(config, gi_permutation_seed=99)
    ).result.gi_permutation
    assert base is not None and fewer is not None and reseeded is not None
    assert fewer.permutations == 199 and base.permutations == 999
    assert reseeded.seed == 99
    base_p = {s.segment_id: s.permutation_p for s in base.segments}
    assert {s.segment_id: s.permutation_p for s in reseeded.segments} != base_p
