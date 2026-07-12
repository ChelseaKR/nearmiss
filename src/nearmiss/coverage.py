"""Conservative city evidence-tier and source-coverage assessment.

National scale must not turn heterogeneous inputs into one opaque "danger
score". A city declares its sources, this module checks those declarations
against the data that actually load, and the resulting tier says only which
analyses are supportable. Partner status is never inferred from data volume.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import tomllib
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal, cast

from .config import Config
from .engine import load_city
from .errors import ConfigError

SourceKind = Literal[
    "streets", "incidents", "exposure", "official_outcomes", "context", "interventions"
]
SourceAccess = Literal["open", "partner", "licensed", "private"]
EvidenceTier = Literal[
    "demonstration", "national_baseline", "modeled_city", "measured_city", "partner_city"
]

_SOURCE_KINDS = {
    "streets",
    "incidents",
    "exposure",
    "official_outcomes",
    "context",
    "interventions",
}
_SOURCE_ACCESS = {"open", "partner", "licensed", "private"}
_CORE_KINDS = {"streets", "incidents", "exposure"}


@dataclass(frozen=True)
class DataSource:
    id: str
    kind: SourceKind
    name: str
    license: str
    updated_at: str
    geography: str
    access: SourceAccess = "open"
    url: str | None = None
    synthetic: bool = False
    stale_after_days: int = 365


@dataclass(frozen=True)
class SourceRegistry:
    city: str
    sources: tuple[DataSource, ...]
    measured_min_coverage: float = 0.8
    partner_organization: str | None = None
    partner_review_ref: str | None = None
    content_sha256: str = ""


@dataclass(frozen=True)
class CoverageAssessment:
    city: str
    evidence_tier: EvidenceTier
    segments_total: int
    reports_total: int
    usable_exposure_coverage: float
    observed_exposure_coverage: float
    source_count: int
    sources: tuple[DataSource, ...]
    registry_sha256: str
    source_kinds: tuple[str, ...]
    missing_core_source_kinds: tuple[str, ...]
    stale_source_ids: tuple[str, ...]
    capabilities: tuple[str, ...]
    unlocks: tuple[str, ...]
    partner_organization: str | None
    partner_review_ref: str | None
    as_of: str

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def _parse_date(value: object, *, field: str, path: Path) -> dt.date:
    try:
        return dt.date.fromisoformat(str(value))
    except ValueError as exc:
        raise ConfigError(f"source registry {path}: {field} must be YYYY-MM-DD") from exc


def _load_registry_toml(path: Path) -> dict[str, object]:
    try:
        with path.open("rb") as handle:
            return tomllib.load(handle)
    except FileNotFoundError as exc:
        raise ConfigError(f"source registry not found: {path}") from exc
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ConfigError(f"could not load source registry {path}: {exc}") from exc


def _parse_source(row: object, *, index: int, path: Path, ids: set[str]) -> DataSource:
    if not isinstance(row, dict):
        raise ConfigError(f"source registry {path}: sources[{index}] must be a table")
    required = ("id", "kind", "name", "license", "updated_at", "geography")
    missing = [key for key in required if not row.get(key)]
    if missing:
        raise ConfigError(f"source registry {path}: sources[{index}] missing {', '.join(missing)}")
    source_id = str(row["id"])
    if source_id in ids:
        raise ConfigError(f"source registry {path}: duplicate source id {source_id!r}")
    ids.add(source_id)
    kind = str(row["kind"])
    access = str(row.get("access", "open"))
    if kind not in _SOURCE_KINDS:
        raise ConfigError(f"source registry {path}: source {source_id!r} has invalid kind {kind!r}")
    if access not in _SOURCE_ACCESS:
        raise ConfigError(
            f"source registry {path}: source {source_id!r} has invalid access {access!r}"
        )
    updated = _parse_date(row["updated_at"], field=f"{source_id}.updated_at", path=path)
    try:
        stale_after_days = int(row.get("stale_after_days", 365))
    except (TypeError, ValueError) as exc:
        raise ConfigError(
            f"source registry {path}: {source_id}.stale_after_days must be an integer"
        ) from exc
    if stale_after_days < 0:
        raise ConfigError(f"source registry {path}: {source_id}.stale_after_days must be >= 0")
    return DataSource(
        id=source_id,
        kind=cast(SourceKind, kind),
        name=str(row["name"]),
        license=str(row["license"]),
        updated_at=updated.isoformat(),
        geography=str(row["geography"]),
        access=cast(SourceAccess, access),
        url=str(row["url"]) if row.get("url") else None,
        synthetic=bool(row.get("synthetic", False)),
        stale_after_days=stale_after_days,
    )


def _parse_partner(raw: dict[str, object], path: Path) -> tuple[str | None, str | None]:
    partner = raw.get("partner", {})
    if not isinstance(partner, dict):
        raise ConfigError(f"source registry {path}: [partner] must be a table")
    organization = str(partner["organization"]).strip() if partner.get("organization") else None
    review_ref = str(partner["review_ref"]).strip() if partner.get("review_ref") else None
    if bool(organization) != bool(review_ref):
        raise ConfigError(
            f"source registry {path}: partner organization and review_ref must appear together"
        )
    return organization, review_ref


def load_source_registry(path: str | Path) -> SourceRegistry:
    """Load a strict, versioned TOML source registry."""
    registry_path = Path(path)
    raw = _load_registry_toml(registry_path)

    if raw.get("version") != 1:
        raise ConfigError(f"source registry {registry_path}: version must be 1")
    city = str(raw.get("city", "")).strip()
    if not city:
        raise ConfigError(f"source registry {registry_path}: city is required")

    raw_threshold = raw.get("measured_min_coverage", 0.8)
    try:
        if not isinstance(raw_threshold, (int, float, str)):
            raise TypeError
        measured_min_coverage = float(raw_threshold)
    except (TypeError, ValueError) as exc:
        raise ConfigError(
            f"source registry {registry_path}: measured_min_coverage must be numeric"
        ) from exc
    if not 0 < measured_min_coverage <= 1:
        raise ConfigError(
            f"source registry {registry_path}: measured_min_coverage must be in (0, 1]"
        )

    rows = raw.get("sources", [])
    if not isinstance(rows, list):
        raise ConfigError(f"source registry {registry_path}: [[sources]] must be an array")
    ids: set[str] = set()
    sources = tuple(
        _parse_source(row, index=index, path=registry_path, ids=ids)
        for index, row in enumerate(rows)
    )
    organization, review_ref = _parse_partner(raw, registry_path)
    return SourceRegistry(
        city=city,
        sources=sources,
        measured_min_coverage=measured_min_coverage,
        partner_organization=organization,
        partner_review_ref=review_ref,
        content_sha256=hashlib.sha256(registry_path.read_bytes()).hexdigest(),
    )


def _assessment_date(config: Config, registry: SourceRegistry) -> dt.date:
    """Choose a reproducible reference date; never depend on the wall clock."""
    if config.window_end:
        return dt.date.fromisoformat(config.window_end)
    city = load_city(config)
    dates: list[dt.date] = []
    for report in city.reports:
        try:
            parsed = dt.datetime.fromisoformat(report.occurred_at.replace("Z", "+00:00"))
            dates.append(parsed.date())
        except ValueError:
            continue
    if dates:
        return max(dates)
    source_dates = [dt.date.fromisoformat(source.updated_at) for source in registry.sources]
    if source_dates:
        return max(source_dates)
    raise ConfigError("coverage assessment needs a window, a dated report, or a dated source")


def _stale_sources(registry: SourceRegistry, assessment_date: dt.date) -> tuple[str, ...]:
    return tuple(
        sorted(
            source.id
            for source in registry.sources
            if (assessment_date - dt.date.fromisoformat(source.updated_at)).days
            > source.stale_after_days
        )
    )


def _evidence_tier(
    registry: SourceRegistry,
    *,
    missing: tuple[str, ...],
    usable_count: int,
    observed_coverage: float,
    stale: tuple[str, ...],
) -> EvidenceTier:
    synthetic = any(source.synthetic for source in registry.sources if source.kind in _CORE_KINDS)
    if synthetic:
        return "demonstration"
    if not usable_count or "exposure" in missing:
        return "national_baseline"
    core_stale = any(
        source.id in stale for source in registry.sources if source.kind in _CORE_KINDS
    )
    measured = (
        not missing and observed_coverage >= registry.measured_min_coverage and not core_stale
    )
    reviewed_partner = bool(registry.partner_organization and registry.partner_review_ref)
    if measured and reviewed_partner:
        return "partner_city"
    if measured:
        return "measured_city"
    return "modeled_city"


def _capabilities_and_unlocks(
    registry: SourceRegistry,
    *,
    kinds: set[str],
    usable_count: int,
    observed_coverage: float,
    stale: tuple[str, ...],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    capabilities = ["source_coverage_screening"]
    if "context" in kinds:
        capabilities.append("contextual_screening")
    if usable_count and "exposure" in kinds:
        capabilities.append("exposure_normalized_segment_rates")
    if "official_outcomes" in kinds:
        capabilities.append("official_outcome_triangulation")
    if "interventions" in kinds:
        capabilities.append("before_after_evaluation_inputs")

    unlocks = []
    if observed_coverage < registry.measured_min_coverage:
        unlocks.append("raise observed exposure coverage")
    if "official_outcomes" not in kinds:
        unlocks.append("add an official-outcomes source")
    if "interventions" not in kinds:
        unlocks.append("add an intervention-history source")
    if not (registry.partner_organization and registry.partner_review_ref):
        unlocks.append("record a partner organization and review reference")
    if stale:
        unlocks.append("refresh stale sources")
    return tuple(capabilities), tuple(unlocks)


def assess_coverage(
    config: Config, registry: SourceRegistry, *, as_of: dt.date | None = None
) -> CoverageAssessment:
    """Assess what a city's actual inputs support, without manufacturing certainty."""
    if registry.city.casefold() != config.city.casefold():
        raise ConfigError(
            f"source registry city {registry.city!r} does not match config city {config.city!r}"
        )
    city = load_city(config)
    segment_ids = {segment.id for segment in city.segments}
    segment_count = len(segment_ids)
    usable_ids = {
        sid
        for sid, exposure in city.exposure.items()
        if sid in segment_ids and exposure.estimate > config.exposure_floor
    }
    observed_ids = {sid for sid in usable_ids if city.exposure[sid].tier == "observed"}
    usable_coverage = len(usable_ids) / segment_count if segment_count else 0.0
    observed_coverage = len(observed_ids) / segment_count if segment_count else 0.0

    kinds = {source.kind for source in registry.sources}
    missing = tuple(sorted(_CORE_KINDS - kinds))
    assessment_date = as_of or _assessment_date(config, registry)
    stale = _stale_sources(registry, assessment_date)
    tier = _evidence_tier(
        registry,
        missing=missing,
        usable_count=len(usable_ids),
        observed_coverage=observed_coverage,
        stale=stale,
    )
    capabilities, unlocks = _capabilities_and_unlocks(
        registry,
        kinds=set(kinds),
        usable_count=len(usable_ids),
        observed_coverage=observed_coverage,
        stale=stale,
    )

    return CoverageAssessment(
        city=config.city,
        evidence_tier=tier,
        segments_total=segment_count,
        reports_total=len(city.reports),
        usable_exposure_coverage=round(usable_coverage, 4),
        observed_exposure_coverage=round(observed_coverage, 4),
        source_count=len(registry.sources),
        sources=registry.sources,
        registry_sha256=registry.content_sha256,
        source_kinds=tuple(sorted(kinds)),
        missing_core_source_kinds=missing,
        stale_source_ids=stale,
        capabilities=capabilities,
        unlocks=unlocks,
        partner_organization=registry.partner_organization,
        partner_review_ref=registry.partner_review_ref,
        as_of=assessment_date.isoformat(),
    )
