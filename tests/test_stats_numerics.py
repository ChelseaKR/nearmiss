"""Exact-value guards for the spatial-statistics core (mutation-hardening).

The known-answer fixtures in ``test_hotspot.py`` prove the *pipeline* recovers the
planted hotspot, but they only pin coarse properties (seg-06 is the hottest and
significant). Advisory mutation testing (``make mutation``, backlog #15) showed
that lets whole classes of silent numerical bugs survive inside
:func:`nearmiss.stats.getis_ord.getis_ord_star` — a flipped sign in the Gi*
numerator, a ``*``/``/`` slip in the standard-error denominator, an ``n - 1`` ->
``n + 1`` off-by-one in the variance term — because they perturb the z-scores
without changing the ranking.

These tests close that gap by pinning the Gi* z-scores of a tiny, fully
hand-computable arrangement to their exact closed-form values, and by nailing the
degenerate branches and the FDR ranking. See docs/MUTATION-TESTING.md.
"""

from __future__ import annotations

import math

import pytest

from nearmiss.stats.getis_ord import benjamini_hochberg, getis_ord_star


def test_getis_ord_star_pins_exact_zscores() -> None:
    """Gi* z-scores match the exact closed form on a hand-computable layout.

    Two hot neighbours (A, B ~222 m apart) and two distant cold neighbours
    (C, D ~111 km away, ~222 m apart) with a 300 m band. In/out-of-band membership
    is unambiguous and the weights are binary, so the statistic is exactly solvable:

        n = 4,  mean = 5,  s = 5;
        every segment neighbours exactly its own pair (w_sum = w2_sum = 2), so the
        standardization factor is (n*w2_sum - w_sum^2)/(n-1) = 4/3 (deliberately
        NOT 1, so a ``*``/``/`` slip in the standard error cannot hide);
        z_A = z_B = +sqrt(3);  z_C = z_D = -sqrt(3).

    This single assertion kills the numerator sign flip, the denominator ``*``/``/``
    swap, the ``(n - 1)`` off-by-one, and the mean/variance mutants.
    """
    values = {"A": 10.0, "B": 10.0, "C": 0.0, "D": 0.0}
    centroids = {
        "A": (0.0, 0.0),
        "B": (0.0, 0.002),
        "C": (0.0, 1.0),
        "D": (0.0, 1.002),
    }

    z = getis_ord_star(values, centroids, band_m=300.0)

    assert z["A"] == pytest.approx(math.sqrt(3.0), abs=1e-9)
    assert z["B"] == pytest.approx(math.sqrt(3.0), abs=1e-9)
    assert z["C"] == pytest.approx(-math.sqrt(3.0), abs=1e-9)
    assert z["D"] == pytest.approx(-math.sqrt(3.0), abs=1e-9)
    # The hot pair is strictly positive and the cold pair strictly negative:
    # a numerator sign flip would not preserve this opposition.
    assert z["A"] > 0.0 > z["C"]


def test_getis_ord_star_boundary_and_degenerate_inputs() -> None:
    """The n == 3 boundary computes; undefined cases return exactly 0.0 for every id."""
    # Exactly three segments is the MINIMUM that standardizes (guard is `n < 3`),
    # and it must still produce a real hotspot, not silently collapse to zeros.
    # Same geometry as above minus D: A,B neighbour each other, C is isolated ->
    # z_A = z_B = +sqrt(2), z_C = -sqrt(2). Kills the `n < 3` -> `n <= 3` off-by-one.
    three = getis_ord_star(
        {"A": 10.0, "B": 10.0, "C": 0.0},
        {"A": (0.0, 0.0), "B": (0.0, 0.002), "C": (0.0, 1.0)},
        band_m=300.0,
    )
    assert three["A"] == pytest.approx(math.sqrt(2.0), abs=1e-9)
    assert three["C"] == pytest.approx(-math.sqrt(2.0), abs=1e-9)

    # Fewer than three segments -> no stable standardization -> 0.0 (never None).
    two = getis_ord_star({"A": 1.0, "B": 9.0}, {"A": (0.0, 0.0), "B": (0.0, 0.002)}, band_m=300.0)
    assert two == {"A": 0.0, "B": 0.0}

    # Zero spatial variance (all values identical) -> s == 0 -> 0.0 everywhere.
    centroids = {"A": (0.0, 0.0), "B": (0.0, 0.002), "C": (0.0, 1.0)}
    flat = getis_ord_star({"A": 5.0, "B": 5.0, "C": 5.0}, centroids, band_m=300.0)
    assert flat == {"A": 0.0, "B": 0.0, "C": 0.0}


def test_benjamini_hochberg_ranks_by_pvalue_and_handles_edges() -> None:
    """FDR rejection is by p-value rank, with correct empty/singleton behaviour."""
    # A single clearly significant test is rejected (m == 1 path).
    assert benjamini_hochberg({"only": 0.001}, 0.05) == {"only"}

    # Nothing clears its rank-adjusted threshold -> empty set, not a partial reject
    # and not an error (guards the loop's initial threshold_rank == 0).
    assert benjamini_hochberg({"a": 0.9, "b": 0.95}, 0.05) == set()

    # Ordering is by p-value, NOT by key/insertion order: the significant id wins
    # even though it sorts LAST alphabetically.
    assert benjamini_hochberg({"z": 0.001, "a": 0.5}, 0.05) == {"z"}
