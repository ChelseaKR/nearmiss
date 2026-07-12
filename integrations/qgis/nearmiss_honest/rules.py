# SPDX-License-Identifier: Apache-2.0
"""Pure-Python honest-symbology rules for the nearmiss QGIS plugin.

This module contains NO PyQGIS imports so it can be unit-tested with plain
pytest, without a QGIS install, in CI. `qgis_layer.py` is the thin PyQGIS
glue that turns these decisions into an actual `QgsVectorLayer` renderer,
maptip, and layer metadata; `plugin.py` wires that glue into the QGIS GUI.

The rules encode the same reading rules the web map and the brief already
enforce (see schema/dataset.schema.md and README.md's "hard rules"), so a GIS
analyst who only ever opens this plugin in QGIS gets the same honest picture
as a reader of the web map:

  * HR1 — rate, not count, drives the symbology; report_count never implies
    danger on its own, and a missing denominator is drawn as "exposure
    unknown," never as zero or as the coldest color on a rate ramp.
  * HR2 — every rate is shown with its confidence interval and its sample
    size `n`; a small/wide-interval feature is never presented as certain.
  * HR3 — quality_flags (reporting-bias caveats) travel with the tooltip.
  * Significance is conveyed as a fill PATTERN plus explicit text, never by
    color alone, so it survives grayscale printing, color-vision deficiency,
    and casual misreading of a red/blue ramp as "significant vs not."
"""

from __future__ import annotations

from typing import Any

# --- Closed vocabularies mirrored from schema/dataset.schema.md ------------

CONFIDENCE_LABELS = ("certain", "uncertain", "exposure_unknown")
PUBLISHED_QUALITY_FLAGS = ("low_sample", "geocode_low_confidence", "exposure_unknown")

# Symbology classes for the graduated rate renderer. "unknown" is a real,
# always-present class (HR1 degradability) rather than an implicit fallback,
# so it is impossible to build a renderer that silently folds unknown
# exposure into the lowest-rate bucket.
UNKNOWN_CLASS = "exposure_unknown"

# Fill patterns used for significance. Deliberately NOT a color-only signal:
# QGIS brush styles print in grayscale and are distinguishable without color
# vision, satisfying the same "text and pattern, never color alone" rule the
# web map and the accessible table already follow for significance.
PATTERN_SIGNIFICANT_HOT = "hot_significant"  # dense diagonal hatch
PATTERN_SIGNIFICANT_COLD = "cold_significant"  # dense cross hatch
PATTERN_NOT_SIGNIFICANT = "not_significant"  # no hatch, solid fill
PATTERN_UNKNOWN = "unknown"  # sparse dot pattern, neutral gray


def significance_marker(properties: dict[str, Any]) -> dict[str, Any]:
    """Classify a feature's spatial-significance state into pattern + label.

    Returns a dict with:
      - `pattern`: one of the PATTERN_* constants above (drives the QGIS
        brush style, independent of the fill color).
      - `label`: short plain-language text for the legend/tooltip. Significance
        is always paired with this text; a reader who cannot perceive the
        pattern or the color still gets the word.
      - `significant`: the raw boolean-or-None from the data, preserved for
        callers that need it directly.
    """
    z = properties.get("getis_ord_z")
    sig = properties.get("getis_ord_significant")

    if z is None or sig is None:
        return {
            "pattern": PATTERN_UNKNOWN,
            "label": "not evaluated (exposure unknown)",
            "significant": None,
        }
    if sig and z > 0:
        return {
            "pattern": PATTERN_SIGNIFICANT_HOT,
            "label": "significant hot spot",
            "significant": True,
        }
    if sig and z < 0:
        return {
            "pattern": PATTERN_SIGNIFICANT_COLD,
            "label": "significant cold spot",
            "significant": True,
        }
    return {
        "pattern": PATTERN_NOT_SIGNIFICANT,
        "label": "not significant at threshold",
        "significant": False,
    }


