"""The conformance gate must audit every published artifact, or say which it did not.

`make conformance` ran `tools/verify_dataset.py` over two hard-coded paths and echoed
"all published datasets pass HR1-HR5". Ten artifacts ship under `data/published/`. Two
were audited. Unaudited were the six NHTSA FARS state-mode files — the only real data
this project publishes — and the two `<slug>.corridors.geojson` companion views, which
carry `rate`, `rate_ci_low/high`, `n` and the exposure provenance that HR1, HR2 and HR4
exist to police. A universal claim over a two-item list is the exact failure this
repository polices everywhere else. Issue #156.

`tools/conformance_sweep.py` replaces the list with an enumeration. The tests here hold
it to the three things that make an enumerating gate honest:

* it audits *this* directory, not a remembered one, and the audited set is asserted
  by name so a silently shrinking sweep fails;
* a published file it cannot classify **fails** — a new artifact is audited or it stops
  the build, and can no longer be covered by an echo;
* it cannot go vacuous: an empty family and an empty sweep are failures, because
  "nothing to check" must never render as "everything passed".

The rule checks are then broken one at a time. Each mutation is a published value a
real defect would move — a suppressed count restored, a byte appended, an accounting
total edited, a caveat reworded — and each must produce a `fail`, not a `pass`.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
PUBLISHED = ROOT / "data" / "published"
SWEEP = ROOT / "tools" / "conformance_sweep.py"

#: Every artifact the sweep must audit. Asserted by name: a sweep that quietly stops
#: seeing a family would otherwise still print a green summary.
EXPECTED_AUDITED = {
    "davis.corridors.geojson",
    "davis.geojson",
    "fars-2020-state-mode.json",
    "fars-2021-state-mode.json",
    "fars-2022-state-mode.json",
    "fars-2023-state-mode.json",
    "fars-2024-state-mode-r2.json",
    "fars-2024-state-mode.json",
    "riverside.corridors.geojson",
    "riverside.geojson",
}

#: What the retired two-path gate covered. The sweep must be a strict superset.
PREVIOUSLY_AUDITED = {"davis.geojson", "riverside.geojson"}


def _load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, ROOT / "tools" / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


vd = _load("verify_dataset")
cs = _load("conformance_sweep")


def audited_names(directory: Path) -> set[str]:
    verdicts, _unclassified, _excluded = cs.sweep(directory)
    return {Path(verdict["artifact"]).name for verdict in verdicts}


def run_sweep(directory: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SWEEP), "--dir", str(directory)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.fixture
def published_copy(tmp_path: Path) -> Path:
    destination = tmp_path / "published"
    shutil.copytree(PUBLISHED, destination)
    return destination


# --- The sweep sees the whole directory ------------------------------------------


def test_the_sweep_audits_every_committed_published_artifact() -> None:
    assert audited_names(PUBLISHED) == EXPECTED_AUDITED


def test_the_sweep_is_a_strict_superset_of_the_two_paths_the_old_gate_named() -> None:
    audited = audited_names(PUBLISHED)
    assert audited > PREVIOUSLY_AUDITED
    assert len(audited) - len(PREVIOUSLY_AUDITED) == 8


def test_every_committed_published_file_is_audited_or_excluded_with_a_reason() -> None:
    _verdicts, unclassified, excluded = cs.sweep(PUBLISHED)
    assert unclassified == []
    assert all(reason.strip() for _name, reason in excluded)


def test_the_committed_tree_passes_the_sweep() -> None:
    result = run_sweep(PUBLISHED)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "no published file is unaccounted for" in result.stdout


# --- The sweep refuses to go vacuous ---------------------------------------------


def test_an_unclassified_published_file_fails_the_sweep(published_copy: Path) -> None:
    (published_copy / "mystery-artifact.dat").write_text("counts?\n", encoding="utf-8")
    result = run_sweep(published_copy)
    assert result.returncode == 1
    assert "mystery-artifact.dat" in result.stderr
    assert "not classified" in result.stderr


def test_an_empty_published_tree_fails_the_sweep(tmp_path: Path) -> None:
    empty = tmp_path / "published"
    empty.mkdir()
    result = run_sweep(empty)
    assert result.returncode == 1
    assert "must not report" in result.stderr


def test_a_family_with_no_artifacts_fails_the_sweep(published_copy: Path) -> None:
    for path in published_copy.glob("fars-*-state-mode*.json"):
        path.unlink()
    result = run_sweep(published_copy)
    assert result.returncode == 1
    assert "FARS state-mode context" in result.stderr


# --- The FARS family's rules can each fail ---------------------------------------


def _fars(published: Path) -> Path:
    return published / "fars-2024-state-mode-r2.json"


def _rewrite(path: Path, mutate: Any) -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    mutate(payload)
    path.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")), encoding="utf-8")


def test_fars_hr1_fails_when_a_rate_is_published(published_copy: Path) -> None:
    artifact = _fars(published_copy)

    def mutate(payload: dict[str, Any]) -> None:
        payload["states"][0]["cells"][0]["rate_per_100k"] = 1.4

    _rewrite(artifact, mutate)
    verdict = vd.verify_fars_state_context(artifact)
    assert verdict["rules"]["HR1"]["status"] == "fail"
    assert verdict["verdict"] == "fail"


def test_fars_hr1_fails_when_the_caveat_stops_saying_counts_are_not_risk(
    published_copy: Path,
) -> None:
    artifact = _fars(published_copy)
    _rewrite(artifact, lambda payload: payload.__setitem__("caveat", "2024 crash counts."))
    verdict = vd.verify_fars_state_context(artifact)
    assert verdict["rules"]["HR1"]["status"] == "fail"


def test_fars_hr2_is_not_applicable_and_never_reports_as_a_pass() -> None:
    verdict = vd.verify_fars_state_context(_fars(PUBLISHED))
    assert verdict["rules"]["HR2"]["status"] == "not_applicable"
    assert verdict["rules"]["HR2"]["pass"] is False
    assert verdict["rules_not_applicable"]["HR2"].strip()


def test_fars_hr2_becomes_applicable_the_moment_an_estimate_is_published(
    published_copy: Path,
) -> None:
    artifact = _fars(published_copy)

    def mutate(payload: dict[str, Any]) -> None:
        payload["states"][0]["cells"][0]["estimated_crashes"] = 900

    _rewrite(artifact, mutate)
    verdict = vd.verify_fars_state_context(artifact)
    assert verdict["rules"]["HR2"]["status"] == "fail"
    assert verdict["verdict"] == "fail"


def test_fars_hr3_fails_when_the_caveat_is_reworded_away_from_the_published_schema(
    published_copy: Path,
) -> None:
    artifact = _fars(published_copy)
    original = json.loads(artifact.read_text(encoding="utf-8"))["caveat"]
    _rewrite(
        artifact,
        lambda payload: payload.__setitem__(
            "caveat",
            original.replace("must never be read as zero", "is usually zero"),
        ),
    )
    verdict = vd.verify_fars_state_context(artifact)
    assert verdict["rules"]["HR3"]["status"] == "fail"


def test_fars_hr4_fails_when_a_suppressed_cell_is_restored_below_k(
    published_copy: Path,
) -> None:
    artifact = _fars(published_copy)

    def mutate(payload: dict[str, Any]) -> None:
        for state in payload["states"]:
            for cell in state["cells"]:
                if cell["status"] == "suppressed_or_zero":
                    cell["status"] = "published"
                    cell["crash_count"] = 4
                    return
        raise AssertionError("no suppressed cell to restore")

    _rewrite(artifact, mutate)
    verdict = vd.verify_fars_state_context(artifact)
    assert verdict["rules"]["HR4"]["status"] == "fail"
    assert "k=10" in " ".join(verdict["rules"]["HR4"]["failures"])


def test_fars_hr4_fails_when_a_suppressed_cell_still_carries_its_count(
    published_copy: Path,
) -> None:
    artifact = _fars(published_copy)

    def mutate(payload: dict[str, Any]) -> None:
        for state in payload["states"]:
            for cell in state["cells"]:
                if cell["status"] == "suppressed_or_zero":
                    cell["crash_count"] = 3
                    return
        raise AssertionError("no suppressed cell to leak")

    _rewrite(artifact, mutate)
    verdict = vd.verify_fars_state_context(artifact)
    assert verdict["rules"]["HR4"]["status"] == "fail"


def test_fars_hr5_fails_when_the_bytes_stop_matching_the_release_index(
    published_copy: Path,
) -> None:
    artifact = _fars(published_copy)
    artifact.write_bytes(artifact.read_bytes() + b" ")
    verdict = vd.verify_fars_state_context(artifact)
    assert verdict["rules"]["HR5"]["status"] == "fail"
    assert "artifact_sha256" in " ".join(verdict["rules"]["HR5"]["failures"])


def test_fars_hr5_fails_when_the_accounting_no_longer_recomputes(
    published_copy: Path,
) -> None:
    artifact = _fars(published_copy)

    def mutate(payload: dict[str, Any]) -> None:
        payload["accounting"]["published_cell_count"] += 1

    _rewrite(artifact, mutate)
    verdict = vd.verify_fars_state_context(artifact)
    failures = " ".join(verdict["rules"]["HR5"]["failures"])
    assert verdict["rules"]["HR5"]["status"] == "fail"
    assert "published_cell_count" in failures


def test_fars_hr5_fails_when_no_release_index_binds_the_artifact(
    published_copy: Path,
) -> None:
    for name in ("fars-state-mode-index-v2.json", "fars-state-mode-index.json"):
        (published_copy / name).unlink()
    verdict = vd.verify_fars_state_context(_fars(published_copy))
    assert verdict["rules"]["HR5"]["status"] == "fail"
    assert "no published release index binds this artifact" in " ".join(
        verdict["rules"]["HR5"]["failures"]
    )


# --- The corridor companion view's rules can each fail ----------------------------


def test_corridor_view_passes_and_names_its_primary() -> None:
    verdict = vd.verify_corridor_artifact(PUBLISHED / "davis.corridors.geojson")
    assert verdict["verdict"] == "pass"
    assert verdict["primary_verdict"] == "pass"
    assert Path(verdict["primary"]).name == "davis.geojson"


def test_corridor_view_fails_when_it_stops_naming_its_block_level_dataset(
    published_copy: Path,
) -> None:
    corridor = published_copy / "davis.corridors.geojson"
    _rewrite(
        corridor,
        lambda payload: payload["metadata"].__setitem__("block_level_dataset", "somewhere.geojson"),
    )
    verdict = vd.verify_corridor_artifact(corridor)
    assert verdict["rules"]["HR3"]["status"] == "fail"
    assert verdict["rules"]["HR5"]["status"] == "fail"


def test_corridor_view_fails_when_the_primary_stops_naming_it_back(
    published_copy: Path,
) -> None:
    sidecar = published_copy / "davis.metadata.json"
    _rewrite(sidecar, lambda payload: payload.__setitem__("corridor_dataset", "other.geojson"))
    verdict = vd.verify_corridor_artifact(published_copy / "davis.corridors.geojson")
    assert verdict["verdict"] == "fail"
    assert "one-way" in " ".join(verdict["rules"]["HR3"]["failures"])


def test_corridor_view_fails_when_a_corridor_rate_loses_its_denominator(
    published_copy: Path,
) -> None:
    corridor = published_copy / "davis.corridors.geojson"

    def mutate(payload: dict[str, Any]) -> None:
        payload["features"][0]["properties"]["exposure_estimate"] = 0

    _rewrite(corridor, mutate)
    verdict = vd.verify_corridor_artifact(corridor)
    assert verdict["rules"]["HR1"]["status"] == "fail"


def test_corridor_view_fails_when_a_corridor_rate_leaves_its_interval(
    published_copy: Path,
) -> None:
    corridor = published_copy / "davis.corridors.geojson"

    def mutate(payload: dict[str, Any]) -> None:
        payload["features"][0]["properties"]["rate_ci_high"] = 0.1

    _rewrite(corridor, mutate)
    verdict = vd.verify_corridor_artifact(corridor)
    assert verdict["rules"]["HR2"]["status"] == "fail"


# --- Every per-feature rule says how much of the artifact it judged ---------------
#
# `riverside.corridors.geojson` is an empty FeatureCollection (its metadata records
# `corridors_published: 0`), and the sweep printed
#
#     PASS  riverside.corridors.geojson [city_corridor_view] HR1=pass, HR2=pass, ...
#
# over it, counting the file among "10 published artifacts audited against HR1-HR5".
# HR1, HR2 and HR4 are per-feature loops: over no features they return no failures,
# which is byte-for-byte what a rule that examined every feature and found nothing
# wrong returns. The FARS family already prints `HR2=not_applicable` with a written
# reason in exactly that position; the city families had no such disclosure.
#
# HR2 narrows further, on every artifact: it opens `if rate is None: continue`, so
# its four assertions are reached only through a rated feature. Measured across the
# published tree on 2026-09-08: 15 of 183 features.


def test_a_per_feature_rule_over_no_features_is_not_reported_as_a_pass() -> None:
    verdict = vd.verify_corridor_artifact(PUBLISHED / "riverside.corridors.geojson")
    assert verdict["rules"]["HR1"]["examined"] == 0
    assert verdict["rules"]["HR1"]["available"] == 0
    for rule in ("HR1", "HR2", "HR4"):
        assert verdict["rules"][rule]["status"] == "not_applicable", rule
        assert verdict["rules_not_applicable"][rule].strip(), rule
    # The verdict itself is unchanged: not_applicable was never a failure.
    assert verdict["verdict"] == "pass"


def test_hr2_reports_the_rated_share_rather_than_the_feature_count() -> None:
    """The guard `if rate is None: continue` is where HR2's scope actually is."""
    path = PUBLISHED / "davis.geojson"
    features = vd._features(json.loads(path.read_text(encoding="utf-8")))
    rated = sum(1 for f in features if (f.get("properties") or {}).get("rate") is not None)

    hr2 = vd.verify_artifact(path)["rules"]["HR2"]
    assert hr2["available"] == len(features)
    assert hr2["examined"] == rated
    assert hr2["examined"] < hr2["available"], hr2


