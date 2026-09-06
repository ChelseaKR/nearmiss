"""A group's own spreadsheet as a first-class source (#246, #186).

Two things are under test. `nearmiss crosswalk init` proposes a crosswalk from
a CSV header row without deciding anything the author did not ask it to, and
`SpreadsheetAdapter` turns that CSV into intake reports while *counting* every
row it could not turn into one.

The second half is the one worth the test file. A row whose travel mode is not
mapped, whose timestamp has no timezone, or which names no place at all is a
row this adapter refuses to invent a value for. Refusing is only honest if the
refusal is visible, so each exclusion is counted under its own reason and the
CLI prints all four counters including the zeroes.
"""

from __future__ import annotations

import copy
import json
import tomllib
from pathlib import Path
from typing import Any

import pytest

from nearmiss.__main__ import main
from nearmiss.adapters.base import load_crosswalk_file
from nearmiss.adapters.spreadsheet import (
    SKIP_REASONS,
    SpreadsheetAdapter,
    SpreadsheetCrosswalkError,
    load_field_map,
)
from nearmiss.crosswalk_init import (
    CrosswalkInitError,
    init_crosswalk,
    load_answers,
    prompt_answers,
    propose_columns,
)
from nearmiss.validation import validate_report

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "spreadsheet"
CSV = FIXTURES / "member_reports.csv"
MESSY_CSV = FIXTURES / "member_reports_messy.csv"
ANSWERS = FIXTURES / "answers.toml"
HANDWRITTEN = FIXTURES / "handwritten.toml"


def _generated(tmp_path: Path, answers: dict[str, Any] | None = None) -> Path:
    out = tmp_path / "generated.toml"
    init_crosswalk(CSV, answers if answers is not None else load_answers(ANSWERS), out)
    return out


# --- the issue's own acceptance criteria -------------------------------------


def test_a_generated_crosswalk_produces_the_same_reports_as_a_hand_written_one(
    tmp_path: Path,
) -> None:
    """#246: the CSV's columns are in a shuffled order with the group's own names."""
    generated = SpreadsheetAdapter(_generated(tmp_path)).read(CSV)
    handwritten = SpreadsheetAdapter(HANDWRITTEN).read(CSV)
    assert generated.reports == handwritten.reports
    assert generated.reports, "the fixture produced no reports; this comparison would be vacuous"


def test_a_spreadsheet_with_no_mode_column_cannot_produce_a_crosswalk(tmp_path: Path) -> None:
    no_mode = tmp_path / "no_mode.csv"
    no_mode.write_text(
        "Outcome,Longitude,When it happened,Latitude,What happened\n"
        "near miss,-121.74,2026-06-15 08:42,38.54,close pass\n",
        encoding="utf-8",
    )
    with pytest.raises(CrosswalkInitError, match="mode"):
        init_crosswalk(no_mode, load_answers(ANSWERS), tmp_path / "out.toml")
    assert not (tmp_path / "out.toml").exists()


def test_a_blank_bias_answer_is_rejected_by_the_same_loader_as_a_committed_crosswalk(
    tmp_path: Path,
) -> None:
    """The generator has no lane of its own around hard rule #3."""
    answers = copy.deepcopy(load_answers(ANSWERS))
    answers["source"]["bias_profile"]["language"] = ""
    with pytest.raises(ValueError, match="bias_profile"):
        init_crosswalk(CSV, answers, tmp_path / "out.toml")
    assert not (tmp_path / "out.toml").exists()


def test_an_n_a_bias_answer_is_rejected_too(tmp_path: Path) -> None:
    answers = copy.deepcopy(load_answers(ANSWERS))
    answers["source"]["bias_profile"]["salience"] = "n/a"
    with pytest.raises(ValueError, match="asserts nothing"):
        init_crosswalk(CSV, answers, tmp_path / "out.toml")


# --- nothing is filled in, and every exclusion is counted --------------------


def test_every_excluded_row_is_counted_under_its_own_reason(tmp_path: Path) -> None:
    result = SpreadsheetAdapter(_generated(tmp_path)).read(MESSY_CSV)
    assert result.rows_read == 4
    assert len(result.reports) == 1
    assert result.skipped == {
        "unmapped_mode": 1,
        "unparseable_time": 1,
        "naive_time_no_offset": 0,
        "no_location": 1,
    }
    assert result.skipped_total == 3
    # rows_read is carried beside the report count on purpose: a consumer that
    # sees only "1 report" cannot tell a one-row export from a four-row one
    # that lost three quarters of its rows.
    assert result.counts_by_kind()["rows_read"] == 4


def test_an_unmapped_travel_mode_costs_the_row_rather_than_defaulting(tmp_path: Path) -> None:
    result = SpreadsheetAdapter(_generated(tmp_path)).read(MESSY_CSV)
    assert result.skipped["unmapped_mode"] == 1
    assert [r["mode"] for r in result.reports] == ["cyclist"]
    # No report anywhere carries a mode the crosswalk did not map.
    assert all(r["mode"] in {"cyclist", "pedestrian", "wheelchair"} for r in result.reports)


