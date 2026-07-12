"""Render an advocacy brief that a city council can read and a skeptic can check.

Every ranked location is a rate with a confidence interval and an n; significant
clusters are flagged from Getis-Ord Gi* (FDR-corrected); the reporting bias is
named in plain language; and a plain-language glossary plus a bottom-line
sentence make it usable without a statistics background. The output is
deterministic markdown and can render in English or Spanish.

This is nearmiss's only end-user-facing, natural-language surface. Every such
string is wrapped in gettext ``_()``/``ngettext()`` (INTERNATIONALIZATION-
STANDARD §3) and extracted into ``locales/messages.pot``; the translation for a
requested ``lang`` is loaded via :mod:`nearmiss.i18n`.
"""

from __future__ import annotations

import gettext
import json
from collections.abc import Callable

from .config import Config
from .engine import AnalysisBundle, build_analysis
from .i18n import (
    confidence_label,
    exposure_tier_label,
    get_translation,
    hazard_type_label,
    part_of_day_label,
    weekday_label,
)
from .models import Segment, SegmentStats
from .publish import _slug
from .stats.bias import BiasFinding
from .stats.corridors import CorridorStats


def _names(segments: list[Segment]) -> dict[str, str]:
    return {s.id: s.name for s in segments}


def _fmt(value: float | None) -> str:
    return "—" if value is None else f"{value:.2f}"


def _render_intro(
    out: list[str],
    bundle: AnalysisBundle,
    config: Config,
    withheld: int,
    translation: gettext.NullTranslations,
) -> None:
    """Append the title, dataset note, rate caveat, exposure coverage, and k-anonymity notice."""
    _ = translation.gettext
    ngettext = translation.ngettext
    per = int(config.rate_per)
    unit = config.exposure_unit
    title = _("Where the danger actually is — {city}").format(city=config.city)
    out.append(f"# {title}")
    out.append("")
    if config.dataset_note:
        out.append(f"> ⚠️ **{config.dataset_note}**")
        out.append("")
    # METHODOLOGY §1: a rate with no window attached is not a publishable number.
    # State the analysis window explicitly; warn in-line when none is configured.
    if config.window_start or config.window_end:
        start = config.window_start or "…"
        end = config.window_end or "…"
        out.append(_("**Analysis window:** {start} to {end}.").format(start=start, end=end))
    else:
        out.append(
            _(
                "**Analysis window:** all available data (no window configured — rates below "
                "are all-time and not bounded to a stated period)."
            )
        )
    out.append("")
    out.append(
        _(
            "> Rates are reports per {per} {unit}. Every rate carries a 95% confidence "
            "interval and an n. Raw counts are not danger; they are report volume. Read the "
            "caveats — they are the point."
        ).format(per=per, unit=unit)
    )
    out.append("")
    out.append(
        _(
            "**Exposure coverage:** {pct}% of segments have an exposure denominator. "
            "Segments without one are listed as *exposure unknown*, not ranked."
        ).format(pct=f"{bundle.result.exposure_coverage * 100:.0f}")
    )
    out.append("")
    if withheld:
        out.append(
            ngettext(
                "*{n} segment with fewer than {floor} reports is withheld from this brief and "
                "the open dataset to protect contributor privacy (k-anonymity).*",
                "*{n} segments with fewer than {floor} reports are withheld from this brief and "
                "the open dataset to protect contributor privacy (k-anonymity).*",
                withheld,
            ).format(n=withheld, floor=config.min_publish_n)
        )
        out.append("")


def _render_glossary(out: list[str], config: Config, translation: gettext.NullTranslations) -> None:
    """Append the plain-language glossary section."""
    _ = translation.gettext
    per = int(config.rate_per)
    unit = config.exposure_unit
    out.append(_("## What the numbers mean (plain language)"))
    out.append("")
    out.append(
        _(
            "- **Rate** — reports per {per} {unit}. It adjusts for how many people travel a "
            "street, so a quiet street with a few reports can rank above a busy one with many."
        ).format(per=per, unit=unit)
    )
    out.append(
        _(
            "- **95% CI (confidence interval)** — the plausible range for the true rate. A wide "
            "range means few reports and real uncertainty; treat those rankings gently."
        )
    )
    out.append(
        _(
            "- **Hotspot (Getis-Ord Gi\\*)** — a segment marked ★ Significant is hot *beyond* "
            "what traffic and chance explain, after a multiple-comparison correction: a real "
            "cluster, not a fluke. Several streets can share a rate while only one is a "
            "significant cluster."
        )
    )
    out.append("")


