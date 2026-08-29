#!/usr/bin/env python3
"""HR1-HR5 conformance verifier for nearmiss-style published artifacts (EXP-10).

`ADAPTING.md` invites people to fork nearmiss and stand up their own city instance.
Nothing in prose stops a fork from publishing a raw-count "danger" map under the
nearmiss name and quietly dropping the guarantees that make the method honest. This
tool is the *machine* half of quality control: it audits any `<slug>.geojson`
(plus its `<slug>.metadata.json` sidecar) against the five hard rules the published
dataset contract commits to (`schema/dataset.schema.md`), and emits a JSON verdict
plus a 0/1 exit code so it can gate a fork gallery or run in CI.

The five hard rules audited (see `README.md` and `schema/dataset.schema.md`):

- **HR1** No rate without a denominator. Every feature carrying a `rate` also carries
  a positive `exposure_estimate`, an `exposure_source`, and an `exposure_date`; a raw
  count is named `report_count`, never `danger`/`score`.
- **HR2** No estimate without an interval. Every `rate` sits inside
  `rate_ci_low <= rate <= rate_ci_high` with an integer `n`; small-sample features are
  marked `uncertain`/`low_sample`, not ranked as certain.
- **HR3** Reporting bias is named, not hidden. The dataset-level `metadata.privacy`
  and `metadata.significance` statements are present, every feature exposes a
  `quality_flags` key, and a `data_card` reference travels with the file.
- **HR4** Contributor privacy is protected. No feature has `0 < n < floor`
  (k-anonymity), no per-report coordinate/timestamp/reporter field appears anywhere in
  properties, and geometry is aggregated to street segments (`LineString`/
  `MultiLineString`).
- **HR5** Open and reproducible. A sidecar manifest exists whose `geojson_sha256`
  matches the actual file hash and which carries `methods`, `schema`, `schema_version`,
  and `version`.

Scope caveat, stated so the verdict is not overclaimed: a `pass` is about the
*artifact* only. It does not certify the publisher's private conduct, the honesty of
the upstream pipeline, or that the underlying reports exist. It certifies that this one
file and its sidecar are internally consistent with the five hard rules.

Usage:
    python tools/verify_dataset.py data/published/davis.geojson
    python tools/verify_dataset.py path/to/city.geojson --metadata path/to/city.metadata.json
    python tools/verify_dataset.py path/to/city.geojson --k-floor 5

Exit: 0 if every rule passes, 1 otherwise (the JSON verdict is always written to
stdout). See `docs/ideation/03-expansions.md` (EXP-10) and `docs/ADAPTING.md`.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

# Default k-anonymity floor: a published segment with a non-zero report count below
# this is a re-identification risk and must have been withheld. Overridable with
# --k-floor; when unset we prefer the sidecar's own `methods.min_publish_n`.
DEFAULT_K_FLOOR = 3

# Default small-sample threshold used for the HR2 "marked uncertain" check when the
# sidecar does not record its own `methods.small_n`.
DEFAULT_SMALL_N = 5

# HR1: property names that present a raw quantity as danger. A count must be named
# `report_count`; a field named like danger/score is a raw-count-as-danger violation.
_DANGER_TOKENS = frozenset({"danger", "score", "threat"})

# HR4: property-name tokens that would leak a per-report attribute — reporter identity,
# a per-report timestamp, or a raw coordinate. Matched against the alphanumeric tokens
# of each (recursively nested) property key. Deliberately conservative: aggregate-safe
# fields such as `exposure_date` or `report_count` split into tokens that never appear
# here.
_FORBIDDEN_TOKENS = frozenset(
    {
        "reporter",
        "token",
        "severity",
        "heading",
        "accuracy",
        "note",
        "notes",
        "mode",
        "modes",
        "timestamp",
        "datetime",
        "occurred",
        "lat",
        "lon",
        "lng",
        "latitude",
        "longitude",
        "coordinate",
        "coordinates",
        "coord",
        "coords",
        "uuid",
        "email",
    }
)

_TOKEN_RE = re.compile(r"[a-z0-9]+")

_AGGREGATED_GEOMETRY = frozenset({"LineString", "MultiLineString"})

VERDICT_NOTE = (
    "This verdict covers the artifact (this GeoJSON and its sidecar) only — not the "
    "publisher's conduct, the upstream pipeline, or whether the underlying reports "
    "exist. A pass means the file is internally consistent with the five hard rules."
)


def _tokens(key: str) -> set[str]:
    """Lower-cased alphanumeric tokens of a key (``rate_ci_low`` -> {rate, ci, low})."""
    return set(_TOKEN_RE.findall(key.lower()))


def _feature_label(props: dict[str, Any], index: int) -> str:
    """A readable handle for a feature: its ``segment_id`` if present, else its index."""
    seg = props.get("segment_id")
    if isinstance(seg, str) and seg:
        return seg
    return f"feature[{index}]"


def _is_number(value: Any) -> bool:
    """True for a real JSON number (``bool`` is excluded — it is not a rate)."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _is_int(value: Any) -> bool:
    """True for a JSON integer (``bool`` excluded)."""
    return isinstance(value, int) and not isinstance(value, bool)


