"""EXP-10 conformance verifier: the committed datasets pass; a corrupted fork fails each rule.

Two guarantees, matching the excellence bar in `docs/ideation/03-expansions.md` (EXP-10):

1. Both committed published datasets (`data/published/davis.geojson`,
   `riverside.geojson`) pass all five hard rules.
2. A deliberately corrupted artifact — built by mutating a loaded copy of
   `davis.geojson` — fails on *each* of the five rules individually. Every corruption
   starts from the clean dataset and breaks exactly one rule; for HR1-HR4 the sidecar
   hash is recomputed so HR5 stays green and the failure is isolated to the targeted
   rule.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
PUBLISHED = ROOT / "data" / "published"


def _load_tool() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "verify_dataset", ROOT / "tools" / "verify_dataset.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


vd = _load_tool()


# --- Guarantee 1: the committed datasets pass -----------------------------------


@pytest.mark.parametrize("slug", ["davis", "riverside"])
def test_committed_dataset_passes(slug: str) -> None:
    verdict = vd.verify_artifact(PUBLISHED / f"{slug}.geojson")
    assert verdict["verdict"] == "pass", verdict["rules"]
    assert all(rule["pass"] for rule in verdict["rules"].values())
    # The sidecar is auto-discovered next to the GeoJSON.
    assert verdict["sidecar"] == str(PUBLISHED / f"{slug}.metadata.json")


def test_verdict_carries_the_scope_caveat() -> None:
    verdict = vd.verify_artifact(PUBLISHED / "davis.geojson")
    assert "artifact" in verdict["note"].lower()
    assert "publisher" in verdict["note"].lower()


# --- Guarantee 2: a corrupted fork fails each rule individually ------------------


def _clean_geojson() -> dict[str, Any]:
    data: dict[str, Any] = json.loads((PUBLISHED / "davis.geojson").read_text(encoding="utf-8"))
    return data


def _clean_sidecar() -> dict[str, Any]:
    data: dict[str, Any] = json.loads(
        (PUBLISHED / "davis.metadata.json").read_text(encoding="utf-8")
    )
    return data


def _first_feature_with_rate(geojson: dict[str, Any]) -> dict[str, Any]:
    for feature in geojson["features"]:
        if feature["properties"].get("rate") is not None:
            result: dict[str, Any] = feature
            return result
    raise AssertionError("fixture has no feature with a rate")


def _run(
    tmp_path: Path,
    geojson: dict[str, Any],
    sidecar: dict[str, Any] | None,
    *,
    recompute_hash: bool,
) -> dict[str, Any]:
    """Write the (possibly mutated) artifact to tmp and verify it.

    When ``recompute_hash`` is set, the sidecar's ``geojson_sha256`` is refreshed to
    match the bytes written, so HR5 stays green and any failure is attributable to the
    rule the caller deliberately broke.
    """
    geojson_path = tmp_path / "fork.geojson"
    payload = json.dumps(geojson, ensure_ascii=False).encode("utf-8")
    geojson_path.write_bytes(payload)

    if sidecar is not None:
        if recompute_hash:
            sidecar = {**sidecar, "geojson_sha256": hashlib.sha256(payload).hexdigest()}
        (tmp_path / "fork.metadata.json").write_text(
            json.dumps(sidecar, ensure_ascii=False), encoding="utf-8"
        )
    verdict: dict[str, Any] = vd.verify_artifact(geojson_path)
    return verdict


def test_clean_copy_passes_when_rehashed(tmp_path: Path) -> None:
    # Sanity: a faithful copy written by the test harness passes, so any failure below
    # is the injected corruption and not an artifact of copying/hashing.
    verdict = _run(tmp_path, _clean_geojson(), _clean_sidecar(), recompute_hash=True)
    assert verdict["verdict"] == "pass", verdict["rules"]


def test_hr1_fails_when_rate_loses_its_denominator(tmp_path: Path) -> None:
    geojson = _clean_geojson()
    _first_feature_with_rate(geojson)["properties"]["exposure_estimate"] = None
    verdict = _run(tmp_path, geojson, _clean_sidecar(), recompute_hash=True)
    assert verdict["rules"]["HR1"]["pass"] is False
    assert verdict["verdict"] == "fail"


def test_hr1_fails_on_a_danger_named_property(tmp_path: Path) -> None:
    geojson = _clean_geojson()
    geojson["features"][0]["properties"]["danger_score"] = 99
    verdict = _run(tmp_path, geojson, _clean_sidecar(), recompute_hash=True)
    assert verdict["rules"]["HR1"]["pass"] is False


def test_hr2_fails_when_rate_leaves_its_interval(tmp_path: Path) -> None:
    geojson = _clean_geojson()
    props = _first_feature_with_rate(geojson)["properties"]
    props["rate_ci_low"] = props["rate"] + 1.0  # low bound above the point estimate
    verdict = _run(tmp_path, geojson, _clean_sidecar(), recompute_hash=True)
    assert verdict["rules"]["HR2"]["pass"] is False
    assert verdict["verdict"] == "fail"


def test_hr3_fails_when_bias_statement_is_dropped(tmp_path: Path) -> None:
    geojson = _clean_geojson()
    geojson["metadata"]["privacy"] = ""
    verdict = _run(tmp_path, geojson, _clean_sidecar(), recompute_hash=True)
    assert verdict["rules"]["HR3"]["pass"] is False
    assert verdict["verdict"] == "fail"


def test_hr4_fails_on_a_below_floor_segment(tmp_path: Path) -> None:
    geojson = _clean_geojson()
    # A published segment with n=1 breaks the k-anonymity floor (default 3).
    _first_feature_with_rate(geojson)["properties"]["n"] = 1
    verdict = _run(tmp_path, geojson, _clean_sidecar(), recompute_hash=True)
    assert verdict["rules"]["HR4"]["pass"] is False
    assert verdict["verdict"] == "fail"


def test_hr4_fails_on_a_per_report_field(tmp_path: Path) -> None:
    geojson = _clean_geojson()
    geojson["features"][0]["properties"]["reporter_token"] = "abc123"
    verdict = _run(tmp_path, geojson, _clean_sidecar(), recompute_hash=True)
    assert verdict["rules"]["HR4"]["pass"] is False


def test_hr4_fails_on_unaggregated_point_geometry(tmp_path: Path) -> None:
    geojson = _clean_geojson()
    geojson["features"][0]["geometry"] = {"type": "Point", "coordinates": [-121.74, 38.54]}
    verdict = _run(tmp_path, geojson, _clean_sidecar(), recompute_hash=True)
    assert verdict["rules"]["HR4"]["pass"] is False


def test_hr5_fails_on_hash_mismatch(tmp_path: Path) -> None:
    # Do NOT recompute the hash: the sidecar keeps davis's original hash while the
    # bytes on disk differ, which is exactly the tampering/drift HR5 must catch.
    geojson = _clean_geojson()
    verdict = _run(tmp_path, geojson, _clean_sidecar(), recompute_hash=False)
    assert verdict["rules"]["HR5"]["pass"] is False
    assert verdict["verdict"] == "fail"


def test_hr5_fails_when_sidecar_is_absent(tmp_path: Path) -> None:
    verdict = _run(tmp_path, _clean_geojson(), None, recompute_hash=False)
    assert verdict["rules"]["HR5"]["pass"] is False
    assert verdict["sidecar"] is None


def test_hr5_fails_when_manifest_field_missing(tmp_path: Path) -> None:
    sidecar = _clean_sidecar()
    del sidecar["methods"]
    verdict = _run(tmp_path, _clean_geojson(), sidecar, recompute_hash=True)
    assert verdict["rules"]["HR5"]["pass"] is False


def test_every_rule_can_be_individually_broken() -> None:
    # A compact restatement of the excellence bar: each rule has at least one test
    # above that drives it to fail. Guards against a rule silently becoming
    # unfalsifiable.
    covered = {"HR1", "HR2", "HR3", "HR4", "HR5"}
    assert covered == set(vd.verify_artifact(PUBLISHED / "davis.geojson")["rules"])


def test_cli_main_exit_codes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    good = vd.main([str(PUBLISHED / "davis.geojson")])
    out = json.loads(capsys.readouterr().out)
    assert good == 0
    assert out["verdict"] == "pass"

    # Corrupt copy in tmp: mutate bytes without refreshing the hash -> HR5 fail -> exit 1.
    geojson = _clean_geojson()
    geojson["features"][0]["properties"]["danger_score"] = 1
    (tmp_path / "bad.geojson").write_text(json.dumps(geojson), encoding="utf-8")
    (tmp_path / "bad.metadata.json").write_text(json.dumps(_clean_sidecar()), encoding="utf-8")
    bad = vd.main([str(tmp_path / "bad.geojson")])
    assert bad == 1