def _render_bottom_line(
    out: list[str],
    ranked: list[SegmentStats],
    name_of: Callable[[str], str],
    config: Config,
    translation: gettext.NullTranslations,
) -> None:
    """Append the headline sentence a non-statistician can read aloud, if there is a ranking."""
    if not ranked:
        return
    _ = translation.gettext
    per = int(config.rate_per)
    unit = config.exposure_unit
    top = ranked[0]
    sig = _(", and it is a statistically significant cluster") if top.significant else ""
    out.append(
        _(
            "**Bottom line:** the highest exposure-normalized near-miss rate is on "
            "**{name}** — about {rate} reports per {per} {unit} (95% CI {lo}–{hi}, "
            "n={n}){sig}. Because it is normalized by exposure, this is a rate, not just a "
            "busy street; still, it rests on {n} reports, so read it with the interval and "
            "the reporting-bias caveats below."
        ).format(
            name=name_of(top.segment_id),
            rate=_fmt(top.rate),
            per=per,
            unit=unit,
            lo=_fmt(top.rate_ci_low),
            hi=_fmt(top.rate_ci_high),
            n=top.n,
            sig=sig,
        )
    )
    out.append("")


def _render_top_table(
    out: list[str],
    ranked: list[SegmentStats],
    name_of: Callable[[str], str],
    config: Config,
    translation: gettext.NullTranslations,
) -> None:
    """Append the highest-rate (top 10) segments table."""
    _ = translation.gettext
    per = int(config.rate_per)
    out.append(_("## Highest-rate segments (exposure-normalized)"))
    out.append("")
    th_rank = _("Rank")
    th_segment = _("Segment")
    th_rate = _("Rate /{per}").format(per=per)
    th_ci = _("95% CI")
    th_n = _("n")
    th_confidence = _("Confidence")
    # FIX-04: the exposure trust tier travels with the rate so a reader never
    # silently compares an observed count against a proxy layer (METHODOLOGY §3.1).
    th_tier = _("Exposure tier")
    th_hotspot = _("Hotspot")
    out.append(
        f"| {th_rank} | {th_segment} | {th_rate} | {th_ci} | {th_n} | {th_confidence} | "
        f"{th_tier} | {th_hotspot} |"
    )
    out.append("| ---: | --- | ---: | --- | ---: | --- | --- | --- |")
    for i, s in enumerate(ranked[:10], start=1):
        ci = f"{_fmt(s.rate_ci_low)}-{_fmt(s.rate_ci_high)}"
        hotspot = (
            f"★ Gi* z={s.getis_ord_z:.2f}" if (s.significant and s.getis_ord_z is not None) else ""
        )
        tier = exposure_tier_label(translation, s.exposure_tier)
        out.append(
            f"| {i} | {name_of(s.segment_id)} | {_fmt(s.rate)} | "
            f"{ci} | {s.n} | {confidence_label(translation, s.confidence_label)} | "
            f"{tier} | {hotspot} |"
        )
    out.append("")