def test_every_per_feature_rule_carries_its_coverage_on_both_city_families() -> None:
    """The floor. Without it the two assertions above could pass on one artifact."""
    for verdict in (
        vd.verify_artifact(PUBLISHED / "davis.geojson"),
        vd.verify_corridor_artifact(PUBLISHED / "davis.corridors.geojson"),
    ):
        for rule in ("HR1", "HR2", "HR4"):
            entry = verdict["rules"][rule]
            assert "examined" in entry and "available" in entry, (verdict["family"], rule)
        # HR3 and HR5 read the document as a whole; a feature count would be a lie
        # about what they judged.
        for rule in ("HR3", "HR5"):
            assert "examined" not in verdict["rules"][rule], (verdict["family"], rule)


def test_the_printed_line_carries_the_counts_and_the_corridor_note() -> None:
    result = run_sweep(PUBLISHED)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "HR2=pass(9/177 features)" in result.stdout, result.stdout
    assert "HR1=not_applicable(0/0 features)" in result.stdout, result.stdout
    # CORRIDOR_VERDICT_NOTE explains that HR3 and HR5 are carried through the primary
    # -- which is also why both cells come from one predicate. It sat on the verdict
    # object and was printed by nothing, so the two cells read as two judgements.
    assert "note: This verdict covers the corridor companion artifact" in result.stdout


