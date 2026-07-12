from __future__ import annotations

import copy
import hashlib
import io
import json
import math
import zipfile
from pathlib import Path
from typing import Any, cast

import pytest

import nearmiss.fars_context as fars_context
import nearmiss.point_snap as point_snap
import nearmiss.verified_outcomes as verified_outcomes
from nearmiss.adapters.fars import FARS_MAPPING_VERSION
from nearmiss.adapters.fars_joined import (
    PERSON_MODE_MAPPING_VERSION,
    collect_joined,
    read_joined_export_bytes,
)
from nearmiss.config import Config
from nearmiss.errors import ConfigError, NearmissError
from nearmiss.fars_context import (
    CONTEXT_MODE_ORDER,
    FARS_CONTEXT_ARTIFACT_TYPE,
    FARS_CONTEXT_SCHEMA_VERSION,
    LIMITATION_CODES,
    _build_parsed_fars_context,
    build_verified_fars_context,
    canonical_fars_context_bytes,
    canonical_parsed_network_sha256,
)
from nearmiss.joined_outcome_artifacts import (
    build_joined_outcome_artifact,
    canonical_joined_outcome_artifact_bytes,
)
from nearmiss.models import Segment
from nearmiss.point_snap import DECISION_TOLERANCE_M, point_snap_method_descriptor
from nearmiss.verified_outcomes import VerifiedJoinedOutcomeEvidence, _VerifiedJoinedSnapshot

LAT, LON = 38.54, -121.74
ROOT = Path(__file__).resolve().parents[1]
ACCIDENT = (
    (ROOT / "tests" / "fixtures" / "fars" / "accident.csv")
    .read_bytes()
    .replace(b",2023,", b",2024,")
)
PERSON = b"""STATE,ST_CASE,VEH_NO,PER_NO,PER_TYP,INJ_SEV,BODY_TYP
6,100001,1,1,1,4,4
6,100001,0,1,5,2,
6,100002,1,1,1,4,80
6,100002,0,1,6,4,
6,100003,0,1,5,4,
"""
FARS_URL = "https://static.nhtsa.gov/nhtsa/downloads/FARS/2024/National/FARS2024.zip"


def _source_lineage(record_count: int) -> dict[str, object]:
    return {
        "source_id": "fars-joined",
        "dataset_year": 2024,
        "release_status": "final",
        "attempt_id": "attempt-1",
        "raw_sha256": "a" * 64,
        "normalized_sha256": "b" * 64,
        "accident_sha256": "c" * 64,
        "person_sha256": "d" * 64,
        "crash_mapping_version": FARS_MAPPING_VERSION,
        "person_mapping_version": PERSON_MODE_MAPPING_VERSION,
        "crash_records_read": record_count + 1,
        "crash_records_accepted": record_count,
        "crash_records_rejected": 1,
        "person_records_read": record_count + 1,
        "person_records_accepted": record_count,
        "person_records_excluded": 1,
        "cases_joined": record_count,
        "cases_excluded": 1,
    }


def _joined_payload() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("FARS/accident.csv", ACCIDENT)
        archive.writestr("FARS/person.csv", PERSON)
    return buffer.getvalue()


def _proof_snapshot(*, noncanonical: bool = False) -> _VerifiedJoinedSnapshot:
    raw = _joined_payload()
    outcomes, summaries, crash, person = collect_joined(
        read_joined_export_bytes(raw), release_status="final"
    )
    artifact = build_joined_outcome_artifact(
        outcomes,
        summaries,
        person,
        crash,
        distribution_url=FARS_URL,
        max_invalid_fraction=0.34,
    )
    normalized = canonical_joined_outcome_artifact_bytes(artifact)
    if noncanonical:
        normalized = normalized[:-1] + b" \n"
    evidence = VerifiedJoinedOutcomeEvidence(
        source_id="fars-joined",
        dataset_year=2024,
        crash_mapping_version=FARS_MAPPING_VERSION,
        person_mapping_version=PERSON_MODE_MAPPING_VERSION,
        release_status="final",
        crash_records_read=crash.records_read,
        crash_records_accepted=crash.records_accepted,
        crash_records_rejected=crash.records_read - crash.records_accepted,
        person_records_read=person.records_read,
        person_records_accepted=person.records_accepted,
        person_records_excluded=person.records_excluded_with_rejected_crash,
        cases_joined=person.cases_joined,
        cases_excluded=person.cases_excluded_with_rejected_crash,
        raw_sha256=hashlib.sha256(raw).hexdigest(),
        accident_sha256=person.accident_sha256,
        person_sha256=person.person_sha256,
        normalized_sha256=hashlib.sha256(normalized).hexdigest(),
        attempt_id="context-proof",
        _proof_token=verified_outcomes._JOINED_PROOF_TOKEN,
    )
    return _VerifiedJoinedSnapshot(
        evidence=evidence,
        normalized_bytes=normalized,
        _proof_token=verified_outcomes._JOINED_SNAPSHOT_PROOF_TOKEN,
    )