def rate_class(properties: dict[str, Any], breaks: list[float]) -> str:
    """Bucket a feature into a graduated-rate class, or the unknown class.

    `breaks` is an ascending list of class-boundary values (as produced by
    `compute_rate_breaks`). A `None` rate (exposure unknown, HR1) ALWAYS maps
    to `UNKNOWN_CLASS`, regardless of `breaks` — there is no numeric coercion
    of "unknown" to a rate of zero anywhere in this module.
    """
    rate = properties.get("rate")
    if rate is None:
        return UNKNOWN_CLASS
    for i, upper in enumerate(breaks):
        if rate <= upper:
            return f"class_{i}"
    return f"class_{len(breaks)}"


def compute_rate_breaks(features: list[dict[str, Any]], n_classes: int = 5) -> list[float]:
    """Quantile breaks over non-null rates only.

    Features with `rate is None` (exposure unknown) are excluded from the
    breaks computation entirely — they must never pull down the low end of a
    rate ramp or otherwise distort the classification of features that DO
    have a denominator.
    """
    rates = sorted(
        f["properties"]["rate"] for f in features if f.get("properties", {}).get("rate") is not None
    )
    if not rates:
        return []
    if len(rates) < n_classes:
        n_classes = len(rates)
    breaks = []
    for i in range(1, n_classes + 1):
        idx = min(len(rates) - 1, round(i * len(rates) / n_classes) - 1)
        breaks.append(rates[max(idx, 0)])
    # De-duplicate while preserving order (ties in the data can collapse
    # classes; a shorter, still-ascending break list is fine).
    deduped: list[float] = []
    for b in breaks:
        if not deduped or b > deduped[-1]:
            deduped.append(b)
    return deduped


def confidence_text(properties: dict[str, Any]) -> str:
    """Human-readable rate + CI + n string, or the honest 'unknown' text.

    Never renders a bare number for an unknown rate: `exposure_estimate is
    None` always produces the word "unknown," matching HR1's rule that a
    missing denominator is stated, not defaulted to zero.
    """
    label = properties.get("confidence_label")
    rate = properties.get("rate")
    if rate is None or label == "exposure_unknown":
        return "rate: exposure unknown"
    ci_low = properties.get("rate_ci_low")
    ci_high = properties.get("rate_ci_high")
    n = properties.get("n")
    ci_txt = (
        f"95% CI {ci_low:g}–{ci_high:g}"
        if ci_low is not None and ci_high is not None
        else "95% CI unavailable"
    )
    label_txt = f" ({label})" if label else ""
    return f"rate: {rate:g}{label_txt}, {ci_txt}, n={n if n is not None else '?'}"


def tooltip_html(properties: dict[str, Any]) -> str:
    """Build the HTML maptip content for one feature.

    Every element that carries a risk claim (rate, CI, significance,
    quality_flags) is stated as text in the tooltip, not implied by color —
    the same "text, not just color" rule the web map's table view follows.
    """
    name = properties.get("name") or properties.get("segment_id") or "(unnamed segment)"
    count = properties.get("report_count", 0)
    sig = significance_marker(properties)
    flags = properties.get("quality_flags") or []
    flags_txt = ", ".join(flags) if flags else "none"

    exposure_estimate = properties.get("exposure_estimate")
    exposure_source = properties.get("exposure_source")
    exposure_date = properties.get("exposure_date")
    if exposure_estimate is None:
        exposure_line = "exposure: unknown (no denominator available)"
    else:
        exposure_line = (
            f"exposure: {exposure_estimate:g} "
            f"(source: {exposure_source or 'unknown'}, as of {exposure_date or 'unknown'})"
        )

    lines = [
        f"<b>{_escape(str(name))}</b>",
        f"report_count (volume, not danger): {count}",
        _escape(exposure_line),
        _escape(confidence_text(properties)),
        f"significance: {_escape(sig['label'])}",
        f"quality flags: {_escape(flags_txt)}",
    ]
    return "<br/>".join(lines)


def _escape(text: str) -> str:
    return (
        text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
    )