def _features(geojson: Any) -> list[dict[str, Any]]:
    """The Feature objects of a FeatureCollection, or an empty list if malformed."""
    if not isinstance(geojson, dict):
        return []
    feats = geojson.get("features")
    if not isinstance(feats, list):
        return []
    return [f for f in feats if isinstance(f, dict)]


def _properties(feature: dict[str, Any]) -> dict[str, Any]:
    props = feature.get("properties")
    return props if isinstance(props, dict) else {}


def _walk_keys(obj: Any) -> list[str]:
    """Every mapping key reachable in a nested properties object, depth-first."""
    keys: list[str] = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            if isinstance(key, str):
                keys.append(key)
            keys.extend(_walk_keys(value))
    elif isinstance(obj, list):
        for item in obj:
            keys.extend(_walk_keys(item))
    return keys


def check_hr1(features: list[dict[str, Any]]) -> list[str]:
    """HR1 — no rate without a denominator; counts are named ``report_count``, never danger."""
    failures: list[str] = []
    for i, feature in enumerate(features):
        props = _properties(feature)
        label = _feature_label(props, i)

        # A raw count must be present and named report_count.
        if "report_count" not in props:
            failures.append(
                f"{label}: missing report_count (a raw count must be named report_count)"
            )
        elif not _is_int(props["report_count"]) or props["report_count"] < 0:
            failures.append(f"{label}: report_count must be an integer >= 0")

        # No property may present a raw quantity as danger/score.
        for key in props:
            if _tokens(key) & _DANGER_TOKENS:
                failures.append(
                    f"{label}: property '{key}' names a raw quantity as danger/score; "
                    "a count must be named report_count and a risk estimate must be a "
                    "denominator-normalized rate"
                )

        # A published rate must carry its full denominator provenance.
        rate = props.get("rate")
        if rate is None:
            continue
        exposure = props.get("exposure_estimate")
        if not _is_number(exposure) or exposure <= 0:
            failures.append(f"{label}: has a rate but exposure_estimate is not a positive number")
        if not isinstance(props.get("exposure_source"), str) or not props.get("exposure_source"):
            failures.append(f"{label}: has a rate but exposure_source is missing/empty")
        if not isinstance(props.get("exposure_date"), str) or not props.get("exposure_date"):
            failures.append(f"{label}: has a rate but exposure_date is missing/empty")
    return failures


def check_hr2(features: list[dict[str, Any]], small_n: int) -> list[str]:
    """HR2 — every rate lies within its interval with an integer n; small-n is marked uncertain."""
    failures: list[str] = []
    for i, feature in enumerate(features):
        props = _properties(feature)
        label = _feature_label(props, i)
        rate = props.get("rate")
        if rate is None:
            continue

        if not _is_number(rate):
            failures.append(f"{label}: rate is present but not a number")
            continue

        low = props.get("rate_ci_low")
        high = props.get("rate_ci_high")
        if not _is_number(low) or not _is_number(high):
            failures.append(f"{label}: rate has no numeric rate_ci_low/rate_ci_high interval")
        elif not (low <= rate <= high):
            failures.append(
                f"{label}: rate {rate} outside its interval [{low}, {high}] "
                "(require rate_ci_low <= rate <= rate_ci_high)"
            )

        n = props.get("n")
        if not _is_int(n) or n < 0:
            failures.append(f"{label}: rate published without an integer n >= 0")
            continue

        report_count = props.get("report_count")
        has_reports = (_is_int(report_count) and report_count > 0) or rate > 0
        if has_reports and n < 1:
            # A positive rate/count must rest on at least one report.
            failures.append(f"{label}: positive rate/report_count but n < 1")

        # Small (but non-zero) samples must be marked, not ranked as certain.
        if 0 < n < small_n:
            flags = props.get("quality_flags")
            flags_list = flags if isinstance(flags, list) else []
            label_ok = props.get("confidence_label") in {"uncertain", "exposure_unknown"}
            if "low_sample" not in flags_list and not label_ok:
                failures.append(
                    f"{label}: small sample (n={n} < {small_n}) not marked "
                    "'uncertain'/'low_sample' — it must not be ranked as certain"
                )
    return failures


