# SPDX-License-Identifier: Apache-2.0
"""PyQGIS glue: turn the pure decisions in `rules.py` into a real QGIS layer.

This module imports `qgis.core` / `qgis.PyQt` and is only importable inside a
QGIS Python environment (QGIS Desktop's Python console, or `qgis_process`).
It is deliberately thin — every judgment call about what counts as "honest"
lives in `rules.py`, which has no PyQGIS dependency and is unit-tested
directly with plain pytest. This module's job is limited to "how do I
express that decision as a QgsRuleBasedRenderer / maptip / layer metadata."

NOTE for maintainers: this module cannot be exercised by the repo's plain
pytest suite because PyQGIS is only available inside a QGIS install (there is
no pip-installable `qgis` package). Before publishing a release, smoke-test
it manually in QGIS Desktop's Python console:
`from nearmiss_honest.qgis_layer import apply_honest_style` against the
bundled `sample_data/davis.geojson`, per README.md's manual QA checklist.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from qgis.core import (
    Qgis,
    QgsLayerMetadata,
    QgsLineSymbol,
    QgsMarkerSymbol,
    QgsMessageLog,
    QgsRuleBasedRenderer,
    QgsSimpleFillSymbolLayer,
    QgsSimpleLineSymbolLayer,
    QgsSimpleMarkerSymbolLayerBase,
    QgsSymbol,
    QgsVectorLayer,
    QgsWkbTypes,
)
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QColor

from .rules import (
    PATTERN_NOT_SIGNIFICANT,
    PATTERN_SIGNIFICANT_COLD,
    PATTERN_SIGNIFICANT_HOT,
    PATTERN_UNKNOWN,
    compute_rate_breaks,
    verify_dataset,
)

LOG_TAG = "nearmiss-honest"

# Sequential rate ramp (light -> dark). Deliberately NOT a red/green ramp:
# danger/significance is conveyed by PATTERN + text (below), not by this
# color alone, so the map still reads correctly for color-vision deficiency
# and in grayscale print.
_RATE_RAMP = ["#fee5d9", "#fcae91", "#fb6a4a", "#de2d26", "#a50f15"]
_UNKNOWN_COLOR = "#969696"  # neutral gray, visually distinct from the ramp

# Significance -> pattern, expressed per geometry type. A LineString segment
# (the default aggregation unit) encodes pattern as pen/line style; a Point
# cell encodes it as marker shape. Both are distinguishable in grayscale and
# without color vision, and both are always paired with the tooltip's text
# label (rules.tooltip_html / significance_marker) rather than standing
# alone.
_LINE_PEN_STYLE = {
    PATTERN_SIGNIFICANT_HOT: Qt.PenStyle.DashDotLine,
    PATTERN_SIGNIFICANT_COLD: Qt.PenStyle.DashLine,
    PATTERN_NOT_SIGNIFICANT: Qt.PenStyle.SolidLine,
    PATTERN_UNKNOWN: Qt.PenStyle.DotLine,
}
_LINE_WIDTH_MM = {
    PATTERN_SIGNIFICANT_HOT: 1.4,
    PATTERN_SIGNIFICANT_COLD: 1.2,
    PATTERN_NOT_SIGNIFICANT: 0.8,
    PATTERN_UNKNOWN: 0.6,
}
_MARKER_SHAPE = {
    PATTERN_SIGNIFICANT_HOT: QgsSimpleMarkerSymbolLayerBase.Shape.Star,
    PATTERN_SIGNIFICANT_COLD: QgsSimpleMarkerSymbolLayerBase.Shape.Diamond,
    PATTERN_NOT_SIGNIFICANT: QgsSimpleMarkerSymbolLayerBase.Shape.Circle,
    PATTERN_UNKNOWN: QgsSimpleMarkerSymbolLayerBase.Shape.Cross2,
}

# (expression fragment, pattern key, legend suffix) for the three
# significance states a feature with a known rate can be in. A feature can
# only be in one of these AND ALSO have getis_ord_z is null iff rate is
# null (schema-guaranteed), so these three plus the "rate is null" rule
# below are exhaustive and mutually exclusive.
_SIGNIFICANCE_BRANCHES = [
    (
        '"getis_ord_significant" AND "getis_ord_z" > 0',
        PATTERN_SIGNIFICANT_HOT,
        "significant hot spot",
    ),
    (
        '"getis_ord_significant" AND "getis_ord_z" < 0',
        PATTERN_SIGNIFICANT_COLD,
        "significant cold spot",
    ),
    (
        'NOT "getis_ord_significant"',
        PATTERN_NOT_SIGNIFICANT,
        "not significant",
    ),
]


def load_geojson_layer(path: str, layer_name: str | None = None) -> QgsVectorLayer:
    """Load a nearmiss published GeoJSON as a QgsVectorLayer."""
    name = layer_name or Path(path).stem
    layer = QgsVectorLayer(path, name, "ogr")
    if not layer.isValid():
        raise ValueError(f"Could not load '{path}' as a vector layer")
    return layer


def read_geojson(path: str) -> dict[str, Any]:
    with Path(path).open(encoding="utf-8") as fh:
        return json.load(fh)


def apply_honest_style(layer: QgsVectorLayer, dataset: dict[str, Any]) -> None:
    """Build and apply the honest-symbology renderer, maptip, and metadata.

    A single QgsRuleBasedRenderer drives both axes at once:
      * color = rate class, computed off `rate` (never `report_count`) with
        `null` (exposure unknown) as its own always-present, neutral-gray,
        distinctly-patterned class (HR1) — never folded into the coolest
        color on the ramp.
      * pattern (line style / marker shape) = spatial-significance state,
        so significance is legible even in grayscale or without color
        vision (never color-alone).
    """
    root_rule = QgsRuleBasedRenderer.Rule(None)

    unknown_rule = QgsRuleBasedRenderer.Rule(
        _build_symbol(layer.geometryType(), _UNKNOWN_COLOR, PATTERN_UNKNOWN),
        label="exposure unknown",
        filterExp='"rate" IS NULL',
    )
    root_rule.appendChild(unknown_rule)

    breaks = compute_rate_breaks(dataset.get("features", []))
    lower = 0.0
    for i, upper in enumerate(breaks):
        color = _RATE_RAMP[min(i, len(_RATE_RAMP) - 1)]
        for sig_expr, pattern, sig_label in _SIGNIFICANCE_BRANCHES:
            filter_expr = (
                f'"rate" IS NOT NULL AND "rate" > {lower!r} '
                f'AND "rate" <= {upper!r} AND ({sig_expr})'
            )
            rule = QgsRuleBasedRenderer.Rule(
                _build_symbol(layer.geometryType(), color, pattern),
                label=f"rate {lower:g}–{upper:g}, {sig_label}",
                filterExp=filter_expr,
            )
            root_rule.appendChild(rule)
        lower = upper

    layer.setRenderer(QgsRuleBasedRenderer(root_rule))
    _set_maptip(layer)
    _load_metadata(layer, dataset.get("metadata", {}))


def _build_symbol(geometry_type, color_hex: str, pattern: str) -> QgsSymbol:
    color = QColor(color_hex)

    if geometry_type == QgsWkbTypes.GeometryType.LineGeometry:
        symbol = QgsLineSymbol.createSimple({"color": color_hex})
        line_layer = symbol.symbolLayer(0)
        if isinstance(line_layer, QgsSimpleLineSymbolLayer):
            line_layer.setColor(color)
            line_layer.setPenStyle(_LINE_PEN_STYLE[pattern])
            line_layer.setWidth(_LINE_WIDTH_MM[pattern])
        return symbol

    if geometry_type == QgsWkbTypes.GeometryType.PointGeometry:
        symbol = QgsMarkerSymbol.createSimple({"color": color_hex})
        marker_layer = symbol.symbolLayer(0)
        marker_layer.setColor(color)
        marker_layer.setShape(_MARKER_SHAPE[pattern])
        return symbol

    # Polygon or unknown geometry is not part of the published schema
    # (LineString segments or Point cells only), but degrade gracefully
    # with a fill + brush pattern rather than raising.
    symbol = QgsSymbol.defaultSymbol(geometry_type)
    fill_layer = symbol.symbolLayer(0)
    if isinstance(fill_layer, QgsSimpleFillSymbolLayer):
        fill_layer.setColor(color)
    return symbol


def _set_maptip(layer: QgsVectorLayer) -> None:
    """Install an HTML maptip mirroring `rules.tooltip_html`'s content.

    QGIS maptips are field-expression templates evaluated per-feature by
    QGIS itself, not Python callbacks, so this is a QGIS expression string
    that mirrors `tooltip_html`'s fields rather than a call into it.
    `tests/test_rules.py` pins the Python function's output so a future
    change to the tooltip's fields has a test to update on both sides.
    """
    template = (
        '<b>[% coalesce("name", "segment_id", \'unnamed segment\') %]</b><br/>'
        'report_count (volume, not danger): [% "report_count" %]<br/>'
        '[% CASE WHEN "exposure_estimate" IS NULL '
        "THEN 'exposure: unknown (no denominator available)' "
        "ELSE 'exposure: ' || \"exposure_estimate\" || "
        "' (source: ' || coalesce(\"exposure_source\", 'unknown') || "
        "', as of ' || coalesce(\"exposure_date\", 'unknown') || ')' END %]<br/>"
        '[% CASE WHEN "rate" IS NULL '
        "THEN 'rate: exposure unknown' "
        "ELSE 'rate: ' || \"rate\" || ' (' || coalesce(\"confidence_label\", '?') || "
        "'), 95% CI ' || coalesce(\"rate_ci_low\", 0) || '–' || "
        "coalesce(\"rate_ci_high\", 0) || ', n=' || coalesce(\"n\", '?') END %]<br/>"
        '[% CASE WHEN "getis_ord_significant" IS NULL THEN '
        "'significance: not evaluated (exposure unknown)' "
        'WHEN "getis_ord_significant" AND "getis_ord_z" > 0 THEN '
        "'significance: significant hot spot' "
        'WHEN "getis_ord_significant" AND "getis_ord_z" < 0 THEN '
        "'significance: significant cold spot' "
        "ELSE 'significance: not significant at threshold' END %]<br/>"
        "quality flags: [% array_to_string(\"quality_flags\", ', ', 'none') %]"
    )
    layer.setMapTipTemplate(template)


def _load_metadata(layer: QgsVectorLayer, metadata: dict[str, Any]) -> None:
    """Copy the GeoJSON `metadata` foreign member into QGIS layer metadata
    and custom properties so it survives saving a `.qgs`/`.qgz` project and
    is visible from Layer Properties without digging through the raw file.
    """
    layer.setCustomProperty("nearmiss_honest/metadata_json", json.dumps(metadata))
    layer.setCustomProperty(
        "nearmiss_honest/significance_statement", metadata.get("significance", "")
    )
    layer.setCustomProperty("nearmiss_honest/privacy_statement", metadata.get("privacy", ""))

    qmd = QgsLayerMetadata()
    qmd.setTitle(f"nearmiss — {metadata.get('city', layer.name())}")
    abstract_lines = [
        metadata.get("dataset_note") or "",
        f"Exposure unit: {metadata.get('exposure_unit', 'unknown')}",
        f"Significance method: {metadata.get('significance', 'unknown')}",
        f"Privacy: {metadata.get('privacy', 'unknown')}",
        f"Schema: {metadata.get('schema_doc', 'unknown')} (v{metadata.get('schema_version', '?')})",
    ]
    qmd.setAbstract("\n".join(line for line in abstract_lines if line))
    if metadata.get("license"):
        qmd.setLicenses([metadata["license"]])
    layer.setMetadata(qmd)


def run_verifier_and_log(path: str, dataset: dict[str, Any]) -> list[str]:
    """Run rules.verify_dataset and push any violations to the QGIS log."""
    problems = verify_dataset(dataset)
    if problems:
        QgsMessageLog.logMessage(
            f"{path}: {len(problems)} honest-symbology invariant violation(s) found:\n"
            + "\n".join(f"  - {p}" for p in problems),
            LOG_TAG,
            level=Qgis.MessageLevel.Warning,
        )
    else:
        QgsMessageLog.logMessage(
            f"{path}: no honest-symbology invariant violations found",
            LOG_TAG,
            level=Qgis.MessageLevel.Info,
        )
    return problems


__all__ = [
    "apply_honest_style",
    "load_geojson_layer",
    "read_geojson",
    "run_verifier_and_log",
]
