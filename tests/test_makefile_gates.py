from __future__ import annotations

import os
import re
import stat
import subprocess
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[1]


def test_make_test_independently_blocks_a_coverage_floor_failure(tmp_path: Path) -> None:
    """A zero pytest status cannot mask a failing coverage database report."""

    log = tmp_path / "calls.log"
    fake_python = tmp_path / "python"
    fake_python.write_text(
        """#!/bin/sh
printf '%s\n' "$*" >> "$FAKE_PYTHON_LOG"
case "$*" in
  "-m pytest "*) exit 0 ;;
  "-m coverage report "*)
    echo "FAIL Required test coverage of 90% not reached. Total coverage: 89.75%"
    exit 1
    ;;
esac
exit 2
""",
        encoding="utf-8",
    )
    fake_python.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
    environment = os.environ.copy()
    environment["FAKE_PYTHON_LOG"] = str(log)

    completed = subprocess.run(
        [
            "make",
            "--no-print-directory",
            "-o",
            "lint",
            "-o",
            "type",
            "-o",
            "accessibility",
            "-o",
            "security",
            "-o",
            "i18n",
            "-o",
            "claims",
            "-o",
            "conformance",
            "verify",
            f"PYTHON={fake_python}",
        ],
        cwd=REPOSITORY,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode != 0
    assert "89.75%" in completed.stdout
    assert "verify: all merge gates green" not in completed.stdout
    calls = log.read_text(encoding="utf-8").splitlines()
    assert calls[0].startswith("-m pytest ")
    assert calls[1] == "-m coverage report --fail-under=90 --precision=2"


def test_make_test_preserves_pytest_no_tests_failure(tmp_path: Path) -> None:
    """Pytest exit 5 remains blocking and does not fall through to coverage."""

    log = tmp_path / "calls.log"
    fake_python = tmp_path / "python"
    fake_python.write_text(
        """#!/bin/sh
printf '%s\n' "$*" >> "$FAKE_PYTHON_LOG"
case "$*" in
  "-m pytest "*) exit 5 ;;
  "-m coverage report "*) exit 0 ;;
esac
exit 2
""",
        encoding="utf-8",
    )
    fake_python.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
    environment = os.environ.copy()
    environment["FAKE_PYTHON_LOG"] = str(log)

    completed = subprocess.run(
        ["make", "--no-print-directory", "test", f"PYTHON={fake_python}"],
        cwd=REPOSITORY,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode != 0
    calls = log.read_text(encoding="utf-8").splitlines()
    assert len(calls) == 1
    assert calls[0].startswith("-m pytest ")


# ---------------------------------------------------------------------------
# No gate may end with `|| echo`, `|| true`, or `|| :`.
#
# `make verify` is this repository's whole local story: "run the same command CI
# runs". That promise is only worth something if every line inside it can fail.
# The `security` target used to invoke both optional scanners as
#
#     command -v gitleaks && gitleaks detect ... || echo "gitleaks not found"
#
# and a scanner *finding* — the event the gate exists for — took the `||` branch
# and exited 0, printing that the tool was missing. `tests/test_security_gate_
# recipe.py` proves that one recipe now behaves; the checks below stop the shape
# from reappearing anywhere else, because the next person adding an optional tool
# will reach for the same one-liner.
#
# A detector like this is itself a check that could quietly stop checking: narrow
# the regex, or let the recipe parser return nothing, and it passes forever over a
# Makefile full of violations. So it carries its own witnesses — the historical
# chain is embedded verbatim and must still be flagged, and the parser is asserted
# to actually read this repository's recipes.
#
# `|| rc=$?` (capture the status, then decide) and `|| $(PIP) install ...` (fetch a
# missing on-demand extra) are not swallows and are deliberately allowed: neither
# discards a gate verdict.
# ---------------------------------------------------------------------------

MAKEFILE = REPOSITORY / "Makefile"

#: `||` followed by a command that always succeeds and reports nothing upward.
SWALLOW = re.compile(r"\|\|\s*(echo\b|true\b|:\s*(?:$|;))")

#: The exact chain that shipped a green `make security` over a reported secret.
HISTORICAL_SWALLOW = (
    "\t@command -v gitleaks >/dev/null 2>&1 \\\n"
    "\t\t&& gitleaks detect --no-banner --redact --source . \\\n"
    '\t\t|| echo "security: gitleaks not found (it is a Go binary, not a pip dep);'
    ' install it to enable the secret scan. CI runs it."\n'
)


def logical_recipe_lines(makefile_text: str) -> list[str]:
    """Every recipe line, backslash continuations joined into one logical line."""
    lines: list[str] = []
    pending: list[str] = []
    for raw in makefile_text.splitlines():
        if not raw.startswith("\t"):
            if pending:  # a continuation that ran off the end of a recipe
                lines.append(" ".join(pending))
                pending = []
            continue
        command = raw[1:].strip()
        if command.endswith("\\"):
            pending.append(command[:-1].strip())
            continue
        pending.append(command)
        lines.append(" ".join(pending))
        pending = []
    if pending:
        lines.append(" ".join(pending))
    return lines


def swallowing_lines(makefile_text: str) -> list[str]:
    """Recipe lines that discard a command's failure into a no-op."""
    return [
        line
        for line in logical_recipe_lines(makefile_text)
        if not line.lstrip().startswith("#") and SWALLOW.search(line)
    ]


def test_the_swallow_parser_actually_reads_this_repositorys_recipes() -> None:
    """Guard the guard: an empty parse would make every assertion below vacuous."""
    lines = logical_recipe_lines(MAKEFILE.read_text(encoding="utf-8"))
    assert len(lines) > 50, f"only {len(lines)} recipe lines parsed out of the Makefile"
    assert any("ruff check" in line for line in lines)
    assert any("gitleaks detect" in line for line in lines)


def test_the_swallow_detector_flags_the_shape_that_actually_shipped() -> None:
    """The historical `security` chain must still be recognised as a swallow."""
    assert len(swallowing_lines(HISTORICAL_SWALLOW)) == 1


def test_the_swallow_detector_flags_every_swallowing_form() -> None:
    synthetic = "gate:\n\tscanner --strict || true\n\tother || :\n\tthird || echo skipped\n"
    assert len(swallowing_lines(synthetic)) == 3


def test_the_swallow_detector_allows_status_capture_and_on_demand_install() -> None:
    allowed = (
        "gate:\n"
        "\trc=0; scanner || rc=$$?\n"
        '\t@$(PYTHON) -c "import mutmut" 2>/dev/null || $(PIP) install -e ".[mutation]"\n'
    )
    assert swallowing_lines(allowed) == []


def test_no_makefile_gate_swallows_a_failure() -> None:
    offenders = swallowing_lines(MAKEFILE.read_text(encoding="utf-8"))
    assert offenders == [], (
        "a Makefile recipe discards a command's failure into a no-op, so the gate "
        "cannot report what it exists to report:\n  " + "\n  ".join(offenders)
    )
