#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Diff two published nearmiss dataset vintages and *attribute* every hotspot
change to its mechanical cause.

The politically dangerous moment for any safety dataset is when a hotspot
vanishes between releases: "was it fixed, or did you fiddle the numbers?" This
tool answers that mechanically. It compares two ``<slug>.geojson`` snapshots
(optionally with their ``<slug>.metadata.json`` sidecars as the run manifest)
and, for every segment whose Getis-Ord hotspot status changed, assigns one
cause in a fixed precedence order:

  1. ``method_change``    — a modelling key in ``metadata.methods`` differs
                            (band, bandwidth, rate unit, significance rule).
  2. ``threshold_change`` — a decision threshold differs (fdr_alpha,
                            confidence_z, small_n; or min_publish_n lowered so a
                            previously withheld segment is now publishable).
  3. ``revised_exposure`` — the segment's exposure estimate/source/date changed
                            while its report count did not.
  4. ``new_reports``      — the segment's report count changed.
  5. ``suppression``      — the segment is now withheld (below min_publish_n).
  6. ``recomputation``    — the z-score crossed significance with the same
                            inputs (a neighbourhood effect from other segments).

It NEVER claims a hazard was "resolved": a decline in reports is not evidence a
street got safer (see the caveat emitted in every report). When the metadata
sidecars are absent the tool degrades gracefully to counts-only attribution.

Usage:
    python tools/diff_datasets.py OLD.geojson NEW.geojson \
        --old-meta OLD.metadata.json --new-meta NEW.metadata.json \
        --out-dir data/published/changes/ [--slug davis]

Stdlib only, deterministic output (sorted by segment_id) so the generated
change reports diff cleanly in CI, matching the rest of ``tools/``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

# --- Attribution vocabulary -------------------------------------------------
#
# Keys of metadata.methods are split by *what a change to them explains*. A
# modelling key changes how the statistic is computed; a decision threshold
# changes where the significance / publication line is drawn.
METHOD_KEYS = frozenset({"getis_ord_band_m", "kde_bandwidth_m", "rate_per", "significance"})
# Thresholds that can flip a *published* segment's significance in place.
SIGNIF_THRESHOLD_KEYS = frozenset({"fdr_alpha", "confidence_z", "small_n"})
# The publication threshold governs whether a computed segment is shown at all.
PUBLICATION_THRESHOLD_KEY = "min_publish_n"
ALL_THRESHOLD_KEYS = SIGNIF_THRESHOLD_KEYS | {PUBLICATION_THRESHOLD_KEY}

# The one non-negotiable sentence this whole tool exists to protect. Emitted
# verbatim in every JSON and markdown report; wording carries over from the
# dataset's standing limitations (docs/LIMITATIONS.md §2 reporting bias).
CAVEAT = (
    "A decline in reports is not evidence that a hazard was fixed. Reporting is "
    "self-selected and the numerator is biased, so a hotspot that disappears "
    "between vintages may reflect fewer people reporting rather than a safer "
    "street. This report attributes each ranking change to its mechanical cause "
    "(new reports, revised exposure, a method change, a threshold change, or "
    "suppression under the k-anonymity floor) and never claims a hazard was "
    "resolved."
)

_VERSION_FALLBACK = "unknown"


def _load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def load_geojson(path: Path) -> tuple[dict[str, dict], dict[str, Any]]:
    """Return ({segment_id: properties}, embedded_metadata) for a snapshot.

    Withheld (low-count) segments are absent from a published GeoJSON entirely,
    so a segment missing from this map means "not published in this vintage".
    """
    data = _load_json(path)
    by_id: dict[str, dict] = {}
    for feature in data.get("features", []):
        props = feature.get("properties") or {}
        sid = props.get("segment_id")
        if sid is not None:
            by_id[str(sid)] = props
    embedded = data.get("metadata") or {}
    return by_id, embedded


def resolve_version(meta: dict[str, Any], embedded: dict[str, Any]) -> str:
    """Pick a version string from the sidecar, then the embedded block."""
    for source in (meta, embedded):
        for key in ("dataset_version", "version"):
            value = source.get(key)
            if value:
                return str(value)
    for source in (meta, embedded):
        value = source.get("schema_version")
        if value:
            return str(value)
    return _VERSION_FALLBACK


