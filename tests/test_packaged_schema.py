"""The wheel must ship the schemas it reads at runtime.

Every release through 0.3.0 built cleanly, installed cleanly, and then raised
``could not locate schema/report.schema.json`` on the first report validation:
``find_report_schema`` walked up from ``__file__`` to the repository root,
which exists in a source checkout and does not exist under site-packages.
Nothing caught it because nothing had ever installed the built artifact.
"""

from __future__ import annotations

import subprocess
import sys
import tomllib
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_force_include_ships_the_schema_directory() -> None:
    """pyproject must copy the root schema/ tree into the package."""
    cfg = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    include = cfg["tool"]["hatch"]["build"]["targets"]["wheel"]["force-include"]
    assert include["schema"] == "nearmiss/schema"


@pytest.mark.slow
def test_built_wheel_contains_report_schema(tmp_path: Path) -> None:
    """Build a real wheel and assert the runtime contract is inside it."""
    pytest.importorskip("build", reason="the `build` package is not installed")
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
