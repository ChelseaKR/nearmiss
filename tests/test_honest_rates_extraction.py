"""EXP-08: nearmiss's stats modules must genuinely delegate to honest_rates,
not merely duplicate it — the whole point of the extraction is a single
source of truth for the numerical core, with nearmiss as that library's first
consumer.
"""

from __future__ import annotations

import honest_rates.geometry as hr_geometry
import honest_rates.hotspot as hr_hotspot
import honest_rates.rates as hr_rates
import honest_rates.spatial_index as hr_spatial_index
import nearmiss.geometry as nm_geometry
import nearmiss.spatial_index as nm_spatial_index
import nearmiss.stats.getis_ord as nm_getis_ord
import nearmiss.stats.rates as nm_rates


def test_nearmiss_rates_reexports_honest_rates_functions() -> None:
    assert nm_rates.poisson_ci is hr_rates.poisson_ci
    assert nm_rates.rate_with_ci is hr_rates.rate_with_ci
    assert nm_rates.wilson_ci is hr_rates.wilson_ci


def test_nearmiss_getis_ord_reexports_honest_rates_hotspot() -> None:
    assert nm_getis_ord.getis_ord_star is hr_hotspot.getis_ord_star
    assert nm_getis_ord.two_sided_p is hr_hotspot.two_sided_p
    assert nm_getis_ord.benjamini_hochberg is hr_hotspot.benjamini_hochberg


def test_nearmiss_spatial_index_reexports_honest_rates() -> None:
    assert nm_spatial_index.SpatialIndex is hr_spatial_index.SpatialIndex


def test_nearmiss_geometry_reexports_shared_functions() -> None:
    assert nm_geometry.project is hr_geometry.project
    assert nm_geometry.haversine_m is hr_geometry.haversine_m
    assert nm_geometry.projection_margin_m is hr_geometry.projection_margin_m


def test_honest_rates_has_no_import_of_nearmiss() -> None:
    """The library must be genuinely standalone: no module inside it may ever
    import nearmiss. This is the concrete check behind the "usable on any
    point-event dataset" README claim -- a static source scan, not just an
    absence-of-crash smoke test, so it catches the import even if no test
    happens to exercise the code path that would use it."""
    import ast
    import importlib
    import pathlib

    package = importlib.import_module("honest_rates")
    assert package.__file__ is not None
    pkg_dir = pathlib.Path(package.__file__).parent
    for py_file in pkg_dir.rglob("*.py"):
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert not alias.name.startswith("nearmiss"), py_file
            elif isinstance(node, ast.ImportFrom):
                assert not (node.module or "").startswith("nearmiss"), py_file
