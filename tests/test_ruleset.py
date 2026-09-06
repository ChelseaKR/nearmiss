"""The committed ruleset names every gate a pull request actually runs, or says why not.

Branch protection is a repository setting. It can be widened, narrowed or deleted
without a commit, and the history would not show it, so `.github/rulesets/main.json`
is committed as the evidence the README's CI/CD row is checked against.

The invariant is not "the committed file matches the live ruleset". A public-scope
token cannot read `bypass_actors`, and a comparison that silently drops a field it
could not read is a check that passes for the wrong reason. The invariant is the one
that catches the mistake this repository can actually make: **a job runs on a pull
request, goes red, and the pull request merges anyway**, because nothing ever made
it required.

That is not hypothetical here. When this file was written, four jobs ran on pull
requests and were not required, and one of them was `claims`, the docs-code
claims-parity drift gate. A drift gate that cannot block a merge is a drift gate
that reports drift to nobody. They are enumerated in `NOT_REQUIRED` below with a
reason each, so the list is reviewable rather than invisible, and so a *fifth* one
cannot be added without this test failing.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import yaml  # type: ignore[import-untyped]

REPO = Path(__file__).resolve().parent.parent
RULESET = REPO / ".github" / "rulesets" / "main.json"
WORKFLOWS = REPO / ".github" / "workflows"

# Jobs that run on a pull request and are deliberately not required to merge.
# Each entry is a claim someone has to defend at review time. Removing a job from
# this list without making it required will fail the first test below.
NOT_REQUIRED: dict[str, str] = {
    "dco (Signed-off-by on every commit)": (
        "Requiring it would block a merge on a missing trailer rather than on a "
        "defect. Owner's policy call; recorded rather than silently omitted."
    ),
    "qgis-plugin (EXP-11 honest-symbology rules, no PyQGIS needed)": (
        "Not required today. It guards published symbology honesty and is a "
        "candidate for promotion; nothing about it is inherently advisory."
    ),
    "claims (docs-code claims-parity drift gate)": (
        "NOT REQUIRED, and this is the one that should change. A drift gate that "
        "cannot block a merge reports drift to nobody. Left as-is here only because "
        "making a check required is a repository-settings change, which this "
        "repository's own history says should be a deliberate act rather than a "
        "side effect of a pull request."
    ),
    "build minimal public artifact": (
        "A build step whose output the push-only deploy jobs consume. On a pull "
        "request it is a smoke build, so a failure is visible without being a gate."
    ),
}


def committed_ruleset() -> dict[str, Any]:
    return cast("dict[str, Any]", json.loads(RULESET.read_text(encoding="utf-8")))


def required_contexts() -> set[str]:
    for rule in committed_ruleset()["rules"]:
        if rule["type"] == "required_status_checks":
            checks = rule["parameters"]["required_status_checks"]
            return {check["context"] for check in checks}
    raise AssertionError("the committed ruleset requires no status checks at all")


def _runs_on_pull_request(condition: object) -> bool:
    """A job runs on a pull request unless its own `if:` rules that out.

    The two shapes this repository uses are `github.event_name != 'schedule'`, which
    includes pull requests, and `github.event_name == 'push'`, which does not.
    """
    if condition is None:
        return True
    text = str(condition)
    return not ("== 'push'" in text or '== "push"' in text)


def pull_request_check_names() -> set[str]:
    """Every check name a pull request can produce, matrix legs expanded.

    GitHub names a matrix job `<name> (<value>, <value>)` in declaration order, which
    is why the ruleset carries `test (pytest, known-answer fixtures) (3.11)` rather
    than `test`. A checker that compared bare job ids would think those were missing.
    """
    names: set[str] = set()
    for path in sorted(WORKFLOWS.glob("*.yml")):
        workflow = cast("dict[Any, Any]", yaml.safe_load(path.read_text(encoding="utf-8")))
        triggers = workflow.get(True) or workflow.get("on") or {}
        if "pull_request" not in (triggers if isinstance(triggers, dict) else {}):
            continue
        for job_id, job in (workflow.get("jobs") or {}).items():
            if not _runs_on_pull_request(job.get("if")):
                continue
            base = job.get("name", job_id)
            matrix = ((job.get("strategy") or {}).get("matrix")) or {}
            axes = [v for v in matrix.values() if isinstance(v, list)]
            if len(axes) == 1:
                names.update(f"{base} ({value})" for value in axes[0])
            else:
                names.add(base)
    return names


def test_every_unrequired_pull_request_job_is_declared() -> None:
    """A job that runs on a pull request either blocks the merge or is named here."""
    undeclared = pull_request_check_names() - required_contexts() - set(NOT_REQUIRED)
    assert not undeclared, (
        "these jobs run on a pull request, are not required, and are not declared in "
        f"NOT_REQUIRED, so they can go red and still merge: {sorted(undeclared)}"
    )


def test_no_required_check_names_a_job_that_cannot_report() -> None:
    """A required check nothing produces blocks every merge, forever."""
    stale = required_contexts() - pull_request_check_names()
    assert not stale, (
        "the committed ruleset requires checks no pull-request job produces, which "
        f"would block every merge: {sorted(stale)}"
    )


def test_the_not_required_list_does_not_outlive_its_jobs() -> None:
    """An exemption for a job that no longer exists is a stale excuse."""
    gone = set(NOT_REQUIRED) - pull_request_check_names()
    assert not gone, f"NOT_REQUIRED excuses jobs that no pull request runs any more: {sorted(gone)}"


def test_the_not_required_list_and_the_ruleset_do_not_overlap() -> None:
    """A job cannot be both required and excused; one of the two is then a lie."""
    both = set(NOT_REQUIRED) & required_contexts()
    assert not both, f"these are required AND excused in NOT_REQUIRED: {sorted(both)}"


def test_the_ruleset_still_refuses_deletion_and_force_push() -> None:
    types = {rule["type"] for rule in committed_ruleset()["rules"]}
    assert {"deletion", "non_fast_forward"} <= types


def test_the_bypass_actors_are_stated_rather_than_omitted() -> None:
    """The admin bypass is real. A file that hides it is a file that lies politely."""
    assert "bypass_actors" in committed_ruleset(), (
        "bypass_actors is absent from the committed ruleset; an omitted bypass reads "
        "as no bypass, which is a stronger claim than this repository can make"
    )
