"""EXP-16: pre-registered prospective evaluation of the method itself.

``RE-01`` (see docs/ideation) is a *retrospective* validation study. This
module is the *prospective*, unfakeable companion: freeze which corridors the
current dataset flags as FDR-significant hotspots — with a timestamp and a
content hash, before the evaluation window opens — then, one period later,
score those frozen predictions against independent held-out data using a
scoring rule that was itself frozen at registration time. The scored result is
committed as a dated audit artifact whether the method's predictions held up
or not (the portfolio's defer-and-report-honestly ethos, applied to the
portfolio's own central claim: "near-miss data is a leading indicator").

Two steps, two CLI commands (``nearmiss preregister`` / ``nearmiss
score-preregistration``):

1. **Register.** :func:`write_registration` runs the normal analysis, takes
   every segment currently flagged ``significant`` (and publishable — the same
   k-anonymity floor the public dataset uses), and writes two files: the
   registration artifact itself (predictions + frozen method params + the
   scoring rule) and a manifest sidecar carrying its SHA-256 and registration
   timestamp — the same split-artifact-then-hash idiom :mod:`nearmiss.publish`
   uses for the public GeoJSON, so the hash is never self-referential.

2. **Score.** :func:`score_registration` takes a registration and an
   :class:`~nearmiss.engine.AnalysisBundle` built from the *next* period's
   independent data (new reports, or official collisions once ``RE-01``'s
   pipeline exists), and computes two frozen metrics — see
   ``SCORING_RULE_DESCRIPTION`` — over the segments the registration flagged.
   :func:`write_score_result` commits the outcome as a dated artifact
   regardless of whether it is favorable.

**SME gate (do not skip this).** The scoring rule below is a draft. Per
docs/ideation/03-expansions.md EXP-16, *a statistician must approve the
scoring rule before any registration produced under it is treated as
evidence*. That approval is tracked in
``docs/preregistration/scoring-rule-signoff.json`` — a human-edited file, not
something this code can satisfy on its own — and every registration artifact
stamps the sign-off status it was produced under (see
``scoring_rule.signoff_status`` in the artifact) so a reader never has to take
the claim on faith. Registrations produced before sign-off are valid dry runs
of the mechanism; they are not yet evidence of predictive validity, and
docs/PREREGISTRATION.md says so.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from .config import Config
from .engine import AnalysisBundle, build_analysis
from .errors import NearmissError
from .publish import _slug
from .stats.rank import spearman_rho
from .stats.rates import wilson_ci

SCHEMA_VERSION = "1.0.0"

DEFAULT_SIGNOFF_PATH = Path("docs/preregistration/scoring-rule-signoff.json")
DEFAULT_REGISTRATION_DIR = Path("data/published/preregistration")

SCORING_RULE_VERSION = "v1-draft"

SCORING_RULE_DESCRIPTION = (
    "Two metrics, frozen at registration time and computed only over the "
    "segments flagged in the registration (the flagged set is never "
    "re-selected, expanded, or pruned at scoring time): "
    "(1) hit_rate = the fraction of flagged, held-out-evaluable segments that "
    "are STILL a Getis-Ord Gi* / Benjamini-Hochberg-FDR-significant hotspot "
    "when the held-out period's independent data is run through the "
    "identical pipeline and config, reported with a Wilson 95% CI; "
    "(2) rank_correlation = Spearman's rho between each flagged segment's "
    "registered rate and its held-out rate, over the same evaluable subset "
    "(null if fewer than 2 points or if either series has zero rank "
    "variance). A held-out segment that was withheld for k-anonymity or that "
    "no longer matches an exposure denominator is 'unevaluable', not a miss — "
    "it is reported separately and never silently dropped from n_flagged."
)


def load_signoff(path: Path = DEFAULT_SIGNOFF_PATH) -> dict[str, object]:
    """Read the human-maintained statistician sign-off record.

    This is intentionally never auto-satisfied by code: the file starts with
    ``status: "pending_statistician_review"`` and only a human editing it after
    an actual review changes that.
    """
    if not path.is_file():
        raise NearmissError(f"scoring-rule sign-off file not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if "status" not in data:
        raise NearmissError(f"sign-off file {path} missing required 'status' field")
    return data  # type: ignore[no-any-return]


def _method_params(config: Config) -> dict[str, object]:
    return {
        "rate_per": config.rate_per,
        "confidence_z": config.confidence_z,
        "small_n": config.small_n,
        "min_publish_n": config.min_publish_n,
        "fdr_alpha": config.fdr_alpha,
        "getis_ord_band_m": config.gi_band_m,
        "kde_bandwidth_m": config.kde_bandwidth_m,
        "significance": "Getis-Ord Gi* on the exposure-normalized rate, Benjamini-Hochberg FDR",
    }


def _flagged_segments(bundle: AnalysisBundle) -> list[dict[str, object]]:
    """Every currently-significant, publishable segment, as a frozen prediction.

    Restricted to ``publishable`` segments (k-anonymity, same floor as the
    public dataset) so a registration artifact never creates a new privacy
    surface beyond what ``nearmiss publish`` already exposes.
    """
    flagged = [
        s for s in bundle.result.segments if s.significant and s.publishable and s.rate is not None
    ]
    return [
        {
            "segment_id": s.segment_id,
            "predicted_rate": s.rate,
            "predicted_rate_ci_low": s.rate_ci_low,
            "predicted_rate_ci_high": s.rate_ci_high,
            "getis_ord_z": s.getis_ord_z,
            "report_count": s.report_count,
        }
        for s in sorted(flagged, key=lambda s: s.segment_id)
    ]


def _canonical_json(obj: object) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def build_registration(
    config: Config,
    *,
    now: datetime | None = None,
    signoff_path: Path = DEFAULT_SIGNOFF_PATH,
) -> dict[str, object]:
    """Build the registration artifact dict (predictions frozen; not yet written)."""
    bundle = build_analysis(config)
    signoff = load_signoff(signoff_path)
    ts = (now or datetime.now(UTC)).astimezone(UTC).isoformat(timespec="seconds")
    flagged = _flagged_segments(bundle)
    return {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": "exp16_preregistration",
        "created_at": ts,
        "city": config.city,
        "dataset_note": config.dataset_note,
        "method_params": _method_params(config),
        "scoring_rule": {
            "version": SCORING_RULE_VERSION,
            "description": SCORING_RULE_DESCRIPTION,
            "signoff_status": signoff.get("status"),
            "signoff_reviewer": signoff.get("reviewer_name"),
            "signoff_reviewed_at": signoff.get("reviewed_at"),
        },
        "flagged_segments": flagged,
        "n_flagged": len(flagged),
        "commitment": (
            "This registration freezes the flagged-segment set and the scoring "
            "rule above before the evaluation window opens. The scored result "
            "will be published under docs/preregistration/ with the same "
            "prominence as this registration, whether the method's predictions "
            "held up or not. See docs/PREREGISTRATION.md."
        ),
    }


@dataclass
class RegistrationResult:
    artifact_path: Path
    manifest_path: Path
    artifact_sha256: str
    n_flagged: int
    registered_at: str


def write_registration(
    config: Config,
    out_dir: Path = DEFAULT_REGISTRATION_DIR,
    *,
    now: datetime | None = None,
    signoff_path: Path = DEFAULT_SIGNOFF_PATH,
) -> RegistrationResult:
    """Freeze the current flagged corridors to a hashed, timestamped artifact.

    Raises if a registration already exists for this city and date: a
    pre-registration is a one-time freeze for a given evaluation window, not a
    file you overwrite when you don't like the flagged set.
    """
    artifact = build_registration(config, now=now, signoff_path=signoff_path)
    payload = _canonical_json(artifact)
    sha = _sha256(payload)
    slug = _slug(config.city)
    date_str = str(artifact["created_at"])[:10]

    out_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = out_dir / f"{slug}-{date_str}.json"
    if artifact_path.exists():
        raise NearmissError(
            f"a registration already exists at {artifact_path} — pre-registration "
            "freezes one prediction set per city per day; if this is a genuinely "
            "new evaluation window, register on a different date"
        )

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": "exp16_preregistration_manifest",
        "artifact_file": artifact_path.name,
        "artifact_sha256": sha,
        "registered_at": artifact["created_at"],
        "status": "registered_pending_evaluation_window",
    }
    manifest_path = out_dir / f"{slug}-{date_str}.manifest.json"

    artifact_path.write_text(payload, encoding="utf-8")
    manifest_path.write_text(_canonical_json(manifest), encoding="utf-8")

    return RegistrationResult(
        artifact_path=artifact_path,
        manifest_path=manifest_path,
        artifact_sha256=sha,
        n_flagged=len(artifact["flagged_segments"]),  # type: ignore[arg-type]
        registered_at=str(artifact["created_at"]),
    )


def verify_registration(artifact_path: Path, manifest_path: Path) -> bool:
    """Recompute the artifact's hash and compare it to the manifest's claim."""
    payload = artifact_path.read_text(encoding="utf-8")
    manifest: dict[str, object] = json.loads(manifest_path.read_text(encoding="utf-8"))
    return bool(_sha256(payload) == manifest.get("artifact_sha256"))


def load_registration(artifact_path: Path) -> dict[str, object]:
    data: dict[str, object] = json.loads(artifact_path.read_text(encoding="utf-8"))
    return data


@dataclass
class ScoreResult:
    n_flagged: int
    n_evaluable: int
    hit_count: int
    hit_rate: float
    hit_rate_ci_low: float
    hit_rate_ci_high: float
    rank_correlation: float | None
    evaluated_at: str
    missed_segments: list[str]
    unevaluable_segments: list[str]


def score_registration(
    registration: dict[str, object],
    held_out_bundle: AnalysisBundle,
    *,
    now: datetime | None = None,
) -> ScoreResult:
    """Score a frozen registration against the next period's independent data.

    ``held_out_bundle`` must come from :func:`nearmiss.engine.build_analysis`
    run over the held-out period's config (new reports; the held-out period's
    exposure/streets, per the scoring rule freezing method params, not raw
    inputs). Raises if none of the flagged segments are evaluable.
    """
    flagged = registration.get("flagged_segments")
    if not isinstance(flagged, list) or not flagged:
        raise NearmissError("registration has no flagged_segments to score")

    held_out_by_id = {s.segment_id: s for s in held_out_bundle.result.segments}
    hit_count = 0
    missed: list[str] = []
    unevaluable: list[str] = []
    registered_rates: list[float] = []
    held_out_rates: list[float] = []

    for seg in flagged:
        seg_id = str(seg["segment_id"])
        held = held_out_by_id.get(seg_id)
        if held is None or not held.publishable or held.rate is None:
            unevaluable.append(seg_id)
            continue
        if held.significant:
            hit_count += 1
        else:
            missed.append(seg_id)
        registered_rates.append(float(seg["predicted_rate"]))
        held_out_rates.append(float(held.rate))

    n_evaluable = hit_count + len(missed)
    if n_evaluable == 0:
        raise NearmissError(
            "no flagged segment from the registration is evaluable against the "
            "held-out dataset (all withheld or unmatched) — cannot score"
        )

    low, high = wilson_ci(hit_count, n_evaluable)
    rho = spearman_rho(registered_rates, held_out_rates)
    ts = (now or datetime.now(UTC)).astimezone(UTC).isoformat(timespec="seconds")

    return ScoreResult(
        n_flagged=len(flagged),
        n_evaluable=n_evaluable,
        hit_count=hit_count,
        hit_rate=hit_count / n_evaluable,
        hit_rate_ci_low=low,
        hit_rate_ci_high=high,
        rank_correlation=rho,
        evaluated_at=ts,
        missed_segments=sorted(missed),
        unevaluable_segments=sorted(unevaluable),
    )


def write_score_result(
    result: ScoreResult,
    registration_manifest_path: Path,
    held_out_city: str,
    out_dir: Path = DEFAULT_REGISTRATION_DIR,
) -> Path:
    """Commit the scored outcome as a dated audit artifact — win or lose."""
    date_str = result.evaluated_at[:10]
    stem = registration_manifest_path.stem
    if stem.endswith(".manifest"):
        stem = stem[: -len(".manifest")]

    payload_dict: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": "exp16_prospective_score",
        "registration_manifest": registration_manifest_path.name,
        "held_out_city": held_out_city,
        "evaluated_at": result.evaluated_at,
        "n_flagged": result.n_flagged,
        "n_evaluable": result.n_evaluable,
        "hit_count": result.hit_count,
        "hit_rate": round(result.hit_rate, 4),
        "hit_rate_ci_low": round(result.hit_rate_ci_low, 4),
        "hit_rate_ci_high": round(result.hit_rate_ci_high, 4),
        "rank_correlation": (
            round(result.rank_correlation, 4) if result.rank_correlation is not None else None
        ),
        "missed_segments": result.missed_segments,
        "unevaluable_segments": result.unevaluable_segments,
        "publication_commitment": (
            "This result is published as scored, whether it supports or fails "
            "to support the near-miss-data-as-leading-indicator claim. See "
            "docs/PREREGISTRATION.md."
        ),
    }
    payload = _canonical_json(payload_dict)

    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{stem}-scored-{date_str}.json"
    path.write_text(payload, encoding="utf-8")
    return path
