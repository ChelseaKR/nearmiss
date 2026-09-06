"""The citation metadata has to name the versions this repository actually ships.

Issue #227. `CITATION.cff` is what a citing researcher reads, and its
`preferred-citation` block is the *dataset* citation — the versioned artifact somebody
is told to cite. It said `version: 0.1.0` while
`src/nearmiss/versions.py` had carried `DATASET_VERSION = "0.1.2"` since 2026-08-22
(`f90fabe`) and both committed sidecars — `data/published/davis.metadata.json` and
`data/published/riverside.metadata.json` — recorded `"version": "0.1.2"`. The header of
`docs/DATA-CARD.md` restated the same field as "currently `0.1.0`" and the dataset schema
version as "currently `1.0.0`", which had been `1.3.0` since 2026-08-27 (`4991ad9`).

That is this portfolio's recurring shape: a stale number rendered as a current
measurement. Nothing was missing and nothing failed — the citation simply pointed at a
dataset version that is not the one in the repository, so a reader doing exactly what the
data card asks would have cited an artifact that was never published under that number.

Nothing tied any of it to the constants, so all three could drift independently. These
tests derive every number from `nearmiss.versions` and from the published sidecars, so the
prose cannot restate a version the code does not hold.

**What these tests do not check, stated rather than left implicit.**

* `date-released` is not derivable from anything in the tree: no published artifact
  carries a generation timestamp. The dataset block's date was set to 2026-08-28, the day
  `4bfb726` last regenerated the committed sidecars, and it has to be maintained by hand.
* This is not CFF schema validation. `docs/standards/DOCUMENTATION-STANDARD.md` declares
  DOC-08 an AUTO-GATE enforced by `cffconvert --validate` in CI, and no such gate exists
  anywhere in this repository — not in `make verify`, not in a workflow, not in
  pre-commit. Closing that means either a new dependency or a hand-rolled CFF validator,
  which is a decision for the owner rather than something to attach to a version fix; the
  gap is recorded on #227.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from nearmiss.versions import DATASET_SCHEMA_VERSION, DATASET_VERSION

ROOT = Path(__file__).resolve().parents[1]
CITATION = ROOT / "CITATION.cff"
DATA_CARD = ROOT / "docs" / "DATA-CARD.md"
PUBLISHED = ROOT / "data" / "published"

CITIES = ("davis", "riverside")


def _preferred_citation_block() -> str:
    """The `preferred-citation:` mapping, as raw text.

    Read as text rather than parsed: the repository has no YAML dependency (the runtime
    surface is deliberately `jsonschema` alone), and the assertions below are about the
    literal strings a reader sees in the file.
    """
    text = CITATION.read_text(encoding="utf-8")
    _, _, after = text.partition("\npreferred-citation:\n")
    assert after, "CITATION.cff no longer has a preferred-citation block; update this test."
    return after


def test_the_dataset_citation_names_the_dataset_version_that_ships() -> None:
    """`preferred-citation` is the dataset citation, so its version is DATASET_VERSION."""
    block = _preferred_citation_block()
    match = re.search(r"^  version: (\S+)$", block, flags=re.MULTILINE)
    assert match is not None, "the preferred-citation block carries no `version:` field"
    assert match.group(1) == DATASET_VERSION, (
        f"CITATION.cff tells a citing reader to cite dataset version {match.group(1)}, but "
        f"nearmiss.versions.DATASET_VERSION is {DATASET_VERSION}. One of the two moved "
        f"without the other."
    )


@pytest.mark.parametrize("city", CITIES)
def test_every_published_sidecar_agrees_with_the_constant(city: str) -> None:
    """The citation is only worth gating if the artifacts really carry that number."""
    sidecar = json.loads((PUBLISHED / f"{city}.metadata.json").read_text(encoding="utf-8"))
    assert sidecar["version"] == DATASET_VERSION
    assert sidecar["schema_version"] == DATASET_SCHEMA_VERSION


@pytest.mark.parametrize(
    ("field", "expected"),
    [("dataset_version", DATASET_VERSION), ("schema_version", DATASET_SCHEMA_VERSION)],
)
def test_the_data_card_header_restates_the_live_versions(field: str, expected: str) -> None:
    """The header a citing reader meets first must not name a superseded version."""
    text = DATA_CARD.read_text(encoding="utf-8")
    match = re.search(rf"`{field}`, currently `([^`]+)`", text)
    assert match is not None, f"docs/DATA-CARD.md no longer states `{field}`; update this test."
    assert match.group(1) == expected, (
        f"docs/DATA-CARD.md says {field} is currently {match.group(1)}, but the code holds "
        f"{expected}. The data card is the document that tells people what to cite."
    )
