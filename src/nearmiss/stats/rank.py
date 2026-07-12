"""Spearman rank correlation.

Pure Python, per ADR-0003 (no numpy/scipy dependency). Used by
:mod:`nearmiss.preregister` to compare the rank order of a pre-registered
corridor's predicted rate against its held-out observed rate — a scale-free
companion to the hit-rate metric that survives even if the two periods' raw
rates aren't directly comparable.
"""

from __future__ import annotations


def _ranks(values: list[float]) -> list[float]:
    """Fractional (average) ranks, 1-indexed, tie-safe.

    Ties share the mean of the ranks they would otherwise occupy, the standard
    treatment for Spearman's rho with tied observations.
    """
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        avg_rank = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[order[k]] = avg_rank
        i = j + 1
    return ranks


def spearman_rho(x: list[float], y: list[float]) -> float | None:
    """Spearman's rank correlation coefficient between two equal-length samples.

    Returns ``None`` (rather than 0.0 or NaN) when the coefficient is
    undefined: fewer than 2 points, or either series has zero rank variance
    (every value tied) — a null result should read as "undefined", not as "no
    correlation".
    """
    n = len(x)
    if n != len(y):
        raise ValueError("x and y must have the same length")
    if n < 2:
        return None
    rx = _ranks(x)
    ry = _ranks(y)
    mean_rx = sum(rx) / n
    mean_ry = sum(ry) / n
    cov = sum((a - mean_rx) * (b - mean_ry) for a, b in zip(rx, ry, strict=True))
    var_x = sum((a - mean_rx) ** 2 for a in rx)
    var_y = sum((b - mean_ry) ** 2 for b in ry)
    if var_x == 0.0 or var_y == 0.0:
        return None
    return float(cov / (var_x * var_y) ** 0.5)
