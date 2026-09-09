#!/usr/bin/env python3
"""A small, dependency-free accessibility gate for the static web UI.

This is the fast, merge-blocking structural check that runs in `make accessibility`
and on every CI run: it verifies the foundations that automated and manual audits
build on — a language, a title, landmarks and a heading, labeled data tables, a
skip link, and image alternatives. It is intentionally NOT a substitute for the
deeper axe run and the manual NVDA/VoiceOver review described in
docs/ACCESSIBILITY.md; it is the floor those sit on.

**Nine rules, and four of them are per-element.** Five (language, title, `<main>`,
`<h1>`, skip link) are page-level and always evaluate. The other four —
`<table>` captions, `<th scope>` headers, `<img>` alternatives, `<button>` text —
are guarded by their element's population, so on a page carrying none of that
element they judged nothing and the output was the same `PASS` line a page whose
tables are all captioned gets. Measured over the nine audited documents on
2026-09-08:

    rule                      pages where it had an input
    table caption                     2 of 9
    table header scope                2 of 9
    image alternative                 0 of 9   <- 0 <img> elements in the whole set
    button text                       5 of 9

So `a11y: PASS index.html (structural checks)` was a nine-rule verdict over a page
where four of the nine had nothing to read, and the image-alternative rule — named
in `docs/ACCESSIBILITY.md` as one of the foundations this gate checks — has never
once had an input. This module now carries `examined`/`available` per rule, reports
a rule with no input as `not_applicable` with its reason rather than as a pass, and
prints the census. `tools/verify_dataset.py` already made exactly this repair for
the published artifacts; this is the same repair, for the pages.

`NO_INPUT_IN_THE_AUDITED_SET` is self-limiting in both directions: a rule listed
there that later gains an input fails until the entry is deleted, and a rule with
no input anywhere and no entry fails too. A `not_applicable` never fails a run --
it was never a failure -- but a rule the whole audited set cannot exercise is a
claim about coverage, and it has to be written down.

Usage:  python tools/a11y_check.py web/index.html
Exit:   0 if all checks pass, 1 otherwise (with a list of failures).
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path


class _Audit(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.html_lang = False
        self.has_title = False
        self.has_main = False
        self.has_h1 = False
        self.has_skip_link = False
        self.tables = 0
        self.tables_with_caption = 0
        self.tables_with_th_scope = 0
        self.img_total = 0
        self.img_with_alt = 0
        self.buttons_with_text = 0
        self.buttons_total = 0
        self._in_title = False
        self._title_text = ""
        self._in_table = False
        self._cur_caption = False
        self._cur_scope = False
        self._first_anchor_href = ""
        self._capture_text: list[str] = []

    def handle_starttag(self, tag: str, attrs_list: list[tuple[str, str | None]]) -> None:
        attrs = {k: (v or "") for k, v in attrs_list}
        if self._handle_landmark_tag(tag, attrs):
            return
        self._handle_content_tag(tag, attrs)

    def _handle_landmark_tag(self, tag: str, attrs: dict[str, str]) -> bool:
        """Handle page-landmark start tags (lang, title, main, h1, skip link).

        Returns True if `tag` was one of these (so the caller can skip the
        content-tag dispatch below).
        """
        if tag == "html" and attrs.get("lang", "").strip():
            self.html_lang = True
        elif tag == "title":
            self._in_title = True
        elif tag == "main":
            self.has_main = True
        elif tag == "h1":
            self.has_h1 = True
        elif tag == "a" and attrs.get("href", "") == "#main":
            self.has_skip_link = True
        else:
            return False
        return True

    def _handle_content_tag(self, tag: str, attrs: dict[str, str]) -> None:
        """Handle content start tags: table/caption/th scoping, img alt, button text capture."""
        if tag == "table":
            self._in_table = True
            self.tables += 1
            self._cur_caption = False
            self._cur_scope = False
        elif tag == "caption" and self._in_table:
            self._cur_caption = True
        elif tag == "th" and attrs.get("scope", "").strip():
            self._cur_scope = True
        elif tag == "img":
            self.img_total += 1
            if "alt" in attrs:
                self.img_with_alt += 1
        elif tag == "button":
            self.buttons_total += 1
            self._capture_text = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False
        elif tag == "table" and self._in_table:
            self._in_table = False
            if self._cur_caption:
                self.tables_with_caption += 1
            if self._cur_scope:
                self.tables_with_th_scope += 1
        elif tag == "button" and "".join(self._capture_text).strip():
            self.buttons_with_text += 1

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self._title_text += data
            if data.strip():
                self.has_title = True
        if self.buttons_total and self._capture_text is not None:
            self._capture_text.append(data)


#: Statuses, deliberately the same three words `tools/verify_dataset.py` uses for
#: the published artifacts. `not_applicable` always carries a reason and is never
#: a pass.
STATUS_PASS = "pass"
STATUS_FAIL = "fail"
STATUS_NOT_APPLICABLE = "not_applicable"

#: A rule that no audited document can exercise, with the written reason. Empty is
#: the state to aim for. An entry here is a claim that the whole audited set holds
#: no input for that rule, and it fails as soon as that stops being true --
#: including on the day someone adds the first `<img>`, which is exactly when the
#: disclosure needs re-reading.
NO_INPUT_IN_THE_AUDITED_SET: dict[str, str] = {
    "image-alt": (
        "no audited document embeds an <img>: the site's only raster asset is the Open "
        'Graph card, referenced from <meta property="og:image"> and never rendered '
        "into a page. Maps and figures ship as inline SVG. So WCAG 1.1.1 is named in "
        "docs/ACCESSIBILITY.md as a foundation this gate checks, and this gate has "
        "never read one image."
    ),
}


@dataclass(frozen=True)
class RuleResult:
    """One rule's verdict over one document, with the population behind it.

    ``examined``/``available`` are equal for every rule here -- each one reads its
    whole population -- and both are carried anyway, because the number that
    matters is neither of them on its own but the fact that it can be zero.
    """

    rule: str
    criterion: str
    status: str
    examined: int
    available: int
    problem: str | None = None
    reason: str | None = None


def _page_rule(rule: str, criterion: str, satisfied: bool, problem: str) -> RuleResult:
    """A page-level rule. Its population is the document, so it always evaluates."""
    return RuleResult(
        rule=rule,
        criterion=criterion,
        status=STATUS_PASS if satisfied else STATUS_FAIL,
        examined=1,
        available=1,
        problem=None if satisfied else problem,
    )


def _element_rule(
    rule: str,
    criterion: str,
    *,
    population: int,
    satisfying: int,
    element: str,
    problem: str,
) -> RuleResult:
    """A per-element rule, which reports ``not_applicable`` over an empty population.

    This is the whole point of the module's docstring: ``satisfying == population``
    is trivially true at zero, and a rule that read no elements printed the same
    line as a rule that read every one and found nothing wrong.
    """
    if population == 0:
        return RuleResult(
            rule=rule,
            criterion=criterion,
            status=STATUS_NOT_APPLICABLE,
            examined=0,
            available=0,
            reason=(
                f"the document contains no {element}, so this rule judged nothing; "
                "a rule that examined zero elements is not the same statement as a "
                "rule that examined every one and found nothing wrong"
            ),
        )
    ok = satisfying >= population
    return RuleResult(
        rule=rule,
        criterion=criterion,
        status=STATUS_PASS if ok else STATUS_FAIL,
        examined=population,
        available=population,
        problem=None if ok else problem,
    )


def audit_rules(html: str) -> list[RuleResult]:
    """Every rule's verdict over one document, in a fixed order."""
    a = _Audit()
    a.feed(html)
    return [
        _page_rule(
            "html-lang",
            "WCAG 3.1.1",
            a.html_lang,
            "<html> is missing a non-empty lang attribute (WCAG 3.1.1)",
        ),
        _page_rule(
            "document-title",
            "WCAG 2.4.2",
            a.has_title,
            "missing a non-empty <title> (WCAG 2.4.2)",
        ),
        _page_rule(
            "main-landmark",
            "WCAG 1.3.1 / 2.4.1",
            a.has_main,
            "missing a <main> landmark (WCAG 1.3.1 / 2.4.1)",
        ),
        _page_rule(
            "h1-heading",
            "WCAG 1.3.1 / 2.4.6",
            a.has_h1,
            "missing an <h1> heading (WCAG 1.3.1 / 2.4.6)",
        ),
        _page_rule(
            "skip-link",
            "WCAG 2.4.1",
            a.has_skip_link,
            'missing a skip link (<a href="#main">) (WCAG 2.4.1)',
        ),
        _element_rule(
            "table-caption",
            "WCAG 1.3.1",
            population=a.tables,
            satisfying=a.tables_with_caption,
            element="<table>",
            problem="a data <table> is missing a <caption> (WCAG 1.3.1)",
        ),
        _element_rule(
            "table-header-scope",
            "WCAG 1.3.1",
            population=a.tables,
            satisfying=a.tables_with_th_scope,
            element="<table>",
            problem="a data <table> is missing <th scope> headers (WCAG 1.3.1)",
        ),
        _element_rule(
            "image-alt",
            "WCAG 1.1.1",
            population=a.img_total,
            satisfying=a.img_with_alt,
            element="<img>",
            problem="an <img> is missing an alt attribute (WCAG 1.1.1)",
        ),
        _element_rule(
            "button-text",
            "WCAG 4.1.2",
            population=a.buttons_total,
            satisfying=a.buttons_with_text,
            element="<button>",
            problem="a <button> has no accessible text (WCAG 4.1.2)",
        ),
    ]