# --- The FARS family says how much of the artifact each rule judged ---------------
#
# The fix above reached the two city families and stopped there. The FARS family --
# six of the ten audited artifacts, and the only real data this project publishes --
# printed `HR1=pass, HR2=not_applicable, HR3=pass, HR4=pass, HR5=pass` with no
# denominator anywhere on the line. Two of those cells are per-item rules over
# collections that can be empty, and both are satisfied by an empty collection.


def test_the_fars_rules_report_the_universe_each_one_judged() -> None:
    """Measured on the committed artifacts: 44 distinct property names, 306 cells."""
    verdict = vd.verify_fars_state_context(_fars(PUBLISHED))
    for rule, unit in (
        ("HR1", "property names"),
        ("HR2", "property names"),
        ("HR4", "state-mode cells"),
    ):
        entry = verdict["rules"][rule]
        assert entry["examined"] > 0, (rule, entry)
        assert entry["available"] == entry["examined"], (rule, entry)
        assert entry["unit"] == unit, (rule, entry)
    # HR3 reads the caveat and the metric block, and HR5 binds the artifact's bytes
    # to the release index. Neither is per-item, and a count beside them would
    # describe a scope they do not have.
    for rule in ("HR3", "HR5"):
        assert "examined" not in verdict["rules"][rule], rule


