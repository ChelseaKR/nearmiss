#!/usr/bin/env python3
"""Rebuild every committed artifact under `data/published/` into a temporary directory
and byte-compare, refusing to leave any committed file unaccounted for.

`make reproduce` already rebuilt the two demo cities. It did it *in the working tree*
and then ran `git diff --exit-code -- data/published`, and those two properties together
leave three holes this tool closes.

**It heals the thing it is asked to check.** Perturb `data/published/davis-sensitivity.md`
on disk and run `make reproduce`: the rebuild overwrites the perturbation, `git diff`
finds the tree equal to the index, and the gate exits 0. It only ever compares the
*index* to a fresh build, never the file a reader has. That is the same shape that let a
sibling project's committed artifact stay stale for a week while every local run went
green. This tool never writes into the tree, so the bytes it compares are the bytes that
are committed.

**It ran nowhere a contributor would meet it.** `reproduce` is not a prerequisite of
`verify`; only a dedicated CI job invoked it, while `.github/workflows/ci.yml` opens by
saying every job "mirrors a `make` target so contributors run the same checks locally
(`make verify`)". For the one gate that protects Hard Rule 5 that sentence was not true.
`reproduce-check` is in `verify`.

**It only looked at what it happened to rebuild.** Twelve of the twenty-three committed
files under `data/published/` were produced by no step of `reproduce`: the six annual
NHTSA FARS artifacts, the two release indexes, the correction ledger, the state boundary
asset, and the preregistration record. `git diff` cannot notice a stale file that
nothing regenerates. So this tool enumerates the directory instead of naming files and
**fails on any committed file it neither rebuilds nor documents an exclusion for**, the
same refusal `tools/conformance_sweep.py` makes for the hard-rule audit: a new published
artifact is regenerated and compared, or it stops the build.

Two stages, both rebuilt into a temporary directory:

1. **The demo cities.** `nearmiss run`, `nearmiss figures` and `tools/sensitivity_note.py`
   over `config/davis-demo.toml` and `config/riverside-demo.toml`, with `out_dir`,
   `raw_dir` and `submissions_dir` redirected into the temporary tree so no private
   store and no committed file is touched.
2. **The FARS release index and correction ledger.** `tools/build_fars_public_index.py`
   rebuilds the live index from the committed annual artifacts, and
   `tools/build_fars_correction_ledger.py` rebuilds the ledger from the four committed
   payloads it names. Both write into the temporary tree.

Stage 2 is what puts the annual FARS artifacts under a gate at all. The index pins every
annual artifact's byte length and SHA-256, so an index that regenerates byte-for-byte
from the committed annual files is a statement about those files too; and the ledger
builder refuses any prior artifact or prior index that is not the immutable published
revision it pins in `nearmiss.fars_public_index`, which is what accounts for the frozen
v1 index and the superseded 2024 revision 1.

    python tools/reproduce_check.py           # rebuild to a temp dir and compare
    python tools/reproduce_check.py --dir DIR # compare against another published tree

Exit: 0 when every rebuilt artifact matches byte-for-byte and every committed file is
accounted for; 1 otherwise. No network. Nothing is ever written inside the repository.
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import re
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DIR = ROOT / "data" / "published"

#: The city configurations `reproduce` rebuilds. Both are synthetic, known-answer
#: fixtures: no private raw report is read and no network call is made.
CITY_CONFIGS: tuple[Path, ...] = (
    ROOT / "config" / "davis-demo.toml",
    ROOT / "config" / "riverside-demo.toml",
)

#: Top-level config keys whose value is a path resolved against the config's directory.
#: `config.load` resolves exactly these; a temp copy has to make them absolute or the
#: rebuild would read the wrong tree.
_CONFIG_INPUT_PATH_KEYS = ("streets", "reports", "exposure", "gazetteer", "weather")
#: Path keys redirected into the temporary tree, so a rebuild cannot write into the repo.
_CONFIG_OUTPUT_PATH_KEYS = ("out_dir", "raw_dir", "submissions_dir")
#: Path keys that name a file the rebuild only reads, and that must stay absolute.
_CONFIG_OTHER_PATH_KEYS = ("source_registry",)
_CONFIG_PATH_KEYS = frozenset(
    _CONFIG_INPUT_PATH_KEYS + _CONFIG_OUTPUT_PATH_KEYS + _CONFIG_OTHER_PATH_KEYS
)

#: Names that are not part of the published set at all, with the reason. They are
#: dropped from BOTH sides of the comparison: `.gitignore` excludes them, so one sitting
#: in a working tree is a local by-product and not a committed artifact. A produced file
#: matching none of these and absent from the published tree is a failure, not a shrug:
#: that is how a new, uncommitted artifact would otherwise slip in.
NOT_PART_OF_THE_PUBLISHED_SET: tuple[tuple[str, str], ...] = (
    (
        "*.run.json",
        "per-run provenance manifest written by `nearmiss publish`; `.gitignore` excludes "
        "it and the published dataset contract does not include it",
    ),
)

#: Committed files this gate does not rebuild, each with the reason it cannot. Printed on
#: every run: an exclusion a reader cannot see is the silence this tool exists to remove.
NOT_REBUILT: tuple[tuple[str, str], ...] = (
    (".gitkeep", "directory placeholder, not an artifact"),
    (
        "preregistration/*",
        "a hand-written preregistration record, not a derived artifact: no code produces "
        "it, so there is nothing to regenerate it from",
    ),
    (
        "us-state-boundaries-2024.json",
        "built by tools/build_us_state_boundaries.py from the Census cartographic boundary "
        "archive it downloads and pins by SHA-256. Rebuilding it needs the network, so an "
        "offline gate cannot compare it; the input is pinned in that tool, the output is not",
    ),
    (
        "fars-2024-state-mode.json",
        "the superseded 2024 revision 1. It is not rebuilt from raw here (the private "
        "ingestion that produced it is not in this checkout); rebuilding the correction "
        "ledger below reads it and refuses any prior artifact that is not the immutable "
        "published revision pinned in nearmiss.fars_public_index",
    ),
    (
        "fars-state-mode-index.json",
        "the frozen v1 release index. Same binding: rebuilding the correction ledger reads "
        "it and refuses any prior index that is not the immutable pinned revision",
    ),
    (
        "fars-*-state-mode*.json",
        "an annual artifact exported from the private verified FARS root, which is not in "
        "this checkout. Its byte length and SHA-256 are pinned by the release index rebuilt "
        "below, so a change to any of these files fails this gate through that index. The "
        "pattern is a glob, not a list of years: a new release year is accounted for and "
        "pinned the moment it is committed",
    ),
)

_ANNUAL_ARTIFACT = re.compile(r"^fars-([0-9]{4})-state-mode(?:-r([2-9][0-9]*))?\.json$", re.ASCII)

#: The live release index names the newest revision of every year; the frozen v1 index
#: names revision 1 of every year. Getting this backwards cannot pass silently: the
#: rebuilt bytes are compared against the committed file named here.
LIVE_INDEX_NAME = "fars-state-mode-index-v2.json"
FROZEN_INDEX_NAME = "fars-state-mode-index.json"
LEDGER_NAME = "fars-release-corrections.json"


class RebuildError(RuntimeError):
    """A producer could not be run, or a config could not be copied faithfully."""


def _relative(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


# ---------------------------------------------------------------------------
# Stage 1: the demo cities.
# ---------------------------------------------------------------------------


def _toml_scalar(value: object) -> str:
    """Emit one TOML scalar, and refuse anything this writer cannot render exactly.

    The temp config has to mean what the committed config means. A value type this does
    not handle raises rather than being coerced, because a rebuild driven by a subtly
    different config would compare the wrong thing and still be able to pass.
    """
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, str):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
        return f'"{escaped}"'
    if isinstance(value, list):
        return "[" + ", ".join(_toml_scalar(item) for item in value) + "]"
    raise RebuildError(
        f"the config carries a {type(value).__name__} value this gate cannot re-emit; "
        "extend _toml_scalar rather than letting the rebuild run on a different config"
    )


def _render_config(data: dict[str, Any]) -> str:
    """Render a parsed config back to TOML: scalars first, then tables."""
    lines = [
        "# Generated by tools/reproduce_check.py from the committed config.",
        "# Output paths are redirected into a temporary tree; nothing here is committed.",
        "",
    ]
    for key, value in data.items():
        if isinstance(value, dict):
            continue
        lines.append(f"{key} = {_toml_scalar(value)}")
    for key, value in data.items():
        if not isinstance(value, dict):
            continue
        lines += ["", f"[{key}]"]
        for inner, inner_value in value.items():
            if isinstance(inner_value, dict):
                raise RebuildError(
                    f"nested table [{key}.{inner}] is not handled by this gate's TOML writer"
                )
            lines.append(f"{inner} = {_toml_scalar(inner_value)}")
    return "\n".join(lines) + "\n"


def _temp_config(config_path: Path, work: Path, out_dir: Path) -> Path:
    """Write a copy of `config_path` whose outputs land under `work`.

    Every path the committed config states relative to its own directory becomes
    absolute, so the copy can live anywhere. Any other key whose string value looks like
    a path fails here: an unhandled path key would silently resolve against the temporary
    directory and the rebuild would read something other than the committed input.
    """
    data: dict[str, Any] = tomllib.loads(config_path.read_text(encoding="utf-8"))
    base = config_path.parent

    for key, value in data.items():
        if key in _CONFIG_PATH_KEYS or isinstance(value, dict) or not isinstance(value, str):
            continue
        if "/" in value or "\\" in value:
            raise RebuildError(
                f"{_relative(config_path)}: key {key!r} holds a path-shaped value this gate "
                "does not know how to resolve; add it to _CONFIG_PATH_KEYS"
            )

    for key in _CONFIG_INPUT_PATH_KEYS + _CONFIG_OTHER_PATH_KEYS:
        if key in data:
            data[key] = str((base / str(data[key])).resolve())

    slug = re.sub(r"[^A-Za-z0-9]+", "-", str(data["city"])).strip("-").lower() or "city"
    data["out_dir"] = str(out_dir)
    data["raw_dir"] = str(work / "raw" / slug)
    data["submissions_dir"] = str(work / "pending" / slug)

    target = work / f"{config_path.stem}.toml"
    target.write_text(_render_config(data), encoding="utf-8")
    return target


def _run(argv: list[str]) -> None:
    completed = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        raise RebuildError(
            f"{' '.join(argv[1:])} exited {completed.returncode}\n"
            f"{completed.stdout}\n{completed.stderr}"
        )


def rebuild_cities(work: Path, out_dir: Path) -> None:
    """Run every city producer `make reproduce` runs, writing only under `work`."""
    for config_path in CITY_CONFIGS:
        if not config_path.is_file():
            raise RebuildError(f"{_relative(config_path)} is missing")
        copy = _temp_config(config_path, work, out_dir)
        _run(
            [
                sys.executable,
                "-m",
                "nearmiss",
                "run",
                "--config",
                str(copy),
                "--out",
                str(work / f"{config_path.stem}-brief.md"),
            ]
        )
        _run([sys.executable, "-m", "nearmiss", "figures", "--config", str(copy)])
        _run([sys.executable, str(ROOT / "tools" / "sensitivity_note.py"), "--config", str(copy)])


# ---------------------------------------------------------------------------
# Stage 2: the FARS release index and correction ledger.
# ---------------------------------------------------------------------------


def annual_artifacts(directory: Path) -> dict[int, dict[int, Path]]:
    """`{year: {revision: path}}` for every committed annual FARS artifact."""
    found: dict[int, dict[int, Path]] = {}
    for path in sorted(directory.glob("fars-*-state-mode*.json")):
        match = _ANNUAL_ARTIFACT.fullmatch(path.name)
        if match is None:
            continue
        year = int(match.group(1))
        revision = int(match.group(2)) if match.group(2) else 1
        found.setdefault(year, {})[revision] = path
    return found


def rebuild_fars(directory: Path, out_dir: Path) -> None:
    """Rebuild the live index, the frozen index and the correction ledger under `out_dir`."""
    annual = annual_artifacts(directory)
    if not annual:
        raise RebuildError(
            f"no annual FARS artifact under {_relative(directory)}; an empty set must not "
            "read as a reproducible index"
        )

    live_inputs = [revisions[max(revisions)] for _, revisions in sorted(annual.items())]
    frozen_inputs = [revisions[1] for _, revisions in sorted(annual.items()) if 1 in revisions]

    builder = str(ROOT / "tools" / "build_fars_public_index.py")

    def _artifact_args(paths: list[Path]) -> list[str]:
        return [token for path in paths for token in ("--artifact", str(path))]

    live_index = out_dir / LIVE_INDEX_NAME
    _run([sys.executable, builder, "--out", str(live_index), *_artifact_args(live_inputs)])

    # The frozen v1 index is rebuilt only as the correction ledger's pinned input. It is
    # never compared to the committed file here: v1 is immutable, so a later dataset year
    # legitimately appears in the live index and not in it. The ledger builder is what
    # holds the committed v1 index to its pin.
    frozen_index = out_dir / "_frozen-index-for-ledger.json"
    _run([sys.executable, builder, "--out", str(frozen_index), *_artifact_args(frozen_inputs)])

    ledger_builder = str(ROOT / "tools" / "build_fars_correction_ledger.py")
    _run(
        [
            sys.executable,
            ledger_builder,
            "--prior-artifact",
            str(directory / "fars-2024-state-mode.json"),
            "--replacement-artifact",
            str(directory / "fars-2024-state-mode-r2.json"),
            "--prior-index",
            str(directory / FROZEN_INDEX_NAME),
            "--replacement-index",
            str(live_index),
            "--out",
            str(out_dir / LEDGER_NAME),
        ]
    )
    frozen_index.unlink()


# ---------------------------------------------------------------------------
# Comparison and accounting.
# ---------------------------------------------------------------------------


def _excluded(patterns: tuple[tuple[str, str], ...], relative: str) -> str | None:
    for pattern, reason in patterns:
        if fnmatch.fnmatch(relative, pattern) or fnmatch.fnmatch(Path(relative).name, pattern):
            return reason
    return None


def _files(directory: Path) -> list[str]:
    return sorted(
        str(path.relative_to(directory))
        for path in directory.rglob("*")
        if path.is_file() and not path.is_symlink()
    )


def compare(published: Path, rebuilt: Path) -> tuple[list[str], list[str], list[tuple[str, str]]]:
    """Return `(problems, matched, skipped)` for the rebuilt tree against the committed one."""
    problems: list[str] = []
    matched: list[str] = []

    for relative in _files(rebuilt):
        if _excluded(NOT_PART_OF_THE_PUBLISHED_SET, relative) is not None:
            continue
        committed = published / relative
        produced_bytes = (rebuilt / relative).read_bytes()
        if not committed.is_file():
            problems.append(
                f"{relative}: a rebuild produced it and {_relative(published)} has no such "
                "file. Commit it, or record why it is not part of the published set."
            )
            continue
        if committed.read_bytes() != produced_bytes:
            problems.append(
                f"{relative}: the committed file is not what the code produces "
                f"(committed sha256 {hashlib.sha256(committed.read_bytes()).hexdigest()[:12]}, "
                f"rebuilt {hashlib.sha256(produced_bytes).hexdigest()[:12]}). "
                "Regenerate it and commit the result; never edit it by hand."
            )
        else:
            matched.append(relative)

    rebuilt_names = set(_files(rebuilt))
    skipped: list[tuple[str, str]] = []
    for relative in _files(published):
        if relative in rebuilt_names:
            continue
        if _excluded(NOT_PART_OF_THE_PUBLISHED_SET, relative) is not None:
            continue
        reason = _excluded(NOT_REBUILT, relative)
        if reason is None:
            problems.append(
                f"{relative}: committed under {_relative(published)} and rebuilt by nothing. "
                "Add it to this gate's rebuild, or record why it cannot be rebuilt — it must "
                "not stand in for a computation no gate ever repeats."
            )
        else:
            skipped.append((relative, reason))
    return problems, matched, skipped


def report(published: Path) -> int:
    with tempfile.TemporaryDirectory(prefix="nearmiss-reproduce-") as name:
        work = Path(name)
        rebuilt = work / "published"
        rebuilt.mkdir(parents=True)
        try:
            rebuild_cities(work, rebuilt)
            rebuild_fars(published, rebuilt)
        except RebuildError as error:
            print(f"reproduce-check FAILED: {error}", file=sys.stderr)
            return 1
        problems, matched, skipped = compare(published, rebuilt)

    for relative, reason in skipped:
        print(f"  skip  {relative}\n          not rebuilt: {reason}")
    for relative in matched:
        print(f"  same  {relative}")

    if not matched:
        problems.append(
            "no artifact was rebuilt and compared; an empty run must not report that every "
            "published artifact reproduces"
        )
    if problems:
        print("\nreproduce-check FAILED:", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1

    print(
        f"\nreproduce-check: {len(matched)} published artifacts rebuilt into a temporary "
        f"directory and byte-identical to the committed bytes; {len(skipped)} files skipped "
        "for the stated reasons; no published file is unaccounted for."
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="reproduce_check.py",
        description="Rebuild every committed published artifact to a temp dir and compare.",
    )
    parser.add_argument("--dir", type=Path, default=DEFAULT_DIR, help="published tree to check")
    args = parser.parse_args(argv)
    directory: Path = args.dir
    if not directory.is_dir():
        print(f"reproduce-check FAILED: {directory} is not a directory", file=sys.stderr)
        return 1
    return report(directory)


if __name__ == "__main__":
    raise SystemExit(main())
