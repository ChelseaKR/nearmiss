"""The wheel must ship the schemas it reads at runtime.

Every release through 0.3.0 built cleanly, installed cleanly, and then raised
``could not locate schema/report.schema.json`` on the first report validation:
``find_report_schema`` walked up from ``__file__`` to the repository root,
which exists in a source checkout and does not exist under site-packages.
Nothing caught it because nothing had ever installed the built artifact.

**The guard on the wheel test had the same shape as the bug it guards.** It read
``pytest.importorskip("build")``, and this repository's own output directory is
``build/`` — the tree that ``make demo``, ``make reproduce`` and ``make i18n-pseudo``
write into. Python 3 makes any directory on ``sys.path`` an importable *namespace*
package, so on a tree where any of those has run, ``import build`` succeeds while
PyPI's ``build`` is absent. The observed consequence was that ``make verify`` passed on
a clean checkout and failed on the very next run of the same command:

* first run: no ``build/`` yet, so the guard skipped and the wheel was never built;
  later in the same ``verify``, ``i18n-pseudo`` created ``build/``;
* second run: the guard now "passed" on the output directory and the test ran
  ``python -m build``, which reported
  ``No module named build.__main__; 'build' is a package and cannot be directly executed``.

So the assertion that a release ships its schema had, in a normal local checkout, either
not run at all or failed for a reason with nothing to do with packaging.
:func:`build_backend_available` now asks for the installed *distribution*, which a
directory cannot satisfy, and :func:`test_the_skip_guard_is_not_satisfied_by_the_output
_directory` holds it to that.
"""

from __future__ import annotations

import importlib.metadata
import importlib.util
import subprocess
import sys
import tomllib
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BUILD_OUTPUT_DIR = ROOT / "build"


def build_backend_available() -> bool:
    """True only when PyPI's ``build`` is installed, not when ``build/`` merely exists.

    A directory can satisfy ``import build``; it cannot satisfy a distribution lookup,
    and it cannot provide ``build.__main__`` — which is what ``python -m build`` needs.
    Both are required here so the skip means what it says.
    """
    try:
        importlib.metadata.version("build")
    except importlib.metadata.PackageNotFoundError:
        return False
    spec = importlib.util.find_spec("build")
    if spec is None or spec.origin is None:  # a namespace portion, i.e. a bare directory
        return False
    return importlib.util.find_spec("build.__main__") is not None


def test_force_include_ships_the_schema_directory() -> None:
    """pyproject must copy the root schema/ tree into the package."""
    cfg = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    include = cfg["tool"]["hatch"]["build"]["targets"]["wheel"]["force-include"]
    assert include["schema"] == "nearmiss/schema"


def test_the_skip_guard_is_not_satisfied_by_the_output_directory() -> None:
    """The guard must not confuse this repository's `build/` tree for the build backend."""
    if BUILD_OUTPUT_DIR.is_dir() and not (BUILD_OUTPUT_DIR / "__init__.py").exists():
        spec = importlib.util.find_spec("build")
        if spec is not None and spec.origin is None:
            # `import build` currently resolves to the output directory as a namespace
            # package. That must not be read as "the build backend is available".
            assert not build_backend_available(), (
                "the wheel test's skip guard is satisfied by the repository's own "
                f"{BUILD_OUTPUT_DIR.name}/ output directory, so `python -m build` will be "
                "run without the build backend installed"
            )


@pytest.mark.slow
def test_built_wheel_contains_report_schema(tmp_path: Path) -> None:
    """Build a real wheel and assert the runtime contract is inside it."""
    if not build_backend_available():
        pytest.skip("PyPI's `build` distribution is not installed (a `build/` directory is not it)")
    subprocess.run(
        [sys.executable, "-m", "build", "--wheel", "--outdir", str(tmp_path)],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    wheel = next(tmp_path.glob("*.whl"))
    names = zipfile.ZipFile(wheel).namelist()
    assert "nearmiss/schema/report.schema.json" in names, (
        f"wheel ships no report schema; got {[n for n in names if 'schema' in n]}"
    )
