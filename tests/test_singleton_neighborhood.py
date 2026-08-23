"""A singleton Gi* neighborhood is labeled, and can never be significant (ADR-0015).

Gi* is published as a *local* statistic — a ★ claims "hot relative to its
surroundings." With binary weights and a neighborhood of one, the Gi* denominator
collapses to ``s`` and the statistic becomes the plain global z-score
``(x_i - mean) / s``: a different question, published under the local question's
name (issue #193).

These tests pin the three things ADR-0015 decided: the degeneracy is *detected*
(including when it comes from missing values rather than missing edges), it is
*labeled* in the published quality flags, and it can never produce a ★.
"""

from __future__ import annotations

import math

from honest_rates.hotspot import (
    benjamini_hochberg,
    getis_ord_star,
    singleton_neighborhoods,
    two_sided_p,
)
from honest_rates.unit import SimpleUnit, analyze
from nearmiss.engine import AnalysisBundle
from nearmiss.stats.getis_ord import singleton_neighborhoods as reexported


def _global_z(values: dict[str, float], unit_id: str) -> float:
    """The plain global z-score of one unit against the whole value set."""
    xs = list(values.values())
    n = len(xs)
    mean = sum(xs) / n
    s = math.sqrt(sum((x - mean) ** 2 for x in xs) / n)
    return (values[unit_id] - mean) / s


# --- the algebra the whole decision rests on -------------------------------


def test_singleton_gi_star_is_algebraically_the_global_z_score() -> None:
    """The defect itself: for a lone unit, Gi* returns a global z-score.

    If this ever stops holding, the suppression below is guarding against
    something that no longer happens and the ADR needs revisiting.
    """
    values = {"a": 1.0, "b": 2.0, "c": 3.0, "lonely": 40.0}
    neighbors = {"a": {"b"}, "b": {"a", "c"}, "c": {"b"}, "lonely": set()}
    z = getis_ord_star(values, neighbors)
    assert z["lonely"] == _global_z(values, "lonely")
    # ...and a unit with real neighbors is NOT its own global z-score, so the
    # equality above is a property of the degeneracy and not of the fixture.
    assert z["b"] != _global_z(values, "b")


# --- detection --------------------------------------------------------------


def test_isolated_unit_is_reported_as_a_singleton() -> None:
    values = {"a": 1.0, "b": 2.0, "c": 3.0, "lonely": 40.0}
    neighbors = {"a": {"b"}, "b": {"a", "c"}, "c": {"b"}, "lonely": set()}
    assert singleton_neighborhoods(values, neighbors) == frozenset({"lonely"})


def test_unit_absent_from_the_neighbor_map_entirely_is_a_singleton() -> None:
    values = {"a": 1.0, "b": 2.0, "orphan": 9.0}
    neighbors = {"a": {"b"}, "b": {"a"}}  # no key for "orphan" at all
    assert "orphan" in singleton_neighborhoods(values, neighbors)


def test_unit_whose_neighbors_all_lack_values_is_effectively_a_singleton() -> None:
    """The quiet third path: structurally connected, arithmetically alone.

    ``getis_ord_star`` drops neighbor ids absent from ``values``, so a unit with
    real adjacency whose every neighbor lacks a denominator gets the same global
    z-score as a graph island. Deciding degeneracy on the neighbor map alone —
    the obvious implementation — misses this case entirely.
    """
    values = {"a": 1.0, "b": 2.0, "c": 3.0, "connected": 40.0}
    # "connected" has three real neighbors; none of them has a usable value.
    neighbors = {
        "a": {"b"},
        "b": {"a", "c"},
        "c": {"b"},
        "connected": {"no-exposure-1", "no-exposure-2", "no-exposure-3"},
    }
    assert singleton_neighborhoods(values, neighbors) == frozenset({"connected"})
    assert getis_ord_star(values, neighbors)["connected"] == _global_z(values, "connected")


def test_unit_with_one_valued_neighbor_is_not_a_singleton() -> None:
    """The boundary: one real neighbor is a (small) cluster, not a degeneracy."""
    values = {"a": 1.0, "b": 2.0, "c": 3.0, "pair": 40.0}
    neighbors = {"a": {"b"}, "b": {"a", "c"}, "c": {"b"}, "pair": {"a", "gone"}}
    assert singleton_neighborhoods(values, neighbors) == frozenset()


def test_every_unit_is_a_singleton_when_the_neighbor_map_is_empty() -> None:
    values = {"a": 1.0, "b": 2.0, "c": 3.0}
    assert singleton_neighborhoods(values, {}) == frozenset(values)


def test_no_values_means_no_singletons() -> None:
    assert singleton_neighborhoods({}, {"a": {"b"}}) == frozenset()


def test_nearmiss_stats_reexports_the_same_implementation() -> None:
    """One definition, so the dataset, MAUP, and calibration cannot drift apart."""
    assert reexported is singleton_neighborhoods