def audit(html: str) -> list[str]:
    """The problems one document has. Kept for callers that only want the failures."""
    return [r.problem for r in audit_rules(html) if r.problem is not None]


def registry_problems(by_document: dict[str, list[RuleResult]]) -> list[str]:
    """Hold ``NO_INPUT_IN_THE_AUDITED_SET`` to what the audited set actually contains.

    Both directions, because an exemption list goes stale silently: an entry for a
    rule that now has an input somewhere is deleted or this fails, and a rule with
    no input anywhere and no entry fails until its absence is written down.
    """
    if not by_document:
        return ["a11y: no document was audited, so this run is not evidence about any rule"]
    exercised: dict[str, int] = {}
    for results in by_document.values():
        for result in results:
            exercised[result.rule] = exercised.get(result.rule, 0) + result.available
    problems: list[str] = []
    for rule, total in sorted(exercised.items()):
        entry = NO_INPUT_IN_THE_AUDITED_SET.get(rule)
        if total == 0 and entry is None:
            problems.append(
                f"a11y: rule '{rule}' has no input in any audited document, so it reports a "
                "verdict it never reached. Give it a document that exercises it, or record "
                "the absence in NO_INPUT_IN_THE_AUDITED_SET with the reason."
            )
        elif total > 0 and entry is not None:
            problems.append(
                f"a11y: rule '{rule}' is recorded in NO_INPUT_IN_THE_AUDITED_SET as having no "
                f"input, and the audited set now holds {total}. Delete the entry -- and re-read "
                "whatever the entry was excusing."
            )
    for rule in sorted(NO_INPUT_IN_THE_AUDITED_SET):
        if rule not in exercised:
            problems.append(
                f"a11y: NO_INPUT_IN_THE_AUDITED_SET names '{rule}', which is not a rule this "
                "gate has. An entry for a rule that does not exist exempts nothing."
            )
    return problems


