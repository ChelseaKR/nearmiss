# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import json
from pathlib import Path

from nearmiss_honest import verify

SAMPLE_DIR = Path(__file__).resolve().parent.parent / "nearmiss_honest" / "sample_data"


def test_main_returns_zero_for_clean_bundled_dataset(capsys):
    rc = verify.main([str(SAMPLE_DIR / "davis.geojson")])
    assert rc == 0
    assert "OK" in capsys.readouterr().out


def test_main_returns_nonzero_for_violation(tmp_path, capsys):
    bad = {
        "metadata": {
            "schema_version": "1.0.0",
            "significance": "x",
            "privacy": "y",
            "exposure_unit": "trips",
        },
        "features": [
            {
                "properties": {
                    "segment_id": "seg-bad",
                    "exposure_estimate": None,
                    "rate": 5.0,  # HR1 violation: rate present without exposure
                    "rate_ci_low": None,
                    "rate_ci_high": None,
                    "confidence_label": "certain",
                    "getis_ord_z": None,
                    "getis_ord_significant": None,
                }
            }
        ],
    }
    path = tmp_path / "bad.geojson"
    path.write_text(json.dumps(bad), encoding="utf-8")

    rc = verify.main([str(path)])
    assert rc == 1
    assert "FAIL" in capsys.readouterr().err


def test_main_returns_2_for_missing_file(tmp_path, capsys):
    rc = verify.main([str(tmp_path / "does-not-exist.geojson")])
    assert rc == 2
    assert "error" in capsys.readouterr().err