def _exact_config_bytes() -> bytes:
    return b"""city = "test-city"
streets = "network.geojson"
reports = "reports.json"
exposure = "exposure.json"
ref_lat = 38.54
ref_lon = -121.74

[window]
start = "2024-01-01"
end = "2024-12-31"

[thresholds]
min_publish_n = 5
snap_max_m = 999
"""


def _exact_network_bytes() -> bytes:
    return json.dumps(
        {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {"segment_id": "proof-segment", "name": "Proof"},
                    "geometry": {
                        "type": "LineString",
                        "coordinates": [[-121.75, 38.53], [-121.73, 38.56]],
                    },
                }
            ],
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode()


def _config(**changes: object) -> Config:
    values: dict[str, object] = {
        "city": "test-city",
        "streets_path": Path("private/path/streets.json"),
        "reports_path": Path("private/path/reports.json"),
        "exposure_path": Path("private/path/exposure.csv"),
        "raw_dir": Path("private/raw"),
        "out_dir": Path("private/out"),
        "ref_lat": LAT,
        "ref_lon": LON,
        "snap_max_m": 25.0,
        "min_publish_n": 3,
        "window_start": "2024-01-01",
        "window_end": "2024-12-31",
    }
    values.update(changes)
    return Config(**values)  # type: ignore[arg-type]


def _segment(segment_id: str, lon: float) -> Segment:
    return Segment(segment_id, segment_id, ((LAT - 0.01, lon), (LAT + 0.01, lon)))


def _input_lineage(segments: list[Segment]) -> dict[str, object]:
    return {
        "config_raw_sha256": "e" * 64,
        "config_raw_byte_count": 123,
        "network_raw_sha256": "f" * 64,
        "network_raw_byte_count": 456,
        "network_canonical_sha256": canonical_parsed_network_sha256(segments),
        "network_segment_count": len(segments),
        "network_coordinate_count": sum(len(segment.coords) for segment in segments),
    }


def _record(
    number: int,
    *,
    lon: float = LON,
    occurred_on: str = "2024-06-15",
    occurred_time: str | None = "12:00",
    modes: list[str] | None = None,
) -> dict[str, object]:
    source_id = f"2024:{number}"
    outcome: dict[str, object] = {
        "source_record_id": source_id,
        "occurred_on": occurred_on,
        "location": {"lat": LAT, "lon": lon},
    }
    if occurred_time is not None:
        outcome["occurred_time_local"] = occurred_time
    return {
        "outcome": outcome,
        "mode_summary": {
            "source_record_id": source_id,
            "involved_modes": ["pedestrian"] if modes is None else modes,
        },
    }


def _build(
    records: list[dict[str, object]],
    segments: list[Segment] | None = None,
    *,
    config: Config | None = None,
    ambiguity_margin_m: float = 5.0,
    fars_snap_max_m: float = 25.0,
    source_lineage: dict[str, object] | None = None,
    input_lineage: dict[str, object] | None = None,
) -> dict[str, Any]:
    network = [_segment("main", LON)] if segments is None else segments
    return _build_parsed_fars_context(
        records,
        network,
        _config() if config is None else config,
        source_lineage=_source_lineage(len(records)) if source_lineage is None else source_lineage,
        input_lineage=_input_lineage(network) if input_lineage is None else input_lineage,
        fars_snap_max_m=fars_snap_max_m,
        ambiguity_margin_m=ambiguity_margin_m,
    )


def test_stores_only_segment_time_involved_mode_cells_without_overall_residual() -> None:
    records = [_record(index, modes=["pedestrian", "unknown"]) for index in range(1, 6)]
    artifact = _build(records)

    assert artifact["schema_version"] == FARS_CONTEXT_SCHEMA_VERSION
    assert artifact["artifact_type"] == FARS_CONTEXT_ARTIFACT_TYPE
    assert artifact["visibility"] == "private"
    assert artifact["city_key"] == "test-city"
    assert [cell["involved_mode"] for cell in artifact["cells"]] == [
        "pedestrian",
        "unknown_mode",
    ]
    assert all(cell["crash_count"] == 5 for cell in artifact["cells"])
    encoded = canonical_fars_context_bytes(artifact).decode()
    assert '"overall"' not in encoded
    assert "all_crashes" not in encoded
    assert artifact["accounting"]["crash_contribution_total"] == 10
    assert "non-additive" in artifact["caveat"]


