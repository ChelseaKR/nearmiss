"""A committed artifact must not be able to stand in for a computation no gate repeats.

`make reproduce` was the only thing holding `data/published/` to the code, and it held it
two ways short of what its name promises.

It rebuilt **in the working tree** and then diffed the git index, so a perturbed file on
disk was overwritten before anything looked at it. Perturbing
`data/published/davis-sensitivity.md` and running `make reproduce` exits 0, having
silently repaired the very thing the gate exists to notice. That is the shape that let a
sibling project ship a stale artifact for a week while every local run was green.

And it compared only what it happened to rebuild: 14 of the 24 files under
`data/published/`. The six annual NHTSA FARS artifacts, the two release indexes, the
correction ledger, the state boundary asset and the preregistration record were produced
by no step of it, and `git diff` cannot notice a stale file that nothing regenerates.

`tools/reproduce_check.py` rebuilds into a temporary directory, so the bytes it compares
are the committed bytes, and it enumerates the published tree rather than naming files,
so a committed artifact with no regeneration gate fails until it is either rebuilt or
given a written reason it cannot be. These tests hold that tool to the two properties
that make it worth having: it must fail on drift, and it must refuse to be silent about a
file it does not cover.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from tools import reproduce_check

ROOT = Path(__file__).resolve().parents[1]
MAKEFILE = ROOT / "Makefile"


def _tree(root: Path, files: dict[str, str]) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    for name, text in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return root


def test_identical_trees_pass(tmp_path: Path) -> None:
    published = _tree(tmp_path / "published", {"a.json": "{}\n", "b.md": "text\n"})
    rebuilt = _tree(tmp_path / "rebuilt", {"a.json": "{}\n", "b.md": "text\n"})
    problems, matched, skipped = reproduce_check.compare(published, rebuilt)
    assert problems == []
    assert matched == ["a.json", "b.md"]
    assert skipped == []


def test_one_changed_byte_is_a_failure(tmp_path: Path) -> None:
    """The whole point. A committed artifact that is not what the code produces fails."""
    published = _tree(tmp_path / "published", {"a.json": '{"n": 1}\n'})
    rebuilt = _tree(tmp_path / "rebuilt", {"a.json": '{"n": 2}\n'})
    problems, matched, _ = reproduce_check.compare(published, rebuilt)
    assert matched == []
    assert len(problems) == 1
    assert "a.json" in problems[0]
    assert "not what the code produces" in problems[0]


def test_a_committed_file_nothing_rebuilds_is_a_failure(tmp_path: Path) -> None:
    """The defect class itself: an artifact standing in for a computation, ungated."""
    published = _tree(tmp_path / "published", {"a.json": "{}\n", "orphan.json": "{}\n"})
    rebuilt = _tree(tmp_path / "rebuilt", {"a.json": "{}\n"})
    problems, matched, skipped = reproduce_check.compare(published, rebuilt)
    assert matched == ["a.json"]
    assert skipped == []
    assert len(problems) == 1
    assert "orphan.json" in problems[0]
    assert "rebuilt by nothing" in problems[0]


def test_a_documented_exclusion_is_skipped_and_its_reason_is_returned(tmp_path: Path) -> None:
    published = _tree(tmp_path / "published", {"a.json": "{}\n", ".gitkeep": ""})
    rebuilt = _tree(tmp_path / "rebuilt", {"a.json": "{}\n"})
    problems, _, skipped = reproduce_check.compare(published, rebuilt)
    assert problems == []
    assert skipped == [(".gitkeep", "directory placeholder, not an artifact")]


def test_a_rebuilt_file_with_no_committed_counterpart_is_a_failure(tmp_path: Path) -> None:
    """The untracked-artifact hole: `git diff` is silent about a file git does not track."""
    published = _tree(tmp_path / "published", {"a.json": "{}\n"})
    rebuilt = _tree(tmp_path / "rebuilt", {"a.json": "{}\n", "new.json": "{}\n"})
    problems, _, _ = reproduce_check.compare(published, rebuilt)
    assert len(problems) == 1
    assert "new.json" in problems[0]
    assert "no such file" in problems[0]


def test_the_run_manifest_is_dropped_from_both_sides(tmp_path: Path) -> None:
    """`*.run.json` is gitignored, so one on disk is a local by-product, not an artifact."""
    published = _tree(tmp_path / "published", {"a.json": "{}\n", "davis.run.json": "stale\n"})
    rebuilt = _tree(tmp_path / "rebuilt", {"a.json": "{}\n", "davis.run.json": "fresh\n"})
    problems, matched, skipped = reproduce_check.compare(published, rebuilt)
    assert problems == []
    assert matched == ["a.json"]
    assert skipped == []


def test_an_empty_rebuild_cannot_report_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A run that compared nothing must not say every published artifact reproduces.

    An enumerating gate can go vacuous in ways a hard-coded one cannot: point it at a
    tree whose every file is excluded, or break the rebuild into producing nothing, and
    "no mismatches" reads as success. It has to fail instead.
    """
    published = _tree(tmp_path / "published", {".gitkeep": ""})
    monkeypatch.setattr(reproduce_check, "rebuild_cities", lambda work, out: None)
    monkeypatch.setattr(reproduce_check, "rebuild_fars", lambda directory, out: None)

    assert reproduce_check.report(published) == 1
    assert "must not report that every published artifact reproduces" in capsys.readouterr().err


