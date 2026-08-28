"""Reporting-bias characterization and its privacy-safe metadata view (R48).

``characterize_bias`` compares each segment's share of reports to its share of
exposure; ``to_metadata`` turns that into the JSON block the published metadata
(and the web UI) carry — filtered to publishable segments, rounded, and free of
any forbidden key or raw coordinate.
"""

from __future__ import annotations

import json

from nearmiss.models import Exposure
from nearmiss.publish import _FORBIDDEN_KEYS
from nearmiss.stats.bias import characterize_bias, to_metadata


def _exp(segment_id: str, estimate: float) -> Exposure:
    return Exposure(segment_id=segment_id, estimate=estimate, source="test", date="2026-01-01")


def test_over_and_under_representation_split() -> None:
    # seg-a: many reports, little exposure -> over; seg-c: few reports, lots of
    # exposure -> under.
    seg_counts = {"seg-a": 80, "seg-b": 15, "seg-c": 5}
    exposure = {
        "seg-a": _exp("seg-a", 10.0),
        "seg-b": _exp("seg-b", 30.0),
        "seg-c": _exp("seg-c", 60.0),
    }
    report = characterize_bias(seg_counts, exposure)
    over_ids = {f.segment_id for f in report.over_represented()}
    under_ids = {f.segment_id for f in report.under_represented()}
    assert "seg-a" in over_ids
    assert "seg-c" in under_ids


def test_to_metadata_filters_to_publishable_and_rounds() -> None:
    seg_counts = {"seg-a": 80, "seg-b": 15, "seg-c": 5}
    exposure = {
        "seg-a": _exp("seg-a", 10.0),
        "seg-b": _exp("seg-b", 30.0),
        "seg-c": _exp("seg-c", 60.0),
    }
    report = characterize_bias(seg_counts, exposure)

    # Withhold seg-a (as if below the k-anonymity floor): it must not appear.
    publishable = {"seg-b", "seg-c"}
    md = to_metadata(report, publishable)

    assert md["caveat"] == report.note
    over = md["over_represented"]
    under = md["under_represented"]
    assert isinstance(over, list) and isinstance(under, list)
    entries = [*over, *under]
    ids = {e["segment_id"] for e in entries}
    assert ids.issubset(publishable)
    assert "seg-a" not in ids

    for entry in entries:
        assert set(entry) == {"segment_id", "report_share", "exposure_share"}
        for key in ("report_share", "exposure_share"):
            assert round(entry[key], 4) == entry[key]


def test_to_metadata_leaks_no_forbidden_key() -> None:
    seg_counts = {"seg-a": 40, "seg-b": 10}
    exposure = {"seg-a": _exp("seg-a", 5.0), "seg-b": _exp("seg-b", 50.0)}
    report = characterize_bias(seg_counts, exposure)
    text = json.dumps(to_metadata(report, {"seg-a", "seg-b"}))
    for key in _FORBIDDEN_KEYS:
        assert f'"{key}"' not in text, f"bias metadata leaked forbidden key {key}"


def test_top_findings_are_chosen_after_the_k_anonymity_filter() -> None:
    """The published bias audit is the top of the *publishable* ranking.

    `schema/dataset.schema.md` §2 describes the sidecar's `bias` block as "the
    reporting-bias audit over publishable segment ids". Selecting the top three
    findings first and filtering for k-anonymity afterwards publishes fewer than
    three, silently: a withheld segment spends a slot and nothing backfills it.
    Withheld segments are also disproportionately likely to hold a slot, because
    a handful of reports is what both withholds a segment and produces an extreme
    share ratio (issue #200).
    """
    # seg-w is the most over-represented segment and is withheld for k-anonymity.
    seg_counts = {"seg-w": 40, "seg-a": 25, "seg-b": 15, "seg-c": 12, "seg-d": 8}
    exposure = {
        "seg-w": _exp("seg-w", 10.0),
        "seg-a": _exp("seg-a", 20.0),
        "seg-b": _exp("seg-b", 30.0),
        "seg-c": _exp("seg-c", 40.0),
        "seg-d": _exp("seg-d", 400.0),
    }
    report = characterize_bias(seg_counts, exposure)
    publishable = {"seg-a", "seg-b", "seg-c", "seg-d"}
    md = to_metadata(report, publishable)

    over = md["over_represented"]
    assert isinstance(over, list)
    # seg-a, seg-b and seg-c are all over-represented and all publishable, so all
    # three slots are filled from the publishable ranking rather than one being
    # spent on the withheld seg-w.
    assert [e["segment_id"] for e in over] == ["seg-a", "seg-b", "seg-c"]
