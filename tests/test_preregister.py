"""EXP-16: pre-registered prospective evaluation (registration + scoring)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from nearmiss.config import Config
from nearmiss.engine import AnalysisBundle
from nearmiss.errors import NearmissError
from nearmiss.models import SegmentStats
from nearmiss.preregister import (
    ScoreResult,
    build_registration,
    load_registration,
    load_signoff,
    score_registration,
    verify_registration,
    write_registration,
    write_score_result,
)
from nearmiss.stats import AnalysisResult
from nearmiss.stats.bias import BiasReport
from nearmiss.stats.dp_temporal import DPSegmentTimeRelease
from nearmiss.stats.kde import KdeResult
from nearmiss.stats.temporal import TemporalBreakdown

ROOT = Path(__file__).resolve().parents[1]
SIGNOFF_PATH = ROOT / "docs" / "preregistration" / "scoring-rule-signoff.json"
FIXED_NOW = datetime(2026, 8, 1, 12, 0, 0, tzinfo=UTC)


def _stat(
    segment_id: str,
    *,
    rate: float | None,
    significant: bool,
    publishable: bool = True,
    report_count: int = 5,
) -> SegmentStats:
    return SegmentStats(
        segment_id=segment_id,
        report_count=report_count,
        n=report_count,
        exposure_estimate=1000.0,
        exposure_source="test",
        exposure_date="2026-01-01",
        rate=rate,
        rate_ci_low=rate,
        rate_ci_high=rate,
        getis_ord_z=3.0 if significant else 0.1,
        significant=significant,
        confidence_label="certain",
        publishable=publishable,
    )


def _fake_bundle(segments: list[SegmentStats]) -> AnalysisBundle:
    result = AnalysisResult(
        segments=segments,
        bias=BiasReport(findings=(), note="synthetic test bundle"),
        kde=KdeResult(cells=(), peak=None, bandwidth_m=150.0),
        exposure_coverage=1.0,
        kde_peak_segment=None,
        temporal=TemporalBreakdown(total_timed=0, unparseable=0, suppressed=True),
        corridors=[],
        dp_segment_time=DPSegmentTimeRelease(
            enabled=False,
            epsilon=None,
            sensitivity=1.0,
            mechanism="laplace",
            sme_signoff_ref=None,
        ),
    )
    return AnalysisBundle(result=result, records=[], summary={}, segments=[], exposure_unmatched=[])


# --------------------------------------------------------------------------- #
# sign-off record
# --------------------------------------------------------------------------- #
def test_signoff_starts_pending() -> None:
    signoff = load_signoff(SIGNOFF_PATH)
    assert signoff["status"] == "pending_statistician_review"


def test_load_signoff_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(NearmissError):
        load_signoff(tmp_path / "nope.json")


def test_load_signoff_without_status_raises(tmp_path: Path) -> None:
    bad = tmp_path / "signoff.json"
    bad.write_text(json.dumps({"reviewer_name": "someone"}), encoding="utf-8")
    with pytest.raises(NearmissError):
        load_signoff(bad)


# --------------------------------------------------------------------------- #
# registration
# --------------------------------------------------------------------------- #
def test_build_registration_flags_only_significant_publishable_segments(
    config: Config, bundle: AnalysisBundle
) -> None:
    artifact = build_registration(config, now=FIXED_NOW, signoff_path=SIGNOFF_PATH)
    flagged = artifact["flagged_segments"]
    assert isinstance(flagged, list)
    flagged_ids = {seg["segment_id"] for seg in flagged}
    expected = {s.segment_id for s in bundle.result.segments if s.significant and s.publishable}
    assert flagged_ids == expected
    assert "seg-06" in flagged_ids  # the fixture's planted, known-answer hotspot

    scoring_rule = artifact["scoring_rule"]
    assert isinstance(scoring_rule, dict)
    assert scoring_rule["signoff_status"] == "pending_statistician_review"
    assert artifact["n_flagged"] == len(flagged_ids)


def test_write_registration_hash_verifies(config: Config, tmp_path: Path) -> None:
    result = write_registration(config, tmp_path, now=FIXED_NOW, signoff_path=SIGNOFF_PATH)
    assert result.artifact_path.is_file()
    assert result.manifest_path.is_file()
    assert verify_registration(result.artifact_path, result.manifest_path)

    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest["artifact_sha256"] == result.artifact_sha256
    assert manifest["status"] == "registered_pending_evaluation_window"


def test_verify_registration_detects_tampering(config: Config, tmp_path: Path) -> None:
    result = write_registration(config, tmp_path, now=FIXED_NOW, signoff_path=SIGNOFF_PATH)
    tampered = json.loads(result.artifact_path.read_text(encoding="utf-8"))
    tampered["flagged_segments"] = []
    result.artifact_path.write_text(json.dumps(tampered), encoding="utf-8")
    assert not verify_registration(result.artifact_path, result.manifest_path)


def test_write_registration_twice_same_city_and_date_fails_loudly(
    config: Config, tmp_path: Path
) -> None:
    write_registration(config, tmp_path, now=FIXED_NOW, signoff_path=SIGNOFF_PATH)
    with pytest.raises(NearmissError, match="already exists"):
        write_registration(config, tmp_path, now=FIXED_NOW, signoff_path=SIGNOFF_PATH)


def test_load_registration_round_trips(config: Config, tmp_path: Path) -> None:
    result = write_registration(config, tmp_path, now=FIXED_NOW, signoff_path=SIGNOFF_PATH)
    loaded = load_registration(result.artifact_path)
    assert loaded["city"] == "Davis"
    assert len(loaded["flagged_segments"]) == result.n_flagged  # type: ignore[arg-type]


# --------------------------------------------------------------------------- #
# scoring
# --------------------------------------------------------------------------- #
_REGISTRATION: dict[str, object] = {
    "flagged_segments": [
        {"segment_id": "seg-a", "predicted_rate": 10.0},
        {"segment_id": "seg-b", "predicted_rate": 8.0},
        {"segment_id": "seg-c", "predicted_rate": 6.0},
        {"segment_id": "seg-d", "predicted_rate": 4.0},
    ]
}


def test_score_registration_hit_rate_and_ranking() -> None:
    held_out = _fake_bundle(
        [
            _stat("seg-a", rate=11.0, significant=True),  # hit
            _stat("seg-b", rate=9.0, significant=True),  # hit
            _stat("seg-c", rate=1.0, significant=False),  # miss
            _stat("seg-d", rate=0.5, significant=False),  # miss
        ]
    )
    result = score_registration(_REGISTRATION, held_out, now=FIXED_NOW)
    assert result.n_flagged == 4
    assert result.n_evaluable == 4
    assert result.hit_count == 2
    assert result.hit_rate == pytest.approx(0.5)
    assert 0.0 <= result.hit_rate_ci_low <= result.hit_rate <= result.hit_rate_ci_high <= 1.0
    # registered order (a>b>c>d) matches held-out order exactly -> rho == 1.0
    assert result.rank_correlation == pytest.approx(1.0)
    assert result.missed_segments == ["seg-c", "seg-d"]
    assert result.unevaluable_segments == []


def test_score_registration_treats_withheld_and_unmatched_as_unevaluable_not_miss() -> None:
    held_out = _fake_bundle(
        [
            _stat("seg-a", rate=11.0, significant=True),
            _stat("seg-b", rate=None, significant=False, publishable=False),  # withheld
            # seg-c: absent entirely (e.g. street network changed) -> unmatched
            _stat("seg-d", rate=1.0, significant=False),  # miss
        ]
    )
    result = score_registration(_REGISTRATION, held_out, now=FIXED_NOW)
    assert result.n_flagged == 4
    assert result.n_evaluable == 2  # only seg-a (hit) and seg-d (miss)
    assert result.hit_count == 1
    assert sorted(result.unevaluable_segments) == ["seg-b", "seg-c"]


def test_score_registration_null_result_still_scores_and_is_honest() -> None:
    """A method that fails completely: hit_rate == 0.0. Scoring must not error or hide it."""
    held_out = _fake_bundle(
        [_stat(s, rate=0.1, significant=False) for s in ("seg-a", "seg-b", "seg-c", "seg-d")]
    )
    result = score_registration(_REGISTRATION, held_out, now=FIXED_NOW)
    assert result.hit_count == 0
    assert result.hit_rate == 0.0
    assert result.missed_segments == ["seg-a", "seg-b", "seg-c", "seg-d"]


def test_score_registration_no_evaluable_segments_raises() -> None:
    held_out = _fake_bundle([])  # nothing matches at all
    with pytest.raises(NearmissError, match="no flagged segment"):
        score_registration(_REGISTRATION, held_out, now=FIXED_NOW)


def test_score_registration_empty_registration_raises() -> None:
    held_out = _fake_bundle([_stat("seg-a", rate=1.0, significant=True)])
    with pytest.raises(NearmissError, match="no flagged_segments"):
        empty: dict[str, object] = {"flagged_segments": []}
        score_registration(empty, held_out, now=FIXED_NOW)


def test_rank_correlation_is_none_with_fewer_than_two_evaluable_points() -> None:
    held_out = _fake_bundle([_stat("seg-a", rate=11.0, significant=True)])
    registration: dict[str, object] = {
        "flagged_segments": [{"segment_id": "seg-a", "predicted_rate": 10.0}]
    }
    result = score_registration(registration, held_out, now=FIXED_NOW)
    assert result.n_evaluable == 1
    assert result.rank_correlation is None


def test_write_score_result_commits_regardless_of_outcome(tmp_path: Path) -> None:
    result = ScoreResult(
        n_flagged=4,
        n_evaluable=4,
        hit_count=0,
        hit_rate=0.0,
        hit_rate_ci_low=0.0,
        hit_rate_ci_high=0.6,
        rank_correlation=-0.4,
        evaluated_at=FIXED_NOW.isoformat(timespec="seconds"),
        missed_segments=["seg-a", "seg-b", "seg-c", "seg-d"],
        unevaluable_segments=[],
    )
    manifest_path = tmp_path / "davis-2026-08-01.manifest.json"
    manifest_path.write_text("{}", encoding="utf-8")

    path = write_score_result(result, manifest_path, "Davis", tmp_path)
    assert path.is_file()
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["hit_rate"] == 0.0
    assert payload["hit_count"] == 0
    assert payload["registration_manifest"] == manifest_path.name
    assert "publication_commitment" in payload