def check_hr3(geojson: Any, features: list[dict[str, Any]]) -> list[str]:
    """HR3 — dataset bias statements present, quality_flags per feature, data card linked."""
    failures: list[str] = []
    metadata = geojson.get("metadata") if isinstance(geojson, dict) else None
    if not isinstance(metadata, dict):
        failures.append("top-level 'metadata' foreign member is missing")
        metadata = {}

    for field in ("privacy", "significance"):
        value = metadata.get(field)
        if not isinstance(value, str) or not value.strip():
            failures.append(
                f"metadata.{field} is missing or empty (the bias/method account must be named)"
            )

    data_card = metadata.get("data_card")
    if not isinstance(data_card, str) or not data_card.strip():
        failures.append(
            "metadata.data_card reference is missing (the full bias account must be linked)"
        )

    for i, feature in enumerate(features):
        props = _properties(feature)
        label = _feature_label(props, i)
        if "quality_flags" not in props:
            failures.append(
                f"{label}: missing quality_flags key (per-feature caveats must be machine-readable)"
            )
        elif not isinstance(props["quality_flags"], list):
            failures.append(f"{label}: quality_flags must be an array")
    return failures


def check_hr4(features: list[dict[str, Any]], k_floor: int) -> list[str]:
    """HR4 — k-anonymity floor respected, no per-report fields leaked, geometry aggregated."""
    failures: list[str] = []
    for i, feature in enumerate(features):
        props = _properties(feature)
        label = _feature_label(props, i)

        n = props.get("n")
        if _is_int(n) and 0 < n < k_floor:
            failures.append(
                f"{label}: n={n} violates the k-anonymity floor (0 < n < {k_floor}); "
                "such a segment must be withheld"
            )

        for key in _walk_keys(props):
            hit = _tokens(key) & _FORBIDDEN_TOKENS
            if hit:
                failures.append(
                    f"{label}: property name '{key}' looks like a per-report field "
                    f"({', '.join(sorted(hit))}); no per-report coordinate, timestamp, "
                    "or reporter attribute may be published"
                )

        geometry = feature.get("geometry")
        geom_type = geometry.get("type") if isinstance(geometry, dict) else None
        if geom_type not in _AGGREGATED_GEOMETRY:
            failures.append(
                f"{label}: geometry type {geom_type!r} is not an aggregated segment "
                f"({' or '.join(sorted(_AGGREGATED_GEOMETRY))})"
            )
    return failures


def check_hr5(
    geojson_path: Path, geojson_bytes: bytes, sidecar: Any, sidecar_path: Path | None
) -> list[str]:
    """HR5 — a manifest exists whose hash matches and which pins methods/schema/version."""
    failures: list[str] = []
    if sidecar is None:
        expected = geojson_path.with_name(f"{geojson_path.stem}.metadata.json").name
        failures.append(
            f"reproducibility manifest sidecar not found (expected {expected} next to the GeoJSON)"
        )
        return failures
    if not isinstance(sidecar, dict):
        failures.append(f"sidecar {sidecar_path} is not a JSON object")
        return failures

    recorded = sidecar.get("geojson_sha256")
    actual = hashlib.sha256(geojson_bytes).hexdigest()
    if not isinstance(recorded, str) or not recorded:
        failures.append("sidecar is missing geojson_sha256")
    elif recorded.lower() != actual:
        failures.append(
            f"geojson_sha256 mismatch: sidecar records {recorded} but the file hashes to "
            f"{actual} (tampering or drift)"
        )

    for field in ("methods", "schema", "schema_version", "version"):
        value = sidecar.get(field)
        if value is None or (isinstance(value, (str, dict, list)) and len(value) == 0):
            failures.append(f"sidecar is missing a non-empty '{field}'")
    return failures


