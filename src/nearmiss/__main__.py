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
nearmiss contributor export|delete|purge-expired --config C  # data-rights (token = auth)
nearmiss preregister --config C [--out DIR]     # EXP-16: freeze flagged corridors (hash+timestamp)
nearmiss score-preregistration --registration F --config C [--out DIR]  # EXP-16: score vs held-out
nearmiss coverage  --config C [--registry R] [--fars-root R]  # evidence + verified gaps
nearmiss ingest-fars EXPORT --root R --year Y # preserve + validate a private FARS artifact
nearmiss ingest-fars-joined EXPORT --root R    # private 2024 crash/person join
nearmiss serve     [--dir D] [--port P]         # accessible map + data view (read-only)
nearmiss version
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import json
import math
import sys
from pathlib import Path

from . import __version__, obs
from .brief import render_brief
from .config import Config, load_config
from .contributor import delete_reports, export_reports, purge_expired
from .coverage import assess_coverage, load_source_registry
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
from .preregister import (
    DEFAULT_REGISTRATION_DIR,
    DEFAULT_SIGNOFF_PATH,
    load_registration,
    score_registration,
    write_registration,
    write_score_result,
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
    print(f"  metadata:  {result.metadata_path}")
    print(f"  manifest:  {result.manifest_path}")
    print(f"  sha256:    {result.geojson_sha256}")
    print(f"  corridors: {result.corridor_geojson_path} ({result.corridor_count} corridor(s))")
    return 0


def _cmd_preregister(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    out_dir = Path(args.out) if args.out else DEFAULT_REGISTRATION_DIR
    signoff_path = Path(args.signoff) if args.signoff else DEFAULT_SIGNOFF_PATH
    result = write_registration(config, out_dir, signoff_path=signoff_path)
    print(f"preregister [{config.city}]: {result.n_flagged} flagged segment(s) frozen")
    print(f"  artifact: {result.artifact_path}")
    print(f"  manifest: {result.manifest_path}")
    print(f"  sha256:   {result.artifact_sha256}")
    print(f"  registered_at: {result.registered_at}")
    print(
        "  NOTE: this registration is evidence of predictive validity only once "
        f"{signoff_path} records a statistician sign-off — see docs/PREREGISTRATION.md."
    )
    return 0


def _cmd_score_preregistration(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    registration_path = Path(args.registration)
    manifest_path = (
        Path(args.manifest) if args.manifest else _default_manifest_path(registration_path)
    )
    registration = load_registration(registration_path)
    held_out_bundle = build_analysis(config)
    result = score_registration(registration, held_out_bundle)
    out_dir = Path(args.out) if args.out else DEFAULT_REGISTRATION_DIR
    scored_path = write_score_result(result, manifest_path, config.city, out_dir)
    print(f"score-preregistration: scored against held-out city={config.city}")
    print(
        f"  hit_rate: {result.hit_rate:.3f} "
        f"[{result.hit_rate_ci_low:.3f}, {result.hit_rate_ci_high:.3f}] "
        f"({result.hit_count}/{result.n_evaluable})"
    )
    rho = "n/a" if result.rank_correlation is None else f"{result.rank_correlation:.3f}"
    print(f"  rank_correlation: {rho}")
    if result.unevaluable_segments:
        print(f"  unevaluable: {len(result.unevaluable_segments)} flagged segment(s)")
    print(f"  scored artifact: {scored_path}")
    return 0


def _default_manifest_path(registration_path: Path) -> Path:
    """Registration ``<slug>-<date>.json`` -> its sidecar ``<slug>-<date>.manifest.json``."""
    return registration_path.with_name(registration_path.stem + ".manifest.json")


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


def _cmd_contributor(args: argparse.Namespace) -> int:
    """Contributor data-rights: export / delete "my reports", or purge by retention.

    Authorization is token possession ONLY — there is no account or identity check.
    """
    config = load_config(args.config)
    action = args.action
    if action == "export":
        bundle = export_reports(config, args.token)
        payload = json.dumps(bundle.to_dict(), ensure_ascii=False, indent=2) + "\n"
        if args.out:
            out = Path(args.out)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(payload, encoding="utf-8")
            print(f"contributor: exported {bundle.count} report(s) for this token to {out}")
        else:
            print(payload, end="")
        return 0
    if action == "delete":
        d = delete_reports(config, args.token)
        print(
            f"contributor: deleted {d.total_removed} report(s) "
            f"(raw={d.raw_removed} pending={d.pending_removed} approved={d.approved_removed}); "
            f"wrote {d.tombstones_added} tombstone(s)."
        )
        print(
            "  note: published artifacts legitimately change after deletion; "
            "re-run `make reproduce` (or `nearmiss run`) to rebuild from the surviving raw records."
        )
        return 0
    if action == "purge-expired":
        purge = purge_expired(config)
        if purge.retention_days <= 0:
            print("contributor: retention disabled (retention_days <= 0); nothing purged.")
            return 0
        print(
            f"contributor: purged {purge.raw_removed} raw record(s) older than "
            f"{purge.retention_days} day(s) (cutoff {purge.cutoff}); "
            f"wrote {purge.tombstones_added} tombstone(s)."
        )
        return 0
    raise NearmissError(f"unknown contributor action {action!r}")  # pragma: no cover


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


def _cmd_coverage(args: argparse.Namespace) -> int:
    """Print the machine-readable evidence tier and source/capability gaps."""
    config = load_config(args.config)
    registry_path = Path(args.registry) if args.registry else config.source_registry_path
    if registry_path is None:
        raise NearmissError("coverage requires --registry or source_registry in the city config")
    registry = load_source_registry(registry_path)
    as_of = None
    if args.as_of:
        try:
            as_of = dt.date.fromisoformat(args.as_of)
        except ValueError as exc:
            raise NearmissError("--as-of must be an ISO-8601 date (YYYY-MM-DD)") from exc
    verified_outcomes = None
    if args.fars_root is not None:
        from .verified_outcomes import VerificationError, verify_active_fars

        try:
            verified_outcomes = verify_active_fars(Path(args.fars_root).expanduser())
        except (OSError, RuntimeError, VerificationError):
            raise NearmissError("active FARS verification failed") from None
    assessment = assess_coverage(
        config,
        registry,
        as_of=as_of,
        verified_outcomes=verified_outcomes,
    )
    print(json.dumps(assessment.as_dict(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def _positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a positive integer") from exc
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def _fars_year(value: str) -> int:
    if len(value) != 4 or not value.isascii() or not value.isdecimal():
        raise argparse.ArgumentTypeError("must be a four-digit year")
    year = int(value)
    if not 1975 <= year <= dt.datetime.now(tz=dt.UTC).year:
        raise argparse.ArgumentTypeError("must be a FARS year from 1975 through the current year")
    return year


def _fars_joined_year(value: str) -> int:
    year = _fars_year(value)
    if year != 2024:
        raise argparse.ArgumentTypeError("joined FARS person mapping currently supports 2024 only")
    return year


def _invalid_fraction(value: str) -> float:
    try:
        fraction = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a number from 0 through 1") from exc
    if not math.isfinite(fraction) or not 0 <= fraction <= 1:
        raise argparse.ArgumentTypeError("must be a number from 0 through 1")
    return fraction


def _release_status(value: str) -> str:
    status = value.strip()
    if (
        not status
        or len(status) > 64
        or any(ord(character) < 32 or ord(character) == 127 for character in status)
    ):
        raise argparse.ArgumentTypeError("must be a nonempty status of at most 64 characters")
    return status


def _fars_distribution_url(value: str) -> str:
    from .adapters.fars import validate_fars_distribution_url

    try:
        return validate_fars_distribution_url(value)
    except (TypeError, ValueError) as exc:
        raise argparse.ArgumentTypeError(
            "must be an exact static.nhtsa.gov FARS HTTPS distribution URL"
        ) from exc


def _fars_joined_distribution_url(value: str) -> str:
    url = _fars_distribution_url(value)
    if not url.casefold().endswith(".zip"):
        raise argparse.ArgumentTypeError("joined FARS distribution must be an official ZIP URL")
    return url


def _reject_json_constant(value: str) -> object:
    raise ValueError(f"non-standard JSON constant {value!r} is forbidden")


def _unique_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key {key!r} is forbidden")
        result[key] = value
    return result


def _decode_outcome_artifact(payload: bytes) -> dict[str, object]:
    decoded = json.loads(
        payload,
        parse_constant=_reject_json_constant,
        object_pairs_hook=_unique_json_object,
    )
    if not isinstance(decoded, dict):
        raise ValueError("normalized FARS artifact must be an object")
    return decoded


def _accepted_count(artifact: dict[str, object]) -> int:
    provenance = artifact.get("provenance")
    if not isinstance(provenance, dict):  # validated artifacts always have this shape
        raise ValueError("normalized FARS artifact has invalid provenance")
    accepted = provenance.get("records_accepted")
    if not isinstance(accepted, int) or isinstance(accepted, bool):
        raise ValueError("normalized FARS artifact has invalid accepted-record accounting")
    return accepted


def _expected_artifact_year(artifact: dict[str, object]) -> int:
    normalization = artifact.get("normalization")
    if not isinstance(normalization, dict):  # validated artifacts always have this shape
        raise ValueError("normalized FARS artifact has invalid normalization")
    year = normalization.get("expected_year")
    if not isinstance(year, int) or isinstance(year, bool):
        raise ValueError("normalized FARS artifact has invalid expected year")
    return year


def _validate_fars_normalized_candidate(
    candidate: bytes,
    previous: bytes | None,
    *,
    allow_record_regression: bool,
    allow_year_regression: bool,
) -> None:
    from .outcome_artifacts import validate_outcome_artifact

    decoded = _decode_outcome_artifact(candidate)
    validate_outcome_artifact(decoded, expected_source_id="fars")
    if previous is None:
        return
    prior = _decode_outcome_artifact(previous)
    validate_outcome_artifact(prior, expected_source_id="fars")
    if not allow_year_regression and _expected_artifact_year(decoded) < _expected_artifact_year(
        prior
    ):
        raise ValueError(
            "FARS dataset year regressed; use --allow-year-regression only after operator review"
        )
    if not allow_record_regression and _accepted_count(decoded) < _accepted_count(prior):
        raise ValueError(
            "FARS accepted-record count regressed; use --allow-record-regression "
            "only after operator review"
        )


def _joined_section(artifact: dict[str, object], key: str) -> dict[str, object]:
    section = artifact.get(key)
    if not isinstance(section, dict):
        raise ValueError(f"normalized joined FARS artifact has invalid {key}")
    return section


def _joined_count(artifact: dict[str, object], section: str, key: str) -> int:
    value = _joined_section(artifact, section).get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError("normalized joined FARS artifact has invalid record accounting")
    return value


def _joined_mode_totals(artifact: dict[str, object]) -> tuple[int, ...]:
    from .adapters.fars_joined import MODE_ORDER

    records = artifact.get("records")
    if not isinstance(records, list):
        raise ValueError("normalized joined FARS artifact has invalid records")
    involved = dict.fromkeys(MODE_ORDER, 0)
    fatal = dict.fromkeys(MODE_ORDER, 0)
    for record in records:
        if not isinstance(record, dict):
            raise ValueError("normalized joined FARS artifact has invalid records")
        summary = record.get("mode_summary")
        if not isinstance(summary, dict):
            raise ValueError("normalized joined FARS artifact has invalid mode summary")
        for field, totals in (
            ("involved_person_count_by_mode", involved),
            ("fatality_count_by_mode", fatal),
        ):
            counts = summary.get(field)
            if not isinstance(counts, dict):
                raise ValueError("normalized joined FARS artifact has invalid mode accounting")
            for mode in MODE_ORDER:
                value = counts.get(mode)
                if not isinstance(value, int) or isinstance(value, bool):
                    raise ValueError("normalized joined FARS artifact has invalid mode accounting")
                totals[mode] += value
    return tuple(involved[mode] for mode in MODE_ORDER) + tuple(fatal[mode] for mode in MODE_ORDER)


def _validate_fars_joined_normalized_candidate(
    candidate: bytes,
    previous: bytes | None,
    *,
    allow_record_regression: bool,
    allow_mode_regression: bool,
    allow_release_regression: bool,
) -> None:
    from .joined_outcome_artifacts import validate_joined_outcome_artifact

    decoded = _decode_outcome_artifact(candidate)
    validate_joined_outcome_artifact(decoded)
    policy = _joined_section(decoded, "crash_normalization")
    if policy.get("allow_record_regression") is not allow_record_regression:
        raise ValueError("joined FARS artifact override policy does not match the CLI")
    if policy.get("allow_year_regression") is not False:
        raise ValueError("joined FARS artifact must not authorize year regression")
    join_policy = _joined_section(decoded, "join_policy")
    if (
        join_policy.get("allow_mode_regression") is not allow_mode_regression
        or join_policy.get("allow_release_regression") is not allow_release_regression
    ):
        raise ValueError("joined FARS artifact override policy does not match the CLI")
    if previous is None:
        return
    prior = _decode_outcome_artifact(previous)
    validate_joined_outcome_artifact(prior)
    candidate_counts = (
        _joined_count(decoded, "crash_provenance", "records_read"),
        _joined_count(decoded, "crash_provenance", "records_accepted"),
        _joined_count(decoded, "person_join", "records_read"),
        _joined_count(decoded, "person_join", "records_accepted"),
        _joined_count(decoded, "person_join", "cases_joined"),
    )
    prior_counts = (
        _joined_count(prior, "crash_provenance", "records_read"),
        _joined_count(prior, "crash_provenance", "records_accepted"),
        _joined_count(prior, "person_join", "records_read"),
        _joined_count(prior, "person_join", "records_accepted"),
        _joined_count(prior, "person_join", "cases_joined"),
    )
    candidate_exclusions = (
        _joined_count(decoded, "person_join", "records_excluded_with_rejected_crash"),
        _joined_count(decoded, "person_join", "cases_excluded_with_rejected_crash"),
    )
    prior_exclusions = (
        _joined_count(prior, "person_join", "records_excluded_with_rejected_crash"),
        _joined_count(prior, "person_join", "cases_excluded_with_rejected_crash"),
    )
    record_regressed = any(
        candidate_value < prior_value
        for candidate_value, prior_value in zip(candidate_counts, prior_counts, strict=True)
    ) or any(
        candidate_value > prior_value
        for candidate_value, prior_value in zip(candidate_exclusions, prior_exclusions, strict=True)
    )
    if not allow_record_regression and record_regressed:
        raise ValueError(
            "joined FARS accepted-record accounting regressed; use "
            "--allow-record-regression only after operator review"
        )
    prior_release = _joined_section(prior, "crash_provenance").get("release_status")
    candidate_release = _joined_section(decoded, "crash_provenance").get("release_status")
    if (
        not allow_release_regression
        and prior_release == "final"
        and candidate_release == "preliminary"
    ):
        raise ValueError(
            "joined FARS release status regressed; use --allow-release-regression "
            "only after operator review"
        )
    if not allow_mode_regression and any(
        candidate_value < prior_value
        for candidate_value, prior_value in zip(
            _joined_mode_totals(decoded), _joined_mode_totals(prior), strict=True
        )
    ):
        raise ValueError(
            "joined FARS mode accounting regressed; use --allow-mode-regression "
            "only after operator review"
        )


def _cmd_ingest_fars(args: argparse.Namespace) -> int:
    """Preserve a local FARS export and activate its validated outcome artifact."""
    from .adapters import fars
    from .ingestion import IngestionError, run_ingestion
    from .outcome_artifacts import (
        build_outcome_artifact,
        canonical_outcome_artifact_bytes,
    )

    export_path = Path(args.export).expanduser()
    root = Path(args.root).expanduser()
    artifact: dict[str, object] | None = None

    def fetch() -> bytes:
        return fars.load_export_bytes(export_path, limit=args.max_raw_bytes)

    def normalize(raw: bytes) -> bytes:
        nonlocal artifact
        batch = fars.read_export_bytes(raw)
        outcomes, provenance = fars.FarsAdapter().parse(
            batch,
            release_status=args.release_status,
        )
        artifact = build_outcome_artifact(
            outcomes,
            provenance,
            expected_year=args.year,
            distribution_url=args.distribution_url,
            max_invalid_fraction=args.max_invalid_fraction,
            allow_record_regression=args.allow_record_regression,
            allow_year_regression=args.allow_year_regression,
        )
        return canonical_outcome_artifact_bytes(artifact)

    def validate(candidate: bytes, previous: bytes | None) -> None:
        _validate_fars_normalized_candidate(
            candidate,
            previous,
            allow_record_regression=args.allow_record_regression,
            allow_year_regression=args.allow_year_regression,
        )

    try:
        result = run_ingestion(
            root=root,
            source_id="fars",
            fetch=fetch,
            normalize=normalize,
            validate_normalized=validate,
            max_raw_bytes=args.max_raw_bytes,
            max_normalized_bytes=args.max_normalized_bytes,
        )
    except (IngestionError, OSError):
        raise NearmissError(
            "FARS ingestion failed; inspect the private receipt store for the redacted failure"
        ) from None

    if artifact is None:  # pragma: no cover - run_ingestion cannot succeed without normalize
        raise NearmissError("FARS ingestion completed without a normalized artifact")
    provenance = artifact.get("provenance")
    if not isinstance(provenance, dict):  # pragma: no cover - validated above
        raise NearmissError("FARS ingestion produced an invalid normalized artifact")
    reasons = provenance.get("rejection_reasons")
    if not isinstance(reasons, dict):  # pragma: no cover - validated above
        raise NearmissError("FARS ingestion produced invalid rejection accounting")
    records_read = provenance.get("records_read")
    records_accepted = provenance.get("records_accepted")
    if not isinstance(records_read, int) or not isinstance(records_accepted, int):
        raise NearmissError("FARS ingestion produced invalid record accounting")
    output = {
        "source_id": result.source_id,
        "raw_sha256": result.raw_sha256,
        "normalized_sha256": result.normalized_sha256,
        "artifact_path": str(result.normalized_path.relative_to(root)),
        "current_path": str(result.current_path.relative_to(root)),
        "receipt_path": str(result.receipt_path.relative_to(root)),
        "counts": {
            "records_read": records_read,
            "records_accepted": records_accepted,
            "records_rejected": records_read - records_accepted,
            "rejection_reasons": reasons,
        },
        "years": provenance.get("dataset_years"),
        "release_status": provenance.get("release_status"),
    }
    print(json.dumps(output, ensure_ascii=False, sort_keys=True))
    return 0


def _cmd_ingest_fars_joined(args: argparse.Namespace) -> int:
    """Activate a private deterministic 2024 FARS accident/person join."""
    from .adapters import fars
    from .adapters.fars import validate_fars_distribution_url
    from .adapters.fars_joined import collect_joined, read_joined_export_bytes
    from .ingestion import IngestionError, run_ingestion
    from .joined_outcome_artifacts import (
        JOINED_ARTIFACT_SCHEMA_VERSION,
        build_joined_outcome_artifact,
        canonical_joined_outcome_artifact_bytes,
    )

    try:
        validate_fars_distribution_url(args.distribution_url, expected_year=args.year)
    except (TypeError, ValueError):
        raise NearmissError("joined FARS preflight validation failed") from None
    root = Path(args.root).expanduser()
    try:
        resolved_root = root.resolve(strict=False)
        repository_root = Path(__file__).resolve().parents[2]
        resolved_root.relative_to(repository_root)
    except ValueError:
        pass
    except OSError:
        raise NearmissError("joined FARS preflight validation failed") from None
    else:
        raise NearmissError("joined FARS private root must remain outside the repository")
    export_path = Path(args.export).expanduser()
    artifact: dict[str, object] | None = None

    def fetch() -> bytes:
        return fars.load_export_bytes(export_path, limit=args.max_raw_bytes)

    def normalize(raw: bytes) -> bytes:
        nonlocal artifact
        outcomes, summaries, crash_provenance, person_provenance = collect_joined(
            read_joined_export_bytes(raw),
            release_status=args.release_status,
        )
        artifact = build_joined_outcome_artifact(
            outcomes,
            summaries,
            person_provenance,
            crash_provenance,
            distribution_url=args.distribution_url,
            max_invalid_fraction=args.max_invalid_fraction,
            allow_record_regression=args.allow_record_regression,
            allow_mode_regression=args.allow_mode_regression,
            allow_release_regression=args.allow_release_regression,
            schema_version=JOINED_ARTIFACT_SCHEMA_VERSION,
        )
        return canonical_joined_outcome_artifact_bytes(artifact)

    def validate(candidate: bytes, previous: bytes | None) -> None:
        _validate_fars_joined_normalized_candidate(
            candidate,
            previous,
            allow_record_regression=args.allow_record_regression,
            allow_mode_regression=args.allow_mode_regression,
            allow_release_regression=args.allow_release_regression,
        )

    try:
        result = run_ingestion(
            root=root,
            source_id="fars-joined",
            fetch=fetch,
            normalize=normalize,
            validate_normalized=validate,
            max_raw_bytes=args.max_raw_bytes,
            max_normalized_bytes=args.max_normalized_bytes,
        )
    except (IngestionError, OSError):
        raise NearmissError(
            "joined FARS ingestion failed; inspect the private receipt store "
            "for the redacted failure"
        ) from None

    if artifact is None:  # pragma: no cover - normalization is required for success
        raise NearmissError("joined FARS ingestion completed without a normalized artifact")
    crash = _joined_section(artifact, "crash_provenance")
    person = _joined_section(artifact, "person_join")
    output = {
        "source_id": result.source_id,
        "raw_sha256": result.raw_sha256,
        "normalized_sha256": result.normalized_sha256,
        "artifact_path": str(result.normalized_path.relative_to(root)),
        "current_path": str(result.current_path.relative_to(root)),
        "receipt_path": str(result.receipt_path.relative_to(root)),
        "crash_counts": {
            "records_read": crash.get("records_read"),
            "records_accepted": crash.get("records_accepted"),
            "rejection_reasons": crash.get("rejection_reasons"),
        },
        "person_counts": {
            "records_read": person.get("records_read"),
            "records_accepted": person.get("records_accepted"),
            "cases_joined": person.get("cases_joined"),
            "records_excluded_with_rejected_crash": person.get(
                "records_excluded_with_rejected_crash"
            ),
            "cases_excluded_with_rejected_crash": person.get("cases_excluded_with_rejected_crash"),
            "rejection_reasons": person.get("rejection_reasons"),
        },
        "year": person.get("dataset_year"),
        "release_status": crash.get("release_status"),
        "allow_record_regression": args.allow_record_regression,
        "allow_mode_regression": args.allow_mode_regression,
        "allow_release_regression": args.allow_release_regression,
    }
    print(json.dumps(output, ensure_ascii=False, sort_keys=True))
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

    p_prereg = sub.add_parser(
        "preregister",
        help="EXP-16: freeze currently-flagged corridors to a hashed, timestamped artifact",
    )
    add_config(p_prereg)
    p_prereg.add_argument(
        "--out", help="output directory (default: data/published/preregistration)"
    )
    p_prereg.add_argument(
        "--signoff",
        help="path to the scoring-rule sign-off record "
        "(default: docs/preregistration/scoring-rule-signoff.json)",
    )
    p_prereg.set_defaults(func=_cmd_preregister)

    p_score = sub.add_parser(
        "score-preregistration",
        help="EXP-16: score a frozen registration against this config's (held-out) data",
    )
    add_config(p_score)
    p_score.add_argument(
        "--registration", required=True, help="path to a registration artifact JSON"
    )
    p_score.add_argument(
        "--manifest", help="path to the registration's manifest (default: sibling *.manifest.json)"
    )
    p_score.add_argument("--out", help="output directory (default: data/published/preregistration)")
    p_score.set_defaults(func=_cmd_score_preregistration)

    p_con = sub.add_parser(
        "contributor",
        help="contributor data-rights: export/delete my reports, purge by retention",
        description=(
            "Token-based contributor data-rights tooling. AUTH MODEL: token "
            "possession is the ONLY authorization -- there is no account, password, "
            "or identity check, so anyone holding a reporter_token can export or "
            "delete that contributor's reports. Deletion removes the reports from "
            "the private raw store, the moderation queue, and the approved store, and "
            "writes tombstones (keyed by SHA-256 of the report id) so a re-import "
            "cannot resurrect them. Because deletion changes the raw inputs, the "
            "published artifacts legitimately change: `make reproduce` rebuilds from "
            "the surviving raw records and its committed outputs are EXPECTED to move "
            "after a deletion (that is correct behaviour, not drift)."
        ),
    )
    add_config(p_con)
    con_sub = p_con.add_subparsers(dest="action", required=True)
    c_export = con_sub.add_parser(
        "export", help="export every stored report for a reporter_token (token = auth)"
    )
    c_export.add_argument("token", help="the contributor's pseudonymous reporter_token")
    c_export.add_argument("--out", help="write the JSON bundle to a file instead of stdout")
    c_delete = con_sub.add_parser(
        "delete",
        help="delete every stored report for a reporter_token and tombstone their ids",
        description=(
            "Delete all reports carrying this reporter_token from the raw store, the "
            "moderation queue, and the approved store, and tombstone their ids so a "
            "re-import cannot resurrect them. Token possession is the only auth. "
            "Published artifacts legitimately change afterward -- re-run `make "
            "reproduce` to rebuild from the surviving raw records."
        ),
    )
    c_delete.add_argument("token", help="the contributor's pseudonymous reporter_token")
    con_sub.add_parser(
        "purge-expired",
        help="tombstone-delete raw records older than config's retention_days window",
    )
    p_con.set_defaults(func=_cmd_contributor)

    p_coverage = sub.add_parser(
        "coverage",
        help="assess a city's evidence tier and source/capability gaps",
    )
    add_config(p_coverage)
    p_coverage.add_argument(
        "--registry",
        help="source-registry TOML (defaults to source_registry in the city config)",
    )
    p_coverage.add_argument(
        "--as-of",
        help="freshness reference date, YYYY-MM-DD (default: analysis window/report/source date)",
    )
    p_coverage.add_argument(
        "--fars-root",
        help="private ingestion root whose active FARS chain must verify or fail closed",
    )
    p_coverage.set_defaults(func=_cmd_coverage)

    p_fars = sub.add_parser(
        "ingest-fars",
        help="preserve a local FARS export and activate a validated private artifact",
    )
    p_fars.add_argument("export", help="local NHTSA accident.csv or CSV ZIP export")
    p_fars.add_argument("--root", required=True, help="private ingestion artifact root")
    p_fars.add_argument(
        "--year",
        required=True,
        type=_fars_year,
        help="four-digit dataset year expected in every source row",
    )
    p_fars.add_argument(
        "--release-status",
        required=True,
        type=_release_status,
        help="operator-supplied NHTSA release status, such as preliminary or final",
    )
    p_fars.add_argument(
        "--distribution-url",
        required=True,
        type=_fars_distribution_url,
        help="exact static.nhtsa.gov FARS HTTPS distribution URL represented by EXPORT",
    )
    p_fars.add_argument(
        "--max-invalid-fraction",
        type=_invalid_fraction,
        default=0.05,
        help="maximum rejected-row fraction permitted before activation (default: 0.05)",
    )
    p_fars.add_argument(
        "--max-raw-bytes",
        type=_positive_int,
        help="optional maximum raw export size in bytes",
    )
    p_fars.add_argument(
        "--max-normalized-bytes",
        type=_positive_int,
        help="optional post-materialization cap before normalized-artifact activation",
    )
    p_fars.add_argument(
        "--allow-record-regression",
        action="store_true",
        help="activate fewer accepted records than current only after operator review",
    )
    p_fars.add_argument(
        "--allow-year-regression",
        action="store_true",
        help="activate an older dataset year than current only after operator review",
    )
    p_fars.set_defaults(func=_cmd_ingest_fars)

    p_fars_joined = sub.add_parser(
        "ingest-fars-joined",
        help="activate a private 2024 FARS accident/person joined artifact",
    )
    p_fars_joined.add_argument(
        "export", help="local official NHTSA ZIP containing accident.csv and person.csv"
    )
    p_fars_joined.add_argument("--root", required=True, help="private ingestion artifact root")
    p_fars_joined.add_argument(
        "--year",
        required=True,
        type=_fars_joined_year,
        help="dataset year; joined person mapping currently supports 2024 only",
    )
    p_fars_joined.add_argument(
        "--release-status",
        required=True,
        type=_release_status,
        choices=("preliminary", "final"),
        help="operator-supplied NHTSA release status, such as preliminary or final",
    )
    p_fars_joined.add_argument(
        "--distribution-url",
        required=True,
        type=_fars_joined_distribution_url,
        help="exact static.nhtsa.gov FARS ZIP distribution URL represented by EXPORT",
    )
    p_fars_joined.add_argument(
        "--max-invalid-fraction",
        type=_invalid_fraction,
        default=0.05,
        help="maximum rejected crash-row fraction permitted before activation (default: 0.05)",
    )
    p_fars_joined.add_argument(
        "--max-raw-bytes",
        type=_positive_int,
        default=64 * 1024 * 1024,
        help="bounded raw ZIP read cap in bytes (default: 67108864)",
    )
    p_fars_joined.add_argument(
        "--max-normalized-bytes",
        type=_positive_int,
        default=64 * 1024 * 1024,
        help="post-materialization activation cap in bytes (default: 67108864)",
    )
    p_fars_joined.add_argument(
        "--allow-record-regression",
        action="store_true",
        help="activate lower crash/person/case counts only after operator review",
    )
    p_fars_joined.add_argument(
        "--allow-mode-regression",
        action="store_true",
        help="activate lower aggregate per-mode counts only after operator review",
    )
    p_fars_joined.add_argument(
        "--allow-release-regression",
        action="store_true",
        help="activate preliminary data over final data only after operator review",
    )
    p_fars_joined.set_defaults(func=_cmd_ingest_fars_joined)

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
