# SPDX-License-Identifier: Apache-2.0
"""nearmiss honest-symbology QGIS plugin.

`rules.py` and `verify.py` have no PyQGIS dependency and are safe to import
in a plain Python environment (used by the repo's pytest suite). `plugin.py`
and `qgis_layer.py` import `qgis.core`/`qgis.PyQt` and only work inside a
QGIS Python environment; they are imported lazily, from `classFactory`,
so that importing this package outside QGIS (e.g. to run `verify.py`) does
not require a QGIS install.
"""

from __future__ import annotations


def classFactory(iface):  # noqa: N802 — QGIS plugin API requires this exact name
    """Entry point QGIS calls to instantiate the plugin. See metadata.txt."""
    from .plugin import NearmissHonestPlugin

    return NearmissHonestPlugin(iface)
