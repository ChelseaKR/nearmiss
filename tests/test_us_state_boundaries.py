"""The national map geometry is official, bounded, and independently pinned."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from tools import build_us_state_boundaries as boundaries

ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / "data" / "published" / "us-state-boundaries-2024.json"
ARTIFACT_SHA256 = "705219b3339077f1d03466391bb286fe7f1841298fc0bcce948de1d8c66df25d"


def test_committed_boundary_artifact_is_exact_reviewed_release() -> None:
    payload = ARTIFACT.read_bytes()
    assert hashlib.sha256(payload).hexdigest() == ARTIFACT_SHA256
    assert len(payload) == 323_232

    data = json.loads(payload)
    assert data["type"] == "FeatureCollection"
    assert data["source"]["distribution_url"] == boundaries.SOURCE_URL
    assert data["source"]["raw_zip_sha256"] == boundaries.SOURCE_SHA256
    assert data["source"]["raw_zip_size_bytes"] == 158_066
    assert len(data["features"]) == 51
    assert {feature["id"] for feature in data["features"]} == {
        abbreviation for abbreviation, _name in boundaries.EXPECTED_STATES.values()
    }


def test_boundary_converter_fails_closed_on_unreviewed_source_bytes() -> None:
    with pytest.raises(ValueError, match="Census archive SHA-256 mismatch"):
        boundaries.convert(b"not the reviewed Census archive")
