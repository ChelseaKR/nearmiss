"""G9 pseudo-locale gate — the brief has no gettext bypass and keeps placeholders.

This exercises ``tools/make_pseudolocale.py`` end to end: it builds a *build-only*
``xx`` pseudo catalog into ``tmp_path`` (never under the shipped package locales),
renders the advocacy brief through the real gettext seam with ``lang="xx"``, and
then asserts three properties that together make a whole class of i18n defects
merge-blocking without any human translator:

* **No gettext bypass / hardcoded string.** Every fixed, translatable string the
  brief emits is a msgid in the catalog, so under the pseudo locale it renders
  accented and wrapped in the ``[!! … !!]`` sentinels. If any such string showed up
  as plain English *without* the sentinels, it went around ``_()`` — that is the
  bug this catches. (Config-supplied data like street names or ``dataset_note`` is
  legitimately not translated and is not a msgid, so it is never flagged.)
* **Placeholders survive.** Real interpolated data (the city, rates, counts) still
  appears in the pseudo output, proving ``{brace}`` fields round-tripped intact.
* **``xx`` never ships.** The pseudo catalog is not present under
  ``src/nearmiss/locales`` and the generator refuses to write there.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

import nearmiss.i18n as i18n
from nearmiss.brief import render_brief
from nearmiss.config import Config
from nearmiss.engine import AnalysisBundle
from nearmiss.i18n import LOCALEDIR

ROOT = Path(__file__).resolve().parents[1]
POT = ROOT / "src" / "nearmiss" / "locales" / "messages.pot"


def _load_tool() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "make_pseudolocale", ROOT / "tools" / "make_pseudolocale.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


mpl = _load_tool()

# msgids that carry a ``{placeholder}`` or printf token are interpolated with data;
# their *literal* text is still pseudo-ized, but they cannot be matched verbatim.
# The bypass check below focuses on fixed strings; placeholder survival is asserted
# separately.
_FIXED = mpl._TOKEN  # reuse the exact held-out-token regex


def _fixed_msgids() -> list[str]:
    import babel.messages.pofile as pofile

    with POT.open("rb") as handle:
        template = pofile.read_po(handle)
    fixed: list[str] = []
    for message in template:
        if not message.id or isinstance(message.id, (tuple, list)):
            continue
        if _FIXED.search(message.id):
            continue  # has a placeholder/printf token — not a fixed string
        # Very short msgids (e.g. the standalone "n" for a sample count) are not
        # usable bypass anchors — they occur as substrings of ordinary words — so
        # they are excluded from the raw-leak scan. The distinctive headings/labels
        # in _STANDALONE carry the positive-presence half of the gate.
        if len(message.id) < 4:
            continue
        fixed.append(message.id)
    return fixed


# Fixed strings the demo brief is guaranteed to emit *standalone* (section headings
# and table-column labels). These give the gate a positive-presence assertion that
# would fail loudly if any of them stopped routing through gettext, without the
# fragility of guessing standalone-ness for strings that only appear embedded in a
# larger template (e.g. "exposure unknown", which is also a substring of a sentence).
_STANDALONE = (
    "## What the numbers mean (plain language)",
    "## Highest-rate segments (exposure-normalized)",
    "## Reporting bias (named, not hidden)",
    "## When hazards get reported (volume, not risk)",
    "95% CI",
    "Rank",
    "Segment",
    "Confidence",
    "Hotspot",
)


def test_pseudolocale_flags_no_gettext_bypass(
    bundle: AnalysisBundle, config: Config, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # (a) Build the pseudo catalog into a temp dir — NOT under the package.
    localedir = mpl.build_pseudo_catalog(POT, tmp_path / "build")
    assert (localedir / "xx" / "LC_MESSAGES" / "messages.mo").is_file()

    # English render first (uses the real, shipped localedir) so we can prove the
    # fixed strings really are emitted by the brief.
    english = render_brief(bundle, config, "en")

    # Now point the gettext seam at the pseudo catalog and render with xx.
    monkeypatch.setattr(i18n, "LOCALEDIR", localedir)
    pseudo_text = render_brief(bundle, config, "xx")

    # The sentinels are present in force (this really went through the pseudo mo).
    assert pseudo_text.count(mpl.OPEN) >= 10
    assert pseudo_text.count(mpl.OPEN) == pseudo_text.count(mpl.CLOSE)

    # (b) No gettext bypass: no fixed, translatable string may appear as raw English
    # in the pseudo render. Under the pseudo locale a catalog string renders accented
    # (no ASCII letters), so if any fixed msgid's exact text survives verbatim, either
    # the brief emitted it hardcoded (bypassing _()) or it stopped being translated.
    # Config-supplied data (street names, dataset_note) is not a msgid and is not
    # checked, so it is never a false positive.
    for msgid in _fixed_msgids():
        assert msgid not in pseudo_text, (
            f"hardcoded / un-gettext'd user-facing string leaked to output: {msgid!r} "
            "(it rendered as raw English under the pseudo locale — wrap it in _())"
        )

    # Positive presence: the standalone headings/labels really did route through the
    # pseudo catalog (accented + sentinel-wrapped), proving the gate is not vacuous.
    for msgid in _STANDALONE:
        assert msgid in english, f"test assumption broke: brief no longer emits {msgid!r}"
        expected = mpl.pseudo(msgid)
        assert expected in pseudo_text, (
            f"pseudo form of a translatable heading/label is missing: {msgid!r}"
        )


def test_pseudolocale_preserves_placeholders(
    bundle: AnalysisBundle, config: Config, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    localedir = mpl.build_pseudo_catalog(POT, tmp_path / "build")
    monkeypatch.setattr(i18n, "LOCALEDIR", localedir)
    pseudo_text = render_brief(bundle, config, "xx")

    # (c) Interpolated data survived the pseudo transform intact: the city name (a
    # {city} placeholder), the headline segment, and a rate number all appear —
    # accented sentence around them, real data inside.
    assert config.city in pseudo_text  # {city} in the title survived
    assert "5th St (C–D)" in pseudo_text  # {name} placeholder data survived
    assert "20.00" in pseudo_text  # a {rate} value survived
    # And the sentinels wrap that data-bearing title line.
    title_line = next(line for line in pseudo_text.splitlines() if config.city in line)
    assert mpl.OPEN in title_line and mpl.CLOSE in title_line


def test_pseudo_catalog_never_ships_under_package_locales(tmp_path: Path) -> None:
    # The exclusion guard: xx is not a shipped locale and must not appear under
    # src/nearmiss/locales, and the generator must refuse to write there.
    shipped = {p.name for p in LOCALEDIR.iterdir() if (p / "LC_MESSAGES").is_dir()}
    assert "xx" not in shipped, "the build-only pseudo locale must never be committed"

    with pytest.raises(ValueError, match="never ship"):
        mpl.build_pseudo_catalog(POT, LOCALEDIR / "xx-build")
