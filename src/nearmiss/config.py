"""Configuration as data, not code.

Cities, input paths, output paths, and every threshold (snap distance, dedupe
window, small-sample cutoff, the minimum-occupancy publication threshold, the
Getis-Ord distance band, KDE bandwidth, the rate denominator, the confidence
level, the FDR level) live in one checked-in config file. Pointing nearmiss at a
new city is a new config plus an exposure layer — no code change
(administrability / adaptability / configurability).
"""

from __future__ import annotations

import datetime
import difflib
import json
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

from .errors import ConfigError

_MAX_PARSED_NESTING = 256

# Every key the loader understands. Anything else is a typo (e.g. "fdr_aplha")
# that would otherwise silently fall back to a default — so we reject it loudly.
_TOP_KEYS = frozenset(
    {
        "city",
        "streets",
        "reports",
        "exposure",
        "raw_dir",
        "out_dir",
        "submissions_dir",
        "ref_lat",
        "ref_lon",
        "gazetteer",
        "weather",
        "geocoder",
        "geocoder_user_agent",
        "exposure_unit",
        "dataset_note",
        "source_registry",
        "thresholds",
        # FIX-05: optional [window] table (ISO start/end, validated in _parse_window).
        "window",
        # EXP-05: optional [dp_segment_time] table (enabled/epsilon/sme_signoff_ref).
        "dp_segment_time",
        # RR-02: overdispersion adjustment flag may live top-level or in [thresholds].
        "overdispersion_adjust",
    }
)
_THRESHOLD_KEYS = frozenset(
    {
        "snap_max_m",
        "dedupe_window_s",
        "dedupe_distance_m",
        "small_n",
        "min_publish_n",
        "rate_per",
        "confidence_z",
        "fdr_alpha",
        "gi_band_m",
        "kde_bandwidth_m",
        "kde_grid",
        "retention_days",
        "gi_node_snap_m",
        "exposure_floor",
        "exposure_stale_days",
        "overdispersion_adjust",
    }
)


@dataclass(frozen=True)
class Config:
    city: str
    streets_path: Path
    reports_path: Path
    exposure_path: Path
    raw_dir: Path
    out_dir: Path
    submissions_dir: Path = Path("data/pending")  # PRIVATE moderation queue (gitignored)
    ref_lat: float | None = None
    ref_lon: float | None = None
    gazetteer_path: Path | None = None  # address -> coordinate table for the geocoder
    weather_path: Path | None = None  # optional open/supplied weather dataset (date -> conditions)
    geocoder: str | None = None  # "nominatim" to opt into the networked adapter
    geocoder_user_agent: str = "nearmiss/0.1 (+https://github.com/ChelseaKR/nearmiss)"
    exposure_unit: str = "exposure units"  # human-readable denominator unit for the brief
    # Thresholds (all tunable per city; documented in docs/METHODOLOGY.md).
    snap_max_m: float = 25.0
    dedupe_window_s: int = 600
    dedupe_distance_m: float = 15.0
    small_n: int = 5
    min_publish_n: int = 3  # k-anonymity: segments with 0 < count < this are withheld
    rate_per: float = 1000.0
    confidence_z: float = 1.96
    # RR-02: when true, widen every published rate interval by sqrt(dispersion) if the
    # report counts are overdispersed (quasi-Poisson). Off by default so enabling it is
    # a deliberate, versioned methodology change rather than a silent rewrite of every
    # published interval; the dispersion itself is always computed and reported.
    overdispersion_adjust: bool = False
    fdr_alpha: float = 0.05  # Benjamini-Hochberg false-discovery-rate level
    gi_band_m: float = 300.0
    # Two street-segment endpoints within this many metres are treated as the
    # same network intersection when building the Gi* adjacency graph (see
    # network.py). Independent of snap_max_m (which snaps a REPORT to its
    # nearest segment) — this is about recognizing that two segment endpoints
    # are the same real-world junction.
    gi_node_snap_m: float = 5.0
    kde_bandwidth_m: float = 150.0
    kde_grid: int = 24
    # METHODOLOGY §3.3: exposure at/below this is treated as "exposure unknown"
    # rather than producing a giant, meaningless rate as exposure -> 0. Default 0.0
    # preserves the original "any positive estimate is usable" behavior.
    exposure_floor: float = 0.0
    # METHODOLOGY §3.2: a rate whose exposure vintage is more than this many days
    # from the report reference date gets the published "exposure_stale" flag
    # (temporal-alignment caveat). Pending FIX-05's first-class analysis window,
    # the reference date is the latest report date the pipeline actually retained.
    exposure_stale_days: float = 365.0
    # Contributor data-rights: retention window (days) for the PRIVATE raw store.
    # `nearmiss contributor purge-expired` tombstone-deletes raw records whose
    # event time is older than this window. 0 disables retention (keep forever).
    retention_days: int = 0
    # Optional provenance note carried into the brief and the published metadata
    # (e.g. to mark a dataset as synthetic demonstration data).
    dataset_note: str | None = None
    source_registry_path: Path | None = None
    # EXP-05 prototype (see stats/dp_temporal.py + docs/privacy/exp-05-dp-segment-time-bands.md):
    # an epsilon-DP alternative to k-anonymity suppression for segment x part-of-day counts.
    # Disabled by default. Even when enabled, dp_segment_time_sme_signoff_ref MUST be set to a
    # real reviewer reference or the mechanism refuses to run (hard SME sign-off gate).
    dp_segment_time_enabled: bool = False
    dp_segment_time_epsilon: float = 1.0
    dp_segment_time_sme_signoff_ref: str | None = None
    # First-class analysis window (METHODOLOGY §1: "a rate with no window attached is
    # not a publishable number"). ISO-8601 dates (inclusive). Records whose
    # occurred_at date falls outside are filtered before analysis; the window is
    # stamped into every published artifact and brief. Optional, but a real config
    # should set one so published rates are traceable to a stated period.
    window_start: str | None = None
    window_end: str | None = None
    raw: dict[str, object] = field(default_factory=dict)


