"""EXP-09 planted-truth benchmark suite: generation is deterministic and the
frozen, committed cities are exactly what the generator produces (the "known
answers are verifiable" claim in benchmarks/README.md), and the scorer
recovers sane, documented numbers.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import jsonschema
import pytest

ROOT = Path(__file__).resolve().parents[1]
BENCH = ROOT / "benchmarks"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from benchmarks import generator, scorer  # noqa: E402

CONFIG_NAMES = sorted(p.stem for p in (BENCH / "configs").glob("*.json"))
FROZEN_FILES = ("streets.geojson", "exposure.json", "reports.json", "ground_truth.json")


@pytest.mark.parametrize("name", CONFIG_NAMES)
def test_frozen_city_matches_generator(name: str) -> None:
    """Regenerating a config reproduces the committed city byte-for-byte --
    the property that makes the "known answer" claim independently checkable
    (see benchmarks/README.md and `make bench-suite-verify`)."""
    cfg = generator.RegimeConfig.from_json(BENCH / "configs" / f"{name}.json")
    streets, exposure, reports, ground_truth = generator.generate(cfg)
    generated = {
        "streets.geojson": json.dumps(streets, ensure_ascii=False, indent=2) + "\n",
        "exposure.json": json.dumps(exposure, ensure_ascii=False, indent=2) + "\n",
        "reports.json": json.dumps(reports, ensure_ascii=False, indent=2) + "\n",
        "ground_truth.json": json.dumps(ground_truth, ensure_ascii=False, indent=2) + "\n",
    }
    city_dir = BENCH / "cities" / name
    for filename in FROZEN_FILES:
        committed = (city_dir / filename).read_text(encoding="utf-8")
        assert generated[filename] == committed, f"{name}/{filename} drifted from its config"


def test_generation_is_deterministic() -> None:
    cfg = generator.RegimeConfig.from_json(BENCH / "configs" / "baseline.json")
    first = generator.generate(cfg)
    second = generator.generate(cfg)
    assert first == second


def test_maup_pair_shares_identical_report_locations() -> None:
    """maup_fine and maup_coarse must observe the SAME incidents -- only the
    published segment boundaries differ -- or the MAUP comparison is not
    apples-to-apples."""
    fine = (BENCH / "cities" / "maup_fine" / "reports.json").read_text(encoding="utf-8")
    coarse = (BENCH / "cities" / "maup_coarse" / "reports.json").read_text(encoding="utf-8")
    assert fine == coarse


def test_every_city_has_a_planted_hotspot_cluster_and_decoys() -> None:
    for name in CONFIG_NAMES:
        gt = json.loads((BENCH / "cities" / name / "ground_truth.json").read_text(encoding="utf-8"))
        # merge_cols > 1 (maup_coarse) buckets the 5-cell plus-shape cluster into
        # fewer, larger published segments -- still a contiguous nonempty cluster.
        assert 1 <= len(gt["true_hotspot_segments"]) <= 5, name
        assert len(gt["decoy_exposure_segments"]) >= 1, name
        assert len(gt["decoy_reporting_bias_segments"]) >= 1, name
        assert len(gt["background_segments"]) > 0, name


def test_scorer_recovers_the_baseline_scorecard() -> None:
    """nearmiss's own baseline score matches the committed scorecard.json --
    a regression guard on the statistics layer's behavior on a known city,
    mirroring tests/test_reproduce.py's determinism check."""
    city_dir = BENCH / "cities" / "baseline"
    verdicts = scorer._run_nearmiss(city_dir)
    card = scorer.score_city(city_dir, verdicts, tool="nearmiss")
    committed = json.loads((city_dir / "scorecard.json").read_text(encoding="utf-8"))
    assert card == committed


def test_decoy_exposure_never_fools_the_scorer_in_any_committed_regime() -> None:
    """The one guarantee exposure normalization is specifically supposed to
    provide (see SCORECARD.md): a busy-but-average-rate decoy should not be
    flagged, in any regime.

    **This assertion is currently vacuous, and saying so is the point.** Every
    generated city is a fully disconnected graph (see
    ``test_every_benchmark_city_is_currently_a_disconnected_grid``), so under
    ADR-0015 nothing in any regime can be flagged significant — the decoy
    false-positive rate is 0.0 because the numerator is structurally zero, not
    because exposure normalization defeated the decoy. It regains its meaning
    the moment the generator emits a connected grid; until then it is a
    placeholder, not evidence.
    """
    for name in CONFIG_NAMES:
        card = json.loads((BENCH / "cities" / name / "scorecard.json").read_text(encoding="utf-8"))
        assert card["decoy_exposure_fp_rate"] == 0.0, name
        # Pin the vacuity itself, so this test cannot quietly go on "passing"
        # for a different reason than the one documented above.
        assert card["n_flagged_significant"] == 0, name


@pytest.mark.parametrize("name", CONFIG_NAMES)
def test_every_benchmark_city_is_currently_a_disconnected_grid(name: str) -> None:
    """A tripwire on the defect ADR-0015 surfaced in this suite.

    ``generator.py`` lays each grid out as short, mutually non-touching stubs —
    consecutive segments end and begin roughly 122 m apart against a 5 m
    ``gi_node_snap_m`` — so no two segments share an endpoint and the adjacency
    graph has no edges at all. Every Gi* z this suite ever scored was therefore
    a global z-score (issue #193), and every hotspot column in SCORECARD.md is
    unmeasured rather than measured-and-zero. The generator fix is issue #196.

    This test pins the broken state ON PURPOSE. When someone fixes the generator
    it will fail, which is the signal to re-score the suite and rewrite the
    hotspot half of SCORECARD.md — the two things that must not be forgotten.
    """
    from nearmiss.config import load_config
    from nearmiss.loaders import load_streets
    from nearmiss.network import SegmentGraph

    city_dir = BENCH / "cities" / name
    config = load_config(city_dir / "config.toml")
    segments = load_streets(config.streets_path)
    graph = SegmentGraph.build(segments, node_snap_m=config.gi_node_snap_m)
    assert len(graph.isolated) == len(segments), (
        f"{name}: {len(segments) - len(graph.isolated)} segment(s) now have a network "
        "neighbour. The generator has been fixed — re-run `make bench-suite` and rewrite "
        "the hotspot columns and prose in benchmarks/SCORECARD.md, which currently "
        "document the suite as unmeasured."
    )


def test_external_results_are_scored_against_ground_truth() -> None:
    """The "bring your own tool" path: a perfect oracle scores 100%/100%."""
    city_dir = BENCH / "cities" / "baseline"
    gt = json.loads((city_dir / "ground_truth.json").read_text(encoding="utf-8"))
    verdicts = {
        sid: scorer.SegmentVerdict(significant=(row["role"] == "hotspot"))
        for sid, row in gt["segments"].items()
    }
    card = scorer.score_city(city_dir, verdicts, tool="oracle")
    assert card["hotspot_recall"] == 1.0
    assert card["hotspot_precision"] == 1.0
    assert card["decoy_exposure_fp_rate"] == 0.0
    assert card["reporting_bias_trap_rate"] == 0.0


def test_results_schema_accepts_a_minimal_valid_submission() -> None:
    schema = json.loads((BENCH / "schema" / "results.schema.json").read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator(schema).validate(
        {"tool": "example", "segments": {"seg-00-00": {"significant": False}}}
    )


def test_results_schema_rejects_a_missing_significant_field() -> None:
    schema = json.loads((BENCH / "schema" / "results.schema.json").read_text(encoding="utf-8"))
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft202012Validator(schema).validate({"segments": {"seg-00-00": {}}})
