"""Google Analytics 4 on the public pages (docs/adr/0022-google-analytics-4-on-the-public-pages.md).

Absent with no ID, silent off the production host and under GPC, DNT or the footer
opt-out, configured exactly as decided everywhere else, and never handed the Atlas's
query-string view state.

The loader is run, not grepped. ``web/analytics.js`` executes in Node against stubbed
``window``, ``navigator``, ``document`` and ``localStorage``, because a string search
over a script cannot show what the script does. Locally those tests skip when Node is
missing; in CI (``CI`` set) a missing Node is a failure, so the gate cannot pass by
never running them. Every negative control asserts its sabotage landed (the guard
occurred exactly once and is gone from the sabotaged copy) before asserting the harness
caught it; a sabotage that matched nothing would otherwise read as a pass.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from tools.build_site import build_site

ROOT = Path(__file__).resolve().parents[1]
LOADER = ROOT / "web" / "analytics.js"
MEASUREMENT_ID = "G-GSJMYXZTHM"
HOST = "nearmiss.chelseakr.com"
KEY = "nearmiss:analytics-opt-out"
DENIED_REGIONS = [
    *("AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE", "GR", "HU", "IE"),
    *("IT", "LV", "LT", "LU", "MT", "NL", "PL", "PT", "RO", "SK", "SI", "ES", "SE"),
    *("IS", "LI", "NO", "GB", "CH"),
]
# The pages that load GA4 and carry the footer control, as built.
GA_PAGES = (
    "index.html",
    "dossier/index.html",
    "fars/national/index.html",
    "privacy/index.html",
    "studio/index.html",
    "web/us-coverage.html",
)
MESSAGES = ("opted-out", "is-out", "back-in", "signal", "no-storage")
SCRIPT_TAG = '<script src="/web/analytics.js"></script>'

Run = Callable[..., dict[str, Any]]


def _loader() -> str:
    return LOADER.read_text(encoding="utf-8")


# --- configuration and the built pages ---


def test_the_committed_id_host_and_key_are_the_decided_ones() -> None:
    source = _loader()
    assert f'var MEASUREMENT_ID = "{MEASUREMENT_ID}";' in source
    assert f'var PRODUCTION_HOST = "{HOST}";' in source
    assert f'var OPT_OUT_KEY = "{KEY}";' in source
    assert "allow_google_signals: false" in source
    assert "allow_ad_personalization_signals: false" in source


@pytest.fixture
def site(tmp_path: Path) -> Path:
    out = tmp_path / "site"
    build_site(out, "a" * 40)
    return out


def test_every_ga_page_loads_the_loader_in_head_and_carries_one_footer_control(
    site: Path,
) -> None:
    for relative in GA_PAGES:
        html = (site / relative).read_text(encoding="utf-8")
        head, _, body = html.partition("</head>")
        assert head.count(SCRIPT_TAG) == 1, relative
        assert SCRIPT_TAG not in body, relative
        footer = re.search(r"<footer.*?</footer>", body, re.DOTALL)
        assert footer is not None, relative
        assert footer.group(0).count("data-analytics-choice") == 1, relative
        assert body.count("data-analytics-choice") == 1, relative
        assert '<a href="/privacy/"' in footer.group(0), relative
        for message in MESSAGES:
            assert f'data-analytics-message="{message}"' in footer.group(0), (relative, message)
        # Nothing names Google as a static subresource: gtag.js is only ever appended by
        # the guarded loader.
        assert "googletagmanager" not in html, relative


def test_the_not_found_page_and_legacy_redirect_carry_no_ga(site: Path) -> None:
    for relative in ("404.html", "web/index.html"):
        html = (site / relative).read_text(encoding="utf-8")
        assert "analytics.js" not in html, relative
        assert "data-analytics-choice" not in html, relative


def test_the_data_files_carry_no_ga(site: Path) -> None:
    published = sorted((site / "data" / "published").iterdir())
    assert published
    for path in [*published, site / "deployment.json", site / "sitemap.xml"]:
        text = path.read_text(encoding="utf-8")
        for marker in ("googletagmanager", "analytics.js", MEASUREMENT_ID):
            assert marker not in text, (path.name, marker)


def test_the_privacy_page_describes_ga_in_english_and_spanish(site: Path) -> None:
    # Whitespace is normalized: the source wraps prose at 100 columns.
    html = " ".join((site / "privacy" / "index.html").read_text(encoding="utf-8").split())
    for fact in (
        "Google Analytics 4",
        "Global Privacy Control",
        "Do Not Track",
        "Opt out of analytics",
        "Opt back in",
        KEY,
        "_ga",
        "two years",
        "cookieless",
        "Switzerland",
        "14 months",
        "Google signals and ad personalization are off",
        "utm_",
    ):
        assert fact in html, fact
    spanish = html.split('lang="es"', 1)[1]
    for fact in ("Suiza", "14 meses", "sin cookies", "Desactivar la analítica", KEY):
        assert fact in spanish, fact


def test_the_atlas_footer_is_translated_from_the_catalogs() -> None:
    html = (ROOT / "web" / "us-coverage.html").read_text(encoding="utf-8")
    keys = re.findall(r'data-i18n="(analytics_[a-z_]+)"', html)
    assert len(keys) == 9
    catalogs = {
        lang: json.loads((ROOT / "web" / "locales" / f"{lang}.json").read_text(encoding="utf-8"))
        for lang in ("en", "es")
    }
    for key in keys:
        english = catalogs["en"][f"web.coverage.{key}"]
        spanish = catalogs["es"][f"web.coverage.{key}"]
        assert english in html, key  # the static fallback is the catalog's English
        assert spanish and spanish != english, key


# --- the loader, run in Node ---

HARNESS = r"""
const fs = require("fs");
const sc = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
const code = fs.readFileSync(process.argv[3], "utf8");
const appended = [];
const listeners = {};
const data = Object.assign({}, sc.storage || {});
const blocked = () => { throw new Error("storage blocked"); };
const storage = sc.storageThrows
  ? { getItem: blocked, setItem: blocked, removeItem: blocked }
  : {
      getItem: (k) => (Object.prototype.hasOwnProperty.call(data, k) ? data[k] : null),
      setItem: (k, v) => { data[k] = String(v); },
      removeItem: (k) => { delete data[k]; },
    };
