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

from pathlib import Path

import pytest

from nearmiss.adapters import registry
from nearmiss.adapters.base import PUBLICATION_STATUSES, Crosswalk, load_crosswalk

ROOT = Path(__file__).resolve().parents[1]
DATA_CARD = ROOT / "docs" / "DATA-CARD.md"
CROSSWALKS = ROOT / "src" / "nearmiss" / "adapters" / "crosswalks"

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
