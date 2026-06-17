"""Render an advocacy brief that a city council can read and a skeptic can check.

Every ranked location is a rate with a confidence interval and an n; significant
clusters are flagged from Getis-Ord Gi* (FDR-corrected); the reporting bias is
named in plain language; and a plain-language glossary plus a bottom-line
sentence make it usable without a statistics background. The output is
deterministic markdown and can render in English or Spanish.
"""

from __future__ import annotations

from .config import Config
from .engine import AnalysisBundle, build_analysis
from .i18n import strings
from .models import Segment, SegmentStats
from .stats.bias import BiasFinding


def _names(segments: list[Segment]) -> dict[str, str]:
    return {s.id: s.name for s in segments}


def _fmt(value: float | None) -> str:
    return "—" if value is None else f"{value:.2f}"


def render_brief(bundle: AnalysisBundle, config: Config, lang: str = "en") -> str:
    t = strings(lang)
    names = _names(bundle.segments)
    stats = bundle.result.segments
    per = int(config.rate_per)
    unit = config.exposure_unit
    publishable = {s.segment_id for s in stats if s.publishable}
    withheld = sum(1 for s in stats if not s.publishable)

    def name_of(sid: str) -> str:
        return names.get(sid, sid)

    def label(confidence_label: str) -> str:
        return t.get(f"label_{confidence_label}", confidence_label.replace("_", " "))

    def bias_line(f: BiasFinding) -> str:
        return t["share_line"].format(
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
    out.append(f"# {t['title'].format(city=config.city)}")
    out.append("")
    if config.dataset_note:
        out.append(f"> ⚠️ **{config.dataset_note}**")
        out.append("")
    out.append(t["intro"].format(per=per, unit=unit))
    out.append("")
    out.append(t["coverage"].format(pct=f"{bundle.result.exposure_coverage * 100:.0f}"))
    out.append("")
    if withheld:
        out.append(t["withheld"].format(n=withheld, floor=config.min_publish_n))
        out.append("")

    # Plain-language glossary.
    out.append(t["glossary_heading"])
    out.append("")
    out.append(t["glossary_rate"].format(per=per, unit=unit))
    out.append(t["glossary_ci"])
    out.append(t["glossary_gi"])
    out.append("")

    # Bottom-line sentence (the headline a non-statistician can read aloud).
    if ranked:
        top = ranked[0]
        out.append(
            t["bottom_line"].format(
                name=name_of(top.segment_id),
                rate=_fmt(top.rate),
                per=per,
                unit=unit,
                lo=_fmt(top.rate_ci_low),
                hi=_fmt(top.rate_ci_high),
                n=top.n,
                sig=t["sig_yes"] if top.significant else t["sig_no"],
            )
        )
        out.append("")

    # Highest-rate table.
    out.append(t["highest_heading"])
    out.append("")
    header = (
        f"| {t['th_rank']} | {t['th_segment']} | {t['th_rate'].format(per=per)} | "
        f"{t['th_ci']} | {t['th_n']} | {t['th_confidence']} | {t['th_hotspot']} |"
    )
    out.append(header)
    out.append("| ---: | --- | ---: | --- | ---: | --- | --- |")
    for i, s in enumerate(ranked[:10], start=1):
        ci = f"{_fmt(s.rate_ci_low)}-{_fmt(s.rate_ci_high)}"
        hotspot = (
            f"★ Gi* z={s.getis_ord_z:.2f}" if (s.significant and s.getis_ord_z is not None) else ""
        )
        out.append(
            f"| {i} | {name_of(s.segment_id)} | {_fmt(s.rate)} | "
            f"{ci} | {s.n} | {label(s.confidence_label)} | {hotspot} |"
        )
    out.append("")

    # Significant hotspots.
    sig: list[SegmentStats] = [s for s in stats if s.significant and s.publishable]
    out.append(t["significant_heading"])
    out.append("")
    if sig:
        out.append(t["significant_intro"])
        out.append("")
        for s in sorted(sig, key=lambda s: s.getis_ord_z or 0.0, reverse=True):
            out.append(
                f"- **{name_of(s.segment_id)}** — Gi* z = "
                f"{s.getis_ord_z:.2f}, rate {_fmt(s.rate)}/{per} (CI "
                f"{_fmt(s.rate_ci_low)}-{_fmt(s.rate_ci_high)}, n={s.n})"
            )
    else:
        out.append(t["significant_none"])
    out.append("")

    # Reporting bias, with a counterweight so honesty does not read as "conclude nothing."
    bias = bundle.result.bias
    out.append(t["bias_heading"])
    out.append("")
    out.append(t["bias_note"])
    out.append("")
    out.append(t["bias_counterweight"])
    out.append("")
    over = [f for f in bias.over_represented if f.segment_id in publishable]
    under = [f for f in bias.under_represented if f.segment_id in publishable]
    if over:
        out.append(t["over_heading"])
        out.extend(bias_line(f) for f in over)
        out.append("")
    if under:
        out.append(t["under_heading"])
        out.extend(bias_line(f) for f in under)
        out.append("")

    peak_seg = bundle.result.kde_peak_segment
    if peak_seg is not None:
        out.append(t["peak"].format(name=name_of(peak_seg)))
        out.append("")

    out.append("---")
    out.append("")
    out.append(t["footer"])
    out.append("")
    return "\n".join(out)


def build_brief(config: Config, lang: str = "en") -> str:
    return render_brief(build_analysis(config), config, lang)
