"""The scheduled secret scan must stay capable of failing.

Four properties of `.github/workflows/secret-scan-scheduled.yml` are asserted here,
because
each one has silently un-armed a secret scan in this portfolio and none of them
shows up as a red build when it breaks:

1. **The result tiers include `unverified`.** TruffleHog sorts a finding into
   `verified` (it authenticated the credential against the live service),
   `unknown` (verification errored) and `unverified` (it asked, and the service
   said no). A credential that leaked and was later *revoked* — the normal end
   state of a real leak, and the exact case a scheduled full-history sweep
   exists to catch — answers "no" and is therefore `unverified`. A scan
   configured `--only-verified`, or `--results=verified,unknown`, cannot fail on
   it. Measured 2026-09-06 on a throwaway clone of this repository with a
   real-shaped AWS key planted in one commit and deleted in the next:
   `--results=verified` exited 0 reporting nothing; the widened tier exited 183.

2. **The action ref and the `version:` input name the same release.** The
   `version:` input is what selects the scanning binary
   (`ghcr.io/trufflesecurity/trufflehog:${VERSION}`); the `uses:` SHA pins only
   the wrapper. Dependabot edits `uses:` and never a `with:` input, so the two
   drift apart and each "upgrade" is a no-op that reads like one. This
   repository was in exactly that state: the ref said v3.97.1 while the scanner
   downloaded 3.96.0, so three Dependabot bumps in a row changed nothing about
   what actually scanned.

3. **`fetch-depth: 0` survives on the checkout.** Without it `actions/checkout`
   fetches a single commit, and a "full-history" sweep becomes a one-commit scan
   that still reports success.

4. **The verified-only lane survives.** The widened lane switches off the URI and
   Postgres detectors, which in this repository match only committed test
   fixtures. That is only safe while a second lane keeps both detectors armed for
   verified results, so deleting that lane must fail the build rather than
   quietly narrowing what the job can catch.

The workflow's pin comment is a YAML comment, so it is invisible to a YAML
parser: these assertions read the file as text on purpose.
"""

from __future__ import annotations

import re
from pathlib import Path

WORKFLOW = (
    Path(__file__).resolve().parents[1] / ".github" / "workflows" / "secret-scan-scheduled.yml"
)

# The tier that a revoked credential lands in. Its absence is the defect.
REQUIRED_RESULT_TIER = "unverified"


def _workflow_text() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def test_workflow_exists() -> None:
    assert WORKFLOW.is_file(), f"{WORKFLOW} is missing; the scheduled secret scan is gone"


def _extra_args() -> list[str]:
    args = re.findall(r"^\s*extra_args:\s*(.+?)\s*$", _workflow_text(), flags=re.MULTILINE)
    assert args, "no `extra_args:` found; this guard can no longer see the tiers"
    return args


def test_every_lane_states_its_tiers_explicitly() -> None:
    """`--only-verified` is never acceptable, in either lane."""
    for args in _extra_args():
        assert "--only-verified" not in args, (
            "`--only-verified` cannot fail on a revoked credential, which is the "
            "normal end state of a real leak and the case this scan exists for. "
            f"Offending args: {args!r}"
        )
        assert re.search(r"--results=[\w,]+", args), (
            f"expected an explicit `--results=` tier list, got {args!r}"
        )


def test_scan_reports_the_unverified_tier() -> None:
    """A revoked credential is `unverified`; excluding that tier disarms the scan.

    This job runs two lanes: one over every result tier with the three
    fixture-matching detectors off, and one verified-only lane that keeps those
    detectors armed (see the workflow for why). So the property asserted here is
    that AT LEAST ONE lane reports `unverified` — not that every lane does, which
    would forbid the verified-only lane that makes the exclusions safe.
    """
    tier_lists = [
        match.group(1).split(",")
        for args in _extra_args()
        if (match := re.search(r"--results=([\w,]+)", args))
    ]
    assert any(REQUIRED_RESULT_TIER in tiers for tiers in tier_lists), (
        f"no lane of this scan reports `{REQUIRED_RESULT_TIER}` results "
        f"(found {tier_lists}), so nothing here can fail on a credential the "
        "provider has already revoked. Measured: verified / verified,unknown both "
        "exit 0 on a planted-then-deleted AWS key; adding unverified exits 183."
    )


