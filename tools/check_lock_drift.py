#!/usr/bin/env python3
"""CQ-09-equivalent drift gate for `requirements-dev.lock` (issue #189).

`uv.lock` (the runtime lock) has `uv lock --check` (`make lock-check`), wired into CI
before anything can rewrite it. `requirements-dev.lock` -- the hashed, `--require-hashes`
lock CI actually installs the dev toolchain from (`make lock-dev`, FIX-11) -- had no
equivalent, so it drifted silently: by the time this was measured, the lock pinned
`ruff==0.15.20`, `mypy==2.2.0`, and `hypothesis==6.156.6` while `pyproject.toml` had
long since required `ruff>=0.16.2`, `mypy>=2.3.0`, and `hypothesis>=6.165.0`. Every gate
result was produced by a toolchain older than the one the project declared it required,
and nothing said so.

This tool parses `pyproject.toml`'s runtime and `dev`-extra dependency specifiers and
`requirements-dev.lock`'s pinned versions, and fails if any locked version does not
satisfy its own declared specifier -- or is missing from the lock entirely. That is
deliberately a narrower question than "is this the newest possible resolution" (which is
Dependabot's job, per `.github/dependabot.yml`, and would require a full network
re-resolution to answer): it is the same question `uv lock --check` asks of `uv.lock` --
does the committed lock still honestly satisfy the manifest it claims to lock? -- answered
with a fast, local, offline check so it can run on every PR without adding a network
dependency to the hot path. When a specifier bump makes the committed pins fail this
check, the fix is `make lock-dev` (a real re-resolution, reviewed on its own -- see that
target's docstring in the Makefile for why it is not folded into an unrelated commit).

    python tools/check_lock_drift.py     # or: make lock-dev-check
"""

from __future__ import annotations

import argparse
import sys
import tomllib
from pathlib import Path

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name
from packaging.version import InvalidVersion, Version

ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = ROOT / "pyproject.toml"
LOCK = ROOT / "requirements-dev.lock"

# The lock is compiled with `--extra=dev` (make lock-dev), so it covers runtime +
# this one extra -- NOT `mutation`, which is deliberately excluded from the dev
# toolchain (see pyproject.toml's comment on that group).
LOCKED_EXTRA = "dev"


def _declared_specs() -> list[Requirement]:
    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    project = data["project"]
    raw = list(project.get("dependencies", []))
    raw += list(project.get("optional-dependencies", {}).get(LOCKED_EXTRA, []))
    return [Requirement(spec) for spec in raw]


def _locked_versions() -> dict[str, str]:
    """Package name (canonicalized) -> pinned version, from lines of the form
    `name==1.2.3 \\` or `name==1.2.3` at the start of a line -- piptools writes every
    pin unindented and every hash/comment continuation indented, so this needs no
    knowledge of the rest of the line format."""
    versions: dict[str, str] = {}
    for line in LOCK.read_text(encoding="utf-8").splitlines():
        if not line or line[0].isspace() or line.startswith("#"):
            continue
        name_version = line.split(maxsplit=1)[0]
        if "==" not in name_version:
            continue
        name, _, version = name_version.partition("==")
        versions[canonicalize_name(name)] = version
    return versions


def find_drift() -> list[str]:
    """Every declared dependency whose lock pin is missing or fails its own
    specifier, as a human-readable message."""
    locked = _locked_versions()
    problems: list[str] = []
    for req in _declared_specs():
        name = canonicalize_name(req.name)
        pinned = locked.get(name)
        if pinned is None:
            problems.append(f"{req.name}: declared ({req}) but not pinned in {LOCK.name} at all")
            continue
        try:
            version = Version(pinned)
        except InvalidVersion:
            problems.append(
                f"{req.name}: pinned version {pinned!r} in {LOCK.name} is not parseable"
            )
            continue
        if version not in req.specifier:
            problems.append(
                f"{req.name}: pyproject.toml requires {req.specifier}, "
                f"{LOCK.name} pins {pinned} -- does not satisfy it"
            )
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args(argv)

    problems = find_drift()
    if problems:
        print(
            f"{LOCK.name} has drifted from pyproject.toml -- run `make lock-dev` "
            "and commit the diff (review it: this moves the gate toolchain and may "
            "surface new findings):",
            file=sys.stderr,
        )
        for problem in problems:
            print(f"  {problem}", file=sys.stderr)
        return 1

    print(f"lock-dev-check OK: every pin in {LOCK.name} satisfies pyproject.toml.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
