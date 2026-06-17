# 3. Pure-Python statistics and a local planar projection

Date: 2026-06-16

## Status

Accepted

## Context

The product is a dataset and an analysis that an advocacy group with no budget
can run, that a skeptic can reproduce, and that a contributor can read and check.
That argues for the implementation to be trivially installable, deterministic,
and fully type-checked — and to avoid anything that makes "it didn't install"
the first experience.

The two places where a geospatial project usually reaches for heavy dependencies
are (a) geometry — projecting coordinates and snapping points to street segments
— and (b) the statistics — confidence intervals, kernel density, and the
Getis-Ord Gi\* local hotspot statistic. The usual stack is `numpy` + `shapely` +
`pyproj`. Those pull native wheels, add build and CI friction, are noisier under
`mypy --strict`, and are overkill for a single city's worth of segments (hundreds
to low thousands), which is small enough to compute in plain Python.

## Decision

Implement the geometry and the statistics in **pure, typed standard-library
Python**. The only runtime dependency is `jsonschema`, used to validate reports
at intake against the published schema.

- **Geometry** uses a local **equirectangular projection** about a reference
  latitude to convert coordinates to metres, then plain point-to-polyline
  distance for snapping (`src/nearmiss/geometry.py`).
- **Statistics** are closed-form and deterministic: a **Byar approximation** to
  the Poisson confidence interval (well behaved down to a count of zero), the
  **Wilson** score interval for proportions, a Gaussian **KDE** over a grid, and
  the **Getis-Ord Gi\*** z-score computed on the exposure-normalized rate
  (`src/nearmiss/stats/`).

## Consequences

- **Positive.** `pip install` needs no compiler and no native geospatial stack;
  the analysis runs anywhere Python 3.11+ runs. Runs are deterministic, so
  `make reproduce` is byte-for-byte meaningful. The code is `mypy --strict`
  clean. Contributors can read every statistic without a numerical-computing
  background.
- **Negative / accepted limits.** The equirectangular projection is an
  approximation; it is accurate to well within the precision this analysis needs
  at city scale, and the assumption and its limits are documented in
  `docs/METHODOLOGY.md`. Pure-Python loops are slower than vectorized `numpy`;
  this is irrelevant at a city's data volume and is not yet benchmarked.

## Alternatives considered

- **`numpy` + `shapely` + `pyproj`.** Rejected for now: native-wheel and
  `mypy` friction, and dependency weight, for no benefit at this scale. This ADR
  would be revisited if nearmiss needs geodesic precision, very large regions, or
  many cities at once.
- **PostGIS / a spatial database.** Rejected: an always-on server dependency
  contradicts the scale-to-zero, run-anywhere, zero-cost goal.
