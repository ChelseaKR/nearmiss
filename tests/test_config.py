"""Strict config validation (FIX-08).

A config is data, not code, so a typo like ``fdr_aplha`` or an out-of-range
threshold must fail loudly at load time rather than silently running defaults
(dependability / data integrity — see docs METHODOLOGY).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from nearmiss.config import load_config
from nearmiss.errors import ConfigError

_BASE_LINES = (
    'city = "Testville"',
    'streets = "streets.geojson"',
    'reports = "reports.json"',
    'exposure = "exposure.json"',
)


def _write_config(tmp_path: Path, *, top: str = "", thresholds: str = "") -> Path:
    """Write a minimal valid TOML config, optionally with extra top-level or
    threshold lines appended. Input paths need not exist: load_config only
    resolves them, it does not read them."""
    lines = list(_BASE_LINES)
    if top:
        lines.append(top)
    if thresholds:
        lines.extend(["", "[thresholds]", thresholds])
    cfg = tmp_path / "city.toml"
    cfg.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return cfg


def test_valid_config_loads(tmp_path: Path) -> None:
    cfg = load_config(_write_config(tmp_path))
    assert cfg.city == "Testville"
    assert cfg.fdr_alpha == 0.05  # default applied


def test_unknown_top_level_key_raises(tmp_path: Path) -> None:
    cfg = _write_config(tmp_path, top='citty = "oops"')
    with pytest.raises(ConfigError, match="citty"):
        load_config(cfg)


def test_misspelled_threshold_key_suggests_correction(tmp_path: Path) -> None:
    cfg = _write_config(tmp_path, thresholds="fdr_aplha = 0.05")
    with pytest.raises(ConfigError, match="did you mean 'fdr_alpha'"):
        load_config(cfg)


@pytest.mark.parametrize("value", ["0", "1", "1.5"])
def test_fdr_alpha_out_of_range_raises(tmp_path: Path, value: str) -> None:
    cfg = _write_config(tmp_path, thresholds=f"fdr_alpha = {value}")
    with pytest.raises(ConfigError, match="fdr_alpha"):
        load_config(cfg)


def test_min_publish_n_too_small_raises(tmp_path: Path) -> None:
    cfg = _write_config(tmp_path, thresholds="min_publish_n = 1")
    with pytest.raises(ConfigError, match="min_publish_n"):
        load_config(cfg)


def test_kde_grid_too_small_raises(tmp_path: Path) -> None:
    cfg = _write_config(tmp_path, thresholds="kde_grid = 1")
    with pytest.raises(ConfigError, match="kde_grid"):
        load_config(cfg)


def test_confidence_z_zero_raises(tmp_path: Path) -> None:
    cfg = _write_config(tmp_path, thresholds="confidence_z = 0")
    with pytest.raises(ConfigError, match="confidence_z"):
        load_config(cfg)