def verify_artifact(
    geojson_path: Path,
    sidecar_path: Path | None = None,
    k_floor: int | None = None,
) -> dict[str, Any]:
    """Audit one artifact and return the verdict dict (does not exit or print)."""
    geojson_bytes = geojson_path.read_bytes()
    geojson: Any = json.loads(geojson_bytes)

    if sidecar_path is None:
        candidate = geojson_path.with_name(f"{geojson_path.stem}.metadata.json")
        sidecar_path = candidate if candidate.exists() else None

    sidecar: Any = None
    if sidecar_path is not None and sidecar_path.exists():
        sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))

    # Resolve the k-anonymity floor: explicit flag wins, else the sidecar's own
    # min_publish_n, else the project default. The resolved value is reported so a
    # gallery gate can see which floor was applied.
    resolved_floor = k_floor
    if resolved_floor is None:
        methods = sidecar.get("methods") if isinstance(sidecar, dict) else None
        min_publish_n = methods.get("min_publish_n") if isinstance(methods, dict) else None
        resolved_floor = (
            min_publish_n if _is_int(min_publish_n) and min_publish_n > 0 else DEFAULT_K_FLOOR
        )

    small_n = DEFAULT_SMALL_N
    if isinstance(sidecar, dict):
        methods = sidecar.get("methods")
        if isinstance(methods, dict) and _is_int(methods.get("small_n")) and methods["small_n"] > 0:
            small_n = methods["small_n"]

    features = _features(geojson)

    rule_failures: dict[str, list[str]] = {
        "HR1": check_hr1(features),
        "HR2": check_hr2(features, small_n),
        "HR3": check_hr3(geojson, features),
        "HR4": check_hr4(features, resolved_floor),
        "HR5": check_hr5(geojson_path, geojson_bytes, sidecar, sidecar_path),
    }

    rules: dict[str, Any] = {rule: _rule(fails) for rule, fails in rule_failures.items()}
    verdict = "pass" if all(r["pass"] for r in rules.values()) else "fail"

    return {
        "artifact": str(geojson_path),
        "family": "city_segment_dataset",
        "sidecar": str(sidecar_path) if sidecar_path is not None else None,
        "k_floor": resolved_floor,
        "small_n": small_n,
        "verdict": verdict,
        "rules": rules,
        "note": VERDICT_NOTE,
    }


# ---------------------------------------------------------------------------
# Family 2: the published FARS state-mode context artifacts.
#
# `Makefile`'s conformance target promised to "audit every published dataset
# against the five hard rules" and then ran this tool over exactly two files,
# both from the retired Davis/Riverside demo, before echoing that *all* published
# datasets passed. The only real data this project ships — six NHTSA FARS
# state-by-mode artifacts and their release index — had never received an HR
# verdict. Issue #156.
#
# The FARS family is not a GeoJSON of segments, so the rules are re-derived for
# it from the artifact's own *published* contract
# (`schema/public-fars-state-context.schema.json`, which pins the caveat, the
# accounting bounds and the per-year provenance) and from the release index
# (`fars-state-mode-index*.json`, which pins each artifact's byte length and
# SHA-256). Nothing here is invented: every predicate reads a value the
# repository already publishes.
#
# HR2 is the interesting one. These artifacts publish enumerated crash counts,
# not estimates, so "no estimate without an interval" has nothing to bind to.
# That is reported as `not_applicable` with its reason — never as a `pass` — and
# the not-applicability is *derived*: the artifact is scanned for any
# estimate-shaped field, and finding one makes HR2 applicable and failing. A rule
# that cannot be evaluated must not report as satisfied (ADR 0016's discipline,
# applied to this verifier).
# ---------------------------------------------------------------------------

#: Rule statuses. `not_applicable` always carries a reason and is never a pass.
STATUS_PASS = "pass"
STATUS_FAIL = "fail"
STATUS_NOT_APPLICABLE = "not_applicable"

#: HR1 for a count-only artifact: no property may present a rate or a risk score.
_FARS_RATE_TOKENS = frozenset({"rate", "risk", "danger", "score", "threat", "normalized"})

#: HR2: fields that would mean an *estimate* was published and would need an interval.
_ESTIMATE_TOKENS = frozenset(
    {
        "estimate",
        "estimated",
        "ci",
        "interval",
        "confidence",
        "lower",
        "upper",
        "mean",
        "median",
        "projected",
        "modeled",
        "modelled",
        "predicted",
    }
)

#: The two published release indexes, newest first. An artifact must be bound by one.
FARS_INDEX_FILENAMES = (
    "fars-state-mode-index-v2.json",
    "fars-state-mode-index.json",
)

FARS_SCHEMA_FILENAME = "public-fars-state-context.schema.json"

#: The artifact_type every published FARS state-mode file declares.
FARS_ARTIFACT_TYPE = "nearmiss.public.fars_state_context"

