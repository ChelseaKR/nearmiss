"""The reproducible figures are deterministic and mark the hotspot accessibly."""

from __future__ import annotations

import json

from nearmiss.config import Config
from nearmiss.figures import render_bar_svg, render_ranked_md


def test_svg_is_deterministic_and_valid(config: Config) -> None:
    a = render_bar_svg(config)
    b = render_bar_svg(config)
    assert a == b  # byte-stable -> make reproduce can diff it
    assert a.startswith("<svg") and a.rstrip().endswith("</svg>")


def test_svg_marks_the_hotspot_without_relying_on_color(config: Config) -> None:
    svg = render_bar_svg(config)
    # The hotspot is marked by a ★ in text and a dashed outline (a pattern), not color alone.
    assert "★" in svg
    assert "stroke-dasharray" in svg


def test_notebook_is_valid_and_references_figures() -> None:
    import pathlib

    nb_path = pathlib.Path(__file__).resolve().parents[1] / "notebooks" / "hotspots.ipynb"
    nb = json.loads(nb_path.read_text(encoding="utf-8"))
    assert nb["nbformat"] == 4
    source = "".join("".join(c.get("source", [])) for c in nb["cells"])
    assert "from nearmiss import figures" in source
    assert "render_bar_svg" in source


def test_ranked_md_has_the_planted_hotspot(config: Config) -> None:
    md = render_ranked_md(config)
    assert "5th St (C–D)" in md
    assert "Gi* z=" in md