def _render_dominant_hazard(
    out: list[str],
    ranked: list[SegmentStats],
    name_of: Callable[[str], str],
    config: Config,
    translation: gettext.NullTranslations,
) -> None:
    """Append the dominant-hazard-type-by-segment section.

    Dominant hazard, with its own rate, for each ranked segment that publishes a
    per-hazard-type rate layer. The headline rate above is pooled across ALL
    hazard types (a union); this names the single most common conflict type at a
    place and gives ITS exposure-normalized rate, so "a corridor of close passes"
    reads differently from "a corridor of surface defects" — with a rate, not a
    raw count. Types below the small-sample threshold are suppressed, so a
    segment may rank without a dominant-hazard line.
    """
    _ = translation.gettext
    per = int(config.rate_per)
    dominant: list[tuple[SegmentStats, str, dict[str, float]]] = []
    for s in ranked[:10]:
        if not s.rates_by_type:
            continue
        # Most common qualifying hazard type (ties broken by name, for determinism).
        top_type = max(sorted(s.rates_by_type), key=lambda t: s.rates_by_type[t]["count"])
        dominant.append((s, top_type, s.rates_by_type[top_type]))
    if dominant:
        out.append(_("## Dominant hazard type by segment (with its own rate)"))
        out.append("")
        out.append(
            _(
                "The headline rate is pooled across every hazard type (a union). This names the "
                "single most common conflict type at each ranked segment and gives *its* "
                "exposure-normalized rate; types with too few reports to share are omitted."
            )
        )
        out.append("")
        dom_line = _(
            "- **{name}** — most common: **{hazard}** ({count} reports), "
            "rate {rate}/{per} (CI {lo}-{hi})"
        )
        for s, top_type, layer in dominant:
            out.append(
                dom_line.format(
                    name=name_of(s.segment_id),
                    hazard=hazard_type_label(translation, top_type),
                    count=int(layer["count"]),
                    rate=_fmt(layer["rate"]),
                    per=per,
                    lo=_fmt(layer["rate_ci_low"]),
                    hi=_fmt(layer["rate_ci_high"]),
                )
            )
        out.append("")


def _render_hotspots(
    out: list[str],
    stats: list[SegmentStats],
    name_of: Callable[[str], str],
    config: Config,
    translation: gettext.NullTranslations,
) -> None:
    """Append the statistically-significant-hotspots section."""
    _ = translation.gettext
    per = int(config.rate_per)
    sig_segments: list[SegmentStats] = [s for s in stats if s.significant and s.publishable]
    out.append(_("## Statistically significant hotspots (Getis-Ord Gi\\*)"))
    out.append("")
    if sig_segments:
        out.append(
            _(
                "These segments are hot *beyond* what exposure and spatial structure explain — "
                "candidates for hot because dangerous, not hot because busy:"
            )
        )
        out.append("")
        bullet = _("- **{name}** — Gi* z = {z}, rate {rate}/{per} (CI {lo}-{hi}, n={n})")
        for s in sorted(sig_segments, key=lambda s: s.getis_ord_z or 0.0, reverse=True):
            out.append(
                bullet.format(
                    name=name_of(s.segment_id),
                    z=f"{s.getis_ord_z:.2f}",
                    rate=_fmt(s.rate),
                    per=per,
                    lo=_fmt(s.rate_ci_low),
                    hi=_fmt(s.rate_ci_high),
                    n=s.n,
                )
            )
    else:
        out.append(_("No segment reaches statistical significance at this sample size."))
    out.append("")