FARS_VERDICT_NOTE = (
    "This verdict covers the artifact (this FARS state-mode JSON, its release-index "
    "binding, and its published schema constants) only — not NHTSA's collection, the "
    "private ingestion that produced it, or any claim about risk. HR2 is reported "
    "not_applicable with its reason: the artifact publishes enumerated counts, not "
    "estimates, and it is checked to contain no estimate-shaped field."
)


def _fars_index_release(artifact_path: Path, index_paths: list[Path]) -> tuple[Any, Path | None]:
    """Return the release record binding ``artifact_path``, and the index it came from."""
    for index_path in index_paths:
        if not index_path.exists():
            continue
        index = json.loads(index_path.read_text(encoding="utf-8"))
        releases = index.get("releases") if isinstance(index, dict) else None
        for release in releases if isinstance(releases, list) else []:
            if isinstance(release, dict) and release.get("artifact_path") == artifact_path.name:
                return release, index_path
    return None, None


def _fars_cells(artifact: Any) -> list[tuple[str, dict[str, Any]]]:
    """Every ``(state_label, cell)`` pair in the artifact, in document order."""
    states = artifact.get("states") if isinstance(artifact, dict) else None
    pairs: list[tuple[str, dict[str, Any]]] = []
    for index, state in enumerate(states if isinstance(states, list) else []):
        if not isinstance(state, dict):
            continue
        label = str(state.get("state_abbreviation") or state.get("state_name") or f"state[{index}]")
        for cell in state.get("cells", []) if isinstance(state.get("cells"), list) else []:
            if isinstance(cell, dict):
                pairs.append((label, cell))
    return pairs


def check_fars_hr1(artifact: Any) -> list[str]:
    """HR1 — a count-only artifact must publish no rate and must say counts are not risk."""
    failures: list[str] = []
    # Deduplicated: the same offending key appears once per cell (306 of them), and 306
    # identical lines would bury the four other rules' output.
    for key in sorted(set(_walk_keys(artifact))):
        hit = _tokens(key) & _FARS_RATE_TOKENS
        if hit:
            failures.append(
                f"property '{key}' names a rate or risk score ({', '.join(sorted(hit))}); "
                "this artifact publishes counts and must not present them as risk"
            )
    caveat = artifact.get("caveat") if isinstance(artifact, dict) else None
    if not isinstance(caveat, str) or not caveat.strip():
        failures.append("caveat is missing or empty (counts must be labelled as not risk)")
    elif "not exposure-normalized risk" not in caveat:
        failures.append(
            "caveat does not say the counts are 'not exposure-normalized risk'; HR1 "
            "requires a raw count to be labelled as volume, never as danger"
        )
    return failures


def check_fars_hr2(artifact: Any) -> tuple[str, list[str], str]:
    """HR2 — returns ``(status, failures, reason)``; not applicable to a count-only artifact."""
    estimate_keys = sorted({key for key in _walk_keys(artifact) if _tokens(key) & _ESTIMATE_TOKENS})
    if estimate_keys:
        return (
            STATUS_FAIL,
            [
                f"property '{key}' is estimate-shaped, so HR2 applies and every such value "
                "must carry a confidence interval and an n"
                for key in estimate_keys
            ],
            "an estimate-shaped field is published",
        )
    return (
        STATUS_NOT_APPLICABLE,
        [],
        "the artifact publishes enumerated FARS crash counts, not estimates; no field in "
        "it is estimate-shaped, so there is no estimate for an interval to attach to",
    )


def check_fars_hr3(artifact: Any, schema: Any) -> list[str]:
    """HR3 — the limits statement is present and is one the published schema pins."""
    failures: list[str] = []
    caveat = artifact.get("caveat") if isinstance(artifact, dict) else None
    allowed = []
    if isinstance(schema, dict):
        caveat_schema = schema.get("properties", {}).get("caveat", {})
        allowed = caveat_schema.get("enum", []) if isinstance(caveat_schema, dict) else []
    if not allowed:
        failures.append(
            f"the published schema ({FARS_SCHEMA_FILENAME}) pins no caveat text, so the "
            "limits statement cannot be checked against the contract"
        )
    elif caveat not in allowed:
        failures.append(
            "caveat is not one of the texts the published schema pins; the bias and "
            "suppression account may not be silently reworded"
        )
    metric = artifact.get("metric") if isinstance(artifact, dict) else None
    if not isinstance(metric, dict):
        failures.append("metric block is missing (the counting rule must be named)")
        return failures
    if metric.get("modes_non_additive") is not True:
        failures.append("metric.modes_non_additive is not true; overlapping modes must be declared")
    if not _is_int(metric.get("effective_k")) or metric["effective_k"] <= 0:
        failures.append("metric.effective_k is missing or not a positive integer")
    if not isinstance(metric.get("contribution_unit"), str) or not metric["contribution_unit"]:
        failures.append("metric.contribution_unit is missing (what one count means must be stated)")
    return failures


