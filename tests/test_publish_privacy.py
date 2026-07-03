"""Publishing never leaks a precise raw report (hard rule #4)."""

from __future__ import annotations

import json

import pytest

from nearmiss.config import Config
from nearmiss.engine import AnalysisBundle, load_city
from nearmiss.errors import PrivacyError
from nearmiss.publish import (
    assert_metadata_clean,
    assert_published_clean,
    build_geojson,
    publish,
)


def _geojson(bundle: AnalysisBundle) -> dict[str, object]:
    return build_geojson(bundle.result.segments, bundle.segments)


def _features(geojson: dict[str, object]) -> list[dict[str, object]]:
    feats = geojson["features"]
    assert isinstance(feats, list)
    out: list[dict[str, object]] = []
    for f in feats:
        assert isinstance(f, dict)
        out.append(f)
    return out


def _props(feature: dict[str, object]) -> dict[str, object]:
    p = feature["properties"]
    assert isinstance(p, dict)
    return p


def test_no_forbidden_keys_in_published_features(bundle: AnalysisBundle) -> None:
    text = json.dumps(_geojson(bundle))
    for forbidden in (
        "reporter_token",
        "occurred_at",
        "accuracy_m",
        "heading_deg",
        "mode",
        "severity",
    ):
        assert f'"{forbidden}"' not in text
    assert "reporter-hot-001" not in text


def test_assert_published_clean_passes_for_real_output(
    bundle: AnalysisBundle, config: Config
) -> None:
    assert_published_clean(_geojson(bundle), load_city(config).reports, config.min_publish_n)


def test_assert_published_clean_catches_a_leak(bundle: AnalysisBundle, config: Config) -> None:
    leaky = _geojson(bundle)
    _props(_features(leaky)[0])["reporter_token"] = "reporter-hot-001"
    with pytest.raises(PrivacyError):
        assert_published_clean(leaky, load_city(config).reports, config.min_publish_n)


def test_assert_published_clean_catches_min_occupancy_violation(
    bundle: AnalysisBundle, config: Config
) -> None:
    leaky = _geojson(bundle)
    _props(_features(leaky)[0])["report_count"] = 1  # below min_publish_n
    with pytest.raises(PrivacyError):
        assert_published_clean(leaky, load_city(config).reports, config.min_publish_n)


def test_k_anonymity_no_low_count_segment_is_published(
    bundle: AnalysisBundle, config: Config
) -> None:
    for p in (_props(f) for f in _features(_geojson(bundle))):
        rc = p["report_count"]
        assert isinstance(rc, int)
        assert rc == 0 or rc >= config.min_publish_n
    # The three planted single-report segments are withheld entirely.
    published_ids = {_props(f)["segment_id"] for f in _features(_geojson(bundle))}
    assert {"seg-04", "seg-08", "seg-11"}.isdisjoint(published_ids)


def test_small_n_hazard_breakdown_is_suppressed(bundle: AnalysisBundle) -> None:
    props = {_props(f)["segment_id"]: _props(f) for f in _features(_geojson(bundle))}
    # seg-01 has n=4 (< small_n) -> breakdown suppressed; seg-06 has n=6 -> present.
    assert props["seg-01"]["hazard_breakdown"] == {}
    assert props["seg-06"]["hazard_breakdown"] != {}


def test_published_geojson_is_self_describing(config: Config, tmp_path: object) -> None:
    import dataclasses
    from pathlib import Path

    assert isinstance(tmp_path, Path)
    result = publish(dataclasses.replace(config, out_dir=tmp_path))
    gj = json.loads(result.geojson_path.read_text(encoding="utf-8"))
    meta = gj["metadata"]
    assert meta["dataset_version"] == "0.1.0"
    assert meta["schema_version"] == "1.0.0"
    assert meta["license"] == "Apache-2.0"
    # The embedded metadata must also be privacy-clean.
    assert_metadata_clean(meta, load_city(config).reports)