def _render_corridors(
    out: list[str],
    corridors: list[CorridorStats],
    config: Config,
    translation: gettext.NullTranslations,
) -> None:
    """Append the corridor view: the unit advocacy asks and council motions use.

    Always published alongside the block-level tables above, never instead of
    them — a corridor is a coarser aggregate of segments that are each already
    ranked and flagged on their own (EXP-03).
    """
    _ = translation.gettext
    per = int(config.rate_per)
    out.append(_("## Corridor view (for advocacy asks)"))
    out.append("")
    out.append(
        _(
            "Blocks are the unit of measurement; corridors are the unit council motions "
            "and campaigns are written in. Each corridor below merges contiguous, "
            "statistically significant blocks of the same street into one named span, "
            "with its own rate, interval, and n — published *alongside*, never instead "
            "of, the block-level table above."
        )
    )
    out.append("")
    if not corridors:
        out.append(
            _(
                "No contiguous run of significant blocks reached corridor size in this "
                "dataset — the block-level hotspots above are the finest and only unit "
                "available this cycle."
            )
        )
        out.append("")
        return
    th_corridor = _("Corridor")
    th_rate = _("Rate /{per}").format(per=per)
    th_ci = _("95% CI")
    th_n = _("n")
    th_blocks = _("Blocks merged")
    out.append(f"| {th_corridor} | {th_rate} | {th_ci} | {th_n} | {th_blocks} |")
    out.append("| --- | ---: | --- | ---: | ---: |")
    for c in sorted(corridors, key=lambda c: c.rate or 0.0, reverse=True):
        ci = f"{_fmt(c.rate_ci_low)}-{_fmt(c.rate_ci_high)}"
        out.append(f"| {c.name} | {_fmt(c.rate)} | {ci} | {c.n} | {len(c.segment_ids)} |")
    out.append("")
    out.append(
        _(
            "**MAUP transparency note:** how you draw the boundary can itself shift a "
            "rate (the Modifiable Areal Unit Problem). Corridor counts and exposure are "
            "sums of the same already-published, already-significant blocks above — no "
            "block is surfaced here that was withheld or non-significant on its own. "
            "Read the corridor rate as a complement to the block rates, not a "
            "replacement for them."
        )
    )


# A quasi-Poisson dispersion at or above this is reported as *material*
# overdispersion in the brief (≈5%+ wider intervals than pure Poisson). Below it,
# sqrt(phi) rounding noise is not worth alarming a reader with. The dispersion phi
# itself is always published in the metadata regardless of this display threshold.
_OVERDISPERSION_MATERIAL = 1.1


def _render_robustness(
    out: list[str],
    bundle: AnalysisBundle,
    translation: gettext.NullTranslations,
    name_of: Callable[[str], str],
) -> None:
    """Append the RR-02 overdispersion and RR-05 MAUP re-segmentation checks.

    These are the skeptic-facing robustness answers: whether the Poisson intervals
    understate uncertainty (clustered reporting) and whether the top hotspot is an
    artifact of where the block lines were drawn.
    """
    _ = translation.gettext
    phi = bundle.result.dispersion
    stability = bundle.result.rank_stability
    out.append(_("## Robustness checks (overdispersion & re-segmentation)"))
    out.append("")

    if phi >= _OVERDISPERSION_MATERIAL:
        if bundle.result.overdispersion_adjusted:
            clause = _("Those intervals have already been widened accordingly (quasi-Poisson).")
        else:
            clause = _(
                "Read them as a lower bound on the true uncertainty (a quasi-Poisson widening "
                "is available via the `overdispersion_adjust` setting)."
            )
        out.append(
            _(
                "- **Overdispersion (clustered reporting).** The report counts are overdispersed "
                "(dispersion ≈ {phi}): by that pooled estimate the Poisson 95% intervals above "
                "could be up to {infl}× too narrow. Genuine between-segment differences inflate "
                "this estimate too, so {infl}× is an upper bound on the needed widening. {clause}"
            ).format(phi=f"{phi:.2f}", infl=f"{phi**0.5:.2f}", clause=clause)
        )
    else:
        out.append(
            _(
                "- **Overdispersion.** Report counts show no material overdispersion (dispersion "
                "≈ {phi}); the Poisson intervals stand as computed."
            ).format(phi=f"{phi:.2f}")
        )

    if stability is not None and stability.top_hotspot_id is not None:
        name = name_of(stability.top_hotspot_id)
        overlap = f"{stability.topk_overlap:.2f}"
        if stability.top_hotspot_survives:
            out.append(
                _(
                    "- **Re-segmentation (MAUP).** Redrawing the network into {coarse} coarser "
                    "units (from {fine}) leaves **{name}** the highest-rate, still-significant "
                    "cluster — the hotspot is not an artifact of where the block lines were "
                    "drawn. Top-{k} rank overlap: {overlap}."
                ).format(
                    coarse=stability.coarse_units,
                    fine=stability.fine_units,
                    name=name,
                    k=stability.k,
                    overlap=overlap,
                )
            )
        else:
            out.append(
                _(
                    "- **Re-segmentation (MAUP).** Redrawing the network into {coarse} coarser "
                    "units (from {fine}), **{name}** stays the highest-rate unit but loses "
                    "statistical significance at the coarser scale — read it as scale-sensitive, "
                    "a lead to confirm rather than a settled cluster. Top-{k} rank overlap: "
                    "{overlap}."
                ).format(
                    coarse=stability.coarse_units,
                    fine=stability.fine_units,
                    name=name,
                    k=stability.k,
                    overlap=overlap,
                )
            )
    out.append("")