def test_a_crosswalk_cannot_declare_a_default_mode(tmp_path: Path) -> None:
    """The escape hatch that would make the previous test vacuous is closed."""
    manifest = tmp_path / "with_default.toml"
    manifest.write_text(
        HANDWRITTEN.read_text(encoding="utf-8").replace(
            "[[mode.rules]]", '[mode]\ndefault = "cyclist"\n\n[[mode.rules]]', 1
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="must not carry a default"):
        load_crosswalk_file(manifest)


def test_a_naive_timestamp_is_excluded_when_no_offset_is_declared(tmp_path: Path) -> None:
    """An assumed hour is a fabricated hour, and time-of-day analysis reads it."""
    manifest = tmp_path / "no_offset.toml"
    manifest.write_text(
        HANDWRITTEN.read_text(encoding="utf-8").replace('timezone_offset = "-07:00"\n', ""),
        encoding="utf-8",
    )
    result = SpreadsheetAdapter(manifest).read(CSV)
    assert result.reports == []
    assert result.skipped["naive_time_no_offset"] == 3


def test_a_timestamp_that_carries_its_own_offset_keeps_it(tmp_path: Path) -> None:
    result = SpreadsheetAdapter(_generated(tmp_path)).read(MESSY_CSV)
    assert result.reports[0]["occurred_at"] == "2026-06-15T08:42:00-07:00"


def test_the_declared_offset_is_applied_to_naive_timestamps(tmp_path: Path) -> None:
    reports = SpreadsheetAdapter(_generated(tmp_path)).read(CSV).reports
    assert [r["occurred_at"] for r in reports] == [
        "2026-06-15T08:42:00-07:00",
        "2026-06-16T17:05:00-07:00",
        "2026-06-17T07:58:00-07:00",
    ]


def test_every_emitted_report_validates_against_the_intake_schema(tmp_path: Path) -> None:
    for report in SpreadsheetAdapter(_generated(tmp_path)).read(CSV).reports:
        assert validate_report(report) == []


def test_an_address_row_is_emitted_as_an_address_for_the_geocode_stage(tmp_path: Path) -> None:
    reports = SpreadsheetAdapter(_generated(tmp_path)).read(CSV).reports
    addressed = [r for r in reports if "address" in r]
    assert len(addressed) == 1
    assert addressed[0]["address"] == "B St & 3rd St Davis CA"
    assert "location" not in addressed[0]


def test_ids_are_stable_across_two_reads_of_the_same_export(tmp_path: Path) -> None:
    adapter = SpreadsheetAdapter(_generated(tmp_path))
    first = [r["id"] for r in adapter.read(CSV).reports]
    second = [r["id"] for r in adapter.read(CSV).reports]
    assert first == second
    assert len(set(first)) == len(first)


# --- inference proposes; it never decides ------------------------------------


def test_two_columns_matching_one_required_field_is_a_refusal_not_a_coin_toss(
    tmp_path: Path,
) -> None:
    ambiguous = tmp_path / "ambiguous.csv"
    ambiguous.write_text(
        "Outcome,Injury,Longitude,When it happened,Latitude,Travel mode,What happened\n"
        "near miss,none,-121.74,2026-06-15 08:42,38.54,bike,close pass\n",
        encoding="utf-8",
    )
    proposal = propose_columns(
        ["Outcome", "Injury", "Longitude", "When it happened", "Latitude", "Travel mode"]
    )
    assert set(proposal.ambiguous["severity"]) == {"Outcome", "Injury"}
    with pytest.raises(CrosswalkInitError, match="more than one column"):
        init_crosswalk(ambiguous, load_answers(ANSWERS), tmp_path / "out.toml")


def test_an_answers_field_map_breaks_the_tie(tmp_path: Path) -> None:
    ambiguous = tmp_path / "ambiguous.csv"
    ambiguous.write_text(
        "Outcome,Injury,Longitude,When it happened,Latitude,Travel mode,What happened\n"
        "near miss,none,-121.74,2026-06-15 08:42,38.54,bike,close pass\n",
        encoding="utf-8",
    )
    answers = copy.deepcopy(load_answers(ANSWERS))
    answers["field_map"]["severity"] = "Outcome"
    out = init_crosswalk(ambiguous, answers, tmp_path / "out.toml")
    assert load_field_map(out).columns["severity"] == "Outcome"


def test_a_field_map_naming_a_column_the_file_does_not_have_is_refused(tmp_path: Path) -> None:
    answers = copy.deepcopy(load_answers(ANSWERS))
    answers["field_map"]["severity"] = "Column That Is Not There"
    with pytest.raises(CrosswalkInitError, match="does not have"):
        init_crosswalk(CSV, answers, tmp_path / "out.toml")


def test_a_mode_value_the_answers_do_not_map_is_named_at_init_not_discovered_later(
    tmp_path: Path,
) -> None:
    with pytest.raises(CrosswalkInitError, match="skateboard"):
        init_crosswalk(MESSY_CSV, load_answers(ANSWERS), tmp_path / "out.toml")


def test_a_field_map_with_only_one_of_lat_lon_is_refused(tmp_path: Path) -> None:
    manifest = tmp_path / "half_coordinate.toml"
    manifest.write_text(
        HANDWRITTEN.read_text(encoding="utf-8")
        .replace('lon = "Longitude"\n', "")
        .replace('address = "Intersection"\n', ""),
        encoding="utf-8",
    )
    with pytest.raises(SpreadsheetCrosswalkError, match="one of lat/lon"):
        load_field_map(manifest)


def test_a_field_map_with_no_place_at_all_is_refused(tmp_path: Path) -> None:
    manifest = tmp_path / "no_place.toml"
    manifest.write_text(
        HANDWRITTEN.read_text(encoding="utf-8")
        .replace('lat = "Latitude"\n', "")
        .replace('lon = "Longitude"\n', "")
        .replace('address = "Intersection"\n', ""),
        encoding="utf-8",
    )
    with pytest.raises(SpreadsheetCrosswalkError, match="neither lat/lon nor address"):
        load_field_map(manifest)


# --- the generated manifest is a real manifest -------------------------------


def test_the_generated_manifest_records_the_publication_status_the_answers_gave(
    tmp_path: Path,
) -> None:
    crosswalk = load_crosswalk_file(_generated(tmp_path))
    assert crosswalk.publication_status == "research_only"
    assert "consent form" in crosswalk.publication_note


def test_the_generated_manifest_is_parseable_toml_with_the_columns_it_inferred(
    tmp_path: Path,
) -> None:
    with _generated(tmp_path).open("rb") as handle:
        data = tomllib.load(handle)
    assert data["field_map"]["mode"] == "Travel mode"
    assert data["field_map"]["occurred_at"] == "When it happened"
    assert data["field_map"]["timezone_offset"] == "-07:00"


def test_a_quote_in_an_answer_survives_the_toml_writer(tmp_path: Path) -> None:
    answers = copy.deepcopy(load_answers(ANSWERS))
    answers["source"]["bias_label"] = 'members who call it a "close call", quotes and all'
    crosswalk = load_crosswalk_file(_generated(tmp_path, answers))
    assert crosswalk.bias_label == 'members who call it a "close call", quotes and all'


# --- the interactive path asks the same questions ----------------------------


def test_the_interactive_path_produces_a_usable_answers_set(tmp_path: Path) -> None:
    source = load_answers(ANSWERS)["source"]
    replies = [
        source["id"],
        source["name"],
        source["url"],
        source["license"],
        source["publication_status"],
        source["publication_note"],
        source["bias_label"],
        *[
            source["bias_profile"][axis]
            for axis in (
                "route_choice",
                "reporter_pool",
                "app_access",
                "language",
                "demographic_skew",
                "survivorship",
                "salience",
                "temporal_campaign",
            )
        ],
        # field map: blank accepts the inferred column for every field
        *[""] * 9,
        "-07:00",
        # one reply per distinct mode value, in first-appearance order
        "cyclist",
        "pedestrian",
        "wheelchair",
        # then hazard_type's distinct values, then its default
        "close_pass",
        "surface_hazard",
        "sightline",
        "",
        # then severity's distinct values, then its default
        "",
        "minor",
        "",
    ]
    said: list[str] = []
    answers = prompt_answers(CSV, lambda _prompt: replies.pop(0), said.append)
    assert not replies, "the prompt flow asked fewer questions than expected"
    assert any("bias" in line for line in said)
    out = init_crosswalk(CSV, answers, tmp_path / "interactive.toml")
    assert (
        SpreadsheetAdapter(out).read(CSV).reports
        == SpreadsheetAdapter(HANDWRITTEN).read(CSV).reports
    )


# --- the CLI -----------------------------------------------------------------


def test_the_cli_writes_a_crosswalk_and_then_intake_ready_reports(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    manifest, reports = tmp_path / "cw.toml", tmp_path / "reports.json"
    assert (
        main(
            [
                "crosswalk",
                "init",
                "--from",
                str(CSV),
                "--answers",
                str(ANSWERS),
                "--out",
                str(manifest),
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "crosswalk",
                "import",
                "--crosswalk",
                str(manifest),
                "--from",
                str(MESSY_CSV),
                "--out",
                str(reports),
            ]
        )
        == 0
    )
    payload = json.loads(reports.read_text(encoding="utf-8"))
    assert [r["mode"] for r in payload["reports"]] == ["cyclist"]
    printed = capsys.readouterr().out
    # Every reason is printed, including the ones that are zero: a counter that
    # appears only when it fires reads as "nothing was dropped" on a run that
    # never looked.
    for reason in SKIP_REASONS:
        assert f"excluded, {reason}:" in printed
    assert "3 row(s) were excluded" in printed


def test_the_cli_refuses_and_exits_non_zero_when_a_crosswalk_cannot_be_built(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert (
        main(
            [
                "crosswalk",
                "init",
                "--from",
                str(MESSY_CSV),
                "--answers",
                str(ANSWERS),
                "--out",
                str(tmp_path / "out.toml"),
            ]
        )
        == 2
    )
    assert "refused" in capsys.readouterr().err
    assert not (tmp_path / "out.toml").exists()