def _resolve(base: Path, value: str) -> Path:
    p = Path(value)
    return p if p.is_absolute() else (base / p).resolve()


def _coerce_flag(raw_val: object) -> bool:
    """Coerce a config value to a boolean (TOML bool, common truthy strings, else bool())."""
    if isinstance(raw_val, bool):
        return raw_val
    if isinstance(raw_val, str):
        return raw_val.strip().lower() in {"1", "true", "yes", "on"}
    return bool(raw_val)


def _require_unicode_scalars(value: object, cfg_path: Path) -> None:
    pending: list[tuple[object, int]] = [(value, 0)]
    while pending:
        current, depth = pending.pop()
        if depth > _MAX_PARSED_NESTING:
            raise ConfigError(f"invalid config {cfg_path}: nesting exceeds safety limit")
        if isinstance(current, str):
            try:
                current.encode("utf-8")
            except UnicodeEncodeError:
                raise ConfigError(
                    f"invalid config {cfg_path}: invalid Unicode scalar value"
                ) from None
        elif isinstance(current, dict):
            pending.extend((child, depth + 1) for pair in current.items() for child in pair)
        elif isinstance(current, list):
            pending.extend((child, depth + 1) for child in current)


def _decode_data(cfg_path: Path, payload: bytes) -> dict[str, object]:
    """Parse one exact config payload, with a clear load error."""
    try:
        text = payload.decode("utf-8")
        if cfg_path.suffix == ".json":
            data: object = json.loads(text)
        else:
            data = tomllib.loads(text)
    except (
        UnicodeDecodeError,
        tomllib.TOMLDecodeError,
        json.JSONDecodeError,
        RecursionError,
    ) as exc:
        raise ConfigError(f"invalid config {cfg_path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"invalid config {cfg_path}: expected a top-level object")
    _require_unicode_scalars(data, cfg_path)
    return cast(dict[str, object], data)


def _load_data(cfg_path: Path) -> dict[str, object]:
    """Read and parse the TOML (or JSON) config file, with a clear load error."""
    return _decode_data(cfg_path, cfg_path.read_bytes())


def _reject_unknown(cfg_path: Path, keys: set[str], allowed: frozenset[str], where: str) -> None:
    """FIX-08: fail loudly on unknown keys, with a did-you-mean hint."""
    unknown = keys - allowed
    if not unknown:
        return
    parts = []
    for key in sorted(unknown):
        close = difflib.get_close_matches(key, allowed, n=1)
        hint = f" (did you mean {close[0]!r}?)" if close else ""
        parts.append(f"unknown {where} key {key!r}{hint}")
    raise ConfigError(f"config {cfg_path}: " + "; ".join(parts))


def _check_range(cfg_path: Path, ok: bool, key: str, value: object, requirement: str) -> None:
    """FIX-08: fail loudly on an out-of-range threshold."""
    if not ok:
        raise ConfigError(
            f"config {cfg_path}: threshold {key!r} = {value!r} out of range ({requirement})"
        )


def _parse_window(data: dict[str, object], cfg_path: Path) -> tuple[str | None, str | None]:
    """Parse and validate the optional ``[window]`` table (ISO dates, ordered).

    Validate parseability up front so a typo fails at load time, not silently
    mid-pipeline, and reject a reversed range.
    """
    win = data.get("window", {})
    win = win if isinstance(win, dict) else {}

    def win_date(key: str) -> str | None:
        if key not in win:
            return None
        value = str(win[key])
        try:
            datetime.date.fromisoformat(value)
        except ValueError as exc:
            raise ConfigError(
                f"config {cfg_path}: [window] {key!r} must be an ISO-8601 date "
                f"(YYYY-MM-DD), got {value!r}"
            ) from exc
        return value

    window_start = win_date("start")
    window_end = win_date("end")
    if window_start is not None and window_end is not None and window_start > window_end:
        raise ConfigError(
            f"config {cfg_path}: [window] start {window_start!r} is after end {window_end!r}"
        )
    return window_start, window_end


def _config_from_data(cfg_path: Path, data: dict[str, object]) -> Config:
    base = cfg_path.parent

    def need(key: str) -> str:
        if key not in data:
            raise ConfigError(f"config {cfg_path} missing required key: {key}")
        return str(data[key])

    th = data.get("thresholds", {})
    th = th if isinstance(th, dict) else {}

    _reject_unknown(cfg_path, set(data), _TOP_KEYS, "[top-level]")
    _reject_unknown(cfg_path, set(th), _THRESHOLD_KEYS, "[thresholds]")

    def num(value: object, key: str) -> float:
        try:
            return float(value)  # type: ignore[arg-type]
        except (TypeError, ValueError) as exc:
            raise ConfigError(f"config {cfg_path}: {key!r} must be numeric, got {value!r}") from exc

    def thr(key: str, default: float) -> float:
        return num(th[key], key) if key in th else default

    def flag(key: str, default: bool) -> bool:
        return _coerce_flag(th[key] if key in th else data.get(key, default))

    ref_lat = num(data["ref_lat"], "ref_lat") if "ref_lat" in data else None
    ref_lon = num(data["ref_lon"], "ref_lon") if "ref_lon" in data else None

    dp = data.get("dp_segment_time", {})
    dp = dp if isinstance(dp, dict) else {}
    dp_signoff = dp.get("sme_signoff_ref")

    # Optional [window] table: an ISO-8601 (YYYY-MM-DD) start/end bounding the
    # analysis period (validated in _parse_window).
    window_start, window_end = _parse_window(data, cfg_path)

    snap_max_m = thr("snap_max_m", 25.0)
    dedupe_window_s = int(thr("dedupe_window_s", 600))
    dedupe_distance_m = thr("dedupe_distance_m", 15.0)
    small_n = int(thr("small_n", 5))
    min_publish_n = int(thr("min_publish_n", 3))
    rate_per = thr("rate_per", 1000.0)
    confidence_z = thr("confidence_z", 1.96)
    fdr_alpha = thr("fdr_alpha", 0.05)
    gi_band_m = thr("gi_band_m", 300.0)
    kde_bandwidth_m = thr("kde_bandwidth_m", 150.0)
    kde_grid = int(thr("kde_grid", 24))
    retention_days = int(thr("retention_days", 0))
    gi_node_snap_m = thr("gi_node_snap_m", 5.0)
    exposure_floor = thr("exposure_floor", 0.0)
    exposure_stale_days = thr("exposure_stale_days", 365.0)

    _check_range(cfg_path, 0 < fdr_alpha < 1, "fdr_alpha", fdr_alpha, "0 < fdr_alpha < 1")
    _check_range(cfg_path, min_publish_n >= 2, "min_publish_n", min_publish_n, "min_publish_n >= 2")
    _check_range(cfg_path, small_n >= 1, "small_n", small_n, "small_n >= 1")
    _check_range(cfg_path, confidence_z > 0, "confidence_z", confidence_z, "confidence_z > 0")
    _check_range(cfg_path, kde_grid >= 2, "kde_grid", kde_grid, "kde_grid >= 2")
    _check_range(
        cfg_path, retention_days >= 0, "retention_days", retention_days, "retention_days >= 0"
    )
    _check_range(
        cfg_path, exposure_floor >= 0, "exposure_floor", exposure_floor, "exposure_floor >= 0"
    )
    _check_range(
        cfg_path, gi_node_snap_m >= 0, "gi_node_snap_m", gi_node_snap_m, "gi_node_snap_m >= 0"
    )
    _check_range(
        cfg_path,
        exposure_stale_days >= 0,
        "exposure_stale_days",
        exposure_stale_days,
        "exposure_stale_days >= 0",
    )
    _check_range(cfg_path, snap_max_m > 0, "snap_max_m", snap_max_m, "snap_max_m > 0")
    _check_range(
        cfg_path, dedupe_window_s >= 0, "dedupe_window_s", dedupe_window_s, "dedupe_window_s >= 0"
    )
    _check_range(
        cfg_path,
        dedupe_distance_m >= 0,
        "dedupe_distance_m",
        dedupe_distance_m,
        "dedupe_distance_m >= 0",
    )
    _check_range(cfg_path, rate_per > 0, "rate_per", rate_per, "rate_per > 0")
    _check_range(cfg_path, gi_band_m > 0, "gi_band_m", gi_band_m, "gi_band_m > 0")
    _check_range(
        cfg_path, kde_bandwidth_m > 0, "kde_bandwidth_m", kde_bandwidth_m, "kde_bandwidth_m > 0"
    )

    return Config(
        city=need("city"),
        streets_path=_resolve(base, need("streets")),
        reports_path=_resolve(base, need("reports")),
        exposure_path=_resolve(base, need("exposure")),
        raw_dir=_resolve(base, str(data.get("raw_dir", "data/raw"))),
        out_dir=_resolve(base, str(data.get("out_dir", "data/published"))),
        submissions_dir=_resolve(base, str(data.get("submissions_dir", "data/pending"))),
        ref_lat=ref_lat,
        ref_lon=ref_lon,
        gazetteer_path=(_resolve(base, str(data["gazetteer"])) if "gazetteer" in data else None),
        weather_path=(_resolve(base, str(data["weather"])) if "weather" in data else None),
        geocoder=(str(data["geocoder"]) if "geocoder" in data else None),
        geocoder_user_agent=str(
            data.get("geocoder_user_agent", "nearmiss/0.1 (+https://github.com/ChelseaKR/nearmiss)")
        ),
        exposure_unit=str(data.get("exposure_unit", "exposure units")),
        snap_max_m=snap_max_m,
        dedupe_window_s=dedupe_window_s,
        dedupe_distance_m=dedupe_distance_m,
        small_n=small_n,
        min_publish_n=min_publish_n,
        rate_per=rate_per,
        confidence_z=confidence_z,
        fdr_alpha=fdr_alpha,
        gi_band_m=gi_band_m,
        kde_bandwidth_m=kde_bandwidth_m,
        kde_grid=kde_grid,
        retention_days=retention_days,
        overdispersion_adjust=flag("overdispersion_adjust", False),
        gi_node_snap_m=gi_node_snap_m,
        exposure_floor=exposure_floor,
        exposure_stale_days=exposure_stale_days,
        dataset_note=(str(data["dataset_note"]) if "dataset_note" in data else None),
        source_registry_path=(
            _resolve(base, str(data["source_registry"])) if "source_registry" in data else None
        ),
        dp_segment_time_enabled=bool(dp.get("enabled", False)),
        dp_segment_time_epsilon=(
            num(dp["epsilon"], "dp_segment_time.epsilon") if "epsilon" in dp else 1.0
        ),
        dp_segment_time_sme_signoff_ref=(str(dp_signoff) if dp_signoff else None),
        window_start=window_start,
        window_end=window_end,
        raw=data,
    )


def load_config(path: str | Path) -> Config:
    """Load a TOML (or JSON) config. Paths resolve relative to the config file."""
    cfg_path = Path(path)
    if not cfg_path.is_file():
        raise ConfigError(f"config file not found: {cfg_path}")
    return _config_from_data(cfg_path, _load_data(cfg_path))


def load_config_bytes(path: str | Path, payload: bytes) -> Config:
    """Parse already-read config bytes while preserving path-relative resolution.

    Security-sensitive derivations use this entry point so the bytes they hash
    are exactly the bytes they parse; the function performs no filesystem read.
    """
    if not isinstance(payload, bytes):
        raise TypeError("config payload must be bytes")
    cfg_path = Path(path)
    return _config_from_data(cfg_path, _decode_data(cfg_path, payload))