# --- Dataset/feature invariant verification ---------------------------------
#
# A lightweight, in-plugin echo of the project's HR1/HR2 conformance rules
# (the fuller, standalone version of this check is tracked separately as
# EXP-10, the HR1-HR5 conformance verifier; this is intentionally NOT a
# reimplementation of that tool, just the handful of invariants relevant to
# what this plugin renders). It runs automatically when a dataset is loaded
# so a malformed or hand-edited GeoJSON that has drifted from the schema
# surfaces as a warning in QGIS instead of silently rendering wrong.


def _verify_exposure_and_rate(seg: str, properties: dict[str, Any]) -> list[str]:
    exposure_estimate = properties.get("exposure_estimate")
    rate = properties.get("rate")
    ci_low = properties.get("rate_ci_low")
    ci_high = properties.get("rate_ci_high")
    label = properties.get("confidence_label")
    problems: list[str] = []

    if exposure_estimate is None:
        if rate is not None or ci_low is not None or ci_high is not None:
            problems.append(f"{seg}: exposure_estimate is null but rate/CI is not (HR1 violation)")
        if label != "exposure_unknown":
            problems.append(
                f"{seg}: exposure_estimate is null but confidence_label != 'exposure_unknown'"
            )
    else:
        if rate is None:
            problems.append(f"{seg}: exposure_estimate present but rate is null")
        if (ci_low is None) != (ci_high is None):
            problems.append(f"{seg}: rate CI has only one of low/high bound (HR2 violation)")
        if rate is not None and (ci_low is None or ci_high is None):
            problems.append(f"{seg}: rate published without a confidence interval (HR2 violation)")

    if label is not None and label not in CONFIDENCE_LABELS:
        problems.append(f"{seg}: confidence_label '{label}' is outside the closed vocabulary")

    return problems


def _verify_significance(seg: str, properties: dict[str, Any]) -> list[str]:
    z = properties.get("getis_ord_z")
    sig = properties.get("getis_ord_significant")
    problems: list[str] = []

    # The schema documents `getis_ord_significant` as null exactly when
    # `getis_ord_z` is null; in practice publish.py's real output sometimes
    # carries `false` instead of `null` for the unrated case, which is
    # harmless for rendering (significance_marker() already treats a null
    # `getis_ord_z` as authoritative for "not evaluated," regardless of
    # what `getis_ord_significant` says). Only flag the combinations that
    # are actually ambiguous or contradictory:
    if z is None and sig is True:
        problems.append(f"{seg}: getis_ord_significant is true but getis_ord_z is null")
    if z is not None and sig is None:
        problems.append(f"{seg}: getis_ord_z is present but getis_ord_significant is null")

    return problems


def _verify_quality_flags(seg: str, properties: dict[str, Any]) -> list[str]:
    flags = properties.get("quality_flags") or []
    return [
        f"{seg}: quality_flags contains unrecognized flag '{flag}'"
        for flag in flags
        if flag not in PUBLISHED_QUALITY_FLAGS
    ]


def verify_feature(properties: dict[str, Any]) -> list[str]:
    """Return a list of human-readable invariant violations for one feature."""
    seg = properties.get("segment_id", "?")
    return [
        *_verify_exposure_and_rate(seg, properties),
        *_verify_significance(seg, properties),
        *_verify_quality_flags(seg, properties),
    ]


def verify_dataset(geojson: dict[str, Any]) -> list[str]:
    """Return a list of human-readable invariant violations for a whole file.

    Checks the top-level `metadata` foreign member for the fields this
    plugin relies on, then every feature via `verify_feature`.
    """
    problems: list[str] = []
    metadata = geojson.get("metadata")
    if not metadata:
        problems.append("dataset: missing top-level 'metadata' foreign member")
    else:
        for key in ("schema_version", "significance", "privacy", "exposure_unit"):
            if not metadata.get(key):
                problems.append(f"dataset: metadata.{key} is missing or empty")

    features = geojson.get("features", [])
    if not features:
        problems.append("dataset: no features present")
    for feature in features:
        problems.extend(verify_feature(feature.get("properties", {})))

    return problems
