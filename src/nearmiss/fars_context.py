# SPDX-License-Identifier: Apache-2.0
"""Pure, deterministic builder for private FARS co-location context.

Only privacy-eligible ``segment × part_of_day × involved_mode`` cells survive
this boundary. Record-level fields and the keys of suppressed positive cells
exist only transiently and cannot be serialized by this module's closed
artifact contract.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import re
from collections import Counter
from collections.abc import Iterable, Mapping
from itertools import islice
from pathlib import Path
from typing import NoReturn, cast

from .adapters.fars import FARS_MAPPING_VERSION
from .adapters.fars_joined import MODE_ORDER, PERSON_MODE_MAPPING_VERSION
from .config import Config, load_config_bytes
from .joined_outcome_artifacts import canonical_joined_outcome_artifact_bytes
from .loaders import load_streets_bytes
from .models import Segment
from .point_snap import SnapPoint, point_snap_method_descriptor, snap_points_to_segments
from .verified_outcomes import _VerifiedJoinedSnapshot

FARS_CONTEXT_SCHEMA_VERSION = "1.0.0"
FARS_CONTEXT_ALGORITHM_VERSION = "1.0.0"
FARS_CONTEXT_ARTIFACT_TYPE = "nearmiss.private.fars_context"
FARS_CONTEXT_MINIMUM_K = 5

PART_OF_DAY_ORDER = (
    "overnight",
    "am_peak",
    "midday",
    "pm_peak",
    "evening",
    "unknown_time",
)
UNKNOWN_MODE = "unknown_mode"
CONTEXT_MODE_ORDER = tuple(UNKNOWN_MODE if mode == "unknown" else mode for mode in MODE_ORDER)

LIMITATION_CODES = (
    "fatal_crash_colocation_only",
    "not_record_linkage",
    "not_outcome_validation",
    "not_causal_attribution",
    "not_nonfatal_risk",
    "not_location_ranking",
    "not_intervention_effect",
    "not_exposure_normalized_risk",
    "involved_mode_strata_non_additive",
    "snapping_and_exclusions_bias_coverage",
)

_CAVEAT = (
    "Fatal-crash co-location context only. It is not record linkage, not outcome validation, "
    "not causal evidence, not a measure of nonfatal risk, not a location ranking, not an "
    "intervention effect estimate, and not exposure-normalized risk. Involved-mode cells "
    "overlap and are non-additive; snapping and exclusions can bias coverage."
)
_TIME_BANDS = (
    {"key": "overnight", "start_hour_inclusive": 0, "end_hour_exclusive": 6},
    {"key": "am_peak", "start_hour_inclusive": 6, "end_hour_exclusive": 10},
    {"key": "midday", "start_hour_inclusive": 10, "end_hour_exclusive": 16},
    {"key": "pm_peak", "start_hour_inclusive": 16, "end_hour_exclusive": 20},
    {"key": "evening", "start_hour_inclusive": 20, "end_hour_exclusive": 24},
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_SEMVER_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
_ATTEMPT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_SOURCE_RECORD_RE = re.compile(r"^2024:[1-9][0-9]*$")
_TIME_RE = re.compile(r"^(?:[01][0-9]|2[0-3]):[0-5][0-9]$")
_YEAR_START = dt.date(2024, 1, 1)
_YEAR_END = dt.date(2024, 12, 31)
_ALLOWED_MODES = frozenset(MODE_ORDER)
_OUTPUT_MODES = frozenset(CONTEXT_MODE_ORDER)

_MAX_RECORDS = 36_297
_MAX_CRASH_SOURCE_RECORDS = 100_000
_MAX_PERSON_SOURCE_RECORDS = 100_000
_MAX_SEGMENTS = 250_000
_MAX_COORDINATES = 2_000_000
_MAX_CELLS = _MAX_RECORDS * len(MODE_ORDER)
_MAX_CONFIG_BYTES = 1024 * 1024
_MAX_NETWORK_BYTES = 64 * 1024 * 1024
_MAX_JOINED_BYTES = 64 * 1024 * 1024
_MAX_DISTANCE_M = 100_000.0

_SOURCE_LINEAGE_KEYS = frozenset(
    {
        "source_id",
        "dataset_year",
        "release_status",
        "attempt_id",
        "raw_sha256",
        "normalized_sha256",
        "accident_sha256",
        "person_sha256",
        "crash_mapping_version",
        "person_mapping_version",
        "crash_records_read",
        "crash_records_accepted",
        "crash_records_rejected",
        "person_records_read",
        "person_records_accepted",
        "person_records_excluded",
        "cases_joined",
        "cases_excluded",
    }
)
_INPUT_LINEAGE_KEYS = frozenset(
    {
        "config_raw_sha256",
        "config_raw_byte_count",
        "network_raw_sha256",
        "network_raw_byte_count",
        "network_canonical_sha256",
        "network_segment_count",
        "network_coordinate_count",
    }
)
_ACCOUNTING_KEYS = frozenset(
    {
        "records_received",
        "records_outside_window",
        "records_in_window",
        "uniquely_snapped_crashes",
        "ambiguous_crashes",
        "unsnapped_crashes",
        "uniquely_snapped_timed_crashes",
        "uniquely_snapped_unknown_time_crashes",
        "positive_candidate_cell_count",
        "eligible_cell_count",
        "suppressed_positive_cell_count",
        "crash_contribution_total",
        "eligible_crash_contribution_total",
        "suppressed_crash_contribution_total",
    }
)
_TOP_LEVEL_KEYS = frozenset(
    {
        "schema_version",
        "artifact_type",
        "visibility",
        "city_key",
        "source_lineage",
        "input_lineage",
        "method",
        "method_sha256",
        "accounting",
        "caveat",
        "cells",
    }
)

CellKey = tuple[str, str, str]
RecordFields = tuple[str, dt.date, str, float, float, tuple[str, ...]]


def _canonical_compact(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except UnicodeEncodeError:
        raise ValueError("FARS context text must contain only Unicode scalar values") from None


def _digest(value: object, label: str) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise ValueError(f"{label} must be an exact lowercase SHA-256 digest")
    return value


def _bounded_int(value: object, label: str, maximum: int, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise ValueError(f"{label} must be an integer in [{minimum}, {maximum}]")
    return value


def _distance(value: object, label: str, *, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    result = float(value)
    valid = 0 < result <= _MAX_DISTANCE_M if positive else 0 <= result <= _MAX_DISTANCE_M
    if not math.isfinite(result) or not valid:
        interval = f"(0, {_MAX_DISTANCE_M}]" if positive else f"[0, {_MAX_DISTANCE_M}]"
        raise ValueError(f"{label} must be finite and in {interval}")
    return result


def _safe_text(value: object, label: str, maximum: int) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > maximum
        or value != value.strip()
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
        or any(0xD800 <= ord(character) <= 0xDFFF for character in value)
    ):
        raise ValueError(f"{label} is invalid Unicode scalar text")
    return value


def _window(config: Config) -> tuple[dt.date, dt.date]:
    if config.window_start is None or config.window_end is None:
        raise ValueError("FARS context window must provide both inclusive bounds")
    try:
        requested_start = dt.date.fromisoformat(config.window_start)
        requested_end = dt.date.fromisoformat(config.window_end)
    except ValueError as exc:
        raise ValueError("FARS context window must use exact ISO-8601 calendar dates") from exc
    if requested_start > requested_end:
        raise ValueError("FARS context window start must not follow its end")
    if requested_start.year != 2024 or requested_end.year != 2024:
        raise ValueError("FARS context window must be wholly within dataset year 2024")
    return requested_start, requested_end


def _effective_k(configured_floor: object) -> tuple[int, int]:
    requested = _bounded_int(configured_floor, "requested privacy floor", _MAX_RECORDS, minimum=1)
    return requested, max(FARS_CONTEXT_MINIMUM_K, requested)


def _part_of_day(value: object) -> str:
    if value is None:
        return "unknown_time"
    if not isinstance(value, str) or _TIME_RE.fullmatch(value) is None:
        raise ValueError("verified FARS occurred_time_local is invalid")
    hour = int(value[:2])
    for band in _TIME_BANDS:
        if cast(int, band["start_hour_inclusive"]) <= hour < cast(int, band["end_hour_exclusive"]):
            return cast(str, band["key"])
    raise AssertionError("closed time bands must cover every valid hour")


def _modes(value: object) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)) or len(value) > len(MODE_ORDER):
        raise ValueError("verified FARS involved_modes must be a bounded array")
    normalized: set[str] = set()
    for raw_mode in value:
        if not isinstance(raw_mode, str) or raw_mode not in _ALLOWED_MODES:
            raise ValueError("verified FARS involved_modes contains an unsupported mode")
        normalized.add(UNKNOWN_MODE if raw_mode == "unknown" else raw_mode)
    if not normalized:
        normalized.add(UNKNOWN_MODE)
    return tuple(mode for mode in CONTEXT_MODE_ORDER if mode in normalized)


def _occurred_on(value: object) -> dt.date:
    if not isinstance(value, str):
        raise ValueError("verified joined outcome requires occurred_on")
    try:
        occurred_on = dt.date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("verified joined outcome occurred_on is invalid") from exc
    if occurred_on.year != 2024:
        raise ValueError("FARS context accepts dataset-year 2024 records only")
    return occurred_on


def _location(value: object) -> tuple[float, float]:
    if not isinstance(value, Mapping):
        raise ValueError("verified joined outcome requires a location mapping")
    location = cast(Mapping[str, object], value)
    lat, lon = location.get("lat"), location.get("lon")
    if (
        isinstance(lat, bool)
        or not isinstance(lat, (int, float))
        or isinstance(lon, bool)
        or not isinstance(lon, (int, float))
    ):
        raise ValueError("verified joined outcome location must contain numeric lat/lon")
    latitude, longitude = float(lat), float(lon)
    if (
        not math.isfinite(latitude)
        or not -90 <= latitude <= 90
        or not math.isfinite(longitude)
        or not -180 <= longitude <= 180
    ):
        raise ValueError("verified joined outcome location is outside WGS84 bounds")
    return latitude, longitude


def _record_fields(record: object) -> RecordFields:
    if not isinstance(record, Mapping):
        raise TypeError("verified joined outcomes must be mapping records")
    outcome_raw, summary_raw = record.get("outcome"), record.get("mode_summary")
    if not isinstance(outcome_raw, Mapping) or not isinstance(summary_raw, Mapping):
        raise ValueError("verified joined outcome requires outcome and mode_summary mappings")
    outcome = cast(Mapping[str, object], outcome_raw)
    summary = cast(Mapping[str, object], summary_raw)
    source_id = outcome.get("source_record_id")
    if not isinstance(source_id, str) or _SOURCE_RECORD_RE.fullmatch(source_id) is None:
        raise ValueError("verified joined outcome requires a canonical 2024 source identity")
    if summary.get("source_record_id") != source_id:
        raise ValueError("verified joined outcome and mode summary identities differ")
    occurred_on = _occurred_on(outcome.get("occurred_on"))
    latitude, longitude = _location(outcome.get("location"))
    return (
        source_id,
        occurred_on,
        _part_of_day(outcome.get("occurred_time_local")),
        latitude,
        longitude,
        _modes(summary.get("involved_modes")),
    )


def _bounded_values(values: Iterable[object], maximum: int, label: str) -> list[object]:
    bounded = list(islice(values, maximum + 1))
    if len(bounded) > maximum:
        raise ValueError(f"{label} exceeds its maxItems limit")
    return bounded


def _validated_records(records: Iterable[Mapping[str, object]]) -> list[RecordFields]:
    values = _bounded_values(records, _MAX_RECORDS, "verified joined outcomes")
    parsed = [_record_fields(record) for record in values]
    identities = [record[0] for record in parsed]
    if len(identities) != len(set(identities)):
        raise ValueError("verified joined outcomes contain duplicate source identities")
    return sorted(parsed, key=lambda record: record[0])


def _validated_segments(segments: Iterable[Segment]) -> tuple[list[Segment], int]:
    raw_values = _bounded_values(segments, _MAX_SEGMENTS, "parsed network segments")
    values: list[Segment] = []
    seen: set[str] = set()
    coordinate_count = 0
    for raw_segment in raw_values:
        if not isinstance(raw_segment, Segment):
            raise TypeError("parsed network must contain Segment values")
        segment = raw_segment
        values.append(segment)
        segment_id = _safe_text(segment.id, "segment id", 512)
        _safe_text(segment.name, f"segment {segment_id!r} name", 1024)
        if segment_id in seen:
            raise ValueError("parsed network contains duplicate segment ids")
        seen.add(segment_id)
        if len(segment.coords) < 2:
            raise ValueError("parsed network segments require at least two coordinates")
        coordinate_count += len(segment.coords)
        if coordinate_count > _MAX_COORDINATES:
            raise ValueError("parsed network exceeds the coordinate maxItems limit")
        for coordinate in segment.coords:
            if not isinstance(coordinate, tuple) or len(coordinate) != 2:
                raise ValueError("parsed network coordinates must be (lat, lon) tuples")
            _location({"lat": coordinate[0], "lon": coordinate[1]})
    return sorted(values, key=lambda segment: segment.id), coordinate_count


def _canonical_network_sha256(segments: list[Segment]) -> str:
    """Hash canonical parsed-network JSON without duplicating the whole network."""

    digest = hashlib.sha256()
    digest.update(b'{"segments":[')
    for segment_index, segment in enumerate(segments):
        if segment_index:
            digest.update(b",")
        # Canonical key order is coords, id, name. Coordinates are emitted one
        # at a time so national-size parsed tuples are never copied into a
        # second full nested list/string representation.
        digest.update(b'{"coords":[')
        for coordinate_index, (lat, lon) in enumerate(segment.coords):
            if coordinate_index:
                digest.update(b",")
            digest.update(b"[")
            digest.update(_canonical_compact(float(lat)))
            digest.update(b",")
            digest.update(_canonical_compact(float(lon)))
            digest.update(b"]")
        digest.update(b'],"id":')
        digest.update(_canonical_compact(segment.id))
        digest.update(b',"name":')
        digest.update(_canonical_compact(segment.name))
        digest.update(b"}")
    digest.update(b"]}")
    return digest.hexdigest()


def canonical_parsed_network_sha256(segments: Iterable[Segment]) -> str:
    """Return the canonical digest used by the context input-lineage contract."""

    values, _coordinate_count = _validated_segments(segments)
    return _canonical_network_sha256(values)


def _validate_source_counts(value: Mapping[str, object]) -> None:
    crash_read = _bounded_int(
        value["crash_records_read"], "crash_records_read", _MAX_CRASH_SOURCE_RECORDS
    )
    crash_accepted = _bounded_int(
        value["crash_records_accepted"], "crash_records_accepted", _MAX_RECORDS
    )
    crash_rejected = _bounded_int(
        value["crash_records_rejected"], "crash_records_rejected", _MAX_CRASH_SOURCE_RECORDS
    )
    person_read = _bounded_int(
        value["person_records_read"], "person_records_read", _MAX_PERSON_SOURCE_RECORDS
    )
    person_accepted = _bounded_int(
        value["person_records_accepted"], "person_records_accepted", _MAX_PERSON_SOURCE_RECORDS
    )
    person_excluded = _bounded_int(
        value["person_records_excluded"], "person_records_excluded", _MAX_PERSON_SOURCE_RECORDS
    )
    cases_joined = _bounded_int(value["cases_joined"], "cases_joined", _MAX_RECORDS)
    cases_excluded = _bounded_int(
        value["cases_excluded"], "cases_excluded", _MAX_CRASH_SOURCE_RECORDS
    )
    if crash_read != crash_accepted + crash_rejected:
        raise ValueError("FARS context crash source accounting equation is invalid")
    if person_read != person_accepted + person_excluded:
        raise ValueError("FARS context person source accounting equation is invalid")
    if cases_joined != crash_accepted or cases_excluded != crash_rejected:
        raise ValueError("FARS context joined-case source accounting equation is invalid")


def _source_lineage(value: Mapping[str, object]) -> dict[str, object]:
    if set(value) != _SOURCE_LINEAGE_KEYS:
        raise ValueError("FARS context source lineage has unexpected or missing fields")
    if value["source_id"] != "fars-joined" or value["dataset_year"] != 2024:
        raise ValueError("FARS context source lineage must identify joined FARS 2024")
    if value["release_status"] not in {"preliminary", "final"}:
        raise ValueError("FARS context release status is invalid")
    attempt = value["attempt_id"]
    if not isinstance(attempt, str) or _ATTEMPT_RE.fullmatch(attempt) is None:
        raise ValueError("FARS context source attempt id is invalid")
    for key in ("raw_sha256", "normalized_sha256", "accident_sha256", "person_sha256"):
        _digest(value[key], key)
    for key, expected in (
        ("crash_mapping_version", FARS_MAPPING_VERSION),
        ("person_mapping_version", PERSON_MODE_MAPPING_VERSION),
    ):
        version = value[key]
        if (
            not isinstance(version, str)
            or _SEMVER_RE.fullmatch(version) is None
            or version != expected
        ):
            raise ValueError(f"FARS context {key} is invalid")
    _validate_source_counts(value)
    return {key: value[key] for key in sorted(_SOURCE_LINEAGE_KEYS)}


def _input_lineage(
    value: Mapping[str, object], segments: list[Segment], coordinate_count: int
) -> dict[str, object]:
    if set(value) != _INPUT_LINEAGE_KEYS:
        raise ValueError("FARS context input lineage has unexpected or missing fields")
    _digest(value["config_raw_sha256"], "config_raw_sha256")
    _digest(value["network_raw_sha256"], "network_raw_sha256")
    expected_canonical = _canonical_network_sha256(segments)
    if _digest(value["network_canonical_sha256"], "network_canonical_sha256") != expected_canonical:
        raise ValueError("FARS context canonical network digest does not match parsed segments")
    _bounded_int(
        value["config_raw_byte_count"], "config_raw_byte_count", _MAX_CONFIG_BYTES, minimum=1
    )
    _bounded_int(
        value["network_raw_byte_count"], "network_raw_byte_count", _MAX_NETWORK_BYTES, minimum=1
    )
    if value["network_segment_count"] != len(segments):
        raise ValueError("FARS context network segment count does not match parsed segments")
    if value["network_coordinate_count"] != coordinate_count:
        raise ValueError("FARS context network coordinate count does not match parsed segments")
    return {key: value[key] for key in sorted(_INPUT_LINEAGE_KEYS)}


def _method(
    *,
    start: dt.date,
    end: dt.date,
    snap_max_m: float,
    ambiguity_margin_m: float,
    ref_lat: float | None,
    ref_lon: float | None,
    requested_k: int,
    effective_k: int,
) -> dict[str, object]:
    if ref_lat is None and ref_lon is None:
        reference_policy = "canonical_network_vertex_mean"
        reference_lat = reference_lon = None
    elif ref_lat is not None and ref_lon is not None:
        reference_policy = "configured_reference_pair"
        reference_lat, reference_lon = _location({"lat": ref_lat, "lon": ref_lon})
    else:
        raise ValueError("FARS context projection reference must provide both coordinates")
    return {
        "context": {
            "algorithm": "segment_part_of_day_involved_mode_fatal_crash_colocation",
            "algorithm_version": FARS_CONTEXT_ALGORITHM_VERSION,
            "artifact_schema_version": FARS_CONTEXT_SCHEMA_VERSION,
        },
        "window": {
            "dataset_year": 2024,
            "effective_start_inclusive": start.isoformat(),
            "effective_end_inclusive": end.isoformat(),
        },
        "snap": {
            "max_distance_m": snap_max_m,
            "ambiguity_margin_m": ambiguity_margin_m,
            "assignment_rule": "unique_nearest_within_max_distance_only",
            "projection": "local_equirectangular_metres",
            "reference_policy": reference_policy,
            "reference_lat": reference_lat,
            "reference_lon": reference_lon,
            "point_snap": point_snap_method_descriptor(),
        },
        "time": {
            "bands": [dict(band) for band in _TIME_BANDS],
            "order": list(PART_OF_DAY_ORDER),
            "unknown_policy": "missing_clock_value_to_unknown_time",
        },
        "mode": {
            "mapping_version": PERSON_MODE_MAPPING_VERSION,
            "source_order": list(MODE_ORDER),
            "output_order": list(CONTEXT_MODE_ORDER),
            "crash_basis": "one_contribution_per_crash_per_distinct_involved_mode",
            "unknown_policy": "source_unknown_and_empty_mode_set_to_unknown_mode",
            "unknown_preserved_alongside_known_modes": True,
            "strata_additive": False,
        },
        "privacy": {
            "requested_k": requested_k,
            "minimum_k": FARS_CONTEXT_MINIMUM_K,
            "effective_k": effective_k,
            "candidate_definition": "positive_observed_segment_time_mode_cell",
            "eligibility_rule": "crash_count_greater_than_or_equal_to_effective_k",
            "suppressed_output": "global_positive_cell_count_and_contribution_total_only",
            "cell_key_order": ["segment_id", "part_of_day", "involved_mode"],
            "serialization_order": [
                "segment_id_lexical",
                "part_of_day_declared_order",
                "involved_mode_declared_order",
            ],
        },
        "limitation_codes": list(LIMITATION_CODES),
    }


def _method_sha256(method: Mapping[str, object]) -> str:
    return hashlib.sha256(_canonical_compact(method)).hexdigest()


def _cell_sort_key(cell: CellKey) -> tuple[str, int, int]:
    segment_id, part, mode = cell
    return segment_id, PART_OF_DAY_ORDER.index(part), CONTEXT_MODE_ORDER.index(mode)


def _validate_method(value: object, digest: object) -> int:
    if not isinstance(value, Mapping):
        raise ValueError("FARS context method must be an object")
    method = cast(Mapping[str, object], value)
    if _digest(digest, "method_sha256") != _method_sha256(method):
        raise ValueError("FARS context method digest does not match its closed method block")
    window = method.get("window")
    snap = method.get("snap")
    privacy = method.get("privacy")
    if (
        not isinstance(window, Mapping)
        or not isinstance(snap, Mapping)
        or not isinstance(privacy, Mapping)
    ):
        raise ValueError("FARS context method shape is invalid")
    try:
        start = dt.date.fromisoformat(cast(str, window["effective_start_inclusive"]))
        end = dt.date.fromisoformat(cast(str, window["effective_end_inclusive"]))
        requested_k = _bounded_int(
            privacy["requested_k"], "method requested_k", _MAX_RECORDS, minimum=1
        )
        effective_k = _bounded_int(
            privacy["effective_k"], "method effective_k", _MAX_RECORDS, minimum=1
        )
        expected = _method(
            start=start,
            end=end,
            snap_max_m=_distance(snap["max_distance_m"], "method snap max", positive=True),
            ambiguity_margin_m=_distance(snap["ambiguity_margin_m"], "method ambiguity margin"),
            ref_lat=cast(float | None, snap["reference_lat"]),
            ref_lon=cast(float | None, snap["reference_lon"]),
            requested_k=requested_k,
            effective_k=effective_k,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("FARS context method shape is invalid") from exc
    if not _YEAR_START <= start <= end <= _YEAR_END:
        raise ValueError("FARS context method effective window is invalid")
    if effective_k != max(FARS_CONTEXT_MINIMUM_K, requested_k):
        raise ValueError("FARS context method privacy threshold is invalid")
    if dict(method) != expected:
        raise ValueError("FARS context method is not the closed supported method")
    return effective_k


def _validate_cells(value: object, effective_k: int) -> tuple[int, int]:
    if not isinstance(value, list) or len(value) > _MAX_CELLS:
        raise ValueError("FARS context cells must be a bounded array")
    keys: list[CellKey] = []
    contribution_total = 0
    for raw_cell in value:
        if not isinstance(raw_cell, Mapping) or set(raw_cell) != {
            "segment_id",
            "part_of_day",
            "involved_mode",
            "crash_count",
        }:
            raise ValueError("FARS context cell shape is invalid")
        segment_id = _safe_text(raw_cell["segment_id"], "cell segment_id", 512)
        part, mode = raw_cell["part_of_day"], raw_cell["involved_mode"]
        if not isinstance(part, str) or part not in PART_OF_DAY_ORDER:
            raise ValueError("FARS context cell part_of_day is invalid")
        if not isinstance(mode, str) or mode not in _OUTPUT_MODES:
            raise ValueError("FARS context cell involved_mode is invalid")
        count = _bounded_int(raw_cell["crash_count"], "cell crash_count", _MAX_RECORDS)
        if count < effective_k:
            raise ValueError("FARS context must not persist a below-threshold cell")
        keys.append((segment_id, part, mode))
        contribution_total += count
    if len(keys) != len(set(keys)) or keys != sorted(keys, key=_cell_sort_key):
        raise ValueError("FARS context cells must be unique and canonically ordered")
    return len(keys), contribution_total


def _accounting_values(value: object) -> dict[str, int]:
    if not isinstance(value, Mapping) or set(value) != _ACCOUNTING_KEYS:
        raise ValueError("FARS context accounting shape is invalid")
    maximum_contributions = _MAX_RECORDS * len(MODE_ORDER)
    record_keys = {
        "records_received",
        "records_outside_window",
        "records_in_window",
        "uniquely_snapped_crashes",
        "ambiguous_crashes",
        "unsnapped_crashes",
        "uniquely_snapped_timed_crashes",
        "uniquely_snapped_unknown_time_crashes",
    }
    cell_keys = {
        "positive_candidate_cell_count",
        "eligible_cell_count",
        "suppressed_positive_cell_count",
    }
    accounting: dict[str, int] = {}
    for key in _ACCOUNTING_KEYS:
        maximum = (
            _MAX_RECORDS
            if key in record_keys
            else _MAX_CELLS
            if key in cell_keys
            else maximum_contributions
        )
        accounting[key] = _bounded_int(value[key], key, maximum)
    return accounting


def _validate_record_accounting(accounting: Mapping[str, int]) -> None:
    if accounting["records_received"] != (
        accounting["records_outside_window"] + accounting["records_in_window"]
    ):
        raise ValueError("FARS context window accounting equation is invalid")
    if accounting["records_in_window"] != (
        accounting["uniquely_snapped_crashes"]
        + accounting["ambiguous_crashes"]
        + accounting["unsnapped_crashes"]
    ):
        raise ValueError("FARS context snap accounting equation is invalid")
    if accounting["uniquely_snapped_crashes"] != (
        accounting["uniquely_snapped_timed_crashes"]
        + accounting["uniquely_snapped_unknown_time_crashes"]
    ):
        raise ValueError("FARS context time accounting equation is invalid")


def _validate_accounting(value: object, cells: object, effective_k: int) -> None:
    accounting = _accounting_values(value)
    eligible_cells, eligible_contributions = _validate_cells(cells, effective_k)
    _validate_record_accounting(accounting)
    if accounting["positive_candidate_cell_count"] != (
        accounting["eligible_cell_count"] + accounting["suppressed_positive_cell_count"]
    ):
        raise ValueError("FARS context positive-cell accounting equation is invalid")
    if accounting["crash_contribution_total"] != (
        accounting["eligible_crash_contribution_total"]
        + accounting["suppressed_crash_contribution_total"]
    ):
        raise ValueError("FARS context contribution accounting equation is invalid")
    if (
        accounting["eligible_cell_count"] != eligible_cells
        or accounting["eligible_crash_contribution_total"] != eligible_contributions
    ):
        raise ValueError("FARS context eligible-cell accounting is invalid")
    suppressed_cells = accounting["suppressed_positive_cell_count"]
    suppressed_contributions = accounting["suppressed_crash_contribution_total"]
    if not (
        (suppressed_cells == 0 and suppressed_contributions == 0)
        or suppressed_cells <= suppressed_contributions <= suppressed_cells * (effective_k - 1)
    ):
        raise ValueError("FARS context suppressed-cell accounting is invalid")
    positive_cells = accounting["positive_candidate_cell_count"]
    contributions = accounting["crash_contribution_total"]
    unique = accounting["uniquely_snapped_crashes"]
    if not ((positive_cells == 0 and contributions == 0) or 1 <= positive_cells <= contributions):
        raise ValueError("FARS context positive contribution bounds are invalid")
    if not (
        (unique == 0 and contributions == 0) or unique <= contributions <= unique * len(MODE_ORDER)
    ):
        raise ValueError("FARS context per-crash contribution bounds are invalid")


def validate_fars_context_artifact(artifact: Mapping[str, object]) -> None:
    """Fail closed on schema, privacy, lineage, method, or accounting drift."""

    if set(artifact) != _TOP_LEVEL_KEYS:
        raise ValueError("FARS context artifact has unexpected or missing fields")
    if artifact["schema_version"] != FARS_CONTEXT_SCHEMA_VERSION:
        raise ValueError("FARS context artifact has an unsupported schema version")
    if artifact["artifact_type"] != FARS_CONTEXT_ARTIFACT_TYPE:
        raise ValueError("FARS context artifact has an unsupported artifact type")
    if artifact["visibility"] != "private" or artifact["caveat"] != _CAVEAT:
        raise ValueError("FARS context privacy contract is invalid")
    _safe_text(artifact["city_key"], "city_key", 128)
    source = artifact["source_lineage"]
    inputs = artifact["input_lineage"]
    if not isinstance(source, Mapping) or _source_lineage(source) != dict(source):
        raise ValueError("FARS context source lineage is not canonical")
    if not isinstance(inputs, Mapping) or set(inputs) != _INPUT_LINEAGE_KEYS:
        raise ValueError("FARS context input lineage is invalid")
    for key in ("config_raw_sha256", "network_raw_sha256", "network_canonical_sha256"):
        _digest(inputs[key], key)
    _bounded_int(
        inputs["config_raw_byte_count"], "config_raw_byte_count", _MAX_CONFIG_BYTES, minimum=1
    )
    _bounded_int(
        inputs["network_raw_byte_count"], "network_raw_byte_count", _MAX_NETWORK_BYTES, minimum=1
    )
    _bounded_int(inputs["network_segment_count"], "network_segment_count", _MAX_SEGMENTS)
    _bounded_int(inputs["network_coordinate_count"], "network_coordinate_count", _MAX_COORDINATES)
    effective_k = _validate_method(artifact["method"], artifact["method_sha256"])
    accounting = artifact["accounting"]
    if not isinstance(accounting, Mapping) or source["cases_joined"] != accounting.get(
        "records_received"
    ):
        raise ValueError("FARS context source cases_joined does not match context accounting")
    _validate_accounting(accounting, artifact["cells"], effective_k)


def _build_parsed_fars_context(
    verified_records: Iterable[Mapping[str, object]],
    segments: Iterable[Segment],
    config: Config,
    *,
    source_lineage: Mapping[str, object],
    input_lineage: Mapping[str, object],
    fars_snap_max_m: float,
    ambiguity_margin_m: float,
) -> dict[str, object]:
    """Test-only parsed helper; public callers must use the proof-bound builder."""

    city_key = _safe_text(config.city, "city_key", 128)
    start, end = _window(config)
    requested_k, effective_k = _effective_k(config.min_publish_n)
    snap_max_m = _distance(fars_snap_max_m, "fars_snap_max_m", positive=True)
    ambiguity_margin = _distance(ambiguity_margin_m, "ambiguity_margin_m")
    segment_values, coordinate_count = _validated_segments(segments)
    safe_source = _source_lineage(source_lineage)
    safe_inputs = _input_lineage(input_lineage, segment_values, coordinate_count)
    records = _validated_records(verified_records)
    if safe_source["cases_joined"] != len(records):
        raise ValueError("FARS context source cases_joined does not match verified records")
    in_window = [record for record in records if start <= record[1] <= end]

    snaps = snap_points_to_segments(
        [SnapPoint(record[0], record[3], record[4]) for record in in_window],
        segment_values,
        max_distance_m=snap_max_m,
        ambiguity_margin_m=ambiguity_margin,
        ref_lat=config.ref_lat,
        ref_lon=config.ref_lon,
    )
    record_by_id = {record[0]: record for record in in_window}
    statuses = Counter(result.status for result in snaps)
    cell_counts: Counter[CellKey] = Counter()
    timed = unknown_time = 0

    for result in snaps:
        if result.status != "snapped" or result.segment_id is None:
            continue
        record = record_by_id[result.point_id]
        part, modes = record[2], record[5]
        if part == "unknown_time":
            unknown_time += 1
        else:
            timed += 1
        for mode in modes:
            cell_counts[(result.segment_id, part, mode)] += 1

    eligible: dict[CellKey, int] = {}
    suppressed_positive_cell_count = 0
    suppressed_contributions = 0
    for key, count in cell_counts.items():
        if count >= effective_k:
            eligible[key] = count
        else:
            # Suppressed keys never enter another container; only these two
            # global counters cross the ephemeral aggregation pass.
            suppressed_positive_cell_count += 1
            suppressed_contributions += count
    cells = [
        {
            "segment_id": segment_id,
            "part_of_day": part,
            "involved_mode": mode,
            "crash_count": eligible[(segment_id, part, mode)],
        }
        for segment_id, part, mode in sorted(eligible, key=_cell_sort_key)
    ]
    eligible_contributions = sum(eligible.values())
    unique = statuses["snapped"]
    method = _method(
        start=start,
        end=end,
        snap_max_m=snap_max_m,
        ambiguity_margin_m=ambiguity_margin,
        ref_lat=config.ref_lat,
        ref_lon=config.ref_lon,
        requested_k=requested_k,
        effective_k=effective_k,
    )
    artifact: dict[str, object] = {
        "schema_version": FARS_CONTEXT_SCHEMA_VERSION,
        "artifact_type": FARS_CONTEXT_ARTIFACT_TYPE,
        "visibility": "private",
        "city_key": city_key,
        "source_lineage": safe_source,
        "input_lineage": safe_inputs,
        "method": method,
        "method_sha256": _method_sha256(method),
        "accounting": {
            "records_received": len(records),
            "records_outside_window": len(records) - len(in_window),
            "records_in_window": len(in_window),
            "uniquely_snapped_crashes": unique,
            "ambiguous_crashes": statuses["ambiguous"],
            "unsnapped_crashes": statuses["unsnapped"],
            "uniquely_snapped_timed_crashes": timed,
            "uniquely_snapped_unknown_time_crashes": unknown_time,
            "positive_candidate_cell_count": len(cell_counts),
            "eligible_cell_count": len(eligible),
            "suppressed_positive_cell_count": suppressed_positive_cell_count,
            "crash_contribution_total": eligible_contributions + suppressed_contributions,
            "eligible_crash_contribution_total": eligible_contributions,
            "suppressed_crash_contribution_total": suppressed_contributions,
        },
        "caveat": _CAVEAT,
        "cells": cells,
    }
    validate_fars_context_artifact(artifact)
    return artifact


def _reject_json_constant(_value: str) -> NoReturn:
    raise ValueError("verified joined snapshot contains a non-finite JSON constant")


def _strict_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, child in pairs:
        if key in value:
            raise ValueError("verified joined snapshot contains a duplicate JSON key")
        value[key] = child
    return value


def _verified_joined_records(snapshot: _VerifiedJoinedSnapshot) -> list[Mapping[str, object]]:
    if type(snapshot) is not _VerifiedJoinedSnapshot:
        raise TypeError("FARS context requires a proof-bound verified joined snapshot")
    payload = snapshot.normalized_bytes
    if type(payload) is not bytes or not 0 < len(payload) <= _MAX_JOINED_BYTES:
        raise ValueError("verified joined snapshot bytes are outside their safety limit")
    if hashlib.sha256(payload).hexdigest() != snapshot.evidence.normalized_sha256:
        raise ValueError("verified joined snapshot digest does not match its evidence")
    try:
        decoded: object = json.loads(
            payload.decode("utf-8", errors="strict"),
            object_pairs_hook=_strict_json_object,
            parse_constant=_reject_json_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ValueError("verified joined snapshot JSON decoding failed") from exc
    if not isinstance(decoded, Mapping):
        raise ValueError("verified joined snapshot must contain a JSON object")
    artifact = cast(Mapping[str, object], decoded)
    if canonical_joined_outcome_artifact_bytes(artifact) != payload:
        raise ValueError("verified joined snapshot is not canonical joined-outcome bytes")
    records = artifact.get("records")
    if not isinstance(records, list):
        raise ValueError("verified joined snapshot records are invalid")
    return [cast(Mapping[str, object], record) for record in records]


def _snapshot_source_lineage(snapshot: _VerifiedJoinedSnapshot) -> dict[str, object]:
    evidence = snapshot.evidence
    return {
        "source_id": evidence.source_id,
        "dataset_year": evidence.dataset_year,
        "release_status": evidence.release_status,
        "attempt_id": evidence.attempt_id,
        "raw_sha256": evidence.raw_sha256,
        "normalized_sha256": evidence.normalized_sha256,
        "accident_sha256": evidence.accident_sha256,
        "person_sha256": evidence.person_sha256,
        "crash_mapping_version": evidence.crash_mapping_version,
        "person_mapping_version": evidence.person_mapping_version,
        "crash_records_read": evidence.crash_records_read,
        "crash_records_accepted": evidence.crash_records_accepted,
        "crash_records_rejected": evidence.crash_records_rejected,
        "person_records_read": evidence.person_records_read,
        "person_records_accepted": evidence.person_records_accepted,
        "person_records_excluded": evidence.person_records_excluded,
        "cases_joined": evidence.cases_joined,
        "cases_excluded": evidence.cases_excluded,
    }


def _exact_input_bytes(value: object, label: str, maximum: int) -> bytes:
    if type(value) is not bytes:
        raise TypeError(f"{label} must be exact immutable bytes")
    payload = value
    if not 0 < len(payload) <= maximum:
        raise ValueError(f"{label} bytes are outside their safety limit")
    return payload


def build_verified_fars_context(
    snapshot: _VerifiedJoinedSnapshot,
    *,
    config_path: str | Path,
    config_bytes: bytes,
    network_bytes: bytes,
    fars_snap_max_m: float,
    ambiguity_margin_m: float,
) -> dict[str, object]:
    """Derive private context only from proof-bound and exact input bytes."""

    records = _verified_joined_records(snapshot)
    exact_config = _exact_input_bytes(config_bytes, "config", _MAX_CONFIG_BYTES)
    exact_network = _exact_input_bytes(network_bytes, "network", _MAX_NETWORK_BYTES)
    config = load_config_bytes(config_path, exact_config)
    segments = load_streets_bytes(config.streets_path, exact_network)
    validated_segments, coordinate_count = _validated_segments(segments)
    input_lineage: dict[str, object] = {
        "config_raw_sha256": hashlib.sha256(exact_config).hexdigest(),
        "config_raw_byte_count": len(exact_config),
        "network_raw_sha256": hashlib.sha256(exact_network).hexdigest(),
        "network_raw_byte_count": len(exact_network),
        "network_canonical_sha256": _canonical_network_sha256(validated_segments),
        "network_segment_count": len(validated_segments),
        "network_coordinate_count": coordinate_count,
    }
    return _build_parsed_fars_context(
        records,
        validated_segments,
        config,
        source_lineage=_snapshot_source_lineage(snapshot),
        input_lineage=input_lineage,
        fars_snap_max_m=fars_snap_max_m,
        ambiguity_margin_m=ambiguity_margin_m,
    )


def canonical_fars_context_bytes(artifact: Mapping[str, object]) -> bytes:
    """Validate and serialize deterministic UTF-8 canonical JSON."""

    validate_fars_context_artifact(artifact)
    return _canonical_compact(artifact) + b"\n"


__all__ = [
    "CONTEXT_MODE_ORDER",
    "FARS_CONTEXT_ALGORITHM_VERSION",
    "FARS_CONTEXT_ARTIFACT_TYPE",
    "FARS_CONTEXT_MINIMUM_K",
    "FARS_CONTEXT_SCHEMA_VERSION",
    "LIMITATION_CODES",
    "PART_OF_DAY_ORDER",
    "UNKNOWN_MODE",
    "build_verified_fars_context",
    "canonical_fars_context_bytes",
    "canonical_parsed_network_sha256",
    "validate_fars_context_artifact",
]
