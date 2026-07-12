from __future__ import annotations

import os
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
