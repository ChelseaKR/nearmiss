"""Publishing is byte-for-byte deterministic, so `make reproduce` is meaningful."""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

from nearmiss.config import Config
from nearmiss.publish import publish


def test_publish_is_deterministic(config: Config, tmp_path: Path) -> None:
    cfg = dataclasses.replace(config, out_dir=tmp_path)
    first = publish(cfg)
    content1 = first.geojson_path.read_text(encoding="utf-8")
    meta1 = first.metadata_path.read_text(encoding="utf-8")
    corridors1 = first.corridor_geojson_path.read_text(encoding="utf-8")

    second = publish(cfg)
    content2 = second.geojson_path.read_text(encoding="utf-8")
    meta2 = second.metadata_path.read_text(encoding="utf-8")
    corridors2 = second.corridor_geojson_path.read_text(encoding="utf-8")

    assert content1 == content2
    assert meta1 == meta2
    assert corridors1 == corridors2
    assert first.geojson_sha256 == second.geojson_sha256
    assert first.corridor_count == second.corridor_count


def test_run_manifest_provenance_is_deterministic(config: Config, tmp_path: Path) -> None:
    """The <slug>.run.json provenance section + digest are the reproduce tripwire.

    They must be byte-stable across runs even though the timings sidecar is not —
    that separation is exactly why the digest can name *what* drifted without the
    unhashed wall-times ever breaking `make reproduce`.
    """
    cfg = dataclasses.replace(config, out_dir=tmp_path)
    first = publish(cfg)
    manifest1 = json.loads(first.manifest_path.read_text(encoding="utf-8"))

    second = publish(cfg)
    manifest2 = json.loads(second.manifest_path.read_text(encoding="utf-8"))

    assert manifest1["provenance"] == manifest2["provenance"]
    assert manifest1["manifest_digest"] == manifest2["manifest_digest"]
    assert first.manifest_digest == second.manifest_digest
    # The digest never covers the timings sidecar, so a slower run cannot flip it.
    assert "timings" in manifest1 and "timings" not in manifest1["provenance"]
