"""Deterministic advocacy figures (no plotting dependency).

Emits a hand-built SVG bar chart of the exposure-normalized segment rates (with
confidence-interval whiskers, the significant hotspot marked by text + pattern,
never color alone) and a ranked markdown table. Output is byte-stable — every
number is rounded and there is no embedded date — so ``make reproduce`` can diff
it. The analysis notebook renders the same figure; this module is what makes it
reproducible without pinning a plotting library.
"""

from __future__ import annotations

from pathlib import Path

from .config import Config
from .engine import build_analysis
from .models import SegmentStats

_W = 680
_ROW_H = 26
_LEFT = 210  # label gutter
_RIGHT = 70  # value gutter
_TOP = 56


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _published_ranked(config: Config) -> tuple[list[SegmentStats], dict[str, str]]:
    bundle = build_analysis(config)
    names = {s.id: s.name for s in bundle.segments}
    ranked = sorted(
        (s for s in bundle.result.segments if s.rate is not None and s.publishable),
        key=lambda s: s.rate or 0.0,
        reverse=True,
    )
    return ranked, names


def render_bar_svg(config: Config, top_n: int = 10) -> str:
    ranked, names = _published_ranked(config)
    rows = ranked[:top_n]
    per = int(config.rate_per)
    max_rate = max((s.rate or 0.0 for s in rows), default=1.0) or 1.0
    plot_w = _W - _LEFT - _RIGHT
    height = _TOP + _ROW_H * len(rows) + 16

    parts: list[str] = []
    parts.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{_W}" height="{height}" '
        f'viewBox="0 0 {_W} {height}" role="img" '
        f'aria-label="Exposure-normalized hazard rate per {per} by segment, {config.city}">'
    )
    parts.append(f"<title>Hazard rate per {per} by segment — {_esc(config.city)}</title>")
    parts.append(
        f'<text x="16" y="28" font-family="sans-serif" font-size="16" font-weight="bold">'
        f"Hazard rate per {per} {_esc(config.exposure_unit)} — {_esc(config.city)}</text>"
    )
    for i, s in enumerate(rows):
        y = _TOP + i * _ROW_H
        rate = s.rate or 0.0
        bar = round(plot_w * rate / max_rate, 1)
        hot = s.significant
        fill = "#8a1c1c" if hot else "#0b4f9c"
        label = names.get(s.segment_id, s.segment_id)
        star = "★ " if hot else ""
        # Label (right-aligned in the gutter).
        parts.append(
            f'<text x="{_LEFT - 8}" y="{y + 16}" font-family="sans-serif" font-size="12" '
            f'text-anchor="end">{_esc(star + label)}</text>'
        )
        # Bar (hotspot gets a dashed outline = a non-color pattern marker).
        extra = ' stroke="#000" stroke-width="1" stroke-dasharray="3 2"' if hot else ""
        parts.append(
            f'<rect x="{_LEFT}" y="{y + 4}" width="{bar}" height="16" fill="{fill}"{extra}/>'
        )
        # CI whisker.
        if s.rate_ci_low is not None and s.rate_ci_high is not None:
            lo = round(_LEFT + plot_w * (s.rate_ci_low or 0.0) / max_rate, 1)
            hi = round(_LEFT + plot_w * (s.rate_ci_high or 0.0) / max_rate, 1)
            cy = y + 12
            parts.append(
                f'<line x1="{lo}" y1="{cy}" x2="{hi}" y2="{cy}" stroke="#222" stroke-width="1"/>'
                f'<line x1="{lo}" y1="{cy - 3}" x2="{lo}" y2="{cy + 3}" stroke="#222"/>'
                f'<line x1="{hi}" y1="{cy - 3}" x2="{hi}" y2="{cy + 3}" stroke="#222"/>'
            )
        # Value.
        parts.append(
            f'<text x="{_W - 8}" y="{y + 16}" font-family="sans-serif" font-size="12" '
            f'text-anchor="end">{rate:.1f}</text>'
        )
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def render_ranked_md(config: Config, top_n: int = 10) -> str:
    ranked, names = _published_ranked(config)
    per = int(config.rate_per)
    out = [f"# Ranked segments — {config.city}", ""]
    out.append(f"| Rank | Segment | Rate /{per} | 95% CI | n | Hotspot |")
    out.append("| ---: | --- | ---: | --- | ---: | --- |")
    for i, s in enumerate(ranked[:top_n], start=1):
        ci = f"{s.rate_ci_low:.2f}–{s.rate_ci_high:.2f}" if s.rate_ci_low is not None else "—"
        hot = (
            f"★ Gi* z={s.getis_ord_z:.2f}" if (s.significant and s.getis_ord_z is not None) else ""
        )
        nm = names.get(s.segment_id, s.segment_id)
        out.append(f"| {i} | {nm} | {s.rate:.2f} | {ci} | {s.n} | {hot} |")
    out.append("")
    return "\n".join(out)


def write_figures(config: Config, out_dir: Path, slug: str = "davis") -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    svg_path = out_dir / f"{slug}-rates.svg"
    md_path = out_dir / f"{slug}-ranked.md"
    svg_path.write_text(render_bar_svg(config), encoding="utf-8")
    md_path.write_text(render_ranked_md(config), encoding="utf-8")
    return [svg_path, md_path]