def check_fars_hr4(artifact: Any) -> list[str]:
    """HR4 — every published cell clears the declared k, and a suppressed cell carries no count."""
    failures: list[str] = []
    metric = artifact.get("metric") if isinstance(artifact, dict) else {}
    k = metric.get("effective_k") if isinstance(metric, dict) else None
    if not _is_int(k) or k <= 0:
        return ["metric.effective_k is missing, so the k-anonymity floor cannot be applied"]
    for label, cell in _fars_cells(artifact):
        mode = cell.get("involved_mode")
        status = cell.get("status")
        count = cell.get("crash_count")
        if status == "published":
            if not _is_int(count) or count < k:
                failures.append(
                    f"{label}/{mode}: published cell has crash_count={count!r}, which does not "
                    f"clear the declared floor k={k}"
                )
        elif status == "suppressed_or_zero":
            if "crash_count" in cell:
                failures.append(
                    f"{label}/{mode}: a suppressed_or_zero cell carries a crash_count, which "
                    "would defeat the suppression"
                )
        else:
            failures.append(f"{label}/{mode}: unknown cell status {status!r}")
    return failures


def _fars_recomputed_accounting(artifact: Any) -> dict[str, int]:
    """Recompute the accounting block straight from ``states[].cells[]``."""
    pairs = _fars_cells(artifact)
    published = [cell for _, cell in pairs if cell.get("status") == "published"]
    suppressed = [cell for _, cell in pairs if cell.get("status") == "suppressed_or_zero"]
    states = artifact.get("states") if isinstance(artifact, dict) else []
    return {
        "state_count": len(states) if isinstance(states, list) else 0,
        "state_mode_cell_count": len(pairs),
        "published_cell_count": len(published),
        "suppressed_or_zero_cell_count": len(suppressed),
        "published_crash_contribution_total": sum(
            int(cell["crash_count"]) for cell in published if _is_int(cell.get("crash_count"))
        ),
    }


def check_fars_hr5(
    artifact_path: Path, artifact_bytes: bytes, artifact: Any, release: Any, index_path: Path | None
) -> list[str]:
    """HR5 — the release index binds these exact bytes, and the accounting recomputes."""
    failures: list[str] = []
    if not isinstance(release, dict):
        failures.append(
            "no published release index binds this artifact (looked for "
            f"{', '.join(FARS_INDEX_FILENAMES)} beside it); an artifact nothing pins is "
            "not reproducible"
        )
    else:
        actual_sha = hashlib.sha256(artifact_bytes).hexdigest()
        recorded_sha = release.get("artifact_sha256")
        if recorded_sha != actual_sha:
            failures.append(
                f"{index_path.name if index_path else 'index'} records artifact_sha256 "
                f"{recorded_sha!r} but the file hashes to {actual_sha}"
            )
        if release.get("artifact_bytes") != len(artifact_bytes):
            failures.append(
                f"index records artifact_bytes {release.get('artifact_bytes')!r} but the file "
                f"is {len(artifact_bytes)} bytes"
            )
        if release.get("dataset_year") != artifact.get("dataset_year"):
            failures.append(
                f"index binds dataset_year {release.get('dataset_year')!r} to an artifact whose "
                f"dataset_year is {artifact.get('dataset_year')!r}"
            )

    accounting = artifact.get("accounting") if isinstance(artifact, dict) else None
    if not isinstance(accounting, dict):
        failures.append("accounting block is missing, so the published totals cannot be rechecked")
        return failures
    for field, recomputed in _fars_recomputed_accounting(artifact).items():
        if accounting.get(field) != recomputed:
            failures.append(
                f"accounting.{field} is {accounting.get(field)!r} but recomputing it from "
                f"states[].cells[] gives {recomputed}"
            )
    published_total = accounting.get("published_crash_contribution_total")
    suppressed_total = accounting.get("suppressed_crash_contribution_total")
    total = accounting.get("crash_contribution_total")
    if (
        _is_int(published_total)
        and _is_int(suppressed_total)
        and _is_int(total)
        and published_total + suppressed_total != total
    ):
        failures.append(
            f"accounting: published ({published_total}) + suppressed ({suppressed_total}) "
            f"!= crash_contribution_total ({total})"
        )
    return failures


