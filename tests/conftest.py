"""Shared pytest fixtures: the demo config and a cached analysis bundle."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from nearmiss.config import Config, load_config
from nearmiss.engine import AnalysisBundle, build_analysis

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "davis-demo.toml"
REPORTS_PATH = ROOT / "tests" / "fixtures" / "davis" / "reports.json"


@pytest.fixture(scope="session")
def config() -> Config:
    return load_config(CONFIG_PATH)


@pytest.fixture(scope="session")
def bundle(config: Config) -> AnalysisBundle:
    return build_analysis(config)


@pytest.fixture(scope="session")
def a_valid_report() -> dict[str, object]:
    data = json.loads(REPORTS_PATH.read_text(encoding="utf-8"))
    return dict(data["reports"][0])
