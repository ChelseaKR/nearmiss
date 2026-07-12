# SPDX-License-Identifier: Apache-2.0
"""Make the `nearmiss_honest` package importable without installing it.

`rules.py` and `verify.py` have no PyQGIS dependency, so they can be
exercised by plain pytest; this conftest just puts `integrations/qgis` on
sys.path so `import nearmiss_honest` resolves without an editable install
(the plugin is distributed as a QGIS plugin zip, not a pip package).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
