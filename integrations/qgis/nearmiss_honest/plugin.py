# SPDX-License-Identifier: Apache-2.0
"""QGIS plugin entry point: menu action to load a nearmiss GeoJSON with
honest symbology pre-wired (EXP-11).

See rules.py for the symbology decisions, qgis_layer.py for how they are
expressed as a QGIS renderer/maptip/layer metadata, and README.md for what
"honest" means here and how to try it against the bundled sample data.
"""

from __future__ import annotations

from pathlib import Path

from qgis.core import Qgis, QgsProject
from qgis.PyQt.QtWidgets import QAction, QFileDialog

from .qgis_layer import apply_honest_style, load_geojson_layer, read_geojson, run_verifier_and_log

SAMPLE_DATA_DIR = Path(__file__).parent / "sample_data"


class NearmissHonestPlugin:
    """QGIS plugin: 'Load honest nearmiss dataset...' menu action."""

    MENU_NAME = "&nearmiss (honest symbology)"

    def __init__(self, iface):
        self.iface = iface
        self.actions: list[QAction] = []

    def initGui(self) -> None:  # noqa: N802 — QGIS plugin API requires this exact name
        load_action = QAction("Load honest nearmiss dataset…", self.iface.mainWindow())
        load_action.triggered.connect(self.load_dataset)
        self.iface.addPluginToMenu(self.MENU_NAME, load_action)
        self.iface.addToolBarIcon(load_action)
        self.actions.append(load_action)

        sample_path = SAMPLE_DATA_DIR / "davis.geojson"
        sample_action = QAction("Load bundled sample data (Davis)…", self.iface.mainWindow())
        sample_action.triggered.connect(lambda: self.load_dataset(sample_path))
        self.iface.addPluginToMenu(self.MENU_NAME, sample_action)
        self.actions.append(sample_action)

    def unload(self) -> None:
        for action in self.actions:
            self.iface.removePluginMenu(self.MENU_NAME, action)
            self.iface.removeToolBarIcon(action)
        self.actions.clear()

    def load_dataset(self, path: str | Path | None = None) -> None:
        if path is None:
            chosen, _ = QFileDialog.getOpenFileName(
                self.iface.mainWindow(),
                "Load nearmiss GeoJSON",
                str(SAMPLE_DATA_DIR),
                "GeoJSON (*.geojson *.json)",
            )
            if not chosen:
                return
            path = chosen
        path = str(path)

        try:
            dataset = read_geojson(path)
            layer = load_geojson_layer(path)
        except (OSError, ValueError) as exc:
            self.iface.messageBar().pushMessage(
                "nearmiss", f"Could not load '{path}': {exc}", level=Qgis.MessageLevel.Critical
            )
            return

        apply_honest_style(layer, dataset)
        problems = run_verifier_and_log(path, dataset)

        QgsProject.instance().addMapLayer(layer)

        if problems:
            self.iface.messageBar().pushMessage(
                "nearmiss",
                f"Loaded '{layer.name()}' with {len(problems)} honest-symbology invariant "
                "warning(s) — see the QGIS log panel ('nearmiss-honest') for details.",
                level=Qgis.MessageLevel.Warning,
            )
        else:
            self.iface.messageBar().pushMessage(
                "nearmiss",
                f"Loaded '{layer.name()}' with honest symbology "
                "(rate-not-count, CI tooltips, significance-as-pattern).",
                level=Qgis.MessageLevel.Success,
            )
