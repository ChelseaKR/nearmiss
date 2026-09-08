"""The count-collection plan: a work list, never a measurement.

`nearmiss coverage --plan-counts` is the honest answer to a city that has reports
and no denominator. These tests hold it to four things:

* it names the segments to count, in a deterministic priority order;
* it states an hours target only when an input justifies one, and says
  "unknown" otherwise rather than inventing a number a group would plan around;
* an empty plan is never ambiguous — "nothing needs counting", "nothing snapped"
  and "there are no reports" are three different statuses;
* the count sheet it emits loads straight back through
  ``tools/build_exposure.py`` and produces exposure for exactly those segments.
"""

from __future__ import annotations

import csv
import importlib.util
import io
import json
import math
from collections.abc import Mapping
from pathlib import Path
from types import ModuleType

import pytest

from nearmiss.config import Config, load_config
from nearmiss.count_plan import (
    COUNT_SHEET_COLUMNS,
    build_count_plan,
    midpoint_on_polyline,
    minimum_detectable_rate_ratio,
    observations_required,
    render_count_plan_json,
    render_count_plan_markdown,
    render_count_sheet_csv,
    z_for_two_sided_alpha_and_power,
)
from nearmiss.errors import ConfigError
from nearmiss.loaders import load_exposure, load_streets

ROOT = Path(__file__).resolve().parents[1]
DAVIS = ROOT / "tests" / "fixtures" / "davis"