def test_a_fars_artifact_with_no_cells_is_not_reported_as_a_pass(
    published_copy: Path,
) -> None:
    """HR4's every assertion is inside `for label, cell in _fars_cells(artifact)`.

    Over no cells it returns no failures, which is the same output as having judged
    all 306 and found nothing wrong -- `riverside.corridors.geojson`'s defect, in
    the family the earlier fix did not reach.
    """
    artifact = _fars(published_copy)

    def mutate(payload: dict[str, Any]) -> None:
        payload["states"] = []

    _rewrite(artifact, mutate)
    verdict = vd.verify_fars_state_context(artifact, index_paths=[])
    hr4 = verdict["rules"]["HR4"]
    assert hr4["examined"] == 0, hr4
    assert hr4["status"] == "not_applicable", hr4
    assert verdict["rules_not_applicable"]["HR4"].strip()
    # not_applicable was never a failure and still is not; what changed is that the
    # label no longer claims a judgement nothing made.
    assert hr4["failures"] == []


def test_a_property_name_scan_that_finds_nothing_fails_hr1_and_hr2(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An empty scan and a clean document produce the same output.

    HR1 looks for rate-shaped names and HR2 for estimate-shaped ones. Both are
    satisfied by finding none -- and HR2 then *publishes* the sentence "no field in
    it is estimate-shaped", which is a claim about a scan. A reader that has stopped
    reaching the document would put that sentence on the page as a fact about
    NHTSA's data. The realistic break is simulated here, because no committed
    artifact can produce it: the walker is made to return nothing.
    """
    artifact = json.loads(_fars(PUBLISHED).read_text(encoding="utf-8"))
    assert artifact, "the artifact must be non-empty for the floor to be the right refusal"
    monkeypatch.setattr(vd, "_walk_keys", lambda _obj: [])

    hr1 = vd.check_fars_hr1(artifact)
    assert any("judged nothing" in failure for failure in hr1), hr1

    status, failures, reason = vd.check_fars_hr2(artifact)
    assert status == "fail", (status, reason)
    assert any("judged nothing" in failure for failure in failures), failures
    assert "not_applicable" not in status


def test_an_artifact_that_really_is_empty_is_not_blamed_for_the_scan_floor() -> None:
    """The floor is about a broken reader, not about a small document.

    Without this the refusal above is satisfied by a rule that fires on everything,
    which is the stricter-looking wrong implementation.
    """
    assert vd._scan_floor({}, [], "HR1") == []
    assert vd._scan_floor({"caveat": "x"}, ["caveat"], "HR1") == []
    assert vd._scan_floor({"caveat": "x"}, [], "HR1") != []


def test_the_printed_fars_line_carries_its_own_denominators() -> None:
    result = run_sweep(PUBLISHED)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "HR4=pass(306/306 state-mode cells)" in result.stdout, result.stdout
    assert "HR1=pass(44/44 property names)" in result.stdout, result.stdout
    # The noun has to travel with the number: these artifacts have no features at all.
    assert "306/306 features" not in result.stdout, result.stdout