def test_metadata_carries_no_coordinate_and_passes_gate(
    bundle: AnalysisBundle, config: Config, tmp_path: object
) -> None:
    import dataclasses
    from pathlib import Path

    assert isinstance(tmp_path, Path)
    cfg = dataclasses.replace(config, out_dir=tmp_path)
    result = publish(cfg)
    meta = json.loads(result.metadata_path.read_text(encoding="utf-8"))
    # The report-intensity peak is a segment id, not a coordinate.
    assert isinstance(meta["report_intensity_peak_segment"], str)
    assert "kde_peak" not in meta
    # And the metadata passes its own privacy gate.
    assert_metadata_clean(meta, load_city(config).reports)


def test_metadata_stamps_the_analysis_window(config: Config, tmp_path: object) -> None:
    import dataclasses
    from pathlib import Path

    assert isinstance(tmp_path, Path)
    cfg = dataclasses.replace(
        config, out_dir=tmp_path, window_start="2026-01-01", window_end="2026-12-31"
    )
    result = publish(cfg)
    meta = json.loads(result.metadata_path.read_text(encoding="utf-8"))
    assert meta["window"] == {"start": "2026-01-01", "end": "2026-12-31"}
    # The embedded FeatureCollection metadata carries the same window.
    gj = json.loads(result.geojson_path.read_text(encoding="utf-8"))
    assert gj["metadata"]["window"] == {"start": "2026-01-01", "end": "2026-12-31"}
    # Stamping the window must not breach the privacy gate.
    assert_metadata_clean(meta, load_city(config).reports)


def test_metadata_window_keys_present_when_unconfigured(config: Config, tmp_path: object) -> None:
    import dataclasses
    from pathlib import Path

    assert isinstance(tmp_path, Path)
    cfg = dataclasses.replace(config, out_dir=tmp_path, window_start=None, window_end=None)
    result = publish(cfg)
    meta = json.loads(result.metadata_path.read_text(encoding="utf-8"))
    # Keys are always present (null when unset) so the schema is stable.
    assert meta["window"] == {"start": None, "end": None}


def test_run_manifest_artifact_is_written_and_privacy_clean(
    config: Config, tmp_path: object
) -> None:
    """publish() drops a <slug>.run.json whose provenance passes the metadata gate."""
    import dataclasses
    from pathlib import Path

    assert isinstance(tmp_path, Path)
    cfg = dataclasses.replace(config, out_dir=tmp_path)
    result = publish(cfg)

    assert result.manifest_path.name.endswith(".run.json")
    assert result.manifest_path.is_file()
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    prov = manifest["provenance"]
    # Provenance is counts-and-hashes only — it passes the same privacy gate.
    assert_metadata_clean(prov, load_city(config).reports)
    # Input identity is by content hash, never by report content.
    assert set(prov["inputs"]) == {"streets", "reports", "exposure"}
    # No forbidden per-report key anywhere in the manifest.
    text = json.dumps(manifest)
    for forbidden in ("reporter_token", "occurred_at", "note", "heading_deg", "severity"):
        assert f'"{forbidden}"' not in text


def test_committed_configs_keep_moderation_store_gitignored() -> None:
    """HR4: every committed config's submissions_dir must resolve to a gitignored
    path. Pending submissions are precise private reports; if a config's
    submissions_dir landed on a tracked path (e.g. the bare default resolving next
    to the config dir), `git add .` could leak them. This locks that invariant."""
    import subprocess
    from pathlib import Path

    from nearmiss.config import load_config

    repo_root = Path(__file__).resolve().parent.parent
    configs = sorted((repo_root / "config").glob("*.toml"))
    assert configs, "expected committed configs under config/"
    for cfg_path in configs:
        cfg = load_config(cfg_path)
        probe = cfg.submissions_dir / "queue.json"
        proc = subprocess.run(
            ["git", "check-ignore", "-q", str(probe)],
            cwd=repo_root,
            check=False,
        )
        assert proc.returncode == 0, (
            f"{cfg_path.name}: submissions_dir {cfg.submissions_dir} is NOT gitignored — "
            "pending submissions could be committed (HR4 violation)"
        )
