"""With JavaScript off, no page may sit at "Loading…" forever.

Issue #157. Neither `web/us-coverage.html` nor `web/studio.html` carried a `<noscript>`
element. Seven regions of the atlas were pinned in the static shell to "Loading the
reviewed artifact…" and "Loading state evidence…" and were only ever replaced by script,
so a reader with scripting off, or behind a script-blocking proxy — a library, a school,
a municipal network, an agency — saw a page permanently in progress. That is this
project's own named failure, rendering an unknown as something else: the reader could
not tell "still fetching" from "the fetch failed" from "your browser will never run
this". The Studio was the same shape without the text: the form rendered and both tools
were inert with no explanation.

Neither automated accessibility gate can see this. `tools/a11y_check.py` and
`web/axe_check.mjs` both evaluate a DOM in which the placeholder is simply present.

The checks here are deliberately *derived*, not listed. `loading_placeholders` walks the
markup and finds every element whose own text says "Loading", then requires each one to
be covered by a selector in that page's `<noscript>` stylesheet. A new placeholder added
tomorrow is therefore covered or it fails here. `test_the_placeholder_finder_still_finds
_the_placeholders` is the witness that keeps the finder from going quietly empty, which
would make every other assertion in this file vacuous.
"""

from __future__ import annotations

import json
import re
from html.parser import HTMLParser
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"
PUBLISHED = ROOT / "data" / "published"

ATLAS = WEB / "us-coverage.html"
STUDIO = WEB / "studio.html"

#: The two pages whose content only script can produce. The other four deployed pages
#: (`index.html`, `404.html`, `web/index.html`, `web/dossier.html`) are static and
#: degrade on their own, so they are deliberately not required to carry a `<noscript>`.
SCRIPT_DEPENDENT_PAGES = (ATLAS, STUDIO)

#: How many "Loading" placeholders the atlas shell carried when #157 was filed. The
#: finder must not silently drop below this.
KNOWN_ATLAS_PLACEHOLDERS = 7


class _Placeholders(HTMLParser):
    """Collect `(tag, id, classes, ancestor selectors)` for every "Loading" element."""

    def __init__(self) -> None:
        super().__init__()
        self.stack: list[tuple[str, set[str]]] = []
        self.found: list[tuple[str, set[str]]] = []
        self._in_noscript = 0

    def handle_starttag(self, tag: str, attrs_list: list[tuple[str, str | None]]) -> None:
        attrs = {k: (v or "") for k, v in attrs_list}
        selectors = set()
        if attrs.get("id"):
            selectors.add(f"#{attrs['id']}")
        selectors.update(f".{name}" for name in attrs.get("class", "").split() if name)
        if tag == "noscript":
            self._in_noscript += 1
        if tag not in {"br", "hr", "img", "input", "meta", "link"}:
            self.stack.append((tag, selectors))

    def handle_endtag(self, tag: str) -> None:
        if tag == "noscript":
            self._in_noscript = max(0, self._in_noscript - 1)
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index][0] == tag:
                del self.stack[index:]
                return

    def handle_data(self, data: str) -> None:
        if self._in_noscript or "Loading" not in data:
            return
        if not self.stack:
            return
        tag = self.stack[-1][0]
        inherited: set[str] = set()
        for _tag, selectors in self.stack:
            inherited |= selectors
        self.found.append((tag, inherited))


def loading_placeholders(page: Path) -> list[tuple[str, set[str]]]:
    """Every element outside `<noscript>` whose own text says "Loading"."""
    parser = _Placeholders()
    parser.feed(page.read_text(encoding="utf-8"))
    return parser.found


def noscript_style_selectors(page: Path) -> set[str]:
    """Every `#id`/`.class` selector named in the page's `<noscript>` stylesheets."""
    text = page.read_text(encoding="utf-8")
    selectors: set[str] = set()
    for block in re.findall(r"<noscript>(.*?)</noscript>", text, re.DOTALL):
        for style in re.findall(r"<style>(.*?)</style>", block, re.DOTALL):
            head = style.split("{")[0] if "{" in style else ""
            selectors.update(re.findall(r"[#.][A-Za-z0-9_-]+", head))
    return selectors


