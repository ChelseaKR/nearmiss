"""`requirements-dev.lock` has to keep satisfying `pyproject.toml`, not just once,
when it was compiled, but forever after -- that is what a lock is for.

By the time this was measured, the committed lock pinned `ruff==0.15.20`,
`mypy==2.2.0`, and `hypothesis==6.156.6` while `pyproject.toml` had long since moved
to `ruff>=0.16.2`, `mypy>=2.3.0`, and `hypothesis>=6.165.0` -- and nothing checked it,
so every merge gate ran on a toolchain older than the one the project declared it
required (issue #189). `uv.lock` has had this check (`uv lock --check`, CQ-09) since
FIX-11; this is its equivalent for the pip-tools lane.

Mirrors `tests/test_doc_audit.py`'s shape: the committed state must currently pass,
and the check must be shown to actually fail on real drift -- a check that cannot be
demonstrated to fail is the green tick this file exists to prevent.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from tools import check_lock_drift

ROOT = Path(__file__).resolve().parents[1]


def test_the_committed_lock_has_no_drift() -> None:
    """`make lock-dev-check`, as a merge gate: every declared dev/runtime dependency's
    pin in requirements-dev.lock must satisfy its own pyproject.toml specifier."""
    problems = check_lock_drift.find_drift()
    assert problems == [], "\n".join(problems)


def test_the_drift_check_actually_fails_on_a_stale_pin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pin a real declared dependency (ruff) below its pyproject.toml floor and
    require the check to catch it -- the exact shape of the defect this tool exists
    to catch (see the module docstring's measured table)."""
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        '[project]\ndependencies = []\n[project.optional-dependencies]\ndev = ["ruff>=0.16.2"]\n',
        encoding="utf-8",
    )
    lock = tmp_path / "requirements-dev.lock"
    lock.write_text("ruff==0.15.20 \\\n    --hash=sha256:0000\n", encoding="utf-8")

    monkeypatch.setattr(check_lock_drift, "PYPROJECT", pyproject)
    monkeypatch.setattr(check_lock_drift, "LOCK", lock)

    problems = check_lock_drift.find_drift()
    assert len(problems) == 1
    assert "ruff" in problems[0] and "0.15.20" in problems[0]
    assert check_lock_drift.main([]) == 1


def test_a_dependency_missing_from_the_lock_is_reported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        '[project]\ndependencies = ["jsonschema>=4.26.0"]\n'
        "[project.optional-dependencies]\ndev = []\n",
        encoding="utf-8",
    )
    lock = tmp_path / "requirements-dev.lock"
    lock.write_text("# empty lock\n", encoding="utf-8")

    monkeypatch.setattr(check_lock_drift, "PYPROJECT", pyproject)
    monkeypatch.setattr(check_lock_drift, "LOCK", lock)

    problems = check_lock_drift.find_drift()
    assert len(problems) == 1
    assert "jsonschema" in problems[0] and "not pinned" in problems[0]


def test_a_pin_that_satisfies_its_specifier_is_not_reported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        '[project]\ndependencies = []\n[project.optional-dependencies]\ndev = ["ruff>=0.16.2"]\n',
        encoding="utf-8",
    )
    lock = tmp_path / "requirements-dev.lock"
    lock.write_text("ruff==0.16.4 \\\n    --hash=sha256:0000\n", encoding="utf-8")

    monkeypatch.setattr(check_lock_drift, "PYPROJECT", pyproject)
    monkeypatch.setattr(check_lock_drift, "LOCK", lock)

    assert check_lock_drift.find_drift() == []
    assert check_lock_drift.main([]) == 0


def test_name_matching_is_canonical_across_hyphen_underscore_and_case(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """PEP 503: `pytest-cov`, `pytest_cov`, and `Pytest-Cov` are the same package."""
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        "[project]\ndependencies = []\n"
        '[project.optional-dependencies]\ndev = ["Pytest-Cov>=7.1.0"]\n',
        encoding="utf-8",
    )
    lock = tmp_path / "requirements-dev.lock"
    lock.write_text("pytest_cov==7.1.0 \\\n    --hash=sha256:0000\n", encoding="utf-8")

    monkeypatch.setattr(check_lock_drift, "PYPROJECT", pyproject)
    monkeypatch.setattr(check_lock_drift, "LOCK", lock)

    assert check_lock_drift.find_drift() == []