def _load_build_exposure() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "build_exposure_for_count_plan", ROOT / "tools" / "build_exposure.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_config(
    tmp_path: Path,
    *,
    exposure: Mapping[str, object],
    reports: Mapping[str, object] | None = None,
) -> Config:
    """A Davis-shaped city whose exposure layer (and optionally reports) we control."""
    exposure_path = tmp_path / "exposure.json"
    exposure_path.write_text(json.dumps(exposure), encoding="utf-8")
    reports_path = DAVIS / "reports.json"
    if reports is not None:
        reports_path = tmp_path / "reports.json"
        reports_path.write_text(json.dumps(reports), encoding="utf-8")
    config_path = tmp_path / "city.toml"
    config_path.write_text(
        "\n".join(
            [
                'city = "Davis"',
                f'streets = "{DAVIS / "streets.geojson"}"',
                f'reports = "{reports_path}"',
                f'exposure = "{exposure_path}"',
                f'raw_dir = "{tmp_path / "raw"}"',
                f'out_dir = "{tmp_path / "out"}"',
                f'submissions_dir = "{tmp_path / "pending"}"',
                "ref_lat = 38.5449",
                "ref_lon = -121.7405",
                "[window]",
                'start = "2026-01-01"',
                'end = "2026-12-31"',
                "[thresholds]",
                "snap_max_m = 25",
                "min_publish_n = 3",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return load_config(config_path)


@pytest.fixture(scope="module")
def no_exposure_config(tmp_path_factory: pytest.TempPathFactory) -> Config:
    """Davis's real reports and streets with the denominator layer removed."""
    return _write_config(tmp_path_factory.mktemp("no-exposure"), exposure={"segments": []})


# --------------------------------------------------------------------------- #
# The formulas
# --------------------------------------------------------------------------- #


def test_observations_required_is_the_hand_computed_value() -> None:
    # N >= y / f**2. Six reports at f = 0.5 needs 6 / 0.25 = 24 observations.
    assert observations_required(6, 0.5) == 24
    # Rounds up rather than down: 5 / 0.25 = 20 exactly, 7 / 0.09 = 77.7...
    assert observations_required(5, 0.5) == 20
    assert observations_required(7, 0.3) == 78
    # Never zero: one report at a permissive share still asks for one observation.
    assert observations_required(1, 1.0) == 1


def test_minimum_detectable_rate_ratio_is_the_hand_computed_value() -> None:
    z_total = z_for_two_sided_alpha_and_power(0.05, 0.8)
    # z_{0.975} + z_{0.8} = 1.959963985 + 0.841621234 = 2.801585218
    assert z_total == pytest.approx(2.801585218, abs=1e-9)
    # exp(2.801585218 * sqrt(1/6 + 1/24)) = exp(2.801585218 * 0.4564354646)
    expected = math.exp(2.801585218 * math.sqrt(1.0 / 6.0 + 1.0 / 24.0))
    assert expected == pytest.approx(3.5924, abs=5e-4)
    assert minimum_detectable_rate_ratio(6, 24, z_total) == pytest.approx(expected, rel=1e-9)


def test_more_counting_shrinks_the_detectable_ratio_but_never_below_the_report_floor() -> None:
    z_total = z_for_two_sided_alpha_and_power(0.05, 0.8)
    ratios = [minimum_detectable_rate_ratio(6, n, z_total) for n in (24, 240, 2400, 24000)]
    assert ratios == sorted(ratios, reverse=True)
    floor = math.exp(z_total * math.sqrt(1.0 / 6.0))
    assert ratios[-1] > floor  # counting forever cannot beat six reports
    assert ratios[-1] == pytest.approx(floor, rel=2e-3)


@pytest.mark.parametrize(
    ("alpha", "power"),
    [(0.0, 0.8), (1.0, 0.8), (0.05, 0.0), (0.05, 1.0), (-0.1, 0.8)],
)
def test_the_test_level_and_power_must_be_probabilities(alpha: float, power: float) -> None:
    with pytest.raises(ConfigError):
        z_for_two_sided_alpha_and_power(alpha, power)


def test_a_target_needs_a_report_and_a_positive_observation_count() -> None:
    with pytest.raises(ConfigError):
        observations_required(0, 0.5)
    with pytest.raises(ConfigError):
        observations_required(3, 0.0)
    with pytest.raises(ConfigError):
        minimum_detectable_rate_ratio(0, 24, 2.8)
    with pytest.raises(ConfigError):
        minimum_detectable_rate_ratio(6, 0, 2.8)


# --------------------------------------------------------------------------- #
# Where a volunteer stands
# --------------------------------------------------------------------------- #


def test_the_count_point_lies_on_a_bent_polyline_where_the_centroid_would_not() -> None:
    """An L-shaped street: the length-weighted centroid is off the pavement."""
    from nearmiss.geometry import point_to_polyline_m, polyline_centroid

    coords = ((38.540, -121.740), (38.540, -121.730), (38.550, -121.730))
    lat, lon = midpoint_on_polyline(coords)
    assert point_to_polyline_m(lat, lon, coords, 38.545, -121.735) < 1e-6
    c_lat, c_lon = polyline_centroid(coords)
    assert point_to_polyline_m(c_lat, c_lon, coords, 38.545, -121.735) > 100.0


def test_the_count_point_of_a_degenerate_segment_is_its_only_vertex() -> None:
    assert midpoint_on_polyline(((38.5, -121.7),)) == (38.5, -121.7)
    assert midpoint_on_polyline(((38.5, -121.7), (38.5, -121.7))) == (38.5, -121.7)
    with pytest.raises(ConfigError):
        midpoint_on_polyline(())


# --------------------------------------------------------------------------- #
# The plan
# --------------------------------------------------------------------------- #


def test_a_city_with_reports_and_no_denominator_gets_a_priority_ordered_plan(
    no_exposure_config: Config,
) -> None:
    plan = build_count_plan(no_exposure_config)
    assert plan.status == "counts_needed"
    assert plan.exposure_layer == "absent"
    assert plan.segments_with_usable_exposure == 0
    assert plan.targets, "Davis's fixture reports snap to segments; some must be listed"
    assert plan.segments_needing_counts == len(plan.targets)
    assert plan.reports_on_targets == sum(t.report_count for t in plan.targets)

    ranks = [t.priority_rank for t in plan.targets]
    assert ranks == list(range(1, len(plan.targets) + 1))
    keys = [(-t.report_count, -t.network_degree, t.segment_id) for t in plan.targets]
    assert keys == sorted(keys), "priority is report count, then degree, then id"
    assert all(t.report_count > 0 for t in plan.targets)


def test_the_plan_is_deterministic_across_two_builds(no_exposure_config: Config) -> None:
    first = render_count_plan_json(build_count_plan(no_exposure_config))
    again = render_count_plan_json(build_count_plan(no_exposure_config))
    assert first == again
    assert json.loads(first)["schema_version"]


def test_without_an_assumed_flow_the_hours_are_unknown_not_estimated(
    no_exposure_config: Config,
) -> None:
    plan = build_count_plan(no_exposure_config)
    assert all(t.observation_hours_target is None for t in plan.targets)
    assert all(t.minimum_detectable_rate_ratio is None for t in plan.targets)
    assert all(t.observations_required >= 1 for t in plan.targets)
    assert any("no assumed flow" in caveat.lower() for caveat in plan.caveats)
    assert "unknown" in render_count_plan_markdown(plan)


def test_with_an_assumed_flow_the_hours_and_ratio_are_computed_and_reproducible(
    no_exposure_config: Config,
) -> None:
    plan = build_count_plan(no_exposure_config, assumed_flow_per_hour=12.0)
    # Restated from the formulas rather than computed by the functions under test: a
    # fixture derived from the code it checks moves with any change to it and can
    # never catch a wrong one. 0.25 is the default denominator share squared, and
    # 2.801585218 is z_{0.975} + z_{0.8}, pinned by value in the two tests above.
    for target in plan.targets:
        required = math.ceil(target.report_count / 0.25)
        hours = float(math.ceil(required / 12.0))
        assert target.observations_required == required
        assert target.observation_hours_target == hours
        assert target.observations_at_target_hours == pytest.approx(hours * 12.0)
        expected_ratio = math.exp(
            2.801585218 * math.sqrt(1.0 / target.report_count + 1.0 / (hours * 12.0))
        )
        assert target.minimum_detectable_rate_ratio == pytest.approx(
            round(expected_ratio, 3), abs=5e-4
        )
        # Nothing to expand onto, so the factor stays absent rather than 1.0.
        assert target.exposure_expansion_factor is None
    assert any("session basis" in caveat for caveat in plan.caveats)


def test_the_expansion_factor_is_per_segment_and_only_appears_when_a_period_is_given(
    no_exposure_config: Config,
) -> None:
    plan = build_count_plan(
        no_exposure_config, assumed_flow_per_hour=6.0, expansion_period_hours=168.0
    )
    factors = {t.segment_id: t.exposure_expansion_factor for t in plan.targets}
    assert all(value is not None for value in factors.values())
    for target in plan.targets:
        assert target.observation_hours_target is not None
        assert target.exposure_expansion_factor == pytest.approx(
            round(168.0 / target.observation_hours_target, 4)
        )
    # Unequal sessions are the whole reason the factor is a row-level field.
    hours = {t.observation_hours_target for t in plan.targets}
    if len(hours) > 1:
        assert len(set(factors.values())) > 1


def test_a_fully_covered_city_yields_an_empty_plan_that_says_nothing_to_collect(
    tmp_path: Path,
) -> None:
    segments = load_streets(DAVIS / "streets.geojson")
    config = _write_config(
        tmp_path,
        exposure={
            "segments": [
                {
                    "segment_id": segment.id,
                    "estimate": 500.0,
                    "source": "synthetic_full_coverage",
                    "date": "2026-05-01",
                    "tier": "observed",
                }
                for segment in segments
            ]
        },
    )
    plan = build_count_plan(config)
    assert plan.status == "no_counts_needed"
    assert plan.exposure_layer == "complete"
    assert plan.targets == ()
    assert plan.segments_without_exposure_and_without_reports == 0
    assert "Nothing to collect" in render_count_plan_markdown(plan)
    assert render_count_sheet_csv(plan).strip() == ",".join(COUNT_SHEET_COLUMNS)


def test_a_city_with_no_reports_is_not_the_same_status_as_a_covered_one(tmp_path: Path) -> None:
    config = _write_config(tmp_path, exposure={"segments": []}, reports={"reports": []})
    plan = build_count_plan(config)
    assert plan.status == "no_reports"
    assert plan.targets == ()
    # The distinction the artifact exists to keep: empty-because-done reads differently
    # from empty-because-nothing-was-there, in the status and in the prose.
    assert "no reports" in render_count_plan_markdown(plan)
    assert "Nothing to collect" in render_count_plan_markdown(plan)


def test_reports_that_reach_no_segment_are_their_own_status(tmp_path: Path) -> None:
    """Every report far out of town: reports exist, nothing snaps, nothing to count."""
    reports = {
        "reports": [
            {
                "schema_version": "1.0.0",
                "id": f"00000000-0000-4000-8000-00000000{index:04d}",
                "occurred_at": f"2026-06-10T0{index}:20:00-07:00",
                "location": {"lat": 10.0 + index / 1000.0, "lon": 10.0},
                "mode": "cyclist",
                "hazard_type": "close_pass",
                "severity": "near_miss",
            }
            for index in range(1, 4)
        ]
    }
    config = _write_config(tmp_path, exposure={"segments": []}, reports=reports)
    plan = build_count_plan(config)
    assert plan.status == "no_snapped_reports"
    assert plan.targets == ()
    assert "none of them snapped" in render_count_plan_markdown(plan)


def test_a_segment_whose_midpoint_is_shared_gets_no_coordinate_and_says_so(
    tmp_path: Path,
) -> None:
    """Two street features on the same alignment: no count point can identify either.

    Duplicated geometry is ordinary in an extract that merges two street sources.
    A midpoint that is exactly as close to the twin as to its own segment cannot
    be attributed, so the plan withholds the coordinate and names the row instead
    of sending a volunteer to a corner where the count would land on either.
    """
    streets = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[-121.744, 38.543], [-121.744, 38.5446]],
                },
                "properties": {"segment_id": segment_id, "name": f"Twinned St ({segment_id})"},
            }
            for segment_id in ("seg-a", "seg-b")
        ],
    }
    streets_path = tmp_path / "streets.geojson"
    streets_path.write_text(json.dumps(streets), encoding="utf-8")
    reports = {
        "reports": [
            {
                "schema_version": "1.0.0",
                "id": f"00000000-0000-4000-8000-0000000{index:05d}",
                "occurred_at": f"2026-06-1{index}T08:20:00-07:00",
                "location": {"lat": 38.5438 + index / 10000.0, "lon": -121.74403},
                "mode": "cyclist",
                "hazard_type": "close_pass",
                "severity": "near_miss",
            }
            for index in range(1, 5)
        ]
    }
    reports_path = tmp_path / "reports.json"
    reports_path.write_text(json.dumps(reports), encoding="utf-8")
    exposure_path = tmp_path / "exposure.json"
    exposure_path.write_text(json.dumps({"segments": []}), encoding="utf-8")
    config_path = tmp_path / "city.toml"
    config_path.write_text(
        "\n".join(
            [
                'city = "Twinsville"',
                f'streets = "{streets_path}"',
                f'reports = "{reports_path}"',
                f'exposure = "{exposure_path}"',
                f'raw_dir = "{tmp_path / "raw"}"',
                f'out_dir = "{tmp_path / "out"}"',
                f'submissions_dir = "{tmp_path / "pending"}"',
                "[window]",
                'start = "2026-01-01"',
                'end = "2026-12-31"',
                "[thresholds]",
                "snap_max_m = 25",
                "min_publish_n = 3",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    plan = build_count_plan(load_config(config_path), assumed_flow_per_hour=10.0)
    assert plan.status == "counts_needed"
    assert plan.targets
    ambiguous = [t for t in plan.targets if t.count_point == "ambiguous"]
    assert ambiguous, "a twinned alignment has no attributable midpoint"
    assert all(t.lat is None and t.lon is None for t in ambiguous)
    assert any("unambiguous count point" in caveat for caveat in plan.caveats)
    # An unusable row is left out of the sheet rather than shipped with blank coordinates,
    # which build_exposure would silently read as an unsnapped observation.
    sheet_ids = {
        row["segment_id"] for row in csv.DictReader(io.StringIO(render_count_sheet_csv(plan)))
    }
    assert sheet_ids.isdisjoint({t.segment_id for t in ambiguous})


def test_a_plan_never_states_a_rate_or_a_ranking_claim(no_exposure_config: Config) -> None:
    plan = build_count_plan(no_exposure_config, assumed_flow_per_hour=10.0)
    assert plan.artifact_kind == "collection_plan"
    assert any("not a measurement" in caveat for caveat in plan.caveats)
    markdown = render_count_plan_markdown(plan)
    assert "not of risk" in markdown
    payload = json.loads(render_count_plan_json(plan))
    for target in payload["targets"]:
        assert "rate" not in target
        assert "rate_ci_low" not in target
        assert "significant" not in target


def test_the_bad_inputs_are_refused_rather_than_defaulted(no_exposure_config: Config) -> None:
    with pytest.raises(ConfigError):
        build_count_plan(no_exposure_config, assumed_flow_per_hour=0.0)
    with pytest.raises(ConfigError):
        build_count_plan(no_exposure_config, expansion_period_hours=-1.0)


# --------------------------------------------------------------------------- #
# The round trip: a filled sheet becomes an exposure layer
# --------------------------------------------------------------------------- #


def test_a_filled_count_sheet_loads_through_build_exposure_without_edits(
    no_exposure_config: Config, tmp_path: Path
) -> None:
    plan = build_count_plan(no_exposure_config, assumed_flow_per_hour=12.0)
    sheet = render_count_sheet_csv(plan)
    rows = list(csv.DictReader(io.StringIO(sheet)))
    assert rows, "the plan has targets, so the sheet has rows"
    assert list(rows[0]) == list(COUNT_SHEET_COLUMNS)
    assert all(row["count"] == "" for row in rows), "a pre-filled denominator is the whole refusal"

    # A volunteer fills the count column and nothing else.
    for index, row in enumerate(rows):
        row["count"] = str(10 + index)
    filled = tmp_path / "counts.csv"
    with filled.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(COUNT_SHEET_COLUMNS), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

    be = _load_build_exposure()
    segments = load_streets(DAVIS / "streets.geojson")
    observations = be.read_counts(filled, "count", "lat", "lon")
    assert len(observations) == len(rows)
    estimates, unsnapped = be.assign(segments, observations, 30.0, "sum")
    assert unsnapped == 0, "every count point sits on its own segment"
    assert set(estimates) == {row["segment_id"] for row in rows}

    exposure_path = tmp_path / "exposure.json"
    exposure_path.write_text(
        json.dumps(
            be.build_exposure(segments, estimates, "volunteer_counts", "2026-09-08", False, None)
        ),
        encoding="utf-8",
    )
    loaded = load_exposure(exposure_path)
    assert set(loaded) == set(estimates)


def test_the_expansion_factor_column_puts_unequal_sessions_on_one_basis(
    no_exposure_config: Config, tmp_path: Path
) -> None:
    plan = build_count_plan(
        no_exposure_config, assumed_flow_per_hour=6.0, expansion_period_hours=168.0
    )
    rows = list(csv.DictReader(io.StringIO(render_count_sheet_csv(plan))))
    for row in rows:
        row["count"] = "10"
    filled = tmp_path / "counts.csv"
    with filled.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(COUNT_SHEET_COLUMNS), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

    be = _load_build_exposure()
    plain = be.read_counts(filled, "count", "lat", "lon")
    scaled = be.read_counts(filled, "count", "lat", "lon", "exposure_expansion_factor")
    assert len(scaled) == len(plain)
    for (_, _, raw), (_, _, expanded), row in zip(plain, scaled, rows, strict=True):
        assert expanded == pytest.approx(raw * float(row["exposure_expansion_factor"]))


def test_a_row_asking_to_be_scaled_with_no_readable_factor_is_dropped_not_scaled_by_one(
    tmp_path: Path,
) -> None:
    """The refusal that keeps a two-hour count from publishing as a whole-year one."""
    be = _load_build_exposure()
    path = tmp_path / "counts.csv"
    path.write_text(
        "lat,lon,count,exposure_expansion_factor\n"
        "38.5,-121.7,10,84\n"
        "38.6,-121.8,10,\n"
        "38.7,-121.9,10,not-a-number\n"
        "38.8,-121.95,10,0\n",
        encoding="utf-8",
    )
    assert len(be.read_counts(path, "count", "lat", "lon")) == 4
    scaled = be.read_counts(path, "count", "lat", "lon", "exposure_expansion_factor")
    assert scaled == [(38.5, -121.7, 840.0)]


# --------------------------------------------------------------------------- #
# The CLI
# --------------------------------------------------------------------------- #


def test_the_cli_writes_the_three_artifacts(
    no_exposure_config: Config, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from nearmiss.__main__ import main

    out = tmp_path / "plan"
    code = main(
        [
            "coverage",
            "--config",
            str(_config_path(no_exposure_config)),
            "--plan-counts",
            "--assumed-flow-per-hour",
            "12",
            "--out-dir",
            str(out),
        ]
    )
    assert code == 0
    assert (out / "davis-count-plan.json").is_file()
    assert (out / "davis-count-plan.md").is_file()
    assert (out / "davis-count-sheet.csv").is_file()
    payload = json.loads((out / "davis-count-plan.json").read_text(encoding="utf-8"))
    assert payload["status"] == "counts_needed"
    assert payload["assumptions"]["assumed_flow_per_hour"] == 12.0
    assert "count plan [Davis]" in capsys.readouterr().out


def _config_path(config: Config) -> Path:
    """The TOML the fixture wrote, recovered from the config's own paths."""
    return config.exposure_path.parent / "city.toml"


def test_the_cli_rejects_a_non_probability_knob(no_exposure_config: Config) -> None:
    from nearmiss.__main__ import main

    with pytest.raises(SystemExit):
        main(
            [
                "coverage",
                "--config",
                str(_config_path(no_exposure_config)),
                "--plan-counts",
                "--alpha",
                "1.5",
            ]
        )
