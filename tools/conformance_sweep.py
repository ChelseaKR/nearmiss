#!/usr/bin/env python3
"""Audit *every* published artifact against HR1-HR5, and refuse to skip one silently.

`make conformance` used to run `tools/verify_dataset.py` over two hard-coded paths —
`davis.geojson` and `riverside.geojson`, both from the retired demo — and then echo:

    conformance: all published datasets pass HR1-HR5

Ten files ship under `data/published/`. Two were audited. The eight that were not
included the six NHTSA FARS state-mode artifacts, which are the only real data this
project publishes, and the two `<slug>.corridors.geojson` companion views, which carry
`rate`, `rate_ci_low/high`, `n` and the exposure provenance that HR1, HR2 and HR4 exist
to police. The gate's *claim* was universal; its *scope* was a two-item list that
nothing kept in step with the directory. Issue #156.

This sweep replaces the list with an enumeration. It walks `data/published/`, classifies
every file, audits each classified artifact through `verify_dataset`, and — the part
that makes the universal claim honest — **fails on any file it cannot classify**. A new
published artifact is therefore audited or it stops the build; it can no longer be
covered by an echo. Non-dataset files (a rendered brief, a figure, a sidecar already
read as another artifact's HR5 witness) are excluded by an explicit, reasoned list, and
each exclusion prints its reason so a reader can disagree with it.

Two further refusals, because an enumerating gate can go vacuous in ways a hard-coded
one cannot: a family whose glob matches nothing fails, and a sweep that audits zero
artifacts fails. An empty directory must not read as "everything passed".

    python tools/conformance_sweep.py            # audit data/published
    python tools/conformance_sweep.py --dir DIR  # audit another published tree

Exit: 0 when every classified artifact passes and every file is accounted for; 1
otherwise. Pure standard library; no network.
"""

from __future__ import annotations

import argparse
import fnmatch
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent

# `from verify_dataset import ...` also works when this file is run as a script, because
# Python puts `tools/` on `sys.path` for it — but only then. Under `mypy` (which now covers
# `tools/`, see `[tool.mypy]` in pyproject.toml) and
# from a test, the module's name is `tools.verify_dataset`, matching how
# `tools/verify_live_site.py` already imports `tools.build_site`. Importing it by the one
# name that is true in every context is what lets the type checker follow the call into
# the verifier instead of treating every verdict it returns as `Any`.
_ROOT_STRING = str(ROOT)
if _ROOT_STRING not in sys.path:
    sys.path.insert(0, _ROOT_STRING)

from tools.verify_dataset import (  # noqa: E402
    detect_family,
    verify_artifact,
    verify_corridor_artifact,
    verify_fars_state_context,
)

DEFAULT_DIR = ROOT / "data" / "published"

#: Files that are published but are not datasets in the HR1-HR5 sense. Every entry
#: carries the reason it is not audited, and the reason is printed on every run: an
#: exclusion a reader cannot see is the same silence this tool exists to remove.
EXCLUSIONS: tuple[tuple[str, str], ...] = (
    (".gitkeep", "directory placeholder"),
    (
        "*.metadata.json",
        "the block-level dataset's sidecar manifest; it is read as that dataset's HR5 "
        "witness rather than audited as an artifact of its own",
    ),
    (
        "*.run.json",
        "per-run provenance written by `nearmiss publish`; not committed and not part "
        "of the published dataset contract",
    ),
    ("*-ranked.md", "rendered prose (the ranked-locations table), not a dataset"),
    ("*-sensitivity.md", "rendered prose (the threshold-sensitivity note), not a dataset"),
    ("*-rates.svg", "a figure, not a dataset"),
    (
        "fars-state-mode-index*.json",
        "the FARS release index; it is read as the HR5 witness that pins each FARS "
        "artifact's byte length and SHA-256",
    ),
    (
        "fars-release-corrections.json",
        "the FARS correction ledger; provenance about the artifacts, not an artifact of counts",
    ),
    (
        "us-state-boundaries-2024.json",
        "published geometry only: it carries no count, rate, interval or occupancy, so "
        "no hard rule has a value in it to bind to",
    ),
    ("preregistration/*", "preregistration records, not published datasets"),
)

#: family -> (human label, glob that must match at least one file).
REQUIRED_FAMILIES: dict[str, tuple[str, str]] = {
    "city": ("city segment dataset", "*.geojson"),
    "corridor": ("city corridor companion view", "*.corridors.geojson"),
    "fars": ("FARS state-mode context", "fars-*-state-mode*.json"),
}