# --- suppression + labeling in the published pipeline -----------------------


def test_no_published_segment_is_both_singleton_and_significant(
    bundle: AnalysisBundle,
) -> None:
    """A ★ always means a cluster."""
    offenders = [
        s.segment_id
        for s in bundle.result.segments
        if s.significant and "singleton_neighborhood" in s.quality_flags
    ]
    assert offenders == []


def test_davis_effectively_singleton_segments_carry_the_flag(
    bundle: AnalysisBundle,
) -> None:
    """davis has no *structural* singleton — its longest segment is 178 m against a
    600 m threshold — but two of its rated segments are effectively alone because
    their neighbors have no exposure denominator. Those were publishing global
    z-scores unlabeled.
    """
    by_id = {s.segment_id: s for s in bundle.result.segments}
    flagged = {
        s.segment_id for s in bundle.result.segments if "singleton_neighborhood" in s.quality_flags
    }
    assert flagged == {"seg-03", "seg-11"}
    # The flag is additive: seg-11 keeps the low_sample flag it already carried.
    assert "low_sample" in by_id["seg-11"].quality_flags
    # ...and the planted cluster, which has real neighbors, is untouched.
    for sid in ("seg-02", "seg-05", "seg-06", "seg-07", "seg-10"):
        assert "singleton_neighborhood" not in by_id[sid].quality_flags
        assert by_id[sid].significant


def test_flagged_segments_still_publish_their_z(bundle: AnalysisBundle) -> None:
    """Labeled, not withheld — an absence rendered in place of a real number is
    this project's own dominant defect class, and the z is a real number."""
    flagged = [s for s in bundle.result.segments if "singleton_neighborhood" in s.quality_flags]
    assert flagged
    assert all(s.getis_ord_z is not None for s in flagged)


# --- the standalone library path -------------------------------------------


def _clustered_plus_one_lonely() -> tuple[list[SimpleUnit], dict[str, int], dict[str, float]]:
    """Nine units in one tight cluster, plus one isolated unit with a huge rate.

    Sized so the lonely unit's *global* z (3.0, the maximum available to a single
    outlier among ten values) clears Benjamini-Hochberg at alpha=0.05 — this is
    the case the committed city fixtures never produced, and the reason the bug
    survived 1,859 tests: a degenerate unit that WOULD be starred.
    """
    units = [SimpleUnit(f"c{i}", 38.5400 + i * 0.0002, -121.7400) for i in range(9)]
    units.append(SimpleUnit("lonely", 39.5000, -121.9000))
    counts: dict[str, int] = {f"c{i}": 1 for i in range(9)}
    counts["lonely"] = 50
    return units, counts, dict.fromkeys(counts, 100.0)


def test_a_singleton_the_fdr_would_have_starred_is_not_significant() -> None:
    """The load-bearing test. Without the ADR-0015 rule this unit is starred."""
    units, counts, exposure = _clustered_plus_one_lonely()
    rows = {r.unit_id: r for r in analyze(units, counts, exposure, band_m=300.0)}
    lonely = rows["lonely"]

    # It really would have been starred: positive z, and FDR-rejected.
    values = {r.unit_id: r.rate for r in rows.values() if r.rate is not None}
    assert lonely.getis_ord_z is not None
    assert lonely.getis_ord_z > 0.0
    assert lonely.getis_ord_z == _global_z(values, "lonely")
    assert "lonely" in benjamini_hochberg(
        {uid: two_sided_p(r.getis_ord_z or 0.0) for uid, r in rows.items()}, 0.05
    )

    # ...and it is not, because a lone unit is not a cluster.
    assert lonely.singleton_neighborhood is True
    assert lonely.significant is False
    # The z is still reported — labeled, not withheld.
    assert lonely.getis_ord_z == 3.0

    # Nothing else in the run is touched: the rule reaches exactly the degenerate
    # unit. (That real clusters keep their ★ is pinned end-to-end on the davis
    # fixture above, where five genuinely-neighbored segments stay significant.)
    for i in range(9):
        assert rows[f"c{i}"].singleton_neighborhood is False


def test_standalone_analyze_labels_a_unit_beyond_the_band() -> None:
    """``honest_rates.unit.analyze`` reaches the degeneracy through the
    straight-line band map, not a network graph: a unit farther than ``band_m``
    from every other rated unit is alone, however extreme its rate."""
    units, counts, exposure = _clustered_plus_one_lonely()
    rows = {r.unit_id: r for r in analyze(units, counts, exposure, band_m=300.0)}
    assert rows["lonely"].singleton_neighborhood is True
    for i in range(9):
        assert rows[f"c{i}"].singleton_neighborhood is False

    # Widen the band past the separation and the same unit stops being degenerate,
    # so the flag tracks the actual neighborhood rather than the unit's identity.
    wide = {r.unit_id: r for r in analyze(units, counts, exposure, band_m=200_000.0)}
    assert wide["lonely"].singleton_neighborhood is False
