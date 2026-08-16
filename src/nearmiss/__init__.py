"""nearmiss — an open dataset and statistically honest analysis of road hazards.

The package is organized as a sequence of pure, recorded transforms:

    intake -> pipeline (dedupe, geocode, snap, classify, quality)
           -> exposure -> stats (rates, bias, kde, getis_ord)
           -> publish -> brief -> server

Each stage consumes and emits plain, inspectable data structures (see
:mod:`nearmiss.models`), so any stage can be tested, piped, or replaced
independently. Nothing in the public path emits a precise raw report.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

__all__ = ["__version__"]

try:
    # Single source of truth: derived from the installed distribution metadata
    # (itself built from `version` in pyproject.toml), not a hand-duplicated
    # literal (REL-02). The distribution is `nearmiss-safety` because the PyPI
    # name `nearmiss` belongs to an unrelated project; the import package and
    # the installed command are both still `nearmiss`.
    __version__ = version("nearmiss-safety")
except PackageNotFoundError:
    # Not installed (e.g. a source checkout with no editable install yet) —
    # fall back so `import nearmiss` still works for local tooling and tests.
    __version__ = "0.4.0"