def verify_fars_state_context(
    artifact_path: Path,
    index_paths: list[Path] | None = None,
    schema_path: Path | None = None,
) -> dict[str, Any]:
    """Audit one published FARS state-mode artifact against the five hard rules."""
    artifact_bytes = artifact_path.read_bytes()
    artifact: Any = json.loads(artifact_bytes)

    if index_paths is None:
        index_paths = [artifact_path.with_name(name) for name in FARS_INDEX_FILENAMES]
    if schema_path is None:
        schema_path = Path(__file__).resolve().parent.parent / "schema" / FARS_SCHEMA_FILENAME
    schema: Any = None
    if schema_path.exists():
        schema = json.loads(schema_path.read_text(encoding="utf-8"))

    release, index_path = _fars_index_release(artifact_path, index_paths)
    hr2_status, hr2_failures, hr2_reason = check_fars_hr2(artifact)

    rules: dict[str, Any] = {
        "HR1": _rule(check_fars_hr1(artifact)),
        "HR2": {"status": hr2_status, "failures": hr2_failures, "reason": hr2_reason},
        "HR3": _rule(check_fars_hr3(artifact, schema)),
        "HR4": _rule(check_fars_hr4(artifact)),
        "HR5": _rule(check_fars_hr5(artifact_path, artifact_bytes, artifact, release, index_path)),
    }
    rules["HR2"]["pass"] = hr2_status == STATUS_PASS
    verdict = "pass" if all(rule["status"] != STATUS_FAIL for rule in rules.values()) else "fail"
    return {
        "artifact": str(artifact_path),
        "family": "fars_state_context",
        "index": str(index_path) if index_path is not None else None,
        "schema": str(schema_path),
        "verdict": verdict,
        "rules": rules,
        "rules_not_applicable": {
            name: rule["reason"]
            for name, rule in rules.items()
            if rule["status"] == STATUS_NOT_APPLICABLE
        },
        "note": FARS_VERDICT_NOTE,
    }


def _rule(failures: list[str]) -> dict[str, Any]:
    """A rule entry carrying both the boolean and the explicit status."""
    return {
        "pass": not failures,
        "status": STATUS_PASS if not failures else STATUS_FAIL,
        "failures": failures,
    }


# ---------------------------------------------------------------------------
# Family 3: the corridor companion artifact (`<slug>.corridors.geojson`).
#
# `schema/dataset.schema.md` §9 publishes this file as a *secondary* view that
# ships "in addition to `<city-slug>.geojson`, never instead of it", and the
# primary sidecar names it back through `corridor_dataset`. It carries `rate`,
# `rate_ci_low/high`, `n` and the exposure provenance — everything HR1, HR2 and
# HR4 govern — and the conformance gate had never looked at it while claiming
# every published dataset passed.
#
# HR3 and HR5 are satisfied *through the primary*, which is the contract the
# schema states; so this verifier requires the two-way binding to exist and the
# primary itself to pass, rather than demanding a bias statement and a sidecar
# hash the published contract never asked this file to carry.
# ---------------------------------------------------------------------------

CORRIDOR_VERDICT_NOTE = (
    "This verdict covers the corridor companion artifact. Per schema/dataset.schema.md "
    "§9 it is secondary to the block-level dataset, so HR3 (bias statements, data card) "
    "and HR5 (reproducibility manifest) are carried by that primary file: they are "
    "checked here as a required two-way binding to a primary that itself passes, not "
    "waived."
)


def check_corridor_binding(
    corridor_path: Path, corridor_geojson: Any, primary_path: Path
) -> list[str]:
    """The corridor file must name its primary, and the primary's sidecar must name it back."""
    failures: list[str] = []
    metadata = corridor_geojson.get("metadata") if isinstance(corridor_geojson, dict) else None
    if not isinstance(metadata, dict):
        return ["top-level 'metadata' foreign member is missing (it must name the primary)"]
    named = metadata.get("block_level_dataset")
    if named != primary_path.name:
        failures.append(
            f"metadata.block_level_dataset is {named!r}; it must name the block-level dataset "
            f"({primary_path.name}) this corridor view is secondary to"
        )
    if not primary_path.exists():
        failures.append(f"the named block-level dataset {primary_path.name} does not exist")
        return failures
    sidecar_path = primary_path.with_name(f"{primary_path.stem}.metadata.json")
    if not sidecar_path.exists():
        failures.append(f"the primary's sidecar {sidecar_path.name} does not exist")
        return failures
    sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
    if not isinstance(sidecar, dict) or sidecar.get("corridor_dataset") != corridor_path.name:
        failures.append(
            f"{sidecar_path.name} does not name {corridor_path.name} in corridor_dataset, so the "
            "binding this file's HR3/HR5 rely on is one-way"
        )
    if not isinstance(metadata.get("maup_note"), str) or not metadata["maup_note"].strip():
        failures.append(
            "metadata.maup_note is missing; a coarser aggregation must state the "
            "Modifiable Areal Unit Problem it introduces"
        )
    return failures