def _methods(meta: dict[str, Any]) -> dict[str, Any]:
    m = meta.get("methods")
    return dict(m) if isinstance(m, dict) else {}


def _is_hotspot(props: dict | None) -> bool:
    return bool(props and props.get("getis_ord_significant"))


def _report_count(props: dict) -> Any:
    """Published report count; ``report_count`` with ``n`` as a fallback."""
    if props.get("report_count") is not None:
        return props.get("report_count")
    return props.get("n")


def _exposure_tuple(props: dict) -> tuple:
    return (
        props.get("exposure_estimate"),
        props.get("exposure_source"),
        props.get("exposure_date"),
    )


def method_diff(
    old_methods: dict[str, Any], new_methods: dict[str, Any], keys: frozenset
) -> dict[str, dict[str, Any]]:
    """Keys (restricted to ``keys``) whose value differs, old vs new."""
    diff: dict[str, dict[str, Any]] = {}
    for key in keys:
        if key in old_methods or key in new_methods:
            old_v = old_methods.get(key)
            new_v = new_methods.get(key)
            if old_v != new_v:
                diff[key] = {"old": old_v, "new": new_v}
    return diff


def _evidence(old: dict | None, new: dict | None) -> dict[str, Any]:
    """Compact old/new evidence for a single segment record."""

    def snap(props: dict | None) -> dict[str, Any] | None:
        if props is None:
            return None
        return {
            "significant": bool(props.get("getis_ord_significant")),
            "getis_ord_z": props.get("getis_ord_z"),
            "report_count": _report_count(props),
            "exposure_estimate": props.get("exposure_estimate"),
            "exposure_source": props.get("exposure_source"),
            "exposure_date": props.get("exposure_date"),
        }

    return {"old": snap(old), "new": snap(new)}


def _classify_appeared(
    old: dict | None,
    new: dict,
    has_meta: bool,
    mchange: dict,
    schange: dict,
    min_pub_old: Any,
    min_pub_new: Any,
) -> tuple[str, str]:
    """Return (cause, note) for a segment that became a hotspot."""
    if mchange:
        return "method_change", "method key(s) changed: " + _keys(mchange)
    if old is None:
        # Absent before, a published hotspot now. Prefer a lowered publication
        # threshold as the explanation; otherwise it crossed the floor on new
        # reports / became significant (we cannot see its prior internals).
        if (
            has_meta
            and _num(min_pub_new) is not None
            and _num(min_pub_old) is not None
            and _num(min_pub_new) < _num(min_pub_old)
        ):
            return (
                "threshold_change",
                f"min_publish_n lowered {min_pub_old} -> {min_pub_new}; "
                "segment was withheld in the prior vintage",
            )
        return (
            "recomputation",
            "absent in the prior vintage (withheld under min_publish_n or not yet significant)",
        )
    if schange:
        return "threshold_change", "significance threshold(s) changed: " + _keys(schange)
    if _exposure_tuple(old) != _exposure_tuple(new) and _report_count(old) == _report_count(new):
        return "revised_exposure", "exposure revised with report count unchanged"
    if _report_count(old) != _report_count(new):
        return (
            "new_reports",
            f"report count changed {_report_count(old)} -> {_report_count(new)}",
        )
    return "recomputation", "z-score crossed significance with the same inputs"


def _classify_disappeared(
    old: dict,
    new: dict,
    mchange: dict,
    schange: dict,
) -> tuple[str, str]:
    """Return (cause, note) for a still-published segment that lost hotspot
    status."""
    if mchange:
        return "method_change", "method key(s) changed: " + _keys(mchange)
    if schange:
        return "threshold_change", "significance threshold(s) changed: " + _keys(schange)
    if _exposure_tuple(old) != _exposure_tuple(new) and _report_count(old) == _report_count(new):
        return "revised_exposure", "exposure revised with report count unchanged"
    if _report_count(old) != _report_count(new):
        return (
            "new_reports",
            f"report count changed {_report_count(old)} -> {_report_count(new)}",
        )
    return "recomputation", "z-score crossed significance with the same inputs"