def test_a_rebuild_that_cannot_run_is_a_failure_not_a_pass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A producer that will not run must never leave the comparison reporting success."""
    published = _tree(tmp_path / "published", {"a.json": "{}\n"})

    def _explode(*_: object) -> None:
        raise reproduce_check.RebuildError("the producer did not run")

    monkeypatch.setattr(reproduce_check, "rebuild_cities", _explode)
    monkeypatch.setattr(reproduce_check, "rebuild_fars", _explode)
    assert reproduce_check.report(published) == 1
    assert "the producer did not run" in capsys.readouterr().err


def test_the_config_copy_refuses_an_unhandled_path_key(tmp_path: Path) -> None:
    """A path key this gate does not resolve would silently point at the wrong tree."""
    config = tmp_path / "city.toml"
    config.write_text(
        'city = "Somewhere"\nstreets = "s.geojson"\nreports = "r.json"\n'
        'exposure = "e.json"\nmystery = "../some/path.json"\n',
        encoding="utf-8",
    )
    with pytest.raises(reproduce_check.RebuildError, match="path-shaped value"):
        reproduce_check._temp_config(config, tmp_path / "work", tmp_path / "out")


def test_the_config_copy_redirects_every_output_out_of_the_repository(tmp_path: Path) -> None:
    """Nothing a rebuild writes may land inside the checkout, private stores included."""
    work = tmp_path / "work"
    work.mkdir()
    out = tmp_path / "out"
    copy = reproduce_check._temp_config(reproduce_check.CITY_CONFIGS[0], work, out)
    text = copy.read_text(encoding="utf-8")
    for key in ("out_dir", "raw_dir", "submissions_dir"):
        value = re.search(rf'^{key} = "([^"]+)"$', text, re.MULTILINE)
        assert value, f"the config copy dropped {key}"
        assert not Path(value.group(1)).is_relative_to(ROOT), (
            f"{key} still points inside the repository: a rebuild would write into the tree"
        )
    # Inputs stay absolute and still point at the committed fixtures.
    streets = re.search(r'^streets = "([^"]+)"$', text, re.MULTILINE)
    assert streets and Path(streets.group(1)).is_file()


def test_the_toml_writer_refuses_a_value_it_cannot_render_exactly() -> None:
    """A coerced value would drive the rebuild from a config the repository does not have."""
    with pytest.raises(reproduce_check.RebuildError, match="cannot re-emit"):
        reproduce_check._toml_scalar({"a": 1})


def test_reproduce_check_is_a_prerequisite_of_make_verify() -> None:
    """A gate nobody runs is the defect, not the fix.

    `.github/workflows/ci.yml` opens by saying every job "mirrors a `make` target so
    contributors run the same checks locally (`make verify`)". `reproduce` was the
    counter-example: a dedicated CI job ran it and `verify` did not, so the one gate
    protecting Hard Rule 5 was the one a contributor could not reach.
    """
    recipe = re.search(r"^verify:([^\n]*)", MAKEFILE.read_text(encoding="utf-8"), re.MULTILINE)
    assert recipe, "the Makefile no longer defines a `verify` target"
    prerequisites = recipe.group(1).split("##")[0].split()
    assert "reproduce-check" in prerequisites, (
        "`make verify` no longer runs `reproduce-check`, so nothing a contributor runs "
        "compares the committed artifacts under data/published to what the code produces"
    )