function el(attrs) {
  return { hidden: true, attrs, getAttribute: (n) => attrs[n] };
}
const labels = [
  el({ "data-analytics-label": "opt-out" }),
  el({ "data-analytics-label": "back-in" }),
];
const messages = ["opted-out", "is-out", "back-in", "signal", "no-storage"].map(
  (m) => el({ "data-analytics-message": m })
);
const button = {
  hidden: true,
  onclick: null,
  addEventListener(t, f) { if (t === "click") this.onclick = f; },
};
const box = {
  hidden: true,
  querySelector: (s) => (s === "button" ? button : null),
  querySelectorAll: (s) =>
    s === "[data-analytics-label]" ? labels : s === "[data-analytics-message]" ? messages : [],
};
const document = {
  readyState: "loading",
  referrer: sc.referrer || "",
  head: { appendChild: (e) => appended.push(e) },
  createElement: (tag) => ({ tagName: tag, async: false, src: "" }),
  addEventListener: (t, f) => { (listeners[t] = listeners[t] || []).push(f); },
  querySelector: (s) => (s === "[data-analytics-choice]" ? box : null),
};
const navigator = Object.assign({}, sc.navigator || {});
const url = new URL(sc.url || "https://nearmiss.chelseakr.com/");
const window = {
  location: {
    hostname: url.hostname, origin: url.origin, pathname: url.pathname, search: url.search,
  },
};
if (sc.windowDoNotTrack !== undefined) window.doNotTrack = sc.windowDoNotTrack;
Object.defineProperty(window, "localStorage", {
  get() { if (sc.storageGetterThrows) throw new Error("denied"); return storage; },
});
new Function("window", "navigator", "document", code)(window, navigator, document);
const shown = (list, attr) => list.filter((e) => !e.hidden).map((e) => e.attrs[attr]);
const snap = () => ({
  box: !box.hidden, button: !button.hidden,
  label: shown(labels, "data-analytics-label"), message: shown(messages, "data-analytics-message"),
  stored: Object.assign({}, data), disabled: window[sc.gaDisable] === true,
});
const states = [];
if (sc.domReady) {
  (listeners.DOMContentLoaded || []).forEach((f) => f());
  states.push(snap());
  for (let i = 0; i < (sc.clicks || 0); i++) { button.onclick(); states.push(snap()); }
}
const plain = (x) => (x instanceof Date ? "<date>" : x);
process.stdout.write(JSON.stringify({
  dataLayer: window.dataLayer ? window.dataLayer.map((a) => Array.from(a).map(plain)) : null,
  appended: appended.map((e) => ({ tag: e.tagName, async: e.async, src: e.src })),
  states,
}));
"""


def _node() -> str:
    node = shutil.which("node")
    if node is None:
        if os.environ.get("CI"):
            pytest.fail("Node is required in CI to run the GA4 loader's behavior tests")
        pytest.skip("Node is not installed; the loader's behavior tests need it")
    return node


@pytest.fixture
def run(tmp_path: Path) -> Iterator[Run]:
    node = _node()
    harness = tmp_path / "harness.js"
    harness.write_text(HARNESS, encoding="utf-8")
    counter = iter(range(1000))

    def _run(source: str | None = None, **scenario: Any) -> dict[str, Any]:
        index = next(counter)
        script = tmp_path / f"loader-{index}.js"
        script.write_text(_loader() if source is None else source, encoding="utf-8")
        scenario.setdefault("gaDisable", f"ga-disable-{MEASUREMENT_ID}")
        spec = tmp_path / f"scenario-{index}.json"
        spec.write_text(json.dumps(scenario), encoding="utf-8")
        done = subprocess.run(
            [node, str(harness), str(spec), str(script)],
            capture_output=True,
            text=True,
            check=True,
            timeout=60,
        )
        result: dict[str, Any] = json.loads(done.stdout)
        return result

    yield _run


def _loaded(result: dict[str, Any]) -> bool:
    return result["dataLayer"] is not None or bool(result["appended"])


NOTHING_LOADS: dict[str, dict[str, Any]] = {
    "the legacy nearmiss.report host": {"url": "https://nearmiss.report/"},
    "localhost": {"url": "http://localhost:8000/"},
    "127.0.0.1": {"url": "http://127.0.0.1:8000/studio/"},
    "GPC": {"navigator": {"globalPrivacyControl": True}},
    "navigator.doNotTrack": {"navigator": {"doNotTrack": "1"}},
    "window.doNotTrack": {"windowDoNotTrack": "1"},
    "navigator.msDoNotTrack": {"navigator": {"msDoNotTrack": "1"}},
    'doNotTrack "yes"': {"navigator": {"doNotTrack": "yes"}},
    "opted out": {"storage": {KEY: "1"}},
}


@pytest.mark.parametrize("case", sorted(NOTHING_LOADS))
def test_nothing_loads_off_host_under_gpc_or_dnt_or_opted_out(run: Run, case: str) -> None:
    result = run(**NOTHING_LOADS[case])
    assert result["dataLayer"] is None
    assert result["appended"] == []


def test_on_the_production_host_ga_loads_with_the_decided_configuration(run: Run) -> None:
    result = run(
        url=f"https://{HOST}/fars/national/?year=2024&state=CA&lang=es&utm_source=news#map",
        referrer="https://www.example.org/some/path?q=who",
    )
    assert result["appended"] == [
        {
            "tag": "script",
            "async": True,
            "src": f"https://www.googletagmanager.com/gtag/js?id={MEASUREMENT_ID}",
        }
    ]
    denied_ads = {"ad_storage": "denied", "ad_user_data": "denied", "ad_personalization": "denied"}
    assert result["dataLayer"] == [
        [
            "consent",
            "default",
            {**denied_ads, "analytics_storage": "denied", "region": DENIED_REGIONS},
        ],
        ["consent", "default", {**denied_ads, "analytics_storage": "granted"}],
        ["js", "<date>"],
        [
            "config",
            MEASUREMENT_ID,
            {
                "allow_google_signals": False,
                "allow_ad_personalization_signals": False,
                # The Atlas's view state never leaves the browser; campaign tags do.
                "page_location": f"https://{HOST}/fars/national/?utm_source=news",
                "page_referrer": "https://www.example.org/",
            },
        ],
    ]


def test_a_same_site_referrer_keeps_its_path_but_not_its_query(run: Run) -> None:
    result = run(url=f"https://{HOST}/studio/", referrer=f"https://{HOST}/fars/national/?state=TX")
    config = result["dataLayer"][-1][2]
    assert config["page_location"] == f"https://{HOST}/studio/"
    assert config["page_referrer"] == f"https://{HOST}/fars/national/"


@pytest.mark.parametrize(
    "scenario",
    [
        {"storage": {KEY: "0"}},
        {"storage": {"some-other-site:analytics-opt-out": "1"}},
        {"storageThrows": True},
        {"storageGetterThrows": True},
        {"navigator": {"doNotTrack": "0", "globalPrivacyControl": False}},
    ],
)
def test_anything_short_of_a_real_signal_or_opt_out_still_loads(
    run: Run, scenario: dict[str, Any]
) -> None:
    assert _loaded(run(**scenario))


def test_the_footer_control_opts_out_and_back_in_and_is_remembered(run: Run) -> None:
    first, out, back = run(domReady=True, clicks=2)["states"]
    assert first == {
        "box": True,
        "button": True,
        "label": ["opt-out"],
        "message": [],
        "stored": {},
        "disabled": False,
    }
    assert out["label"] == ["back-in"]
    assert out["message"] == ["opted-out"]
    assert out["stored"] == {KEY: "1"}
    assert out["disabled"] is True
    assert back["label"] == ["opt-out"]
    assert back["message"] == ["back-in"]
    assert back["stored"] == {}
    later = run(domReady=True, storage={KEY: "1"})
    assert not _loaded(later)
    assert later["states"][0]["label"] == ["back-in"]
    assert later["states"][0]["message"] == ["is-out"]


def test_the_footer_control_is_wired_off_the_production_host_too(run: Run) -> None:
    result = run(url="http://127.0.0.1:8000/", domReady=True, clicks=1)
    assert not _loaded(result)
    assert result["states"][1]["stored"] == {KEY: "1"}


@pytest.mark.parametrize(
    ("scenario", "message"),
    [
        ({"navigator": {"globalPrivacyControl": True}}, "signal"),
        ({"windowDoNotTrack": "1"}, "signal"),
        ({"storageThrows": True}, "no-storage"),
    ],
)
def test_under_a_signal_or_blocked_storage_the_button_is_hidden_and_says_why(
    run: Run, scenario: dict[str, Any], message: str
) -> None:
    state = run(domReady=True, **scenario)["states"][0]
    assert state["box"] is True
    assert state["button"] is False
    assert state["message"] == [message]


# --- negative controls: the harness must see each guard go missing ---

SABOTAGE: dict[str, tuple[str, dict[str, Any]]] = {
    "hostname": (
        "  if (w.location.hostname !== PRODUCTION_HOST) return;\n",
        {"url": "http://127.0.0.1:8000/"},
    ),
    "GPC": (
        "  if (n.globalPrivacyControl === true) return;\n",
        {"navigator": {"globalPrivacyControl": True}},
    ),
    "DNT": ('  if (dnt === "1" || dnt === "yes") return;\n', {"navigator": {"doNotTrack": "1"}}),
    "opt-out": ("  if (optedOut()) return;\n", {"storage": {KEY: "1"}}),
}


@pytest.mark.parametrize("guard", sorted(SABOTAGE))
def test_negative_control_removing_a_guard_is_caught(run: Run, guard: str) -> None:
    line, scenario = SABOTAGE[guard]
    source = _loader()
    assert source.count(line) == 1, f"the {guard} guard is not in the loader to remove"
    broken = source.replace(line, "", 1)
    assert broken != source and line not in broken  # the sabotage landed
    assert not _loaded(run(**scenario)), "the intact loader should load nothing here"
    assert _loaded(run(broken, **scenario)), f"removing the {guard} guard went unnoticed"


def test_negative_control_sending_the_raw_address_is_caught(run: Run) -> None:
    source = _loader()
    call = "    page_location: scrubbedLocation(),\n"
    assert source.count(call) == 1
    raw = "    page_location: w.location.origin + w.location.pathname + w.location.search,\n"
    broken = source.replace(call, raw, 1)
    assert broken != source
    url = f"https://{HOST}/fars/national/?state=CA"
    assert run(url=url)["dataLayer"][-1][2]["page_location"] == f"https://{HOST}/fars/national/"
    assert run(broken, url=url)["dataLayer"][-1][2]["page_location"] == url
