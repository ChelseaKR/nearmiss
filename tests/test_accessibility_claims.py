"""The accessibility documents may not claim work that was never done.

A false statistic misleads a reviewer. A false accessibility statement misleads the
person least able to absorb it: someone who reads it to decide whether this tool will
work with their screen reader before they spend an hour finding out that it does not.
So these gates are written the same way the dataset gates are — they assert the
*absence* of the unearned claim, not merely the presence of a correction.

Four properties, each derived from the tree rather than typed into a doc:

1. **No document asserts screen-reader testing as performed.** Every sentence that
   pairs an assistive technology with a "we did this" verb must also carry an explicit
   negation ("not", "outstanding", "to be"). The original defect — "Each release is
   walked through with NVDA ... and VoiceOver" — fails here.
2. **The statement and the ACR agree**, with the ACR as the source of truth: its
   "No manual screen-reader testing has been performed" sentence must appear verbatim
   in the outward-facing documents a reader lands on first.
3. **The stated axe scope matches `web/package.json`** — the same nine files, named,
   with the jsdom/static-DOM limits stated and no "brief pages" (there are none:
   `nearmiss brief` emits Markdown).
4. **Every deployed HTML document is in scope**, derived by building the site with
   `tools/build_site.py`, and no document claims a release cadence for the ACR that
   the ACR's own report date contradicts.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pytest
from tools.build_site import build_site

ROOT = Path(__file__).resolve().parents[1]
SHA = "b" * 40

ACCESSIBILITY = ROOT / "docs" / "ACCESSIBILITY.md"
ACR = ROOT / "docs" / "accessibility" / "ACR.md"
README = ROOT / "README.md"
AUDITS_README = ROOT / "docs" / "audits" / "README.md"
RESPONSIBLE_TECH = ROOT / "docs" / "RESPONSIBLE-TECH-AUDITS.md"
STUDIO_AUDIT = ROOT / "docs" / "audits" / "2026-07-16-national-evidence-studio-a11y.md"

# The sentence the ACR carries. It is the source of truth; the outward-facing docs
# must not be softer than it.
NO_MANUAL_TESTING = "No manual screen-reader testing has been performed"

# Documents a reader can reach from the live site or the repository front door.
CLAIM_BEARING_DOCS = (ACCESSIBILITY, ACR, README, AUDITS_README, RESPONSIBLE_TECH, STUDIO_AUDIT)

_ASSISTIVE_TECH = re.compile(r"(?i)\b(NVDA|VoiceOver|JAWS|TalkBack|screen[- ]readers?)\b")

# "We did it" verbs. Multi-word by construction: a phrase broken across a line wrap
# fails to match, which errs toward a missed catch rather than a false accusation.
_PERFORMED = re.compile(
    r"(?i)\b("
    r"walked through"
    r"|has been performed|have been performed|was performed|were performed"
    r"|has been completed|have been completed|was completed|were completed"
    r"|has been tested|have been tested|was tested|were tested"
    r"|has been verified|have been verified|was verified|were verified"
    r"|we tested|we verified|we reviewed|we walked|we ran"
    r"|manually verified|manually tested|manually reviewed"
    r"|confirmed by (?:a |an )?(?:manual )?(?:screen[- ]reader|NVDA|VoiceOver)"
    r")\b"
)

# An explicit marker that the sentence describes something absent, outstanding, or
# intended. An honest sentence about untested work always carries one of these.
_NEGATED = re.compile(
    r"(?i)\b("
    r"no|not|never|none|without"
    r"|outstanding|pending|planned|plans?|target|targets"
    r"|to be|will|would|when|once|remain|remains|remaining|await|awaits|awaiting"
    r"|yet|untested|unperformed|absent|missing|commitment|intend|intended"
    r")\b"
)

# Assertions that the ACR is kept current release by release.
_CADENCE = re.compile(
    r"(?i)(re-?committed on (?:each|every) release|regenerated and re-?committed)"
)
_INTENT = re.compile(
    r"(?i)\b(to be|intend|intended|intent|commitment|commit to|should|not yet|aspiration"
    r"|aspirational|will be|plan|planned)\b"
)

_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")
_NUMBER_WORDS = {
    1: "one",
    2: "two",
    3: "three",
    4: "four",
    5: "five",
    6: "six",
    7: "seven",
    8: "eight",
    9: "nine",
    10: "ten",
    11: "eleven",
    12: "twelve",
}


def _blocks(text: str) -> list[str]:
    """Prose paragraphs as single strings; table rows and headings stay separate.

    Sentences wrap across lines in these documents, so a paragraph has to be rejoined
    before it can be split into sentences. Table rows and headings must *not* be
    joined: two unrelated cells glued together would read as one sentence and could
    pair an assistive technology named in one row with a verb from the next.
    """
    out: list[str] = []
    paragraph: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        standalone = not line or line.startswith(("|", "#", "```"))
        if standalone:
            if paragraph:
                out.append(" ".join(paragraph))
                paragraph = []
            if line:
                out.append(line)
            continue
        paragraph.append(line)
    if paragraph:
        out.append(" ".join(paragraph))
    return out


def _sentences(text: str) -> list[str]:
    return [s.strip() for block in _blocks(text) for s in _SENTENCE_END.split(block) if s.strip()]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _axe_targets() -> tuple[str, ...]:
    """Repo-relative paths `npm run axe` actually scans, read from web/package.json."""
    package = json.loads(_read(ROOT / "web" / "package.json"))
    script: str = package["scripts"]["axe"]
    targets = re.findall(r"axe_check\.mjs\s+(\S+)", script)
    assert targets, "web/package.json no longer runs axe_check.mjs — update this gate"
    return tuple((ROOT / "web" / t).resolve().relative_to(ROOT).as_posix() for t in targets)


def _deployed_documents(tmp_path: Path) -> tuple[str, ...]:
    """Every HTML file the published artifact contains, as artifact-relative paths."""
    out = tmp_path / "site"
    build_site(out, SHA)
    return tuple(sorted(p.relative_to(out).as_posix() for p in out.rglob("*.html")))


def _distinct_deployed_documents(tmp_path: Path) -> int:
    """How many *distinct* HTML documents ship, counting a doc served at two routes once.

    `/fars/national/index.html` is a byte-identical copy of `web/us-coverage.html`, so a
    path count would say seven where a reader would say six. Content hashes settle it.
    """
    out = tmp_path / "site"
    if not out.exists():
        build_site(out, SHA)
    return len({hashlib.sha256(p.read_bytes()).hexdigest() for p in out.rglob("*.html")})


def _route_for(document: str) -> str:
    """The URL path a deployed artifact file is served at."""
    if document.endswith("/index.html"):
        return "/" + document[: -len("index.html")]
    if document == "index.html":
        return "/"
    return "/" + document


def test_no_accessibility_document_claims_screen_reader_testing_was_performed() -> None:
    """The defect this file exists for: a performed-tense claim about NVDA/VoiceOver.

    `docs/ACCESSIBILITY.md` asserted "Each release is walked through with NVDA ... and
    VoiceOver" while the ACR and the 2026-07-16 audit both recorded that no such pass
    had ever happened. Any sentence naming an assistive technology alongside a
    completed-work verb, with no negation, is that bug again.
    """
    offenders: list[str] = []
    for path in CLAIM_BEARING_DOCS:
        for sentence in _sentences(_read(path)):
            if not _ASSISTIVE_TECH.search(sentence):
                continue
            if not _PERFORMED.search(sentence):
                continue
            if _NEGATED.search(sentence):
                continue
            offenders.append(f"{path.relative_to(ROOT)}: {sentence}")
    assert not offenders, (
        "these sentences claim assistive-technology testing as performed; the ACR records "
        "that none has been:\n  - " + "\n  - ".join(offenders)
    )


def test_the_statement_does_not_disagree_with_the_acr() -> None:
    """The ACR is the source of truth, and the front doors must not be softer."""
    acr = _read(ACR)
    assert NO_MANUAL_TESTING in acr, (
        "the ACR no longer carries the no-manual-testing sentence; if manual screen-reader "
        "testing has actually happened, update this gate together with the evidence"
    )
    for path in (ACCESSIBILITY, README):
        assert NO_MANUAL_TESTING in _read(path), (
            f"{path.relative_to(ROOT)} must state the ACR's own sentence "
            f"({NO_MANUAL_TESTING!r}) rather than leaving a reader to find it one level down"
        )


def test_the_stated_axe_scope_is_the_scope_axe_actually_runs() -> None:
    """Derived from web/package.json, not from prose. No brief pages: there are none."""
    text = _read(ACCESSIBILITY)
    targets = _axe_targets()

    missing = [t for t in targets if f"`{t}`" not in text]
    assert not missing, (
        f"docs/ACCESSIBILITY.md does not name every file `npm run axe` scans; missing: {missing}"
    )

    count_word = _NUMBER_WORDS.get(len(targets))
    assert count_word is not None, f"extend _NUMBER_WORDS for {len(targets)} axe targets"
    assert re.search(rf"(?i)\*\*{count_word} files\*\*", text), (
        f"docs/ACCESSIBILITY.md must state the axe scope as **{count_word} files** "
        f"({len(targets)} targets in web/package.json)"
    )

    for limit in ("jsdom", "static", "runScripts"):
        assert limit in text, f"docs/ACCESSIBILITY.md must state the axe limit: {limit!r}"

    claimed_briefs = [
        sentence
        for sentence in _sentences(text)
        if re.search(r"(?i)\bbrief pages?\b", sentence) and not _NEGATED.search(sentence)
    ]
    assert not claimed_briefs, (
        "docs/ACCESSIBILITY.md claims a brief page in an accessibility scan; "
        "src/nearmiss/brief.py renders Markdown/text and no axe target is a brief:\n  - "
        + "\n  - ".join(claimed_briefs)
    )
    assert "runs against the rendered map" not in text, (
        "the axe run parses static HTML in jsdom; 'rendered' overstates it"
    )
    brief_html = sorted(p.name for p in (ROOT / "web").glob("*brief*.html"))
    assert not brief_html, f"an HTML brief now exists ({brief_html}) — revisit the axe scope"


def test_every_deployed_html_document_is_in_the_statements_scope(tmp_path: Path) -> None:
    """Scope is derived from the deployed artifact, so a new page cannot be silently absent."""
    text = _read(ACCESSIBILITY)
    documents = _deployed_documents(tmp_path)
    assert documents, "the site build produced no HTML — this gate would prove nothing"

    for document in documents:
        route = _route_for(document)
        if route != "/":
            assert route in text, (
                f"docs/ACCESSIBILITY.md does not scope the deployed route {route} (from {document})"
            )
    assert "`index.html`" in text and "`404.html`" in text, (
        "docs/ACCESSIBILITY.md must name the apex gateway and error documents in its scope"
    )


def test_the_responsible_tech_audit_names_every_shipped_surface(tmp_path: Path) -> None:
    """`Three shipped HTML surfaces` named two retired ones and missed four live ones."""
    text = _read(RESPONSIBLE_TECH)
    count_word = _NUMBER_WORDS.get(_distinct_deployed_documents(tmp_path))
    assert count_word is not None, "extend _NUMBER_WORDS for the deployed-document count"
    assert re.search(rf"(?i)\*\*{count_word}\s+shipped HTML documents\*\*", text), (
        f"docs/RESPONSIBLE-TECH-AUDITS.md must name the {count_word} shipped HTML documents"
    )
    assert "Three shipped" not in text, (
        "the three-surface inventory named two retired surfaces and omitted every live one"
    )
    for name in ("index.html", "404.html", "us-coverage.html", "studio.html", "dossier.html"):
        assert name in text, f"docs/RESPONSIBLE-TECH-AUDITS.md omits the shipped document {name}"


def test_both_automated_gates_cover_every_deployed_document(tmp_path: Path) -> None:
    """A gate that skips the page the public lands on is a claim with a hole in it.

    `index.html` — the apex gateway — was in the axe script and missing from the
    structural gate's argument list, so `docs/ACCESSIBILITY.md`'s "accessibility is a
    merge-blocking gate" was true of every page except the front door.
    """
    structural = re.search(r"a11y_check\.py([^\n]*)", _read(ROOT / "Makefile"))
    assert structural, "the Makefile no longer runs tools/a11y_check.py"
    structural_targets = set(structural.group(1).split())
    axe_targets = set(_axe_targets())

    out = tmp_path / "site"
    build_site(out, SHA)
    deployed = {hashlib.sha256(p.read_bytes()).hexdigest() for p in out.rglob("*.html")}
    sources = {
        hashlib.sha256(p.read_bytes()).hexdigest(): p.relative_to(ROOT).as_posix()
        for p in (*ROOT.glob("*.html"), *(ROOT / "web").glob("*.html"))
    }
    deployed_sources = {sources[digest] for digest in deployed if digest in sources}
    assert len(deployed_sources) == len(deployed), (
        "a deployed HTML document has no matching source file — the gate lists below "
        "cannot be checked against it"
    )

    for source in sorted(deployed_sources):
        assert source in structural_targets, (
            f"{source} is deployed but is not checked by the structural gate "
            "(`accessibility` target in the Makefile)"
        )
        assert source in axe_targets, f"{source} is deployed but `npm run axe` does not scan it"
    assert deployed_sources <= structural_targets & axe_targets


@pytest.mark.parametrize(
    "path",
    [ACCESSIBILITY, ACR, README, AUDITS_README],
    ids=lambda p: str(p.relative_to(ROOT)),
)
def test_no_document_states_the_acr_release_cadence_as_a_history(path: Path) -> None:
    """The cadence is a commitment; the ACR's own date shows it has not been kept."""
    offenders = [
        sentence
        for sentence in _sentences(_read(path))
        if not sentence.startswith("#")
        and _CADENCE.search(sentence)
        and not _INTENT.search(sentence)
    ]
    assert not offenders, (
        f"{path.relative_to(ROOT)} states the ACR/audit release cadence as settled fact:\n  - "
        + "\n  - ".join(offenders)
    )


def test_the_acr_report_date_is_published_where_the_cadence_is_claimed() -> None:
    """A reader told about the cadence must be told the report date in the same place."""
    match = re.search(r"\*\*Report date\*\*\s*\|\s*(\d{4}-\d{2}-\d{2})", _read(ACR))
    assert match, "the ACR no longer carries a machine-readable report date"
    report_date = match.group(1)
    for path in (ACCESSIBILITY, README):
        assert report_date in _read(path), (
            f"{path.relative_to(ROOT)} claims a release cadence for the ACR without stating "
            f"the ACR's actual report date ({report_date})"
        )
