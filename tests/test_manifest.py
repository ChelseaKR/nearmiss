"""The run manifest is deterministic in provenance, honest in hashes, private in content.

FIX-09. The manifest turns a run into a diffable provenance artifact. These tests
pin the three properties that make it trustworthy:

* determinism — two builds over the same fixtures yield an identical ``provenance``
  section and ``manifest_digest``, and the digest deliberately ignores the
  wall-time ``timings`` sidecar (so ``make reproduce`` stays byte-stable);
* hash correctness — ``sha256_file`` is a real SHA256 of the file's bytes;
* privacy — the provenance section is counts-and-hashes only: no report note,
  reporter token, or raw coordinate ever reaches it (hard rule #4).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from nearmiss.config import Config
from nearmiss.engine import build_analysis, load_city
from nearmiss.manifest import build_manifest, canonical_json, effective_config, sha256_file
from nearmiss.publish import assert_metadata_clean


def _inputs(config: Config) -> dict[str, Path]:
    return {
        "streets": config.streets_path,
        "reports": config.reports_path,
        "exposure": config.exposure_path,
    }


# --------------------------------------------------------------------------- #
# Determinism
# --------------------------------------------------------------------------- #
def test_two_builds_yield_identical_provenance_and_digest(config: Config) -> None:
    inputs = _inputs(config)
    first = build_manifest(config, inputs, build_analysis(config).stages, "0.1.0")
    second = build_manifest(config, inputs, build_analysis(config).stages, "0.1.0")

    assert first["provenance"] == second["provenance"]
    assert first["manifest_digest"] == second["manifest_digest"]
    # The digest is exactly the SHA256 of the canonical provenance JSON.
    expect = hashlib.sha256(canonical_json(first["provenance"]).encode("utf-8")).hexdigest()
    assert first["manifest_digest"] == expect


def test_digest_ignores_timings_sidecar(config: Config) -> None:
    """Identical counts + different wall-times => identical provenance and digest."""
    inputs = _inputs(config)
    slow = [{"stage": "pipeline", "counts": {"reports_in": 3}, "ms": 1.0}]
    fast = [{"stage": "pipeline", "counts": {"reports_in": 3}, "ms": 987.6}]

    m_slow = build_manifest(config, inputs, slow, "0.1.0")
    m_fast = build_manifest(config, inputs, fast, "0.1.0")

    assert m_slow["provenance"] == m_fast["provenance"]
    assert m_slow["manifest_digest"] == m_fast["manifest_digest"]
    # The timings section DID change — proving it is a live, unhashed sidecar.
    assert m_slow["timings"] != m_fast["timings"]
    assert m_slow["timings"] == {"stages": [{"stage": "pipeline", "ms": 1.0}]}


def test_stage_counts_are_carried_into_provenance(config: Config) -> None:
    inputs = _inputs(config)
    stages = build_analysis(config).stages
    manifest = build_manifest(config, inputs, stages, "0.1.0")
    prov = manifest["provenance"]
    assert isinstance(prov, dict)

    prov_stages = {s["stage"]: s["counts"] for s in prov["stages"]}
    assert set(prov_stages) == {"load", "pipeline", "analyze"}
    # The pipeline stage carries the counts the pipeline already returns.
    assert "reports_in" in prov_stages["pipeline"]
    assert "duplicates_removed" in prov_stages["pipeline"]
    # None of the provenance stage records carry a wall-time.
    for record in prov["stages"]:
        assert "ms" not in record


# --------------------------------------------------------------------------- #
# Hash correctness
# --------------------------------------------------------------------------- #
def test_sha256_file_matches_hashlib_on_a_tiny_fixture(tmp_path: Path) -> None:
    payload = b"near-miss provenance\n"
    p = tmp_path / "tiny.txt"
    p.write_bytes(payload)
    assert sha256_file(p) == hashlib.sha256(payload).hexdigest()


def test_input_hashes_match_the_files_on_disk(config: Config) -> None:
    inputs = _inputs(config)
    manifest = build_manifest(config, inputs, build_analysis(config).stages, "0.1.0")
    prov = manifest["provenance"]
    assert isinstance(prov, dict)
    block = prov["inputs"]
    assert isinstance(block, dict)
    assert set(block) == {"streets", "reports", "exposure"}
    for name, path in inputs.items():
        assert block[name]["sha256"] == sha256_file(path)
        assert block[name]["filename"] == path.name


def test_config_digest_changes_when_a_knob_changes(config: Config) -> None:
    import dataclasses

    inputs = _inputs(config)
    base = build_manifest(config, inputs, [], "0.1.0")
    tweaked_cfg = dataclasses.replace(config, min_publish_n=config.min_publish_n + 1)
    tweaked = build_manifest(tweaked_cfg, inputs, [], "0.1.0")

    base_prov = base["provenance"]
    tweaked_prov = tweaked["provenance"]
    assert isinstance(base_prov, dict)
    assert isinstance(tweaked_prov, dict)
    assert base_prov["config_digest"] != tweaked_prov["config_digest"]
    assert base["manifest_digest"] != tweaked["manifest_digest"]


def test_effective_config_excludes_absolute_paths_and_coordinates(config: Config) -> None:
    eff = effective_config(config)
    assert "streets_path" not in eff
    assert "reports_path" not in eff
    assert "out_dir" not in eff
    # The projection reference point is a literal coordinate — kept out on purpose.
    assert "ref_lat" not in eff
    assert "ref_lon" not in eff
    # But the output-shaping knobs ARE present.
    assert eff["min_publish_n"] == config.min_publish_n
    assert eff["rate_per"] == config.rate_per


# --------------------------------------------------------------------------- #
# Privacy (hard rule #4): counts and hashes only
# --------------------------------------------------------------------------- #
def test_provenance_passes_the_privacy_gate(config: Config) -> None:
    inputs = _inputs(config)
    manifest = build_manifest(config, inputs, build_analysis(config).stages, "0.1.0")
    prov = manifest["provenance"]
    assert isinstance(prov, dict)
    # Would raise PrivacyError if a forbidden key or a raw coordinate leaked.
    assert_metadata_clean(prov, load_city(config).reports)


def test_manifest_carries_no_report_text_or_coordinate(config: Config) -> None:
    inputs = _inputs(config)
    manifest = build_manifest(config, inputs, build_analysis(config).stages, "0.1.0")
    blob = json.dumps(manifest)  # the WHOLE manifest, timings included
    for r in load_city(config).reports:
        if r.note:
            assert r.note not in blob
        if r.reporter_token:
            assert r.reporter_token not in blob
        # No raw per-report coordinate (both components) appears.
        assert not (f"{round(r.lat, 5)}" in blob and f"{round(r.lon, 5)}" in blob)
