"""Per-run provenance manifest + pipeline-stage telemetry.

A pure, standard-library-only module (matching this project's minimal-runtime
posture) that turns a run into a diffable provenance artifact. The manifest has
two top-level sections:

* ``provenance`` — DETERMINISTIC: the SHA256 of each input file
  (streets/reports/exposure), a canonical-JSON digest of the *effective* config
  (the knobs that shape output, never machine-specific absolute paths), the
  ``nearmiss`` package version, and the per-stage record counts the pipeline
  already produces (intake/dedupe accepted/removed, snapped/unsnapped,
  ``out_of_window``, an excluded fraction, …).
* ``timings`` — an UNHASHED sidecar: per-stage wall-time in milliseconds.

``manifest_digest`` is computed over the canonical JSON of the ``provenance``
section ONLY — never over ``timings`` or any timestamp — so two runs over the
same inputs yield an identical provenance section and digest, and ``make
reproduce`` stays byte-stable. Given only ``data/published/`` a third party can
recompute the input hashes and the config digest and verify exactly which
inputs and config produced a dataset.

Privacy (hard rule #4): the provenance section is counts-and-hashes only — no
per-report coordinate, timestamp, reporter token, note, mode, or severity. The
publisher runs it through ``publish.assert_metadata_clean`` before writing.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .config import Config

__all__ = [
    "MANIFEST_SCHEMA_VERSION",
    "build_manifest",
    "canonical_json",
    "effective_config",
    "sha256_file",
]

# Bump when the manifest layout changes in a way consumers must notice.
MANIFEST_SCHEMA_VERSION = "1.0.0"

# The config fields that actually shape the analysis output. Deliberately EXCLUDES
# absolute filesystem paths (streets/reports/exposure/out_dir/raw_dir/…), which are
# machine-specific and would make the config digest — and therefore the reproduce
# gate — vary across checkouts. Input identity is captured separately, by content
# hash, in the ``inputs`` block. It also EXCLUDES the projection reference point
# (``ref_lat``/``ref_lon``): those are literal coordinates, and echoing a
# coordinate into the manifest would risk tripping the counts-and-hashes-only
# privacy gate on a report that happens to sit on the reference point.
_EFFECTIVE_CONFIG_FIELDS: tuple[str, ...] = (
    "city",
    "exposure_unit",
    "geocoder",
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
    "dataset_note",
)


def canonical_json(obj: object) -> str:
    """Canonical, stable JSON: sorted keys, indented, trailing newline.

    Shared by :mod:`nearmiss.publish` (which imports it back) so every emitted
    artifact serializes identically byte-for-byte.
    """
    return json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def sha256_file(path: str | Path) -> str:
    """SHA256 hex digest of a file's bytes, read in chunks (never loads the body into JSON)."""
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def effective_config(config: Config) -> dict[str, object]:
    """The output-shaping config knobs only (no absolute paths). Deterministic."""
    return {field: getattr(config, field) for field in _EFFECTIVE_CONFIG_FIELDS}


def _config_digest(config: Config) -> str:
    return _sha256_text(canonical_json(effective_config(config)))


def _input_block(inputs: Mapping[str, str | Path]) -> dict[str, dict[str, object]]:
    """Map each logical input name to ``{filename, sha256}``.

    Only the basename is recorded (stable across checkouts); the SHA256 pins the
    exact bytes. Names are the fixed streets/reports/exposure roles.
    """
    block: dict[str, dict[str, object]] = {}
    for name in sorted(inputs):
        p = Path(inputs[name])
        block[name] = {"filename": p.name, "sha256": sha256_file(p)}
    return block


def _split_stage_summaries(
    stage_summaries: Iterable[Mapping[str, object]],
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """Split ``{stage, counts, ms}`` records into (provenance counts, timing ms).

    Counts land in the hashed provenance section; ``ms`` lands in the unhashed
    timings sidecar. A missing ``ms`` is tolerated (recorded as ``None``).
    """
    counts: list[dict[str, object]] = []
    timings: list[dict[str, object]] = []
    for record in stage_summaries:
        stage = str(record["stage"])
        raw_counts = record.get("counts", {})
        stage_counts = dict(raw_counts) if isinstance(raw_counts, Mapping) else {}
        counts.append({"stage": stage, "counts": stage_counts})
        timings.append({"stage": stage, "ms": record.get("ms")})
    return counts, timings


def build_manifest(
    config: Config,
    inputs: Mapping[str, str | Path],
    stage_summaries: Sequence[Mapping[str, object]],
    package_version: str,
) -> dict[str, object]:
    """Assemble the run manifest from a config, its input files, and stage summaries.

    ``inputs`` maps logical roles (``"streets"``, ``"reports"``, ``"exposure"``)
    to the file that fed the run. ``stage_summaries`` is the list the engine
    collects: one ``{"stage": str, "counts": {...}, "ms": float}`` per stage.

    Returns a manifest dict with ``provenance`` (deterministic), a
    ``manifest_digest`` over the canonical JSON of the provenance section only,
    and a ``timings`` sidecar. Byte-stable across runs over identical inputs.
    """
    stage_counts, stage_timings = _split_stage_summaries(stage_summaries)

    provenance: dict[str, object] = {
        "manifest_schema_version": MANIFEST_SCHEMA_VERSION,
        "nearmiss_version": package_version,
        "inputs": _input_block(inputs),
        "config_digest": _config_digest(config),
        "effective_config": effective_config(config),
        "stages": stage_counts,
    }

    digest = _sha256_text(canonical_json(provenance))

    return {
        "provenance": provenance,
        "manifest_digest": digest,
        "timings": {"stages": stage_timings},
    }
