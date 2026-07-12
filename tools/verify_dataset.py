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

    rules: dict[str, Any] = {
        rule: {"pass": len(fails) == 0, "failures": fails} for rule, fails in rule_failures.items()
    }
    verdict = "pass" if all(r["pass"] for r in rules.values()) else "fail"

    return {
        "artifact": str(geojson_path),
        "sidecar": str(sidecar_path) if sidecar_path is not None else None,
        "k_floor": resolved_floor,
        "small_n": small_n,
        "verdict": verdict,
        "rules": rules,
        "note": VERDICT_NOTE,
    }


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="verify_dataset.py",
        description="Audit a nearmiss-style GeoJSON against the five hard rules (HR1-HR5).",
    )
    parser.add_argument("geojson", type=Path, help="Path to the <slug>.geojson to verify.")
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


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if not args.geojson.exists():
        print(f"error: artifact not found: {args.geojson}", file=sys.stderr)
        return 2
    verdict = verify_artifact(args.geojson, args.metadata, args.k_floor)
    json.dump(verdict, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0 if verdict["verdict"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