def test_unknown_mode_is_preserved_alongside_known_and_empty_sets_map_to_unknown() -> None:
    mixed = _build([_record(index, modes=["pedestrian", "unknown"]) for index in range(1, 6)])
    empty = _build([_record(index, modes=[]) for index in range(1, 6)])

    assert [cell["involved_mode"] for cell in mixed["cells"]] == [
        "pedestrian",
        "unknown_mode",
    ]
    assert [cell["involved_mode"] for cell in empty["cells"]] == ["unknown_mode"]


@pytest.mark.parametrize(
    ("clock_value", "expected_bucket"),
    [
        ("00:00", "overnight"),
        ("05:59", "overnight"),
        ("06:00", "am_peak"),
        ("09:59", "am_peak"),
        ("10:00", "midday"),
        ("15:59", "midday"),
        ("16:00", "pm_peak"),
        ("19:59", "pm_peak"),
        ("20:00", "evening"),
        ("23:59", "evening"),
        (None, "unknown_time"),
    ],
)
def test_fixed_half_open_time_bands(clock_value: str | None, expected_bucket: str) -> None:
    artifact = _build([_record(index, occurred_time=clock_value) for index in range(1, 6)])
    assert {cell["part_of_day"] for cell in artifact["cells"]} == {expected_bucket}


def test_exact_inclusive_2024_window_is_explicit_in_method() -> None:
    boundary_records = [
        *[_record(index, occurred_on="2024-01-01") for index in range(1, 4)],
        *[_record(index, occurred_on="2024-12-31") for index in range(4, 7)],
    ]
    artifact = _build(boundary_records)

    expected = {
        "dataset_year": 2024,
        "effective_start_inclusive": "2024-01-01",
        "effective_end_inclusive": "2024-12-31",
    }
    assert artifact["method"]["window"] == expected
    assert artifact["accounting"]["records_in_window"] == 6


def test_partial_window_accounting_equation_is_exact() -> None:
    records = [
        _record(1, occurred_on="2024-05-31"),
        *[_record(index, occurred_on="2024-06-01") for index in range(2, 5)],
        *[_record(index, occurred_on="2024-06-30") for index in range(5, 7)],
        _record(7, occurred_on="2024-07-01"),
    ]
    artifact = _build(
        records,
        config=_config(window_start="2024-06-01", window_end="2024-06-30"),
    )
    accounting = artifact["accounting"]

    assert accounting["records_received"] == 7
    assert accounting["records_outside_window"] == 2
    assert accounting["records_in_window"] == 5
    assert accounting["records_received"] == (
        accounting["records_outside_window"] + accounting["records_in_window"]
    )