def census_lines(by_document: dict[str, list[RuleResult]]) -> list[str]:
    """How many rule cells were evaluated, out of how many exist."""
    cells = [result for results in by_document.values() for result in results]
    evaluated = [r for r in cells if r.status != STATUS_NOT_APPLICABLE]
    lines = [
        f"a11y: {len(evaluated)} of {len(cells)} rule cells evaluated "
        f"({len(by_document)} documents x 9 rules); the rest had no element to read."
    ]
    per_rule: dict[str, tuple[int, int]] = {}
    for result in cells:
        pages, inputs = per_rule.get(result.rule, (0, 0))
        per_rule[result.rule] = (
            pages + (1 if result.status != STATUS_NOT_APPLICABLE else 0),
            inputs + result.available,
        )
    for rule, (pages, inputs) in sorted(per_rule.items()):
        if pages == len(by_document):
            continue
        note = f"  {rule}: evaluated on {pages} of {len(by_document)} documents ({inputs} elements)"
        if inputs == 0:
            note += " -- this rule has never had an input"
        lines.append(note)
    return lines


def main(argv: list[str]) -> int:
    targets = argv[1:] or ["web/index.html"]
    failures = 0
    by_document: dict[str, list[RuleResult]] = {}
    for target in targets:
        path = Path(target)
        if not path.is_file():
            print(f"a11y: FAIL {target}: file not found")
            failures += 1
            continue
        results = audit_rules(path.read_text(encoding="utf-8"))
        by_document[target] = results
        problems = [r.problem for r in results if r.problem is not None]
        skipped = [r for r in results if r.status == STATUS_NOT_APPLICABLE]
        evaluated = len(results) - len(skipped)
        if problems:
            failures += 1
            print(f"a11y: FAIL {target} ({evaluated}/{len(results)} rules evaluated)")
            for p in problems:
                print(f"  - {p}")
        else:
            print(f"a11y: PASS {target} ({evaluated}/{len(results)} rules evaluated)")
        for result in skipped:
            print(f"  {result.rule} not evaluated: {result.reason}")

    print()
    for line in census_lines(by_document):
        print(line)
    registry = registry_problems(by_document)
    for problem in registry:
        print(problem, file=sys.stderr)
    if failures or registry:
        if failures:
            print(f"\na11y: {failures} file(s) failed structural checks.")
        return 1
    print("\na11y: structural checks passed. Run axe + manual SR review for full conformance.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
