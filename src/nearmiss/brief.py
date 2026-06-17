"""Render an advocacy brief that a city council can read and a skeptic can check.

Every ranked location is a rate with a confidence interval and an n; significant
clusters are flagged from Getis-Ord Gi*; the reporting bias is named in plain
language; and the brief states the exposure assumptions behind every number.
The output is deterministic markdown.
"""

from __future__ import annotations

from .config import Config
from .engine import AnalysisBundle, build_analysis
from .models import Segment, SegmentStats
from .stats.bias import BiasFinding


def _names(segments: list[Segment]) -> dict[str, str]:
    return {s.id: s.name for s in segments}


def _fmt(value: float | None) -> str:
    return "—" if value is None else f"{value:.2f}"


def render_brief(bundle: AnalysisBundle, config: Config) -> str:
    names = _names(bundle.segments)
    stats = bundle.result.segments
    per = int(config.rate_per)
    # The brief is a PUBLISHED artifact: only reference segments that clear the
    # minimum-occupancy floor (withheld ones are never named).
    publishable = {s.segment_id for s in stats if s.publishable}
    withheld = sum(1 for s in stats if not s.publishable)

    def bias_line(f: BiasFinding) -> str:
        name = names.get(f.segment_id, f.segment_id)
        return (
            f"- {name}: {f.report_share * 100:.0f}% of reports "
            f"vs {f.exposure_share * 100:.0f}% of exposure"
        )

    ranked = sorted(
        (s for s in stats if s.rate is not None and s.publishable),
        key=lambda s: s.rate or 0.0,
        reverse=True,
    )

    lines: list[str] = []
    lines.append(f"# Where the danger actually is — {config.city}")
    lines.append("")
    if config.dataset_note:
        lines.append(f"> ⚠️ **{config.dataset_note}**")
        lines.append("")
    lines.append(
        "> Rates are reports per "
        f"{per} units of exposure. Every rate carries a 95% confidence interval "
        "and an n. Raw counts are not danger; they are report volume. Read the "
        "caveats — they are the point."
    )
    lines.append("")
    cov = bundle.result.exposure_coverage
    lines.append(
        f"**Exposure coverage:** {cov * 100:.0f}% of segments have an exposure "
        "denominator. Segments without one are listed as *exposure unknown*, not ranked."
    )
    lines.append("")
    if withheld:
        lines.append(
            f"*{withheld} segment(s) with fewer than {config.min_publish_n} reports are withheld "
            "from this brief and the open dataset to protect contributor privacy (k-anonymity).*"
        )
        lines.append("")

    lines.append("## Highest-rate segments (exposure-normalized)")
    lines.append("")
    lines.append(f"| Rank | Segment | Rate /{per} | 95% CI | n | Confidence | Hotspot |")
    lines.append("| ---: | --- | ---: | --- | ---: | --- | --- |")
    for i, s in enumerate(ranked[:10], start=1):
        ci = f"{_fmt(s.rate_ci_low)}-{_fmt(s.rate_ci_high)}"
        hotspot = (
            f"★ Gi* z={s.getis_ord_z:.2f}" if (s.significant and s.getis_ord_z is not None) else ""
        )
        lines.append(
            f"| {i} | {names.get(s.segment_id, s.segment_id)} | {_fmt(s.rate)} | "
            f"{ci} | {s.n} | {s.confidence_label} | {hotspot} |"
        )
    lines.append("")

    sig: list[SegmentStats] = [s for s in stats if s.significant and s.publishable]
    lines.append("## Statistically significant hotspots (Getis-Ord Gi*)")
    lines.append("")
    if sig:
        lines.append(
            "These segments are hot *beyond* what exposure and spatial structure explain "
            "— candidates for hot because dangerous, not hot because busy:"
        )
        lines.append("")
        for s in sorted(sig, key=lambda s: s.getis_ord_z or 0.0, reverse=True):
            lines.append(
                f"- **{names.get(s.segment_id, s.segment_id)}** — Gi* z = "
                f"{s.getis_ord_z:.2f}, rate {_fmt(s.rate)}/{per} (CI "
                f"{_fmt(s.rate_ci_low)}-{_fmt(s.rate_ci_high)}, n={s.n})"
            )
    else:
        lines.append("No segment reaches statistical significance at this sample size.")
    lines.append("")

    bias = bundle.result.bias
    lines.append("## Reporting bias (named, not hidden)")
    lines.append("")
    lines.append(bias.note)
    lines.append("")
    if bias.over_represented:
        lines.append("**Over-represented vs exposure** (more reports than traffic alone predicts):")
        for f in bias.over_represented:
            if f.segment_id in publishable:
                lines.append(bias_line(f))
        lines.append("")
    if bias.under_represented:
        lines.append("**Under-represented vs exposure** (quiet in the data, not necessarily safe):")
        for f in bias.under_represented:
            if f.segment_id in publishable:
                lines.append(bias_line(f))
        lines.append("")

    peak_seg = bundle.result.kde_peak_segment
    if peak_seg is not None:
        lines.append(
            "**Report-intensity peak (KDE, not danger):** around "
            f"{names.get(peak_seg, peak_seg)}. This shows where reports concentrate, "
            "which is not the same as where risk is highest."
        )
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append(
        "Every figure above regenerates from raw inputs with `make reproduce`. Data and "
        "methods are open (Apache-2.0); see `docs/METHODOLOGY.md` and `docs/DATA-CARD.md`."
    )
    lines.append("")
    return "\n".join(lines)


def build_brief(config: Config) -> str:
    return render_brief(build_analysis(config), config)
