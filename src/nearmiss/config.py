"""Configuration as data, not code.

Cities, input paths, output paths, and every threshold (snap distance, dedupe
window, small-sample cutoff, the minimum-occupancy publication threshold, the
Getis-Ord distance band, KDE bandwidth, the rate denominator, the confidence
level, the FDR level) live in one checked-in config file. Pointing nearmiss at a
new city is a new config plus an exposure layer — no code change
(administrability / adaptability / configurability).
"""

from __future__ import annotations

import json
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from .errors import ConfigError


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
    kde_bandwidth_m: float = 150.0
    kde_grid: int = 24
    # Optional provenance note carried into the brief and the published metadata
    # (e.g. to mark a dataset as synthetic demonstration data).
    dataset_note: str | None = None
    raw: dict[str, object] = field(default_factory=dict)


def _resolve(base: Path, value: str) -> Path:
    p = Path(value)
    return p if p.is_absolute() else (base / p).resolve()


def load_config(path: str | Path) -> Config:
    """Load a TOML (or JSON) config. Paths resolve relative to the config file."""
    cfg_path = Path(path)
    if not cfg_path.is_file():
        raise ConfigError(f"config file not found: {cfg_path}")
    base = cfg_path.parent
    try:
        if cfg_path.suffix == ".json":
            data: dict[str, object] = json.loads(cfg_path.read_text(encoding="utf-8"))
        else:
            data = tomllib.loads(cfg_path.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, json.JSONDecodeError) as exc:
        raise ConfigError(f"invalid config {cfg_path}: {exc}") from exc

    def need(key: str) -> str:
        if key not in data:
            raise ConfigError(f"config {cfg_path} missing required key: {key}")
        return str(data[key])

    th = data.get("thresholds", {})
    th = th if isinstance(th, dict) else {}

    def num(value: object, key: str) -> float:
        try:
            return float(value)  # type: ignore[arg-type]
        except (TypeError, ValueError) as exc:
            raise ConfigError(f"config {cfg_path}: {key!r} must be numeric, got {value!r}") from exc

    def thr(key: str, default: float) -> float:
        return num(th[key], key) if key in th else default

    def flag(key: str, default: bool) -> bool:
        raw_val = th[key] if key in th else data.get(key, default)
        if isinstance(raw_val, bool):
            return raw_val
        if isinstance(raw_val, str):
            return raw_val.strip().lower() in {"1", "true", "yes", "on"}
        return bool(raw_val)

    ref_lat = num(data["ref_lat"], "ref_lat") if "ref_lat" in data else None
    ref_lon = num(data["ref_lon"], "ref_lon") if "ref_lon" in data else None

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
        snap_max_m=thr("snap_max_m", 25.0),
        dedupe_window_s=int(thr("dedupe_window_s", 600)),
        dedupe_distance_m=thr("dedupe_distance_m", 15.0),
        small_n=int(thr("small_n", 5)),
        min_publish_n=int(thr("min_publish_n", 3)),
        rate_per=thr("rate_per", 1000.0),
        confidence_z=thr("confidence_z", 1.96),
        overdispersion_adjust=flag("overdispersion_adjust", False),
        fdr_alpha=thr("fdr_alpha", 0.05),
        gi_band_m=thr("gi_band_m", 300.0),
        kde_bandwidth_m=thr("kde_bandwidth_m", 150.0),
        kde_grid=int(thr("kde_grid", 24)),
        dataset_note=(str(data["dataset_note"]) if "dataset_note" in data else None),
        raw=data,
    )