def excluded_reason(relative: str) -> str | None:
    """The documented reason `relative` is not audited, or None if it must be."""
    for pattern, reason in EXCLUSIONS:
        if fnmatch.fnmatch(relative, pattern) or fnmatch.fnmatch(Path(relative).name, pattern):
            return reason
    return None


def audit(path: Path) -> dict[str, Any]:
    """Audit one artifact through the family its own contents select."""
    family = detect_family(path)
    if family == "fars":
        return verify_fars_state_context(path)
    if family == "corridor":
        return verify_corridor_artifact(path)
    return verify_artifact(path)


def sweep(directory: Path) -> tuple[list[dict[str, Any]], list[str], list[tuple[str, str]]]:
    """Return `(verdicts, unclassified, excluded)` for every file under `directory`."""
    verdicts: list[dict[str, Any]] = []
    unclassified: list[str] = []
    excluded: list[tuple[str, str]] = []
    for path in sorted(p for p in directory.rglob("*") if p.is_file()):
        relative = path.relative_to(directory).as_posix()
        reason = excluded_reason(relative)
        if reason is not None:
            excluded.append((relative, reason))
            continue
        if path.suffix == ".geojson" or (path.suffix == ".json" and detect_family(path) == "fars"):
            verdicts.append(audit(path))
            continue
        unclassified.append(relative)
    return verdicts, unclassified, excluded


def missing_families(directory: Path) -> list[str]:
    """Families whose glob matches nothing — an empty glob must never read as a pass."""
    missing: list[str] = []
    for family, (label, pattern) in REQUIRED_FAMILIES.items():
        matches = [p for p in directory.rglob(pattern) if p.is_file()]
        if family == "city":
            matches = [p for p in matches if not p.name.endswith(".corridors.geojson")]
        if not matches:
            missing.append(f"{family} ({label}): no file matches {pattern} under {directory}")
    return missing


def print_verdict(verdict: dict[str, Any]) -> list[str]:
    """Print one artifact's line and return its failures as problem strings."""
    name = Path(verdict["artifact"]).name
    summary = ", ".join(f"{rule}={entry['status']}" for rule, entry in verdict["rules"].items())
    marker = "PASS" if verdict["verdict"] == "pass" else "FAIL"
    print(f"  {marker}  {name} [{verdict['family']}] {summary}")
    for rule, reason in (verdict.get("rules_not_applicable") or {}).items():
        print(f"          {rule} not evaluated: {reason}")
    if verdict["verdict"] == "pass":
        return []
    return [
        f"{name}: {rule}: {failure}"
        for rule, entry in verdict["rules"].items()
        for failure in entry["failures"]
    ]


def report(directory: Path) -> int:
    verdicts, unclassified, excluded = sweep(directory)
    problems: list[str] = []

    for relative, reason in excluded:
        print(f"  skip  {relative}\n          not audited: {reason}")

    for verdict in verdicts:
        problems.extend(print_verdict(verdict))

    if unclassified:
        problems.extend(
            f"{relative}: published but not classified into an audited family, and not "
            "in the documented exclusion list. Add a family for it or record why no "
            "hard rule binds to it — it must not pass by being invisible."
            for relative in unclassified
        )
    problems.extend(missing_families(directory))
    if not verdicts:
        problems.append(
            f"no artifact under {directory} was audited; an empty sweep must not report "
            "that every published dataset passes"
        )

    if problems:
        print("\nconformance sweep FAILED:", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1

    families = sorted({verdict["family"] for verdict in verdicts})
    print(
        f"\nconformance: {len(verdicts)} published artifacts audited against HR1-HR5 "
        f"across {len(families)} families ({', '.join(families)}); "
        f"{len(excluded)} non-dataset files skipped for the stated reasons; "
        "no published file is unaccounted for."
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="conformance_sweep.py",
        description="Audit every published artifact against HR1-HR5 and refuse to skip one.",
    )
    parser.add_argument("--dir", type=Path, default=DEFAULT_DIR, help="Published tree to sweep.")
    args = parser.parse_args(argv)
    if not args.dir.is_dir():
        print(f"error: not a directory: {args.dir}", file=sys.stderr)
        return 2
    return report(args.dir)


if __name__ == "__main__":
    raise SystemExit(main())
