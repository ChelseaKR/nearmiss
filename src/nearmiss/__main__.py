"""Command-line interface for nearmiss.

nearmiss intake   <reports.json>   --config C   # validate -> private raw store
nearmiss pipeline  --config C [--dump]          # dedupe/geocode/snap/classify/quality
nearmiss analyze   --config C                   # rates+CIs, bias, KDE, Getis-Ord
nearmiss publish   --config C                   # open GeoJSON + aggregated public data
nearmiss brief     --config C [--out FILE]      # advocacy brief (markdown)
nearmiss run       --config C                   # intake -> ... -> brief, end to end
nearmiss serve     [--dir D] [--port P]         # accessible map + data view (read-only)
nearmiss version
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from pathlib import Path

from . import __version__
from .brief import render_brief
from .config import load_config
from .engine import build_analysis
from .errors import NearmissError
from .figures import write_figures
from .intake import run_intake
from .publish import _slug, publish
from .server import serve


def _warn_unmatched(unmatched: list[str]) -> None:
    if unmatched:
        print(
            f"warning: {len(unmatched)} exposure segment_id(s) match no street segment "
            f"and are ignored (e.g. {unmatched[:3]})",
            file=sys.stderr,
        )


def _cmd_intake(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    source = Path(args.source) if args.source else None
    rows = run_intake(config, source)
    print(f"intake: {len(rows)} reports validated into {config.raw_dir}")
    return 0


def _cmd_pipeline(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    bundle = build_analysis(config)
    s = bundle.summary
    print(
        f"pipeline [{config.city}]: in={s['reports_in']} "
        f"dupes_removed={s['duplicates_removed']} snapped={s['snapped']} "
        f"unsnapped={s['unsnapped']}"
    )
    if args.dump:
        records = [dataclasses.asdict(r) for r in bundle.records]
        print(json.dumps(records, ensure_ascii=False, indent=2))
    return 0


def _cmd_analyze(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    bundle = build_analysis(config)
    _warn_unmatched(bundle.exposure_unmatched)
    ranked = sorted(
        (s for s in bundle.result.segments if s.rate is not None),
        key=lambda s: s.rate or 0.0,
        reverse=True,
    )
    print(f"analyze [{config.city}]: exposure_coverage={bundle.result.exposure_coverage:.0%}")
    for s in ranked[:5]:
        flag = " *significant*" if s.significant else ""
        print(
            f"  {s.segment_id}: rate={s.rate} "
            f"CI=[{s.rate_ci_low}, {s.rate_ci_high}] n={s.n} ({s.confidence_label}){flag}"
        )
    return 0


def _cmd_publish(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    result = publish(config)
    print(f"publish [{config.city}]: {result.geojson_path}")
    print(f"  metadata: {result.metadata_path}")
    print(f"  sha256:   {result.geojson_sha256}")
    return 0


def _cmd_brief(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    text = render_brief(build_analysis(config), config, args.lang)
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        print(f"brief written to {args.out}")
    else:
        print(text)
    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    rows = run_intake(config)
    result = publish(config)
    bundle = build_analysis(config)
    print(f"run [{config.city}]: {len(rows)} reports -> {result.geojson_path}")
    print(f"  sha256: {result.geojson_sha256}")
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(render_brief(bundle, config, args.lang), encoding="utf-8")
        print(f"  brief:  {args.out}")
    return 0


def _cmd_figures(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    out_dir = Path(args.out) if args.out else config.out_dir
    paths = write_figures(config, out_dir, _slug(config.city))
    for p in paths:
        print(f"figures: {p}")
    return 0


def _cmd_serve(args: argparse.Namespace) -> int:
    serve(Path(args.dir), port=args.port)
    return 0


def _cmd_version(_args: argparse.Namespace) -> int:
    print(__version__)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="nearmiss", description=__doc__)
    parser.add_argument("--version", action="version", version=f"nearmiss {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    def add_config(p: argparse.ArgumentParser) -> None:
        p.add_argument("--config", required=True, help="path to a city config (TOML/JSON)")

    p_intake = sub.add_parser("intake", help="validate reports into the private raw store")
    p_intake.add_argument("source", nargs="?", help="reports JSON (defaults to config)")
    add_config(p_intake)
    p_intake.set_defaults(func=_cmd_intake)

    p_pipe = sub.add_parser("pipeline", help="run the dedupe/geocode/snap/classify pipeline")
    add_config(p_pipe)
    p_pipe.add_argument("--dump", action="store_true", help="print intermediate clean records")
    p_pipe.set_defaults(func=_cmd_pipeline)

    p_an = sub.add_parser("analyze", help="compute exposure-normalized rates, CIs, hotspots")
    add_config(p_an)
    p_an.set_defaults(func=_cmd_analyze)

    p_pub = sub.add_parser("publish", help="build the open GeoJSON + aggregated public dataset")
    add_config(p_pub)
    p_pub.set_defaults(func=_cmd_publish)

    p_brief = sub.add_parser("brief", help="render an advocacy brief")
    add_config(p_brief)
    p_brief.add_argument("--out", help="write the brief to a file instead of stdout")
    p_brief.add_argument("--lang", default="en", choices=["en", "es"], help="brief language")
    p_brief.set_defaults(func=_cmd_brief)

    p_run = sub.add_parser("run", help="intake -> pipeline -> analyze -> publish -> brief")
    add_config(p_run)
    p_run.add_argument("--out", help="also write the brief to this file")
    p_run.add_argument("--lang", default="en", choices=["en", "es"], help="brief language")
    p_run.set_defaults(func=_cmd_run)

    p_fig = sub.add_parser("figures", help="render the deterministic SVG chart + ranked table")
    add_config(p_fig)
    p_fig.add_argument("--out", help="output directory (defaults to the published dir)")
    p_fig.set_defaults(func=_cmd_figures)

    p_serve = sub.add_parser("serve", help="serve the accessible map + data view (read-only)")
    p_serve.add_argument("--dir", default=".", help="directory to serve (repo root)")
    p_serve.add_argument("--port", type=int, default=8000)
    p_serve.set_defaults(func=_cmd_serve)

    p_ver = sub.add_parser("version", help="print the version")
    p_ver.set_defaults(func=_cmd_version)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        result: int = args.func(args)
        return result
    except NearmissError as exc:
        print(f"nearmiss: error: {exc}", file=sys.stderr)
        problems = getattr(exc, "problems", None)
        if problems:
            for p in problems[:20]:
                print(f"  - {p}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