def _render_bias_section(
    out: list[str],
    bundle: AnalysisBundle,
    publishable: set[str],
    name_of: Callable[[str], str],
    translation: gettext.NullTranslations,
) -> None:
    """Append the reporting-bias section, the over/under-represented lists, and the KDE peak."""
    _ = translation.gettext

    def bias_line(f: BiasFinding) -> str:
        template: str = _("- {name}: {rshare}% of reports vs {eshare}% of exposure")
        return template.format(
            name=name_of(f.segment_id),
            rshare=f"{f.report_share * 100:.0f}",
            eshare=f"{f.exposure_share * 100:.0f}",
        )

    bias = bundle.result.bias
    out.append(_("## Reporting bias (named, not hidden)"))
    out.append("")
    out.append(
        _(
            "Shares compare where reports land against where exposure is. They cannot, on their "
            "own, separate 'more dangerous' from 'more reported': reporter pools skew by route "
            "choice, demographics, app access, and language. Treat over-represented segments as "
            "candidates for attention and scrutiny, not as confirmed rankings."
        )
    )
    out.append("")
    out.append(
        _(
            "This does not mean nothing can be concluded — an exposure-normalized rate with a "
            "stated interval and a flagged bias is a far better basis for action than a raw heat "
            "map. It means: act on the strongest, most-significant signals, and treat the rest "
            "as leads to investigate, not verdicts."
        )
    )
    out.append("")
    over = [f for f in bias.over_represented if f.segment_id in publishable]
    under = [f for f in bias.under_represented if f.segment_id in publishable]
    if over:
        out.append(
            _("**Over-represented vs exposure** (more reports than traffic alone predicts):")
        )
        out.extend(bias_line(f) for f in over)
        out.append("")
    if under:
        out.append(
            _("**Under-represented vs exposure** (quiet in the data, not necessarily safe):")
        )
        out.extend(bias_line(f) for f in under)
        out.append("")

    peak_seg = bundle.result.kde_peak_segment
    if peak_seg is not None:
        out.append(
            _(
                "**Report-intensity peak (KDE, not danger):** around {name}. This shows where "
                "reports concentrate, which is not the same as where risk is highest."
            ).format(name=name_of(peak_seg))
        )
        out.append("")


