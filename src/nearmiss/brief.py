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

from .config import Config
from .engine import AnalysisBundle, build_analysis
from .i18n import (
    confidence_label,
    get_translation,
    part_of_day_label,
    weekday_label,
)
from .models import Segment, SegmentStats
from .stats.bias import BiasFinding


def _names(segments: list[Segment]) -> dict[str, str]:
    return {s.id: s.name for s in segments}


def _fmt(value: float | None) -> str:
    return "—" if value is None else f"{value:.2f}"


def render_brief(bundle: AnalysisBundle, config: Config, lang: str = "en") -> str:
    translation = get_translation(lang)
    _ = translation.gettext
    ngettext = translation.ngettext
    names = _names(bundle.segments)
    stats = bundle.result.segments
    per = int(config.rate_per)
    unit = config.exposure_unit
    publishable = {s.segment_id for s in stats if s.publishable}
    withheld = sum(1 for s in stats if not s.publishable)

    def name_of(sid: str) -> str:
        return names.get(sid, sid)

    def bias_line(f: BiasFinding) -> str:
        template: str = _("- {name}: {rshare}% of reports vs {eshare}% of exposure")
        return template.format(
            name=name_of(f.segment_id),
            rshare=f"{f.report_share * 100:.0f}",
            eshare=f"{f.exposure_share * 100:.0f}",
        )

    ranked = sorted(
        (s for s in stats if s.rate is not None and s.publishable),
        key=lambda s: s.rate or 0.0,
        reverse=True,
    )

    out: list[str] = []
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

    # Plain-language glossary.
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

    # Bottom-line sentence (the headline a non-statistician can read aloud).
    if ranked:
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

    # Highest-rate table.
    out.append(_("## Highest-rate segments (exposure-normalized)"))
    out.append("")
    th_rank = _("Rank")
    th_segment = _("Segment")
    th_rate = _("Rate /{per}").format(per=per)
    th_ci = _("95% CI")
    th_n = _("n")
    th_confidence = _("Confidence")
    th_hotspot = _("Hotspot")
    out.append(
        f"| {th_rank} | {th_segment} | {th_rate} | {th_ci} | {th_n} | {th_confidence} | "
        f"{th_hotspot} |"
    )
    out.append("| ---: | --- | ---: | --- | ---: | --- | --- |")
    for i, s in enumerate(ranked[:10], start=1):
        ci = f"{_fmt(s.rate_ci_low)}-{_fmt(s.rate_ci_high)}"
        hotspot = (
            f"★ Gi* z={s.getis_ord_z:.2f}" if (s.significant and s.getis_ord_z is not None) else ""
        )
        out.append(
            f"| {i} | {name_of(s.segment_id)} | {_fmt(s.rate)} | "
            f"{ci} | {s.n} | {confidence_label(translation, s.confidence_label)} | {hotspot} |"
        )
    out.append("")

    # Significant hotspots.
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

    # Reporting bias, with a counterweight so honesty does not read as "conclude nothing."
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

    _render_temporal(out, bundle, translation)

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
