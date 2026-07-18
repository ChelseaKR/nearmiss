"""Render a decision-ready, controlled-claim corridor dossier.

The advocacy brief summarizes a whole analysis.  A Decision Dossier is the
smaller, meeting-ready artifact: one already-publishable corridor, a named
decision request, its evidence readiness, and the checks a reviewer needs to
repeat the result.  It deliberately does *not* turn reported conflicts into a
claim about danger, fault, cause, or a treatment's effectiveness.
"""

from __future__ import annotations

import gettext
from dataclasses import dataclass

from .config import Config
from .coverage import CoverageAssessment, assess_coverage, load_source_registry
from .engine import AnalysisBundle
from .errors import NearmissError
from .i18n import get_translation
from .stats.corridors import CorridorStats


@dataclass(frozen=True)
class DossierEvidence:
    """The evidence-tier context safe to place in a public dossier."""

    tier: str | None
    as_of: str | None
    registry_sha256: str | None
    sources: tuple[tuple[str, str, str], ...]
    stale_source_ids: tuple[str, ...]
    missing_core_source_kinds: tuple[str, ...]


def _format(value: float | None) -> str:
    return "—" if value is None else f"{value:.2f}"


def _find_corridor(bundle: AnalysisBundle, corridor_id: str) -> CorridorStats:
    for corridor in bundle.result.corridors:
        if corridor.corridor_id == corridor_id:
            return corridor
    available = ", ".join(c.corridor_id for c in bundle.result.corridors) or "(none)"
    raise NearmissError(
        f"unknown corridor {corridor_id!r}; use an already-published corridor id "
        f"(available: {available})"
    )


def dossier_evidence(config: Config) -> DossierEvidence:
    """Resolve declared source readiness without inventing a tier.

    A dossier can still be exported without a registry so existing local
    workflows remain usable, but it is explicitly marked as undeclared rather
    than quietly receiving a reassuring evidence label.
    """

    if config.source_registry_path is None:
        return DossierEvidence(None, None, None, (), (), ())
    registry = load_source_registry(config.source_registry_path)
    assessment: CoverageAssessment = assess_coverage(config, registry)
    sources = tuple((source.id, source.name, source.updated_at) for source in assessment.sources)
    return DossierEvidence(
        tier=assessment.evidence_tier,
        as_of=assessment.as_of,
        registry_sha256=assessment.registry_sha256,
        sources=sources,
        stale_source_ids=assessment.stale_source_ids,
        missing_core_source_kinds=assessment.missing_core_source_kinds,
    )


def _render_evidence(
    out: list[str], evidence: DossierEvidence, translation: gettext.NullTranslations
) -> None:
    _ = translation.gettext
    out.append(_("## Evidence readiness"))
    out.append("")
    if evidence.tier is None:
        out.append(
            _(
                "**Source registry not declared.** This dossier can show the analysis result, "
                "but it cannot claim an evidence tier, measured-city coverage, or partner review."
            )
        )
        out.append("")
        return
    out.append(
        _(
            "**Declared evidence tier:** `{tier}` (assessed as of {as_of}). This describes "
            "which analyses the declared sources support; it is not a safety rating."
        ).format(tier=evidence.tier, as_of=evidence.as_of)
    )
    out.append("")
    out.append(_("### Declared sources"))
    out.append("")
    for source_id, name, updated_at in evidence.sources:
        out.append(
            _("- `{source_id}` — {name} (updated {updated_at})").format(
                source_id=source_id, name=name, updated_at=updated_at
            )
        )
    out.append("")
    if evidence.stale_source_ids:
        out.append(
            _(
                "**Freshness warning:** the following declared sources are stale under their "
                "own policy: {sources}."
            ).format(sources=", ".join(f"`{source}`" for source in evidence.stale_source_ids))
        )
        out.append("")
    if evidence.missing_core_source_kinds:
        out.append(
            _(
                "**Missing core source declarations:** {kinds}. The evidence tier reflects "
                "that gap."
            ).format(kinds=", ".join(evidence.missing_core_source_kinds))
        )
        out.append("")


def render_dossier(
    bundle: AnalysisBundle,
    config: Config,
    corridor_id: str,
    decision_request: str,
    lang: str = "en",
) -> str:
    """Return a deterministic, reviewable Markdown dossier for one corridor."""

    corridor = _find_corridor(bundle, corridor_id)
    translation = get_translation(lang)
    _ = translation.gettext
    evidence = dossier_evidence(config)
    start = config.window_start or "…"
    end = config.window_end or "…"
    window = (
        _("{start} to {end}").format(start=start, end=end)
        if config.window_start or config.window_end
        else _("all available data (no bounded analysis window configured)")
    )

    out: list[str] = [
        _("# Decision Dossier — {city}: {corridor}").format(
            city=config.city, corridor=corridor.name
        ),
        "",
        _(
            "> **Status: evidence for review.** This is a reproducible corridor finding, "
            "not a safety verdict or a treatment recommendation."
        ),
        "",
        _("## Decision request"),
        "",
        decision_request,
        "",
        _("## Corridor finding"),
        "",
        _(
            "**{name}** is an aggregate of {blocks} contiguous, publishable segments that "
            "each cleared the configured FDR-corrected hotspot screen. Its pooled reported "
            "near-miss rate is **{rate} per {per} {unit}** (95% CI {lo}–{hi}; n={n})."
        ).format(
            name=corridor.name,
            blocks=len(corridor.segment_ids),
            rate=_format(corridor.rate),
            per=int(config.rate_per),
            unit=config.exposure_unit,
            lo=_format(corridor.rate_ci_low),
            hi=_format(corridor.rate_ci_high),
            n=corridor.n,
        ),
        "",
        _(
            "The corridor uses the same already-published block aggregates; it does not "
            "create a new hotspot test or reveal a withheld segment."
        ),
        "",
        _("## Claim boundary"),
        "",
        _(
            "This dossier does **not** establish danger, fault, causation, the likely effect "
            "of a treatment, or conditions for any individual trip. It records a reported, "
            "exposure-normalized pattern that merits the decision request above."
        ),
        "",
        _("## Uncertainty and checks"),
        "",
        _(
            "- The interval expresses sampling uncertainty in reported counts; it does not "
            "remove reporting bias."
        ),
        _(
            "- Reports can vary by route choice, access, language, and willingness to report; "
            "a quiet data signal is not evidence of safety."
        ),
        _(
            "- The corridor boundary is a coarser view of block results. Read it alongside the "
            "underlying block layer, not instead of it."
        ),
        "",
        _("## Reproduction record"),
        "",
        _("- Corridor id: `{corridor_id}`").format(corridor_id=corridor.corridor_id),
        _("- Analysis window: {window}").format(window=window),
        _("- Exposure source: {source}").format(source=corridor.exposure_source or "unknown"),
        _("- Exposure date: {date}").format(date=corridor.exposure_date or "unknown"),
        _(
            "- Rebuild: run `nearmiss dossier --config <city.toml> --corridor "
            "{corridor_id} --decision-request <request>` against the same inputs."
        ).format(corridor_id=corridor.corridor_id),
        "",
    ]
    if evidence.registry_sha256:
        out.insert(
            len(out) - 1,
            _("- Source registry SHA-256: `{sha256}`").format(sha256=evidence.registry_sha256),
        )
    _render_evidence(out, evidence, translation)
    out.extend(
        [
            _("## Next review"),
            "",
            _(
                "Before acting, confirm the decision owner, inspect the corridor in context, "
                "and record what follow-up measure and review window would test the chosen action."
            ),
            "",
        ]
    )
    return "\n".join(out)