def _render_calibration(
    out: list[str], config: Config, translation: gettext.NullTranslations
) -> None:
    """Append one sentence pointing at the published null-calibration artifact, if
    ``nearmiss analyze --calibrate`` has been run for this city (EXP-01: "we attacked
    our own dataset"). Silently omitted when the artifact hasn't been generated yet —
    the brief must never claim a calibration that wasn't actually run.
    """
    _ = translation.gettext
    calibration_path = config.out_dir / f"{_slug(config.city)}.calibration.json"
    if not calibration_path.is_file():
        return
    try:
        calib = json.loads(calibration_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    rate = calib.get("false_positive_rate")
    n_shuffles = calib.get("n_shuffles")
    if not isinstance(rate, int | float) or not isinstance(n_shuffles, int):
        return
    out.append(
        _(
            "**Null calibration (we attacked our own dataset):** on {n} seeded label-shuffles "
            "of this city's own reports, with exposure and geometry held fixed, the hotspot "
            "method's empirical false-positive rate was {pct}% — see `{file}`."
        ).format(n=n_shuffles, pct=f"{rate * 100:.2f}", file=calibration_path.name)
    )
    out.append("")


def render_brief(bundle: AnalysisBundle, config: Config, lang: str = "en") -> str:
    translation = get_translation(lang)
    _ = translation.gettext
    names = _names(bundle.segments)
    stats = bundle.result.segments
    publishable = {s.segment_id for s in stats if s.publishable}
    withheld = sum(1 for s in stats if not s.publishable)

    def name_of(sid: str) -> str:
        return names.get(sid, sid)

    ranked = sorted(
        (s for s in stats if s.rate is not None and s.publishable),
        key=lambda s: s.rate or 0.0,
        reverse=True,
    )

    out: list[str] = []
    _render_intro(out, bundle, config, withheld, translation)
    _render_glossary(out, config, translation)
    _render_bottom_line(out, ranked, name_of, config, translation)
    _render_top_table(out, ranked, name_of, config, translation)
    _render_dominant_hazard(out, ranked, name_of, config, translation)
    _render_hotspots(out, stats, name_of, config, translation)
    _render_corridors(out, bundle.result.corridors, config, translation)

    # Robustness checks: overdispersion (RR-02) and MAUP re-segmentation (RR-05).
    _render_robustness(out, bundle, translation, name_of)
    _render_bias_section(out, bundle, publishable, name_of, translation)
    _render_temporal(out, bundle, translation)
    _render_calibration(out, config, translation)

    out.append("---")
    out.append("")
    out.append(
        _(
            "Every figure above regenerates from raw inputs with `make reproduce`. Data and "
            "methods are open (Apache-2.0); see `docs/METHODOLOGY.md` and `docs/DATA-CARD.md`."
        )
    )
    out.append("")
    return "\n".join(out)


def _render_temporal(
    out: list[str], bundle: AnalysisBundle, translation: gettext.NullTranslations
) -> None:
    """Append the time-of-day / weather section (report VOLUME, never a rate)."""
    _ = translation.gettext
    ngettext = translation.ngettext
    tb = bundle.result.temporal
    out.append(_("## When hazards get reported (volume, not risk)"))
    out.append("")
    if tb.suppressed:
        out.append(
            _(
                "*Time-of-day breakdown withheld: too few timed reports to share without risking "
                "contributor privacy (k-anonymity).*"
            )
        )
        out.append("")
        return
    out.append(
        _(
            "This is **report volume** by time of day, not a rate: there is no time-of-day "
            "exposure denominator, so it reflects *when people ride and report*, not when a "
            "street is most dangerous. Read it as a lead for outreach timing, not a risk "
            "ranking."
        )
    )
    out.append("")
    total = tb.total_timed or 1
    for part, n in tb.by_part_of_day.items():
        line = ngettext(
            "- **{part}**: {n} report ({pct}%)",
            "- **{part}**: {n} reports ({pct}%)",
            n,
        )
        out.append(
            line.format(
                part=part_of_day_label(translation, part),
                n=n,
                pct=f"{n / total * 100:.0f}",
            )
        )
    out.append("")
    if tb.peak_part_of_day is not None and tb.peak_weekday is not None:
        out.append(
            _(
                "Most reports arrive during the **{part}**; the busiest day is **{weekday}**."
            ).format(
                part=part_of_day_label(translation, tb.peak_part_of_day),
                weekday=weekday_label(translation, tb.peak_weekday),
            )
        )
        out.append("")
    if tb.small_sample:
        out.append(_("*Small sample: too few timed reports to read these peaks with confidence.*"))
        out.append("")
    w = tb.weather
    if w is not None:
        rws = "—" if w.report_wet_share is None else f"{w.report_wet_share * 100:.0f}%"
        bws = "—" if w.baseline_wet_share is None else f"{w.baseline_wet_share * 100:.0f}%"
        out.append(
            _(
                "**Weather (association, not a risk rate):** {rws} of matched reports fell on "
                "wet days, while {bws} of days in the weather record were wet. Wet days usually "
                "carry far fewer riders, so this is an association to investigate, not a weather "
                "risk rate. Source: {src}."
            ).format(rws=rws, bws=bws, src=w.source)
        )
        out.append("")


def build_brief(config: Config, lang: str = "en") -> str:
    return render_brief(build_analysis(config), config, lang)
