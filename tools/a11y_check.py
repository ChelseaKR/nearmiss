#!/usr/bin/env python3
"""A small, dependency-free accessibility gate for the static web UI.

This is the fast, merge-blocking structural check that runs in `make accessibility`
and on every CI run: it verifies the foundations that automated and manual audits
build on — a language, a title, landmarks and a heading, labeled data tables, a
skip link, and image alternatives. It is intentionally NOT a substitute for the
deeper axe run and the manual NVDA/VoiceOver review described in
docs/ACCESSIBILITY.md; it is the floor those sit on.

Usage:  python tools/a11y_check.py web/index.html
Exit:   0 if all checks pass, 1 otherwise (with a list of failures).
"""

from __future__ import annotations

import sys
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
        elif tag == "table":
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


def audit(html: str) -> list[str]:
    a = _Audit()
    a.feed(html)
    problems: list[str] = []
    if not a.html_lang:
        problems.append("<html> is missing a non-empty lang attribute (WCAG 3.1.1)")
    if not a.has_title:
        problems.append("missing a non-empty <title> (WCAG 2.4.2)")
    if not a.has_main:
        problems.append("missing a <main> landmark (WCAG 1.3.1 / 2.4.1)")
    if not a.has_h1:
        problems.append("missing an <h1> heading (WCAG 1.3.1 / 2.4.6)")
    if not a.has_skip_link:
        problems.append('missing a skip link (<a href="#main">) (WCAG 2.4.1)')
    if a.tables and a.tables_with_caption < a.tables:
        problems.append("a data <table> is missing a <caption> (WCAG 1.3.1)")
    if a.tables and a.tables_with_th_scope < a.tables:
        problems.append("a data <table> is missing <th scope> headers (WCAG 1.3.1)")
    if a.img_total != a.img_with_alt:
        problems.append("an <img> is missing an alt attribute (WCAG 1.1.1)")
    if a.buttons_total and a.buttons_with_text < a.buttons_total:
        problems.append("a <button> has no accessible text (WCAG 4.1.2)")
    return problems


def main(argv: list[str]) -> int:
    targets = argv[1:] or ["web/index.html"]
    failures = 0
    for target in targets:
        path = Path(target)
        if not path.is_file():
            print(f"a11y: FAIL {target}: file not found")
            failures += 1
            continue
        problems = audit(path.read_text(encoding="utf-8"))
        if problems:
            failures += 1
            print(f"a11y: FAIL {target}")
            for p in problems:
                print(f"  - {p}")
        else:
            print(f"a11y: PASS {target} (structural checks)")
    if failures:
        print(f"\na11y: {failures} file(s) failed structural checks.")
        return 1
    print("\na11y: structural checks passed. Run axe + manual SR review for full conformance.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