def verify_corridor_artifact(
    corridor_path: Path, primary_path: Path | None = None, k_floor: int | None = None
) -> dict[str, Any]:
    """Audit one `<slug>.corridors.geojson` against the five hard rules."""
    corridor_bytes = corridor_path.read_bytes()
    corridor_geojson: Any = json.loads(corridor_bytes)
    slug = corridor_path.name.split(".corridors.geojson")[0]
    if primary_path is None:
        primary_path = corridor_path.with_name(f"{slug}.geojson")

    primary_verdict: dict[str, Any] | None = None
    if primary_path.exists():
        primary_verdict = verify_artifact(primary_path, None, k_floor)

    resolved_floor = k_floor if k_floor is not None else DEFAULT_K_FLOOR
    if k_floor is None and primary_verdict is not None:
        resolved_floor = int(primary_verdict["k_floor"])
    small_n = int(primary_verdict["small_n"]) if primary_verdict is not None else DEFAULT_SMALL_N

    features = _features(corridor_geojson)
    binding = check_corridor_binding(corridor_path, corridor_geojson, primary_path)
    if primary_verdict is not None and primary_verdict["verdict"] != "pass":
        binding.append(
            f"the block-level dataset {primary_path.name} does not pass HR1-HR5, so this "
            "secondary view cannot inherit its bias statements or its manifest"
        )

    rules: dict[str, Any] = {
        "HR1": _rule(check_hr1(features)),
        "HR2": _rule(check_hr2(features, small_n)),
        "HR3": _rule(binding),
        "HR4": _rule(check_hr4(features, resolved_floor)),
        "HR5": _rule(binding),
    }
    verdict = "pass" if all(rule["status"] != STATUS_FAIL for rule in rules.values()) else "fail"
    return {
        "artifact": str(corridor_path),
        "family": "city_corridor_view",
        "primary": str(primary_path),
        "primary_verdict": primary_verdict["verdict"] if primary_verdict else None,
        "k_floor": resolved_floor,
        "small_n": small_n,
        "verdict": verdict,
        "rules": rules,
        "note": CORRIDOR_VERDICT_NOTE,
    }


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="verify_dataset.py",
        description="Audit a nearmiss-style GeoJSON against the five hard rules (HR1-HR5).",
    )
    parser.add_argument("geojson", type=Path, help="Path to the artifact to verify.")
    parser.add_argument(
        "--family",
        choices=("auto", "city", "corridor", "fars"),
        default="auto",
        help=(
            "Artifact family. 'auto' (default) reads the file: a <slug>.corridors.geojson is "
            "the corridor companion view, a nearmiss.public.fars_state_context object is the "
            "FARS state-mode family, anything else is a city segment dataset."
        ),
    )
    parser.add_argument(
        "--metadata",
        "--sidecar",
        dest="metadata",
        type=Path,
        default=None,
        help="Path to the sidecar manifest (default: <slug>.metadata.json next to the GeoJSON).",
    )
    parser.add_argument(
        "--k-floor",
        dest="k_floor",
        type=int,
        default=None,
        help=(
            "k-anonymity floor: no published feature may have 0 < n < floor. "
            f"Default: the sidecar's methods.min_publish_n, else {DEFAULT_K_FLOOR}."
        ),
    )
    return parser.parse_args(argv)


def detect_family(path: Path) -> str:
    """Classify an artifact by what it is, not by where it sits."""
    if path.name.endswith(".corridors.geojson"):
        return "corridor"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "city"
    if isinstance(payload, dict) and payload.get("artifact_type") == FARS_ARTIFACT_TYPE:
        return "fars"
    return "city"


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if not args.geojson.exists():
        print(f"error: artifact not found: {args.geojson}", file=sys.stderr)
        return 2
    family = args.family if args.family != "auto" else detect_family(args.geojson)
    if family == "fars":
        verdict = verify_fars_state_context(args.geojson)
    elif family == "corridor":
        verdict = verify_corridor_artifact(args.geojson, None, args.k_floor)
    else:
        verdict = verify_artifact(args.geojson, args.metadata, args.k_floor)
    json.dump(verdict, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0 if verdict["verdict"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
