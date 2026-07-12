"""Error handling, input guards, and the server's private-store block."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from nearmiss.config import load_config
from nearmiss.errors import ConfigError, NearmissError
from nearmiss.exposure import attach_exposure, corroboration, coverage, is_stale, is_usable
from nearmiss.loaders import load_reports, load_streets
from nearmiss.models import Exposure, ExposureReading
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


def _window_cfg(tmp_path: Path, start: str, end: str) -> Path:
    cfg = tmp_path / "city.toml"
    cfg.write_text(
        'city = "X"\nstreets = "s"\nreports = "r"\nexposure = "e"\n'
        f'[window]\nstart = "{start}"\nend = "{end}"\n',
        encoding="utf-8",
    )
    return cfg


def test_unparseable_window_date_raises_config_error(tmp_path: Path) -> None:
    with pytest.raises(ConfigError):
        load_config(_window_cfg(tmp_path, "2024-13-40", "2025-01-01"))


def test_reversed_window_raises_config_error(tmp_path: Path) -> None:
    with pytest.raises(ConfigError):
        load_config(_window_cfg(tmp_path, "2025-12-31", "2024-01-01"))


def test_valid_window_parses(tmp_path: Path) -> None:
    config = load_config(_window_cfg(tmp_path, "2024-01-01", "2025-12-31"))
    assert config.window_start == "2024-01-01"
    assert config.window_end == "2025-12-31"


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


def test_exposure_floor_treats_below_floor_as_unusable() -> None:
    # FIX-04 / METHODOLOGY §3.3: an estimate at/below the configured floor is
    # published "exposure unknown" rather than a giant, meaningless rate.
    low = Exposure("a", 5.0, "src", "2026-01-01")
    assert is_usable(low)  # no floor configured -> any positive estimate usable
    assert not is_usable(low, floor=10.0)
    assert is_usable(low, floor=4.9)


def test_coverage_respects_the_exposure_floor() -> None:
    attached: dict[str, Exposure | None] = {
        "a": Exposure("a", 100.0, "src", "2026-01-01"),
        "b": Exposure("b", 5.0, "src", "2026-01-01"),  # below floor
    }
    assert coverage(attached, floor=10.0) == pytest.approx(0.5)


def test_corroboration_omits_single_source_segments() -> None:
    exposure_map = {"a": Exposure("a", 100.0, "counts", "2026-01-01")}
    assert corroboration(exposure_map) == {}


def test_corroboration_omits_segments_with_fewer_than_two_positive_readings() -> None:
    # A "corroborating" reading of zero (or negative) contributes nothing to
    # compare against -> still nothing to corroborate, same as no sources at all.
    exposure_map = {
        "a": Exposure(
            "a",
            100.0,
            "counts",
            "2026-01-01",
            sources=(ExposureReading(0.0, "demand-model", "2026-01-01"),),
        )
    }
    assert corroboration(exposure_map) == {}


def test_corroboration_reports_agreement_ratio_across_sources() -> None:
    # A count station reads 100, a demand model on the same segment reads 50 ->
    # agreement ratio is min/max = 0.5, itself a finding (METHODOLOGY §3.1).
    exposure_map = {
        "a": Exposure(
            "a",
            100.0,
            "count-station",
            "2026-01-01",
            tier="observed",
            sources=(ExposureReading(50.0, "demand-model-v2", "2026-01-15", tier="modeled"),),
        )
    }
    assert corroboration(exposure_map)["a"] == pytest.approx(0.5)


def test_is_stale_flags_exposure_far_from_the_reference_date() -> None:
    assert is_stale("2020-01-01", "2026-01-01", threshold_days=365)
    assert not is_stale("2025-09-01", "2026-01-01", threshold_days=365)


def test_is_stale_is_false_for_unparseable_dates() -> None:
    assert not is_stale("not-a-date", "2026-01-01", threshold_days=365)


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