def _classify_withdrawn(
    old: dict, has_meta: bool, min_pub_old: Any, min_pub_new: Any
) -> tuple[str, str]:
    """Return (cause, note) for a hotspot that is now withheld/absent."""
    n = _num(_report_count(old))
    if (
        has_meta
        and _num(min_pub_new) is not None
        and _num(min_pub_old) is not None
        and _num(min_pub_new) > _num(min_pub_old)
    ):
        note = f"min_publish_n raised {min_pub_old} -> {min_pub_new}"
        if n is not None:
            note += f"; prior report count {n}"
        return "suppression", note
    note = "segment no longer published (withheld under the k-anonymity floor)"
    if has_meta and _num(min_pub_new) is not None and n is not None:
        note += f"; report count {n} vs min_publish_n {min_pub_new}"
    return "suppression", note


def _num(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _keys(diff: dict) -> str:
    return ", ".join(sorted(diff))


def build_report(
    slug: str,
    old_by_id: dict[str, dict],
    new_by_id: dict[str, dict],
    old_meta: dict[str, Any],
    new_meta: dict[str, Any],
    old_embedded: dict[str, Any],
    new_embedded: dict[str, Any],
    sources: dict[str, str | None],
) -> dict[str, Any]:
    has_meta = bool(old_meta) and bool(new_meta)
    old_methods = _methods(old_meta)
    new_methods = _methods(new_meta)

    mchange = method_diff(old_methods, new_methods, METHOD_KEYS) if has_meta else {}
    schange = method_diff(old_methods, new_methods, SIGNIF_THRESHOLD_KEYS) if has_meta else {}
    all_method_changes = (
        method_diff(old_methods, new_methods, METHOD_KEYS | ALL_THRESHOLD_KEYS) if has_meta else {}
    )
    min_pub_old = old_methods.get(PUBLICATION_THRESHOLD_KEY)
    min_pub_new = new_methods.get(PUBLICATION_THRESHOLD_KEY)

    all_ids = set(old_by_id) | set(new_by_id)
    changes: list[dict[str, Any]] = []
    persisted = 0

    for sid in sorted(all_ids):
        old = old_by_id.get(sid)
        new = new_by_id.get(sid)
        old_hot = _is_hotspot(old)
        new_hot = _is_hotspot(new)

        if old_hot and new_hot:
            persisted += 1
            continue
        if not old_hot and not new_hot:
            continue

        name = (new or old or {}).get("name")

        if new_hot and not old_hot:
            cause, note = _classify_appeared(
                old, new, has_meta, mchange, schange, min_pub_old, min_pub_new
            )
            change = "appeared"
        elif old_hot and new is None:
            cause, note = _classify_withdrawn(old, has_meta, min_pub_old, min_pub_new)
            change = "withdrawn"
        else:  # old_hot and new present but not significant
            cause, note = _classify_disappeared(old, new, mchange, schange)
            change = "disappeared"

        changes.append(
            {
                "segment_id": sid,
                "name": name,
                "change": change,
                "cause": cause,
                "note": note,
                "evidence": _evidence(old, new),
            }
        )

    by_cause: dict[str, int] = {}
    by_change: dict[str, int] = {}
    for rec in changes:
        by_cause[rec["cause"]] = by_cause.get(rec["cause"], 0) + 1
        by_change[rec["change"]] = by_change.get(rec["change"], 0) + 1

    return {
        "slug": slug,
        "old_version": resolve_version(old_meta, old_embedded),
        "new_version": resolve_version(new_meta, new_embedded),
        "metadata_available": has_meta,
        "sources": sources,
        "method_changes": all_method_changes,
        "summary": {
            "appeared": by_change.get("appeared", 0),
            "disappeared": by_change.get("disappeared", 0),
            "withdrawn": by_change.get("withdrawn", 0),
            "persisted": persisted,
            "by_cause": dict(sorted(by_cause.items())),
        },
        "caveat": CAVEAT,
        "changes": changes,
    }


def _fmt(value: Any) -> str:
    if value is None:
        return "—"
    return str(value)


def render_markdown(report: dict[str, Any]) -> str:
    slug = report["slug"]
    ov = report["old_version"]
    nv = report["new_version"]
    lines: list[str] = []
    lines.append(f"# Change report — {slug}: {ov} → {nv}")
    lines.append("")
    if not report["metadata_available"]:
        lines.append(
            "> Metadata sidecars were not supplied for both vintages; attribution "
            "is **counts-only** (method and threshold changes cannot be detected)."
        )
        lines.append("")

    s = report["summary"]
    lines.append("## Summary")
    lines.append("")
    lines.append(
        f"- **{s['appeared']}** hotspot(s) appeared, "
        f"**{s['disappeared']}** disappeared, "
        f"**{s['withdrawn']}** withdrawn (withheld), "
        f"**{s['persisted']}** persisted."
    )
    if s["by_cause"]:
        causes = ", ".join(f"{k}: {v}" for k, v in s["by_cause"].items())
        lines.append(f"- Attributed causes — {causes}.")
    lines.append("")

    mc = report["method_changes"]
    if mc:
        lines.append("## Method & threshold changes")
        lines.append("")
        lines.append("| Key | Old | New |")
        lines.append("| --- | --- | --- |")
        for key in sorted(mc):
            lines.append(f"| `{key}` | {_fmt(mc[key]['old'])} | {_fmt(mc[key]['new'])} |")
        lines.append("")

    lines.append("## Hotspot changes")
    lines.append("")
    if report["changes"]:
        lines.append("| Segment | Name | Change | Cause | Detail |")
        lines.append("| --- | --- | --- | --- | --- |")
        for rec in report["changes"]:
            lines.append(
                f"| `{rec['segment_id']}` | {_fmt(rec['name'])} | {rec['change']} "
                f"| {rec['cause']} | {rec['note']} |"
            )
    else:
        lines.append("_No hotspot appearances, disappearances, or withdrawals._")
    lines.append("")

    lines.append("## Caveat")
    lines.append("")
    lines.append(report["caveat"])
    lines.append("")
    return "\n".join(lines)


def _slug_from(path: Path) -> str:
    stem = path.name
    for suffix in (".geojson", ".json"):
        if stem.endswith(suffix):
            stem = stem[: -len(suffix)]
            break
    return stem


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="diff_datasets.py",
        description="Attribute hotspot changes between two dataset vintages.",
    )
    parser.add_argument("old_geojson", help="older <slug>.geojson snapshot")
    parser.add_argument("new_geojson", help="newer <slug>.geojson snapshot")
    parser.add_argument("--old-meta", help="older <slug>.metadata.json (optional; run manifest)")
    parser.add_argument("--new-meta", help="newer <slug>.metadata.json (optional; run manifest)")
    parser.add_argument(
        "--out-dir",
        default="data/published/changes/",
        help="directory for the generated change report (default: %(default)s)",
    )
    parser.add_argument(
        "--slug",
        help="dataset slug (default: derived from the new GeoJSON filename)",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)

    old_path = Path(args.old_geojson)
    new_path = Path(args.new_geojson)
    slug = args.slug or _slug_from(new_path)

    old_by_id, old_embedded = load_geojson(old_path)
    new_by_id, new_embedded = load_geojson(new_path)

    old_meta = _load_json(Path(args.old_meta)) if args.old_meta else {}
    new_meta = _load_json(Path(args.new_meta)) if args.new_meta else {}

    sources = {
        "old_geojson": str(old_path),
        "new_geojson": str(new_path),
        "old_meta": args.old_meta,
        "new_meta": args.new_meta,
    }

    report = build_report(
        slug,
        old_by_id,
        new_by_id,
        old_meta,
        new_meta,
        old_embedded,
        new_embedded,
        sources,
    )

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    base = f"{slug}-{report['old_version']}-to-{report['new_version']}"
    json_path = out_dir / f"{base}.json"
    md_path = out_dir / f"{base}.md"

    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    md_path.write_text(render_markdown(report), encoding="utf-8")

    s = report["summary"]
    print(
        f"diff_datasets: {slug} {report['old_version']} -> {report['new_version']}: "
        f"{s['appeared']} appeared, {s['disappeared']} disappeared, "
        f"{s['withdrawn']} withdrawn, {s['persisted']} persisted -> {json_path}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
