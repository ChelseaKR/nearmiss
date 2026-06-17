"""Error handling, input guards, and the server's private-store block."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from nearmiss.config import load_config
from nearmiss.errors import ConfigError, NearmissError
from nearmiss.exposure import attach_exposure, coverage
from nearmiss.loaders import load_reports, load_streets
from nearmiss.models import Exposure
from nearmiss.server import is_blocked_path


def test_missing_input_file_raises_nearmiss_error(tmp_path: Path) -> None:
    with pytest.raises(NearmissError):
        load_reports(tmp_path / "does-not-exist.json")


def test_single_vertex_linestring_is_rejected(tmp_path: Path) -> None:
    bad = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "LineString", "coordinates": [[-121.7, 38.5]]},
                "properties": {"segment_id": "s1"},
            }
        ],
    }
    p = tmp_path / "streets.geojson"
    p.write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(NearmissError):
        load_streets(p)


def test_non_numeric_threshold_raises_config_error(tmp_path: Path) -> None:
    cfg = tmp_path / "city.toml"
    cfg.write_text(
        'city = "X"\nstreets = "s"\nreports = "r"\nexposure = "e"\n'
        '[thresholds]\nsnap_max_m = "not-a-number"\n',
        encoding="utf-8",
    )
    with pytest.raises(ConfigError):
        load_config(cfg)


def test_total_exposure_mismatch_raises(config: object, tmp_path: Path) -> None:
    import dataclasses

    from nearmiss.config import Config
    from nearmiss.engine import build_analysis

    assert isinstance(config, Config)
    exp = tmp_path / "exp.json"
    exp.write_text(
        json.dumps(
            {
                "segments": [
                    {"segment_id": "NOPE-1", "estimate": 100.0, "source": "x", "date": "2026-01-01"}
                ]
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(NearmissError):
        build_analysis(dataclasses.replace(config, exposure_path=exp))


def test_coverage_counts_only_usable_exposure() -> None:
    attached = attach_exposure(
        ["a", "b", "c"],
        {
            "a": Exposure("a", 100.0, "src", "2026-01-01"),
            "b": Exposure("b", 0.0, "src", "2026-01-01"),  # zero -> not usable
        },
    )
    # a usable, b present-but-zero, c absent -> only 1 of 3 usable.
    assert coverage(attached) == pytest.approx(1 / 3)


@pytest.mark.parametrize(
    "path,blocked",
    [
        ("/data/raw/davis/reports.json", True),
        ("/data/raw", True),
        ("/.git/config", True),
        ("/.env", True),
        ("/web/index.html", False),
        ("/data/published/davis.geojson", False),
    ],
)
def test_server_blocks_private_paths(path: str, blocked: bool) -> None:
    assert is_blocked_path(path) is blocked