def test_method_is_closed_complete_and_internally_hashed() -> None:
    artifact = _build([_record(index) for index in range(1, 6)])
    method = artifact["method"]
    expected_hash = hashlib.sha256(
        json.dumps(method, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()
    ).hexdigest()

    assert artifact["method_sha256"] == expected_hash
    assert method["context"] == {
        "algorithm": "segment_part_of_day_involved_mode_fatal_crash_colocation",
        "algorithm_version": "1.0.0",
        "artifact_schema_version": "1.0.0",
    }
    assert method["snap"]["max_distance_m"] == 25.0
    assert method["snap"]["ambiguity_margin_m"] == 5.0
    assert method["snap"]["point_snap"] == point_snap_method_descriptor()
    assert method["snap"]["point_snap"]["densification_step_m"] == 200.0
    assert method["snap"]["point_snap"]["decision_tolerance_m"] == DECISION_TOLERANCE_M
    assert method["snap"]["reference_lat"] == LAT
    assert method["snap"]["reference_lon"] == LON
    assert method["time"]["order"][-1] == "unknown_time"
    assert method["mode"]["mapping_version"] == PERSON_MODE_MAPPING_VERSION
    assert method["mode"]["output_order"] == list(CONTEXT_MODE_ORDER)
    assert method["privacy"]["requested_k"] == 3
    assert method["privacy"]["effective_k"] == 5
    assert method["limitation_codes"] == list(LIMITATION_CODES)


def test_method_hash_changes_for_every_dynamic_decision_input() -> None:
    records = [_record(index) for index in range(1, 6)]
    baseline = _build(records)["method_sha256"]
    variants = [
        _build(records, fars_snap_max_m=20.0)["method_sha256"],
        _build(records, ambiguity_margin_m=2.0)["method_sha256"],
        _build(records, config=_config(min_publish_n=8))["method_sha256"],
        _build(
            records,
            config=_config(window_start="2024-06-01", window_end="2024-12-31"),
        )["method_sha256"],
        _build(records, config=_config(ref_lat=None, ref_lon=None))["method_sha256"],
        _build(records, config=_config(ref_lat=LAT + 0.01))["method_sha256"],
    ]
    assert all(value != baseline for value in variants)
    assert len(set(variants)) == len(variants)


def test_exact_safe_source_and_input_lineage_survive_without_paths() -> None:
    segments = [_segment("main", LON)]
    artifact = _build([_record(index) for index in range(1, 6)], segments)
    encoded = canonical_fars_context_bytes(artifact).decode()

    assert artifact["source_lineage"] == dict(sorted(_source_lineage(5).items()))
    assert artifact["input_lineage"] == dict(sorted(_input_lineage(segments).items()))
    assert "private/path" not in encoded
    assert "streets.json" not in encoded


def test_canonical_network_digest_and_counts_are_bound_to_actual_segments() -> None:
    segments = [_segment("main", LON)]
    lineage = _input_lineage(segments)
    changed = copy.deepcopy(lineage)
    changed["network_canonical_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="canonical network digest"):
        _build([], segments, input_lineage=changed)
    changed = copy.deepcopy(lineage)
    changed["network_coordinate_count"] = 3
    with pytest.raises(ValueError, match="coordinate count"):
        _build([], segments, input_lineage=changed)


def test_suppression_persists_only_global_positive_counts_and_no_residual_key() -> None:
    retained = [_record(index, lon=LON) for index in range(1, 6)]
    secret_lon = LON + 0.01
    suppressed = [_record(index, lon=secret_lon) for index in range(6, 10)]
    artifact = _build(
        [*retained, *suppressed],
        [_segment("retained", LON), _segment("secret-suppressed-key", secret_lon)],
    )
    encoded = canonical_fars_context_bytes(artifact).decode()
    accounting = artifact["accounting"]

    assert {cell["segment_id"] for cell in artifact["cells"]} == {"retained"}
    assert "secret-suppressed-key" not in encoded
    assert accounting["positive_candidate_cell_count"] == 2
    assert accounting["eligible_cell_count"] == 1
    assert accounting["suppressed_positive_cell_count"] == 1
    assert accounting["crash_contribution_total"] == 9
    assert accounting["eligible_crash_contribution_total"] == 5
    assert accounting["suppressed_crash_contribution_total"] == 4
    assert "suppressed_cells" not in artifact
    assert "marginals" not in artifact
    assert "overall" not in encoded


def test_residual_safety_with_multiple_modes_and_differently_suppressed_cells() -> None:
    records = [
        *[_record(index, modes=["pedestrian", "pedalcyclist"]) for index in range(1, 5)],
        _record(5, modes=["pedestrian"]),
    ]
    artifact = _build(records)
    assert artifact["cells"] == [
        {
            "segment_id": "main",
            "part_of_day": "midday",
            "involved_mode": "pedestrian",
            "crash_count": 5,
        }
    ]
    assert all(cell["involved_mode"] != "pedalcyclist" for cell in artifact["cells"])
    assert artifact["accounting"]["suppressed_positive_cell_count"] == 1
    assert artifact["accounting"]["suppressed_crash_contribution_total"] == 4
    assert "overall" not in canonical_fars_context_bytes(artifact).decode()


def test_configured_floor_can_only_raise_hard_minimum() -> None:
    records = [_record(index) for index in range(1, 7)]
    floor_two = _build(records, config=_config(min_publish_n=2))
    floor_seven = _build(records, config=_config(min_publish_n=7))

    assert floor_two["method"]["privacy"]["effective_k"] == 5
    assert len(floor_two["cells"]) == 1
    assert floor_seven["cells"] == []
    assert floor_seven["accounting"]["suppressed_positive_cell_count"] == 1


def test_only_unique_snaps_contribute_and_snap_accounting_closes() -> None:
    west = _segment("west", LON - 0.0001)
    east = _segment("east", LON + 0.0001)
    artifact = _build(
        [_record(index) for index in range(1, 6)], [west, east], ambiguity_margin_m=1.0
    )
    accounting = artifact["accounting"]

    assert artifact["cells"] == []
    assert accounting["ambiguous_crashes"] == 5
    assert accounting["records_in_window"] == (
        accounting["uniquely_snapped_crashes"]
        + accounting["ambiguous_crashes"]
        + accounting["unsnapped_crashes"]
    )


def test_unique_time_accounting_and_contribution_equations_close() -> None:
    records = [
        *[_record(index, occurred_time=None) for index in range(1, 3)],
        *[_record(index, occurred_time="12:00") for index in range(3, 6)],
    ]
    artifact = _build(records)
    accounting = artifact["accounting"]

    assert accounting["uniquely_snapped_crashes"] == 5
    assert accounting["uniquely_snapped_unknown_time_crashes"] == 2
    assert accounting["uniquely_snapped_timed_crashes"] == 3
    assert accounting["crash_contribution_total"] == (
        accounting["eligible_crash_contribution_total"]
        + accounting["suppressed_crash_contribution_total"]
    )


def test_artifact_is_order_independent_and_canonical() -> None:
    records = [_record(index) for index in range(1, 7)]
    segments = [_segment("far", LON + 0.01), _segment("main", LON)]
    first = _build(records, segments)
    second = _build(list(reversed(records)), list(reversed(segments)))

    assert first == second
    assert canonical_fars_context_bytes(first) == canonical_fars_context_bytes(second)
    assert canonical_fars_context_bytes(first).endswith(b"\n")


def test_no_record_level_coordinates_ids_clock_values_or_snap_distances_survive() -> None:
    records = [
        _record(index, lon=LON + 0.0001, occurred_on="2024-08-19", occurred_time="17:42")
        for index in range(101, 106)
    ]
    artifact = _build(records)
    encoded = canonical_fars_context_bytes(artifact).decode()

    for forbidden in ("2024:101", "2024-08-19", "17:42", str(LON + 0.0001)):
        assert forbidden not in encoded
    assert artifact["method"]["snap"]["reference_lat"] == LAT
    assert artifact["method"]["snap"]["reference_lon"] == LON
    forbidden_keys = {
        "id",
        "case_id",
        "source_record_id",
        "occurred_on",
        "occurred_time_local",
        "lat",
        "lon",
        "distance_m",
        "nearest_distance_m",
        "runner_up_distance_m",
    }

    def nested_keys(value: object) -> set[str]:
        if isinstance(value, dict):
            return set(value) | {key for child in value.values() for key in nested_keys(child)}
        if isinstance(value, list):
            return {key for child in value for key in nested_keys(child)}
        return set()

    assert nested_keys(artifact).isdisjoint(forbidden_keys)


def test_caveat_and_limitation_codes_cover_every_prohibited_inference() -> None:
    artifact = _build([])
    caveat = artifact["caveat"]
    for phrase in (
        "co-location context only",
        "not record linkage",
        "outcome validation",
        "causal",
        "nonfatal risk",
        "location ranking",
        "intervention effect",
        "exposure-normalized risk",
        "non-additive",
        "bias coverage",
    ):
        assert phrase in caveat
    assert artifact["method"]["limitation_codes"] == list(LIMITATION_CODES)


@pytest.mark.parametrize(
    "config",
    [
        _config(window_start=None, window_end=None),
        _config(window_start=None, window_end="2024-12-31"),
        _config(window_start="2024-01-01", window_end=None),
        _config(window_start="2023-01-01", window_end="2023-12-31"),
        _config(window_start="2023-12-31", window_end="2024-12-31"),
        _config(window_start="2024-01-01", window_end="2025-01-01"),
        _config(window_start="2024-12-31", window_end="2024-01-01"),
    ],
)
def test_one_sided_nonoverlapping_and_reversed_windows_fail(config: Config) -> None:
    with pytest.raises(ValueError, match="window"):
        _build([], config=config)


def test_source_and_input_lineage_are_closed_and_bounded() -> None:
    source = _source_lineage(0)
    source["path"] = "/private"
    with pytest.raises(ValueError, match="source lineage"):
        _build([], source_lineage=source)
    source = _source_lineage(0)
    source["raw_sha256"] = "bad"
    with pytest.raises(ValueError, match="raw_sha256"):
        _build([], source_lineage=source)
    network = [_segment("main", LON)]
    inputs = _input_lineage(network)
    inputs["network_raw_byte_count"] = 2**40
    with pytest.raises(ValueError, match="network_raw_byte_count"):
        _build([], network, input_lineage=inputs)


@pytest.mark.parametrize(
    ("field", "message"),
    [
        ("crash_records_read", "crash source accounting"),
        ("person_records_read", "person source accounting"),
        ("cases_excluded", "joined-case source accounting"),
    ],
)
def test_safe_verified_source_counts_are_closed_and_equation_checked(
    field: str, message: str
) -> None:
    source = _source_lineage(0)
    source[field] = cast(int, source[field]) + 1
    with pytest.raises(ValueError, match=message):
        _build([], source_lineage=source)


def test_source_cases_joined_must_equal_the_verified_record_snapshot() -> None:
    records = [_record(index) for index in range(1, 6)]
    with pytest.raises(ValueError, match="cases_joined does not match verified records"):
        _build(records, source_lineage=_source_lineage(4))


def test_duplicate_nonfinite_and_malformed_inputs_fail_closed() -> None:
    with pytest.raises(ValueError, match="duplicate source"):
        _build([_record(1), _record(1)])
    with pytest.raises(ValueError, match="duplicate segment"):
        _build([], [_segment("same", LON), _segment("same", LON + 0.01)])
    malformed = _record(1)
    location = malformed["outcome"]["location"]  # type: ignore[index]
    location["lat"] = math.nan
    with pytest.raises(ValueError, match="WGS84"):
        _build([malformed])
    with pytest.raises(ValueError, match="occurred_time_local"):
        _build([_record(1, occurred_time="24:00")])
    with pytest.raises(ValueError, match="unsupported mode"):
        _build([_record(1, modes=["hoverboard"])])


def test_closed_serializer_rejects_extra_fields_below_k_and_method_tampering() -> None:
    artifact = _build([_record(index) for index in range(1, 6)])
    with pytest.raises(ValueError, match="unexpected or missing"):
        canonical_fars_context_bytes({**artifact, "source_record_id": "2024:1"})
    below_k = copy.deepcopy(artifact)
    below_k["cells"][0]["crash_count"] = 4
    with pytest.raises(ValueError, match="below-threshold"):
        canonical_fars_context_bytes(below_k)
    tampered = copy.deepcopy(artifact)
    tampered["method"]["snap"]["max_distance_m"] = 999.0
    with pytest.raises(ValueError, match="method digest"):
        canonical_fars_context_bytes(tampered)


def test_input_and_output_max_items_caps_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(fars_context, "_MAX_RECORDS", 1)
    with pytest.raises(ValueError, match="maxItems"):
        _build(
            [_record(1), _record(2)],
            config=_config(min_publish_n=1),
            source_lineage=_source_lineage(1),
        )

    monkeypatch.setattr(fars_context, "_MAX_SEGMENTS", 1)
    with pytest.raises(ValueError, match="maxItems"):
        _build(
            [],
            [_segment("one", LON), _segment("two", LON + 0.01)],
            config=_config(min_publish_n=1),
        )

    monkeypatch.setattr(fars_context, "_MAX_COORDINATES", 1)
    with pytest.raises(ValueError, match="coordinate maxItems"):
        canonical_parsed_network_sha256([_segment("one", LON)])


@pytest.mark.parametrize(
    ("fars_snap_max_m", "ambiguity_margin"),
    [
        (0.0, 5.0),
        (math.nan, 5.0),
        (25.0, math.nan),
        (25.0, -1.0),
    ],
)
def test_nonfinite_and_out_of_range_snap_thresholds_fail(
    fars_snap_max_m: float, ambiguity_margin: float
) -> None:
    with pytest.raises(ValueError, match="must be finite"):
        _build(
            [],
            fars_snap_max_m=fars_snap_max_m,
            ambiguity_margin_m=ambiguity_margin,
        )


def test_general_report_snap_config_never_controls_fars_snap_method() -> None:
    records = [_record(index) for index in range(1, 6)]
    first = _build(records, config=_config(snap_max_m=1.0), fars_snap_max_m=30.0)
    second = _build(records, config=_config(snap_max_m=999.0), fars_snap_max_m=30.0)
    assert first["method"]["snap"]["max_distance_m"] == 30.0
    assert second["method"]["snap"]["max_distance_m"] == 30.0


def test_public_builder_derives_same_artifact_and_lineage_from_same_exact_bytes() -> None:
    snapshot = _proof_snapshot()
    config_bytes = _exact_config_bytes()
    network_bytes = _exact_network_bytes()
    kwargs: dict[str, Any] = {
        "config_path": Path("/operator/config.toml"),
        "config_bytes": config_bytes,
        "network_bytes": network_bytes,
        "fars_snap_max_m": 50.0,
        "ambiguity_margin_m": 5.0,
    }

    first = build_verified_fars_context(snapshot, **kwargs)
    second = build_verified_fars_context(snapshot, **kwargs)

    assert canonical_fars_context_bytes(first) == canonical_fars_context_bytes(second)
    assert first["source_lineage"] == dict(sorted(snapshot.evidence.as_dict().items()))
    inputs = cast(dict[str, Any], first["input_lineage"])
    snap = cast(dict[str, Any], cast(dict[str, Any], first["method"])["snap"])
    assert inputs["config_raw_sha256"] == hashlib.sha256(config_bytes).hexdigest()
    assert inputs["network_raw_sha256"] == hashlib.sha256(network_bytes).hexdigest()
    assert snap["max_distance_m"] == 50.0
    assert snap["max_distance_m"] != 999.0


def test_public_builder_rejects_nonproof_and_unrelated_snapshot_bytes() -> None:
    with pytest.raises(TypeError, match="proof-bound"):
        build_verified_fars_context(
            cast(Any, object()),
            config_path=Path("config.toml"),
            config_bytes=_exact_config_bytes(),
            network_bytes=_exact_network_bytes(),
            fars_snap_max_m=50.0,
            ambiguity_margin_m=5.0,
        )

    snapshot = _proof_snapshot()
    forged = object.__new__(_VerifiedJoinedSnapshot)
    object.__setattr__(forged, "evidence", snapshot.evidence)
    object.__setattr__(forged, "normalized_bytes", b"{}\n")
    with pytest.raises(ValueError, match="digest does not match"):
        build_verified_fars_context(
            forged,
            config_path=Path("config.toml"),
            config_bytes=_exact_config_bytes(),
            network_bytes=_exact_network_bytes(),
            fars_snap_max_m=50.0,
            ambiguity_margin_m=5.0,
        )


def test_public_builder_strictly_rejects_noncanonical_proof_bound_joined_bytes() -> None:
    with pytest.raises(ValueError, match="not canonical"):
        build_verified_fars_context(
            _proof_snapshot(noncanonical=True),
            config_path=Path("config.toml"),
            config_bytes=_exact_config_bytes(),
            network_bytes=_exact_network_bytes(),
            fars_snap_max_m=50.0,
            ambiguity_margin_m=5.0,
        )


def test_public_builder_hashes_and_parses_the_same_exact_input_bytes() -> None:
    snapshot = _proof_snapshot()
    with pytest.raises(ConfigError, match=r"config|TOML|JSON"):
        build_verified_fars_context(
            snapshot,
            config_path=Path("config.toml"),
            config_bytes=_exact_network_bytes(),
            network_bytes=_exact_network_bytes(),
            fars_snap_max_m=50.0,
            ambiguity_margin_m=5.0,
        )
    with pytest.raises(NearmissError, match=r"JSON|LineString|GeoJSON"):
        build_verified_fars_context(
            snapshot,
            config_path=Path("config.toml"),
            config_bytes=_exact_config_bytes(),
            network_bytes=_exact_config_bytes(),
            fars_snap_max_m=50.0,
            ambiguity_margin_m=5.0,
        )


def test_public_byte_caps_and_streaming_network_digest(monkeypatch: pytest.MonkeyPatch) -> None:
    snapshot = _proof_snapshot()
    monkeypatch.setattr(fars_context, "_MAX_CONFIG_BYTES", 1)
    with pytest.raises(ValueError, match="config bytes"):
        build_verified_fars_context(
            snapshot,
            config_path=Path("config.toml"),
            config_bytes=_exact_config_bytes(),
            network_bytes=_exact_network_bytes(),
            fars_snap_max_m=50.0,
            ambiguity_margin_m=5.0,
        )

    monkeypatch.setattr(fars_context, "_MAX_CONFIG_BYTES", 1024 * 1024)
    monkeypatch.setattr(fars_context, "_MAX_NETWORK_BYTES", 1)
    with pytest.raises(ValueError, match="network bytes"):
        build_verified_fars_context(
            snapshot,
            config_path=Path("config.toml"),
            config_bytes=_exact_config_bytes(),
            network_bytes=_exact_network_bytes(),
            fars_snap_max_m=50.0,
            ambiguity_margin_m=5.0,
        )

    segments = [_segment("one", LON), _segment("two", LON + 0.01)]
    expected_network = {
        "segments": [
            {
                "id": segment.id,
                "name": segment.name,
                "coords": [[float(lat), float(lon)] for lat, lon in segment.coords],
            }
            for segment in segments
        ]
    }
    expected_digest = hashlib.sha256(
        json.dumps(expected_network, separators=(",", ":"), sort_keys=True).encode()
    ).hexdigest()
    assert canonical_parsed_network_sha256(segments) == expected_digest
    original = fars_context._canonical_compact
    seen: list[type[object]] = []

    def scalar_only(value: object) -> bytes:
        assert not isinstance(value, (dict, list, tuple))
        seen.append(type(value))
        return original(value)

    monkeypatch.setattr(fars_context, "_canonical_compact", scalar_only)
    assert len(canonical_parsed_network_sha256(segments)) == 64
    assert seen


@pytest.mark.parametrize(
    ("constant", "changed_value"),
    [
        ("_DENSIFY_STEP_M", 100.0),
        ("DECISION_TOLERANCE_M", 0.000002),
        ("_MAX_PROJECTED_EDGE_M", 50_000.0),
    ],
)
def test_point_snap_constant_drift_changes_descriptor_and_context_method_hash(
    monkeypatch: pytest.MonkeyPatch, constant: str, changed_value: float
) -> None:
    records = [_record(index) for index in range(1, 6)]
    descriptor = point_snap_method_descriptor()
    method_hash = _build(records)["method_sha256"]

    monkeypatch.setattr(point_snap, constant, changed_value)
    assert point_snap_method_descriptor() != descriptor
    assert _build(records)["method_sha256"] != method_hash


@pytest.mark.parametrize(
    "segment",
    [
        Segment("bad-\ud800-id", "safe", ((LAT, LON), (LAT + 0.001, LON))),
        Segment("safe", "bad-\udfff-name", ((LAT, LON), (LAT + 0.001, LON))),
    ],
)
def test_parsed_network_rejects_lone_surrogates_in_segment_text(segment: Segment) -> None:
    with pytest.raises(ValueError, match="Unicode scalar") as error:
        canonical_parsed_network_sha256([segment])
    assert not isinstance(error.value, UnicodeEncodeError)


def test_city_key_rejects_lone_surrogate_before_method_or_artifact_hashing() -> None:
    with pytest.raises(ValueError, match="Unicode scalar") as error:
        _build([], config=_config(city="bad-city-\ud800"))
    assert not isinstance(error.value, UnicodeEncodeError)


def test_closed_artifact_rejects_lone_surrogate_text_without_encoding_leak() -> None:
    artifact = _build([_record(index) for index in range(1, 6)])
    bad_city = {**artifact, "city_key": "bad-\ud800"}
    with pytest.raises(ValueError, match="Unicode scalar") as error:
        canonical_fars_context_bytes(bad_city)
    assert not isinstance(error.value, UnicodeEncodeError)

    bad_method = copy.deepcopy(artifact)
    bad_method["method"]["mode"]["unknown_policy"] = "bad-\udfff"
    with pytest.raises(ValueError, match="Unicode scalar") as error:
        canonical_fars_context_bytes(bad_method)
    assert not isinstance(error.value, UnicodeEncodeError)


def test_canonical_helper_translates_residual_unicode_encode_error() -> None:
    with pytest.raises(ValueError, match="Unicode scalar") as error:
        fars_context._canonical_compact({"unexpected": "\ud800"})
    assert not isinstance(error.value, UnicodeEncodeError)


@pytest.mark.parametrize(
    ("field", "message"),
    [
        ("records_outside_window", "window accounting"),
        ("ambiguous_crashes", "snap accounting"),
        ("uniquely_snapped_unknown_time_crashes", "time accounting"),
        ("suppressed_positive_cell_count", "positive-cell accounting"),
        ("suppressed_crash_contribution_total", "contribution accounting"),
    ],
)
def test_closed_serializer_enforces_every_accounting_equation(field: str, message: str) -> None:
    artifact = _build([_record(index) for index in range(1, 6)])
    changed = copy.deepcopy(artifact)
    changed["accounting"][field] += 1
    with pytest.raises(ValueError, match=message):
        canonical_fars_context_bytes(changed)
