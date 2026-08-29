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
import os
import re
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


# PyPI's `build` lives in the `release` extra, so `build_backend_available()` is false
# on every machine that has not opted in. That made the wheel test skip in CI (which
# never installs the extra) and skip in .github/workflows/release.yml too, because
# that job runs `make verify` at line 103 and installs `build` at line 109: the suite
# is over before the front-end arrives. A test that runs in no environment at all is
# the failure this module's own docstring describes, one level up. Setting
# NEARMISS_REQUIRE_BUILD=1 turns the skip into a hard failure, and release.yml sets it
# on a step placed after the install, so the one job that can run this test must.
REQUIRE_BUILD = os.environ.get("NEARMISS_REQUIRE_BUILD") == "1"


def _skip_unless_build_backend() -> None:
    if build_backend_available():
        return
    reason = "PyPI's `build` distribution is not installed (a `build/` directory is not it)"
    if REQUIRE_BUILD:
        pytest.fail(f"NEARMISS_REQUIRE_BUILD=1 but {reason}", pytrace=False)
    pytest.skip(reason)


def test_release_workflow_runs_the_wheel_test_after_installing_the_backend() -> None:
    """The claim in the comment above is checked here rather than believed.

    A require-flag protects nothing if no workflow sets it, and an ordering fix
    silently comes undone when someone moves a step. So: release.yml must set the
    flag as a real env key, must run this module under it, and both must come after
    the step installing the build front-end.

    The env key is matched line-anchored rather than as a substring on purpose. The
    first version of this test asked ``"NEARMISS_REQUIRE_BUILD" in workflow``, and
    renaming the key to ``NEARMISS_REQUIRE_BUILD_DISABLED`` left it green: the name
    also appears in the comment block above, so the check could never have gone red.
    """
    workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    env_key = re.search(r'^\s+NEARMISS_REQUIRE_BUILD:\s*"1"\s*$', workflow, re.M)
    assert env_key is not None, (
        'release.yml no longer sets NEARMISS_REQUIRE_BUILD: "1" as a step env key, so '
        "the wheel test is back to skipping in every environment that exists"
    )
    install_at = workflow.find('python -m pip install "build')
    assert install_at != -1, "release.yml no longer installs the build front-end"
    assert install_at < env_key.start(), (
        "release.yml sets NEARMISS_REQUIRE_BUILD before it installs `build`, so the "
        "step it guards would fail for want of the front-end rather than run"
    )
    run_at = workflow.find("pytest tests/test_packaged_schema.py", env_key.end())
    assert run_at != -1, (
        "release.yml sets NEARMISS_REQUIRE_BUILD but does not run "
        "tests/test_packaged_schema.py under it, so nothing reads the flag"
    )


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
    _skip_unless_build_backend()
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
