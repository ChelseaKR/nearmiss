"""What may be published from a source is answered by that source's own manifest.

Issue #186. The adapter registry ships two sources and zero paths from a real source to
a published artifact, and neither adapter said so:

* **SimRa** has abundant real data under CC BY-NC 4.0. `docs/DATA-CARD.md` had already
  drawn the conclusion — "No SimRa-derived data is currently published from this
  repository" — but that decision lived only in a document, three files away from the
  adapter that ships the source, so the framework registered a source it had already
  decided it could not publish from.
* **BikeMaps.org** was listed in the same table as "CC BY 4.0 / permitted with
  attribution" while `bikemaps.toml`, the machine-readable manifest that table is
  supposed to render, claimed only "see https://bikemaps.org/terms for reuse terms".
  That is the same unbacked-licence defect the SimRa row was corrected for on
  2026-08-07, still standing on the row above it.

The fix moves the disposition to the source: `publication_status` is a required,
closed-vocabulary field with a mandatory note saying on what basis it was reached, and
`docs/DATA-CARD.md` quotes the manifests rather than restating them. These tests hold
both halves: the field cannot be omitted, guessed, or answered with a shrug, and the doc
cannot drift from the manifests again without failing here.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from nearmiss.adapters import registry
from nearmiss.adapters.base import PUBLICATION_STATUSES, Crosswalk, load_crosswalk

ROOT = Path(__file__).resolve().parents[1]
DATA_CARD = ROOT / "docs" / "DATA-CARD.md"
REAL_DATA = ROOT / "docs" / "REAL-DATA.md"
CROSSWALKS = ROOT / "src" / "nearmiss" / "adapters" / "crosswalks"

#: The one shape `docs/REAL-DATA.md` may state a source's publication status in. Fixing the
#: shape is what makes the claim findable by a gate instead of by a careful reader.
_STATUS_BLOCK = re.compile(
    r"^> \*\*Publication status: `(?P<status>[a-z_]+)`\*\* "
    r"\(`src/nearmiss/adapters/crosswalks/(?P<source>[a-z0-9_]+)\.toml`\)\.",
    flags=re.MULTILINE,
)


def _real_data_statuses() -> dict[str, str]:
    text = REAL_DATA.read_text(encoding="utf-8")
    return {m.group("source"): m.group("status") for m in _STATUS_BLOCK.finditer(text)}


SOURCE_IDS = sorted(registry)


def crosswalk(source_id: str) -> Crosswalk:
    return load_crosswalk(source_id)


def test_the_registry_still_has_sources_to_check() -> None:
    """Guard the guard: an empty registry would make every parametrised test vacuous."""
    assert SOURCE_IDS, "no report adapters are registered, so nothing below is checked"
    assert {"bikemaps", "simra"} <= set(SOURCE_IDS)


@pytest.mark.parametrize("source_id", SOURCE_IDS)
def test_every_registered_source_declares_a_publication_status(source_id: str) -> None:
    loaded = crosswalk(source_id)
    assert loaded.publication_status in PUBLICATION_STATUSES
    assert len(loaded.publication_note.strip()) >= 40


@pytest.mark.parametrize("source_id", SOURCE_IDS)
def test_a_non_publishable_source_names_what_binds_it(source_id: str) -> None:
    """`research_only` and `undetermined` must say *why*, not merely be flagged."""
    loaded = crosswalk(source_id)
    if loaded.publication_status == "publishable":
        return
    note = loaded.publication_note.lower()
    assert any(word in note for word in ("licen", "clause", "terms", "rights")), (
        f"{source_id}: publication_note does not name the licence, clause, terms, or "
        f"rights that produced status {loaded.publication_status!r}"
    )


def test_simra_is_research_only_for_its_noncommercial_clause() -> None:
    """The decision `docs/DATA-CARD.md` already recorded, now at the adapter."""
    loaded = crosswalk("simra")
    assert loaded.publication_status == "research_only"
    assert "NonCommercial" in loaded.publication_note


def test_bikemaps_is_not_claimed_publishable_on_an_unread_terms_page() -> None:
    loaded = crosswalk("bikemaps")
    assert loaded.publication_status == "undetermined"
    assert "CC BY 4.0" not in loaded.license


# --- The data card renders the manifests rather than restating them ----------------


@pytest.mark.parametrize("source_id", SOURCE_IDS)
def test_the_data_card_quotes_each_crosswalks_licence_verbatim(source_id: str) -> None:
    loaded = crosswalk(source_id)
    text = DATA_CARD.read_text(encoding="utf-8")
    assert loaded.license in text, (
        f"docs/DATA-CARD.md does not quote {source_id}'s licence as its crosswalk states "
        f"it. A licence table not backed by the machine-readable source is the defect "
        f"issue #186 was filed about.\n  crosswalk says: {loaded.license}"
    )


@pytest.mark.parametrize("source_id", SOURCE_IDS)
def test_the_data_card_reports_each_sources_publication_status(source_id: str) -> None:
    text = DATA_CARD.read_text(encoding="utf-8")
    loaded = crosswalk(source_id)
    assert f"`{loaded.publication_status}`" in text


def test_no_data_card_table_row_asserts_a_licence_no_manifest_backs() -> None:
    """Table rows are the assertions. Prose *about* the old claim is not one."""
    declared = {loaded.license for loaded in (crosswalk(s) for s in SOURCE_IDS)}
    for line in DATA_CARD.read_text(encoding="utf-8").splitlines():
        row = line.strip()
        if not row.startswith("|") or "BikeMaps" not in row:
            continue
        assert any(licence in row for licence in declared), (
            "a docs/DATA-CARD.md table row describes BikeMaps without quoting the "
            f"licence its crosswalk states: {row}"
        )


# --- The adapter guide states it too, because that is the document authors read ----
#
# Issue #186 again, second instance. `docs/DATA-CARD.md` and `docs/ADAPTING.md` were both
# corrected to carry each source's publication status; `docs/REAL-DATA.md` — the per-source
# guide an adapter author actually works from — was not, and the gate above could not see it
# because it only ever read the data card. So §1b went on calling SimRa an "openly-published"
# dataset with no mention of CC BY-NC, one hundred and seventy lines above the section that
# refuses a SeeClickFix adapter *for the NonCommercial clause*. The identical objection
# disqualified an unbuilt adapter and stayed silent about a shipped one, which is the
# asymmetry #186 was filed about, surviving in the document that routes contributors.


@pytest.mark.parametrize("source_id", SOURCE_IDS)
def test_the_adapter_guide_states_each_sources_publication_status(source_id: str) -> None:
    """A registered source with no status block in the guide is the drift, restarting."""
    stated = _real_data_statuses()
    assert source_id in stated, (
        f"docs/REAL-DATA.md has no publication-status block for {source_id!r}. Every "
        f"registered source needs one, in the form:\n"
        f"> **Publication status: `<status>`** "
        f"(`src/nearmiss/adapters/crosswalks/{source_id}.toml`)."
    )
    assert stated[source_id] == crosswalk(source_id).publication_status, (
        f"docs/REAL-DATA.md says {source_id} is {stated[source_id]!r}; its crosswalk says "
        f"{crosswalk(source_id).publication_status!r}. The manifest is the source of truth."
    )


def test_the_adapter_guide_describes_no_source_it_does_not_register() -> None:
    """A status block for a source that was removed would be a claim about nothing."""
    assert set(_real_data_statuses()) <= set(SOURCE_IDS)


#: An unqualified openness claim is a redistribution claim, and no registered source can
#: back one today. Written as fragments so this module can name the wording it forbids
#: without tripping its own check — the same convention `tests/test_debt_markers.py` uses
#: for the marker words.
_OPENNESS_CLAIM = ("openly", "published")


def openness_claims_in_prose(text: str) -> list[str]:
    """Lines asserting open publication, ignoring block quotes.

    The status blocks are block quotes, and they are precisely where a correction has to
    quote the wording it replaced. What is being policed is the document's own descriptive
    prose: the sentence a reader takes as this project's current claim about a source.
    """
    joined = "".join(_OPENNESS_CLAIM)
    claims = []
    for line in text.splitlines():
        if line.lstrip().startswith(">"):
            continue
        squashed = "".join(line.lower().split()).replace("-", "").replace("*", "")
        if joined in squashed:
            claims.append(line.strip())
    return claims


def test_no_prose_line_advertises_a_source_as_openly_published() -> None:
    """The exact wording that hid the SimRa clause: an openness claim with no licence.

    Applied to a source whose crosswalk says `research_only` or `undetermined`, it is a
    redistribution assertion no manifest backs — the same defect the BikeMaps licence row
    was corrected for, in prose rather than in a table. This is unconditional while no
    registered source is `publishable`, which the assertion below pins rather than assumes.
    """
    assert all(crosswalk(s).publication_status != "publishable" for s in SOURCE_IDS), (
        "a source is now publishable; this check has to become per-source rather than "
        "unconditional. Do not simply delete it."
    )
    claims = openness_claims_in_prose(REAL_DATA.read_text(encoding="utf-8"))
    assert claims == [], (
        "docs/REAL-DATA.md asserts open publication while no registered source is "
        f"`publishable`: {claims}"
    )


def test_the_openness_check_fails_on_a_planted_claim() -> None:
    """A check that cannot be shown to fail is not a check."""
    planted = "SimRa is a crowdsourced, openly-published dataset of near-crashes.\n"
    assert openness_claims_in_prose(planted) == [planted.strip()]
    assert openness_claims_in_prose("> " + planted) == []


def test_the_guide_names_the_clause_that_binds_simra_where_it_refuses_seeclickfix() -> None:
    """Both halves of the asymmetry have to be visible in one document, or it recurs."""
    text = REAL_DATA.read_text(encoding="utf-8")
    assert "SeeClickFix" in text and "NonCommercial" in text
    simra_block = text.split("crosswalks/simra.toml")[1][:1600]
    assert "NonCommercial" in simra_block, (
        "docs/REAL-DATA.md refuses a SeeClickFix adapter on the NonCommercial clause but "
        "does not name that clause where it documents SimRa, which carries it."
    )


# --- The contract refuses an unanswered or hand-waved status -----------------------


def _manifest_without(source_id: str, key: str, tmp_path: Path) -> Path:
    """A copy of a real crosswalk with one `[source]` key removed."""
    lines = (CROSSWALKS / f"{source_id}.toml").read_text(encoding="utf-8").splitlines()
    kept = [line for line in lines if not line.startswith(f"{key} =")]
    target = tmp_path / f"{source_id}.toml"
    target.write_text("\n".join(kept) + "\n", encoding="utf-8")
    return target


@pytest.mark.parametrize("key", ["publication_status", "publication_note"])
def test_a_crosswalk_missing_the_new_keys_is_rejected(
    key: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _manifest_without("simra", key, tmp_path)
    monkeypatch.setattr("nearmiss.adapters.base.CROSSWALK_DIR", tmp_path)
    with pytest.raises(ValueError, match=key):
        load_crosswalk("simra")


def test_an_unknown_publication_status_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = (CROSSWALKS / "simra.toml").read_text(encoding="utf-8")
    (tmp_path / "simra.toml").write_text(
        source.replace(
            'publication_status = "research_only"', 'publication_status = "probably_ok"'
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("nearmiss.adapters.base.CROSSWALK_DIR", tmp_path)
    with pytest.raises(ValueError, match="publication_status must be one of"):
        load_crosswalk("simra")


def test_a_shrug_for_a_publication_note_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = (CROSSWALKS / "simra.toml").read_text(encoding="utf-8")
    lines = [line for line in source.splitlines() if not line.startswith("publication_note =")]
    lines.append('publication_note = "n/a"')
    (tmp_path / "simra.toml").write_text("\n".join(lines) + "\n", encoding="utf-8")
    monkeypatch.setattr("nearmiss.adapters.base.CROSSWALK_DIR", tmp_path)
    with pytest.raises(ValueError, match="publication_note must say on what basis"):
        load_crosswalk("simra")