def test_action_ref_and_version_input_name_the_same_release() -> None:
    """`version:` selects the binary; `uses:` pins only the wrapper. They must agree."""
    text = _workflow_text()

    pinned = re.findall(r"trufflesecurity/trufflehog@[0-9a-f]{40}\s*#\s*v(\d+(?:\.\d+)*)", text)
    selected = re.findall(r"^\s*version:\s*\"?(\d+(?:\.\d+)*)\"?\s*$", text, flags=re.MULTILINE)

    assert pinned, "could not read the trufflehog action pin and its `# vX.Y.Z` comment"
    assert selected, (
        "no `version:` input on the trufflehog step. Without it the action defaults to "
        '"latest" and the SHA pin above it pins nothing that actually scans.'
    )
    assert len(pinned) == len(selected), (
        f"{len(pinned)} pinned trufflehog ref(s) but {len(selected)} `version:` input(s); "
        "every trufflehog step needs its own pinned version"
    )
    for ref_version, input_version in zip(pinned, selected, strict=True):
        assert ref_version == input_version, (
            f"the action is pinned to v{ref_version} but `version: {input_version}` is what "
            f"downloads the scanner, so the scan would run {input_version} and the bump to "
            f"v{ref_version} is a no-op. Set them to the same release."
        )


def test_checkout_keeps_full_history() -> None:
    """`fetch-depth: 0` is what makes this a history scan rather than a one-commit scan."""
    text = _workflow_text()
    assert "actions/checkout@" in text, "the scan no longer checks the repository out"
    assert re.search(r"^\s*fetch-depth:\s*0\s*(#.*)?$", text, flags=re.MULTILINE), (
        "`fetch-depth: 0` is missing from the checkout. actions/checkout then fetches a "
        "single commit and this full-history sweep silently becomes a one-commit scan "
        "that still reports success."
    )


def test_scan_walks_the_whole_repository() -> None:
    """`path: ./` is what stops the action resolving BASE == HEAD and scanning nothing."""
    text = _workflow_text()
    assert re.search(r"^\s*path:\s*\./\s*$", text, flags=re.MULTILINE), (
        "`path: ./` is missing; with path, base and head all unset the action exits on "
        'its own "BASE and HEAD commits are the same" guard having scanned nothing.'
    )


def _excluded_detectors(args: str) -> set[str]:
    match = re.search(r"--exclude-detectors=([\w,]+)", args)
    return set(match.group(1).split(",")) if match else set()


def test_the_verified_only_lane_keeps_the_excluded_detectors_armed() -> None:
    """Lane 1's URI/Postgres exclusions are only safe while lane 2 still runs them.

    Lane 1 turns URI and Postgres off because the widened tier surfaces three
    committed `example.test` fixtures and nothing else. Lane 2 — verified results
    only, every detector but Lob — is what stops that from costing verified-tier
    coverage for a real DSN. Losing lane 2, or adding the same exclusion to it,
    would silently narrow what this job can catch.
    """
    lanes = _extra_args()
    widened = [a for a in lanes if REQUIRED_RESULT_TIER in a]
    others = [a for a in lanes if REQUIRED_RESULT_TIER not in a]

    # Lob is excluded from every lane on purpose: its detector matches this
    # repository's pytest function names and its verifier promotes them to
    # "verified". Every OTHER exclusion needs a lane that still runs it.
    needing_cover: set[str] = set()
    for args in widened:
        needing_cover |= _excluded_detectors(args)
    needing_cover -= {"Lob"}
    if not needing_cover:
        return

    for detector in sorted(needing_cover):
        assert any(detector not in _excluded_detectors(a) for a in others), (
            f"{detector} is excluded from the widened lane and from every other lane too, "
            "so nothing in this job can catch it any more. Keep the verified-only lane "
            "that leaves it armed."
        )
