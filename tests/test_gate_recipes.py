"""Gate recipes in the Makefile have to be able to fail, and to say why.

Each test here executes the **real recipe lines out of the Makefile** — not a copy —
against stub tools, so a gate cannot quietly become incapable of reporting what it
exists to report.

## `make security`

The recipe used to invoke both optional scanners as a single shell chain::

    command -v gitleaks && gitleaks detect ... || echo "gitleaks not found"

A chain of that shape cannot distinguish *the tool is absent* from *the tool ran
and found something*. gitleaks exits ``1`` on a finding, that non-zero status took
the ``||`` branch, the branch printed "gitleaks not found", and the recipe exited
``0``. Measured on this repository before the fix, with a stub scanner that exits
``1``::

    STUB gitleaks: pretending to find a committed secret
    security: gitleaks not found (it is a Go binary, not a pip dep); ...
    EXIT=0

So the gate that exists to stop a committed secret reaching the public path was
green *over a reported secret*, while telling the reader the scanner was missing.
That is worse than having no scanner: the message actively misdescribes what
happened. The same chain covered ``zizmor``, whose whole job is to fail on a
high-severity workflow finding.

These tests execute the **real recipe lines out of the Makefile** — not a copy —
against stub scanners, so the three outcomes stay distinct and provable:

* the scanner runs and fails  -> the recipe fails;
* the scanner runs and passes -> the recipe passes and says it ran;
* the scanner is absent       -> the recipe passes, says plainly that no scan ran,
  and fails instead when ``SECURITY_REQUIRE_SCANNERS=1`` asks for the scan to be
  real.

The ``pip_audit`` line is filtered out because it needs the network; every other
line of the recipe is executed verbatim.

## `make lock-check`

CQ-09's drift gate is `uv lock --check`. Every Dependabot Python PR fails it:
Dependabot's ``pip`` ecosystem rewrites ``pyproject.toml``'s specifiers and the
pip-tools hashes but never ``uv.lock``, so the bump arrives drifted. Five open PRs
(#202-#206) stopped on exactly that step. The recipe now explains the remediation on
failure, which is only worth anything if the failure still propagates — so that is
asserted here too.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MAKEFILE = ROOT / "Makefile"

# Resolved before PATH is narrowed to the stub directory, so the recipe runs under the
# same shell `make` uses (`SHELL := bash` at the top of the Makefile).
BASH = shutil.which("bash")


def recipe_body(target: str) -> list[str]:
    """Return the recipe lines of `target`, tabs and make prefixes stripped."""
    body: list[str] = []
    started = False
    for line in MAKEFILE.read_text(encoding="utf-8").splitlines():
        if not started:
            if re.match(rf"^{re.escape(target)}[^=]*:", line):
                started = True
            continue
        if line.startswith("\t"):
            command = line[1:]
            if command[:1] in ("@", "-", "+"):
                command = command[1:]
            body.append(command)
        elif not line.strip():
            break
        else:
            break
    if not body:  # pragma: no cover - a renamed target must not pass silently
        raise AssertionError(f"no recipe found for target {target!r} in {MAKEFILE}")
    return body


def scanner_script(tool: str) -> str:
    """The `security` recipe with the networked pip-audit line removed."""
    lines = [line for line in recipe_body("security") if "pip_audit" not in line]
    joined = "\n".join(lines).replace("$$", "$")
    assert tool in joined, f"the security recipe no longer invokes {tool}"
    return "set -eu -o pipefail\n" + joined + "\n"


def run_recipe(
    tmp_path: Path, tool: str, *, stubs: dict[str, int], env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    """Run the real recipe with `stubs` (name -> exit code) as the only PATH."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    for name, code in stubs.items():
        stub = bin_dir / name
        stub.write_text(f'#!/bin/sh\necho "STUB {name} ran"\nexit {code}\n', encoding="utf-8")
        stub.chmod(0o755)
    assert BASH is not None, "bash is required: the Makefile sets SHELL := bash"
    return subprocess.run(
        [BASH, "-c", scanner_script(tool)],
        cwd=ROOT,
        env={"PATH": str(bin_dir), **(env or {})},
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.parametrize("tool", ["gitleaks", "zizmor"])
def test_a_scanner_finding_fails_the_gate(tmp_path: Path, tool: str) -> None:
    """The defect itself: a scanner exiting non-zero must fail `make security`."""
    result = run_recipe(tmp_path, tool, stubs={tool: 1})
    assert result.returncode != 0, (
        f"{tool} reported a finding and the security recipe still exited 0:\n"
        f"{result.stdout}{result.stderr}"
    )
    assert "FAILED" in result.stderr
    assert "not found" not in result.stdout, "a finding must never be reported as a missing tool"


@pytest.mark.parametrize("tool", ["gitleaks", "zizmor"])
def test_a_clean_scanner_passes_and_says_it_ran(tmp_path: Path, tool: str) -> None:
    result = run_recipe(tmp_path, tool, stubs={"gitleaks": 0, "zizmor": 0})
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"STUB {tool} ran" in result.stdout
    assert "SKIPPED" not in result.stdout


@pytest.mark.parametrize("tool", ["gitleaks", "zizmor"])
def test_an_absent_scanner_is_reported_as_a_skip_not_as_a_scan(tmp_path: Path, tool: str) -> None:
    """Absence is survivable locally, but it is never reported as a clean scan."""
    result = run_recipe(tmp_path, tool, stubs={})
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"{tool} SKIPPED" in result.stdout
    assert "No secret scan ran here" in result.stdout or "No workflow scan ran here" in (
        result.stdout
    )


@pytest.mark.parametrize("tool", ["gitleaks", "zizmor"])
def test_require_scanners_turns_an_absent_scanner_into_a_failure(tmp_path: Path, tool: str) -> None:
    result = run_recipe(tmp_path, tool, stubs={}, env={"SECURITY_REQUIRE_SCANNERS": "1"})
    assert result.returncode != 0, result.stdout + result.stderr
    assert "NOT INSTALLED" in result.stderr


# --- `make lock-check` (CQ-09) -----------------------------------------------------


def lock_check_script() -> str:
    """The `lock-check` recipe, ready to run against a stub `uv`."""
    lines = recipe_body("lock-check")
    joined = "\n".join(lines).replace("$$", "$")
    assert "uv lock --check" in joined, "the lock-check recipe no longer runs uv lock --check"
    return "set -eu -o pipefail\n" + joined + "\n"


def run_lock_check(tmp_path: Path, uv_exit: int) -> subprocess.CompletedProcess[str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    stub = bin_dir / "uv"
    stub.write_text(
        f'#!/bin/sh\necho "STUB uv $*"\nexit {uv_exit}\n',
        encoding="utf-8",
    )
    stub.chmod(0o755)
    assert BASH is not None
    return subprocess.run(
        [BASH, "-c", lock_check_script()],
        cwd=ROOT,
        env={"PATH": str(bin_dir)},
        capture_output=True,
        text=True,
        check=False,
    )


def test_lock_check_fails_when_uv_reports_drift(tmp_path: Path) -> None:
    result = run_lock_check(tmp_path, uv_exit=2)
    assert result.returncode != 0, result.stdout + result.stderr
    assert "uv.lock has drifted from pyproject.toml" in result.stderr


def test_lock_check_failure_tells_a_dependabot_pr_what_to_do(tmp_path: Path) -> None:
    result = run_lock_check(tmp_path, uv_exit=2)
    assert "uv lock" in result.stderr
    assert "make lock-dev" in result.stderr
    assert "Dependabot" in result.stderr


def test_lock_check_passes_when_the_lock_is_current(tmp_path: Path) -> None:
    result = run_lock_check(tmp_path, uv_exit=0)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "still satisfies pyproject.toml" in result.stdout
