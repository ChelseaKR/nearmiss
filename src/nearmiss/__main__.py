"""Command-line interface for nearmiss.

nearmiss intake   <reports.json>   --config C   # validate -> private raw store
nearmiss pipeline  --config C [--dump]          # dedupe/geocode/snap/classify/quality
nearmiss analyze   --config C                   # rates+CIs, bias, KDE, Getis-Ord, time-of-day
nearmiss analyze   --config C --calibrate       # + label-shuffle null-calibration artifact
nearmiss publish   --config C                   # open GeoJSON + aggregated public data
nearmiss brief     --config C [--out FILE]      # advocacy brief (markdown)
nearmiss run       --config C                   # intake -> ... -> brief, end to end
nearmiss submit   <submission.json> --config C  # queue a public submission (PENDING)
nearmiss moderate  list|approve|reject|export|stats --config C  # review the moderation queue
nearmiss serve     [--dir D] [--port P]         # accessible map + data view (read-only)
nearmiss version
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from pathlib import Path

from . import __version__, obs
from .brief import render_brief
from .config import Config, load_config
from .engine import AnalysisBundle, build_analysis
from .errors import NearmissError
from .figures import write_figures
from .intake import run_intake
from .loaders import load_reports
from .moderation import (
    APPROVED,
    PENDING,
    REJECTED,
    approve,
    approved_reports,
    list_submissions,
    moderation_stats,
    reject,
    submit,
)
from .publish import _slug, publish
from .server import serve
from .stats.calibration import DEFAULT_N_SHUFFLES, DEFAULT_SEED, run_null_calibration


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
    _print_temporal(bundle)
    if args.calibrate:
        _run_calibration(args, config, bundle)
    return 0


def _run_calibration(args: argparse.Namespace, config: Config, bundle: AnalysisBundle) -> None:
    """Attack our own dataset: label-shuffle this city's own counts (exposure
    and geometry held fixed) and publish the empirical false-positive rate
    beside the dataset (EXP-01, docs/ideation/03-expansions.md)."""
    result = run_null_calibration(
        bundle.result.segments,
        bundle.segments,
        config,
        n_shuffles=args.n_shuffles,
        seed=args.seed,
    )
    print(
        f"calibrate [{config.city}]: {result.n_shuffles} shuffles, "
        f"mean_false_positives={result.mean_false_positives:.3f}, "
        f"false_positive_rate={result.false_positive_rate:.2%}"
    )
    out_dir = Path(args.out) if args.out else config.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{_slug(config.city)}.calibration.json"
    out_path.write_text(
        json.dumps(result.to_metadata(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"  calibration: {out_path}")


def _print_temporal(bundle: AnalysisBundle) -> None:
    """Print the city-wide time-of-day report-volume breakdown (volume, not a rate)."""
    t = bundle.result.temporal
    if t.suppressed:
        print(
            f"  time-of-day: withheld ({t.total_timed} timed reports, below the k-anonymity floor)"
        )
        return
    parts = ", ".join(f"{p}={n}" for p, n in t.by_part_of_day.items())
    print(f"  time-of-day (report VOLUME, not a rate): {parts}")
    if t.peak_part_of_day is not None:
        print(f"    busiest part of day: {t.peak_part_of_day}; busiest weekday: {t.peak_weekday}")
    if t.small_sample:
        print("    (small sample — peaks shown with caution)")
    w = t.weather
    if w is not None:
        rws = "n/a" if w.report_wet_share is None else f"{w.report_wet_share:.0%}"
        bws = "n/a" if w.baseline_wet_share is None else f"{w.baseline_wet_share:.0%}"
        print(
            f"  weather (association, not a risk rate): {rws} of matched reports on wet days "
            f"vs {bws} of days wet [source: {w.source}]"
        )


def _cmd_publish(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    result = publish(config)
    print(f"publish [{config.city}]: {result.geojson_path}")
    print(f"  metadata: {result.metadata_path}")
    print(f"  manifest: {result.manifest_path}")
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
    # Structured pipeline-stage telemetry: one JSON line per stage on stdout, via
    # the same StructuredLogger the read-only server uses. Counts are provenance;
    # ``ms`` is a wall-time sidecar (never hashed into the manifest digest).
    logger = obs.get_logger()
    for stage in bundle.stages:
        logger.emit(
            "info",
            "stage",
            stage=stage.get("stage"),
            counts=stage.get("counts"),
            ms=stage.get("ms"),
        )
    print(f"run [{config.city}]: {len(rows)} reports -> {result.geojson_path}")
    print(f"  sha256: {result.geojson_sha256}")
    print(f"  manifest: {result.manifest_path} (digest {result.manifest_digest[:12]})")
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


def _normalize_reports(source: Path) -> list[dict[str, object]]:
    """Accept a single report object, a list, or a {'reports': [...]} wrapper."""
    data = json.loads(source.read_text(encoding="utf-8"))
    if isinstance(data, dict) and "reports" not in data:
        return [data]  # a lone report object, as the web form emits
    return load_reports(source)


def _cmd_submit(args: argparse.Namespace) -> int:
    """Ingest a public submission (the form's JSON) into the moderation queue."""
    config = load_config(args.config)
    reports = _normalize_reports(Path(args.source))
    for report in reports:
        sub = submit(config, report)
        flags = f" flags={sub.flags}" if sub.flags else ""
        print(f"submit: queued {sub.submission_id} (pending review){flags}")
    print(f"submit: {len(reports)} submission(s) pending in {config.submissions_dir}")
    return 0


def _cmd_moderate(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    action = args.action
    if action == "list":
        status = args.status
        subs = list_submissions(config, status)
        if not subs:
            print(f"moderate: no submissions{f' with status {status}' if status else ''}.")
            return 0
        for s in subs:
            flags = f" flags={s.flags}" if s.flags else ""
            reason = f" reason={s.reason!r}" if s.reason else ""
            print(f"  [{s.status}] {s.submission_id} received={s.received_at}{flags}{reason}")
        print(f"moderate: {len(subs)} submission(s).")
        return 0
    if action == "approve":
        sub = approve(config, args.id, args.note)
        print(
            f"moderate: approved {sub.submission_id} -> approved store (now in the pipeline feed)"
        )
        return 0
    if action == "reject":
        sub = reject(config, args.id, args.reason)
        print(f"moderate: rejected {sub.submission_id} ({sub.reason})")
        return 0
    if action == "stats":
        return _moderate_stats(config, args.out)
    if action == "export":
        reports = approved_reports(config)
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps({"reports": reports}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"moderate: exported {len(reports)} approved report(s) to {out}")
        return 0
    raise NearmissError(f"unknown moderate action {action!r}")  # pragma: no cover


def _fmt_cell(value: object) -> str:
    """Render one count cell for the terminal: a withheld cell shows as such."""
    return "withheld" if value is None else str(value)


def _fmt_counts(counts: dict[str, object]) -> str:
    return ", ".join(f"{k}={_fmt_cell(v)}" for k, v in counts.items()) or "(none)"


def _render_stats_markdown(stats: dict[str, object]) -> str:
    """A dated, human-readable transparency report. Only categories and floored
    counts appear — never a submission's free-text reason."""
    status = stats["status_counts"]
    reasons = stats["reason_categories"]
    flags = stats["flag_counts"]
    latency = stats["review_latency_hours"]
    assert isinstance(status, dict) and isinstance(reasons, dict) and isinstance(flags, dict)
    assert isinstance(latency, dict)
    date = str(stats["generated_at"])[:10]
    median = latency["median"]
    median_str = (
        "withheld (below floor)"
        if median is None and latency["withheld"]
        else ("n/a (no decisions yet)" if median is None else f"{median} h")
    )
    lines = [
        f"# Moderation transparency report — {date}",
        "",
        "Aggregate, privacy-floored moderation statistics. Rejection reasons are shown only as",
        f"coarse categories (never free text), and any count below the k-anonymity floor "
        f"(`min_publish_n = {stats['min_publish_n']}`) is withheld.",
        "",
        f"- Total submissions: **{stats['total_submissions']}**",
        f"- Withheld cells (low count): **{stats['withheld_cells']}**",
        "",
        "## Submissions by status",
        "",
        f"- {_fmt_counts(status)}",
        "",
        "## Rejection-reason categories",
        "",
        f"- {_fmt_counts(reasons)}",
        "",
        "## Review flags",
        "",
        f"- {_fmt_counts(flags)}",
        "",
        "## Review latency",
        "",
        f"- Median (received -> decided): **{median_str}** across {latency['n_decided']} decided "
        "submission(s).",
        "",
    ]
    return "\n".join(lines)


def _moderate_stats(config: Config, out: str | None) -> int:
    stats = moderation_stats(config)
    status = stats["status_counts"]
    reasons = stats["reason_categories"]
    latency = stats["review_latency_hours"]
    assert isinstance(status, dict) and isinstance(reasons, dict) and isinstance(latency, dict)
    print(f"moderate stats [{config.city}]: {stats['total_submissions']} submission(s) total")
    print(f"  by status: {_fmt_counts(status)}")
    print(f"  reason categories: {_fmt_counts(reasons)}")
    median = latency["median"]
    if median is None and latency["withheld"]:
        median_str = "withheld (below floor)"
    elif median is None:
        median_str = "n/a"
    else:
        median_str = f"{median} h"
    print(f"  median review latency: {median_str} (n_decided={latency['n_decided']})")
    floor, withheld = stats["min_publish_n"], stats["withheld_cells"]
    print(f"  withheld cells (k-anonymity floor {floor}): {withheld}")
    if out:
        out_path = Path(out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        if out_path.suffix.lower() == ".json":
            out_path.write_text(
                json.dumps(stats, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
        else:
            out_path.write_text(_render_stats_markdown(stats), encoding="utf-8")
        print(f"  report written to {out_path}")
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
    p_an.add_argument(
        "--calibrate",
        action="store_true",
        help="also run a seeded label-shuffle null calibration and write <slug>.calibration.json",
    )
    p_an.add_argument(
        "--n-shuffles",
        type=int,
        default=DEFAULT_N_SHUFFLES,
        help=f"number of label-shuffles for --calibrate (default {DEFAULT_N_SHUFFLES})",
    )
    p_an.add_argument(
        "--seed",
        type=int,
        default=DEFAULT_SEED,
        help=f"deterministic RNG seed for --calibrate (default {DEFAULT_SEED})",
    )
    p_an.add_argument(
        "--out", help="output directory for --calibrate (defaults to the published dir)"
    )
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

    p_submit = sub.add_parser("submit", help="queue a public submission for moderation (pending)")
    p_submit.add_argument("source", help="submission JSON (one report, a list, or {reports:[...]})")
    add_config(p_submit)
    p_submit.set_defaults(func=_cmd_submit)

    p_mod = sub.add_parser("moderate", help="review the public-submission moderation queue")
    add_config(p_mod)
    mod_sub = p_mod.add_subparsers(dest="action", required=True)
    m_list = mod_sub.add_parser("list", help="list queued submissions")
    m_list.add_argument("--status", choices=[PENDING, APPROVED, REJECTED], help="filter by status")
    m_approve = mod_sub.add_parser("approve", help="approve a pending submission into the dataset")
    m_approve.add_argument("id", help="submission id")
    m_approve.add_argument("--note", help="optional approver note")
    m_reject = mod_sub.add_parser("reject", help="reject a submission with a reason")
    m_reject.add_argument("id", help="submission id")
    m_reject.add_argument("--reason", required=True, help="why it was rejected")
    m_export = mod_sub.add_parser("export", help="write approved reports as a pipeline-ready file")
    m_export.add_argument("out", help="output reports JSON path")
    m_stats = mod_sub.add_parser(
        "stats", help="publish a privacy-floored moderation transparency report"
    )
    m_stats.add_argument(
        "--out",
        help="also write a dated artifact (.md for Markdown, .json for JSON), "
        "e.g. docs/audits/YYYY-MM-DD-moderation.md",
    )
    p_mod.set_defaults(func=_cmd_moderate)

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
