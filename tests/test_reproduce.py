"""Publishing is byte-for-byte deterministic, so `make reproduce` is meaningful."""

from __future__ import annotations

import dataclasses
from pathlib import Path

from nearmiss.config import Config
from nearmiss.publish import publish


def test_publish_is_deterministic(config: Config, tmp_path: Path) -> None:
    cfg = dataclasses.replace(config, out_dir=tmp_path)
    first = publish(cfg)
    content1 = first.geojson_path.read_text(encoding="utf-8")
    meta1 = first.metadata_path.read_text(encoding="utf-8")

    second = publish(cfg)
    content2 = second.geojson_path.read_text(encoding="utf-8")
    meta2 = second.metadata_path.read_text(encoding="utf-8")

    assert content1 == content2
    assert meta1 == meta2
    assert first.geojson_sha256 == second.geojson_sha256