def noscript_body(page: Path) -> str:
    """The text of every `<noscript>` block on the page, stylesheets included."""
    return "\n".join(
        re.findall(r"<noscript>(.*?)</noscript>", page.read_text(encoding="utf-8"), re.DOTALL)
    )


# --- The finder must actually find things ----------------------------------------


def test_the_placeholder_finder_still_finds_the_placeholders() -> None:
    """Guard the guard: an empty finder would make every assertion below vacuous."""
    found = loading_placeholders(ATLAS)
    assert len(found) >= KNOWN_ATLAS_PLACEHOLDERS, (
        f"only {len(found)} 'Loading' placeholders found in {ATLAS.name}; the finder has "
        "stopped seeing the markup it exists to police"
    )


# --- Every script-dependent page explains itself ----------------------------------


@pytest.mark.parametrize("page", SCRIPT_DEPENDENT_PAGES, ids=lambda p: p.name)
def test_a_script_dependent_page_carries_a_noscript_block(page: Path) -> None:
    assert "<noscript>" in page.read_text(encoding="utf-8"), (
        f"{page.name} renders its content with script and offers a reader without it "
        "no explanation at all"
    )


def test_every_atlas_loading_placeholder_is_hidden_without_script() -> None:
    covered = noscript_style_selectors(ATLAS)
    assert covered, "the atlas <noscript> stylesheet names no selectors"
    uncovered = [
        (tag, sorted(selectors))
        for tag, selectors in loading_placeholders(ATLAS)
        if not (selectors & covered)
    ]
    assert uncovered == [], (
        "these 'Loading…' placeholders are still shown when scripting is off, so the "
        f"page keeps claiming to be working on it: {uncovered}"
    )


def test_the_studio_hides_the_two_forms_that_cannot_run() -> None:
    covered = noscript_style_selectors(STUDIO)
    assert {".readiness-form", ".claim-form"} <= covered


# --- The atlas fallback leaves the reader with the data and the rule ---------------


def test_the_atlas_fallback_states_the_suppressed_or_zero_rule() -> None:
    body = noscript_body(ATLAS)
    assert "suppressed_or_zero" in body
    assert "not</em> a zero" in body or "not a zero" in body
    assert "k=10" in body


def test_the_atlas_fallback_links_every_artifact_the_current_index_binds() -> None:
    """Derived from the release index, so a new year is linked or this fails."""
    index = json.loads((PUBLISHED / "fars-state-mode-index-v2.json").read_text(encoding="utf-8"))
    expected = sorted(release["artifact_path"] for release in index["releases"])
    assert len(expected) >= 5, "the release index no longer binds the five published years"
    body = noscript_body(ATLAS)
    missing = [name for name in expected if f"/data/published/{name}" not in body]
    assert missing == [], (
        f"the no-JS reader is told the data is public but is not given these files: {missing}"
    )
    assert "/data/published/fars-state-mode-index-v2.json" in body
    # The retained 2024 revision 1 is reached through the correction ledger rather than
    # linked beside the current artifact, so nobody picks up a superseded file by accident.
    assert "/data/published/fars-release-corrections.json" in body
    assert "/data/published/fars-2024-state-mode.json" not in body


def test_every_link_in_a_noscript_fallback_resolves_to_a_published_file() -> None:
    for page in SCRIPT_DEPENDENT_PAGES:
        for href in re.findall(r'href="(/data/published/[^"]+)"', noscript_body(page)):
            target = ROOT / href.lstrip("/")
            assert target.exists(), f"{page.name} offers a no-JS reader a dead link: {href}"


def test_the_studio_fallback_says_the_file_is_never_uploaded() -> None:
    body = noscript_body(STUDIO)
    assert "never uploaded" in body
    assert "JavaScript" in body
