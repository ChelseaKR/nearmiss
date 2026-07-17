# ---------------------------------------------------------------------------
# nearmiss — Makefile
#
# The dataset and the analysis are the product, not an app. These targets are
# the operator surface for the architecture stages described in the README:
#
#   intake.py -> pipeline/ -> exposure.py -> stats/ -> publish.py -> brief.py -> server.py
#
# Every target is .PHONY (it names a job, not a file) and self-documents via
# the trailing `##` comment that `make help` greps.
#
# Tools are invoked as `$(PYTHON) -m <tool>` so a single PYTHON override points
# the whole gate at one interpreter, e.g.:
#     make verify PYTHON=.venv/bin/python
#
# Hard-rule reminders baked into these targets:
#   HR4 (privacy): `clean` NEVER deletes data/raw/ — precise raw reports are
#                  private and gitignored, and a clean must not destroy them.
#   HR5 (reproducible): `reproduce` rebuilds the published dataset and brief
#                  from raw inputs and fails if the committed output changed.
# ---------------------------------------------------------------------------

SHELL := bash
.SHELLFLAGS := -eu -o pipefail -c

PYTHON  ?= python
PIP     ?= $(PYTHON) -m pip
PACKAGE := nearmiss
CONFIG  ?= config/davis-demo.toml
PUBLISHED_DIR := data/published

.DEFAULT_GOAL := help

.PHONY: help install lock lock-dev lint type test accessibility axe rtl web-check security verify \
        conformance i18n i18n-compile i18n-pseudo claims qgis-plugin-test \
        reproduce sensitivity demo teach publish serve bench bench-suite bench-suite-verify \
        bikemaps simra osm-streets real clean mutation release-build

# Real-data fetch (BikeMaps.org incidents + OpenStreetMap streets + bike counts).
# Override CITY and the output paths as needed.
CITY            ?= victoria
BIKEMAPS_OUT    ?= build/$(CITY)-reports.json
OSM_STREETS_OUT ?= build/$(CITY)-streets.geojson
# SimRa ships as a downloaded directory of ride files, not a live API — point
# SIMRA_DIR at one (see docs/REAL-DATA.md) before running `make simra`.
SIMRA_DIR       ?= data/simra/$(CITY)
SIMRA_OUT       ?= build/$(CITY)-simra-reports.json
# `make real` assembles the three inputs for a committed real config (davis,
# sacramento) into its gitignored input dir. Provide COUNTS=path to a bike-count
# file (GeoJSON points or CSV) for the exposure step; omit it to leave exposure
# unknown (honest) until you have counts.
REAL_DIR        ?= data/real/$(CITY)
COUNTS          ?=

help: ## Show this help — every target with its description
	@echo "nearmiss — open dataset + honest analysis of road near-misses"
	@echo ""
	@echo "Usage: make <target>   (e.g. make demo, make verify PYTHON=.venv/bin/python)"
	@echo ""
	@grep -hE '^[a-zA-Z0-9_-]+:.*?## ' $(MAKEFILE_LIST) \
		| sort \
		| awk 'BEGIN {FS = ":.*?## "} {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

install: ## Install the package (editable) with dev extras and pre-commit hooks
	@$(PYTHON) -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" || { \
		echo "nearmiss requires Python 3.11+ (got $$($(PYTHON) --version 2>&1))."; \
		echo "Re-run with an explicit interpreter, e.g.  make install PYTHON=python3.12"; \
		exit 1; }
	$(PIP) install -e ".[dev]"
	-pre-commit install --install-hooks

lock: ## Generate the hashed reproducible RUNTIME lockfile (requirements.lock)
	$(PYTHON) -m piptools compile --generate-hashes -o requirements.lock pyproject.toml
	@echo "lock: wrote requirements.lock (generated; do not edit by hand)."

lock-dev: ## Generate the hashed reproducible DEV-TOOLCHAIN lockfile (requirements-dev.lock)
	# Covers runtime + the "dev" extra (pytest, ruff, mypy, pip-audit, babel, ...) — the
	# actual gate toolchain CI installs. `make lock` above covers runtime only. CI installs
	# from THIS file with `--require-hashes` (FIX-11) instead of a fresh, unpinned
	# `pip install -e ".[dev]"` resolve, so the toolchain a merge gate runs is reproducible
	# and tamper-evident, not "whatever PyPI serves today." Dependabot (`.github/dependabot.yml`)
	# and Renovate both regenerate this file's pins/hashes on a dependency bump.
	$(PYTHON) -m piptools compile --extra=dev --generate-hashes -o requirements-dev.lock pyproject.toml
	@echo "lock-dev: wrote requirements-dev.lock (generated; do not edit by hand)."

lint: ## Lint with ruff (style + import order + bugbear) and check formatting
	$(PYTHON) -m ruff check .
	$(PYTHON) -m ruff format --check .

type: ## Type-check with mypy --strict (config in pyproject.toml)
	$(PYTHON) -m mypy

test: ## Run pytest (synthetic fixtures, KNOWN answers) under a branch-coverage floor
	$(PYTHON) -m pytest -q \
		--cov=src/nearmiss --cov=src/honest_rates --cov-branch \
		--cov-report=term-missing --cov-fail-under=90
	# Defense in depth: independently re-evaluate pytest-cov's written data. This
	# keeps a coverage-floor failure merge-blocking even if another pytest hook
	# overwrites the session exit status. Precision=2 prevents 89.75% rounding to 90%.
	$(PYTHON) -m coverage report --fail-under=90 --precision=2

qgis-plugin-test: ## Test the QGIS plugin's honest-symbology rules (EXP-11, no QGIS install needed)
	cd integrations/qgis && $(PYTHON) -m pytest tests/ -q

accessibility: ## Structural WCAG gate on the web UI (merge-blocking)
	$(PYTHON) tools/a11y_check.py 404.html web/index.html web/davis-demo.html web/submit.html web/embed.html web/us-coverage.html
	@echo "accessibility: structural checks passed."
	@echo "NOTE: CI also runs axe; full conformance also requires manual NVDA + VoiceOver"
	@echo "      review — see docs/accessibility/ACR.md (this gate is the floor, not the ceiling)."

security: ## Scan deps (pip-audit), history for secrets (gitleaks), and workflow YAML (zizmor)
	# Audit dependencies only: the local editable nearmiss install is not a PyPI
	# release (pip-audit would error on it, and --strict treats a skip as an
	# error), so audit from the hashed dev lock instead of the live environment.
	$(PYTHON) -m pip_audit --strict --require-hashes --disable-pip -r requirements-dev.lock
	@command -v gitleaks >/dev/null 2>&1 \
		&& gitleaks detect --no-banner --redact --source . \
		|| echo "security: gitleaks not found (it is a Go binary, not a pip dep); install it to enable the secret scan. CI runs it."
	@command -v zizmor >/dev/null 2>&1 \
		&& zizmor --min-severity=high .github/workflows/ \
		|| echo "security: zizmor not found (pip install zizmor, or see https://woodruffw.github.io/zizmor/); install it to check workflow YAML locally. CI's zizmor job runs it as a merge-blocking gate."

axe: ## Deeper accessibility check: run axe-core against the built web page (needs node)
	cd web && npm ci && npm run axe

rtl: ## G10 RTL smoke: load the web pages under dir="rtl" and reject direction-unsafe inline styles (needs node)
	cd web && npm ci && npm run rtl

web-check: ## One-install web gate: consumer contracts + axe + RTL-authored CSS scan
	cd web && npm ci && npm run contract && npm run axe && npm run rtl

i18n: ## i18n message-catalog gate: POT current + EN/ES parity + PO compiles + BCP-47
	# G2-lite — regenerate the extraction template and fail if it drifts from the
	# committed one (so a new/changed user-facing string without a re-extract is a
	# merge-blocker). The normalizer freezes volatile header/flag noise so this is
	# a meaningful diff, not a flaky timestamp check. Local == CI.
	$(PYTHON) -m babel.messages.frontend extract -F babel.cfg --no-location \
		--sort-output --project=$(PACKAGE) --version=0.2.0 \
		-o src/$(PACKAGE)/locales/messages.pot src/
	$(PYTHON) tools/i18n_normalize_pot.py src/$(PACKAGE)/locales/messages.pot
	git diff --exit-code -- src/$(PACKAGE)/locales/messages.pot
	# G7 — every PO compiles cleanly (format + domain checks), no msgfmt errors.
	msgfmt --check --check-format --check-domain -o /dev/null \
		src/$(PACKAGE)/locales/en/LC_MESSAGES/messages.po
	msgfmt --check --check-format --check-domain -o /dev/null \
		src/$(PACKAGE)/locales/es/LC_MESSAGES/messages.po
	# G6 EN/ES key-parity + G5 completeness/placeholder parity + web JSON match.
	$(PYTHON) tools/check_catalog_parity.py
	# Web domain — committed web/locales/*.json match the PO catalogs (drift gate).
	$(PYTHON) tools/po2json.py --check
	# G3 — BCP 47 / RFC 5646 validity of every authored locale tag.
	$(PYTHON) tools/check_bcp47.py
	# G9 — pseudo-locale gate: no gettext bypass / hardcoded string, placeholders survive.
	$(MAKE) i18n-pseudo PYTHON=$(PYTHON)
	@echo "i18n: POT current; EN/ES key-parity + completeness; PO + web JSON compile; BCP-47 valid; pseudo-locale gate green."

i18n-pseudo: ## G9 pseudo-locale gate: build the build-only xx catalog and assert no gettext bypass
	# Generates a machine-pseudo `xx` catalog under build/ (NEVER under
	# src/nearmiss/locales — it must not ship) and renders the brief through it: any
	# user-facing string that renders as raw English bypassed gettext. See docs/I18N.md.
	$(PYTHON) tools/make_pseudolocale.py
	$(PYTHON) -m pytest -q tests/test_pseudolocale.py
	@echo "i18n-pseudo: pseudo-locale built (build-only) and the no-bypass gate passed."

i18n-compile: ## Compile the committed PO catalogs to MO (run after editing a .po)
	msgfmt -o src/$(PACKAGE)/locales/en/LC_MESSAGES/messages.mo \
		src/$(PACKAGE)/locales/en/LC_MESSAGES/messages.po
	msgfmt -o src/$(PACKAGE)/locales/es/LC_MESSAGES/messages.mo \
		src/$(PACKAGE)/locales/es/LC_MESSAGES/messages.po
	# Regenerate the committed web JSON catalogs from the web.* PO subset.
	$(PYTHON) tools/po2json.py
	@echo "i18n-compile: refreshed messages.mo (en, es) and web/locales/*.json."

conformance: ## EXP-10: audit every published dataset against the five hard rules (HR1-HR5)
	$(PYTHON) tools/verify_dataset.py data/published/davis.geojson >/dev/null
	$(PYTHON) tools/verify_dataset.py data/published/riverside.geojson >/dev/null
	@echo "conformance: all published datasets pass HR1-HR5 (see tools/verify_dataset.py; forks run it too)."

claims: ## Claims-parity gate: docs/CLAIMS.md manifest <-> doc claim tags <-> witnesses
	# Every load-bearing accuracy claim in the prose docs is a matched
	# <!-- claim:ID --> pair listed in docs/CLAIMS.md with a witness file/test;
	# this fails on drift in either direction (tagged-but-unlisted, or a listed
	# claim whose tag/witness went missing). Local == CI.
	$(PYTHON) tools/check_claims.py

verify: lint type test accessibility web-check security i18n claims conformance ## Full merge gate: lint + type + test + web/a11y + security + i18n + claims + conformance
	@echo "verify: all merge gates green (lint, type, test, web/a11y, security, i18n, claims, conformance)."

mutation: ## ADVISORY (never a merge gate): mutation-test the spatial-stats core with mutmut
	@echo "mutation: ADVISORY ONLY — this is NOT part of 'make verify' and never gates a PR"
	@echo "          (backlog #15). It probes the correctness of the Getis-Ord Gi* hotspot"
	@echo "          and the Poisson/Wilson rate CIs — see docs/MUTATION-TESTING.md."
	@# Install the isolated mutation extra on demand (kept OUT of the dev extra so the
	@# security gate's audited dependency surface is unchanged). mutmut is scoped to
	@# stats/getis_ord.py + stats/rates.py via [tool.mutmut] in pyproject.toml.
	@$(PYTHON) -c "import mutmut" 2>/dev/null || $(PIP) install -e ".[mutation]"
	@# `-` prefixes keep this target advisory: surviving mutants never fail the build.
	-$(PYTHON) -m mutmut run
	-$(PYTHON) -m mutmut results
	@echo "mutation: advisory run complete. Review any survivors above against the"
	@echo "          documented baseline in docs/MUTATION-TESTING.md (equivalent mutants noted)."

reproduce: ## HR5: rebuild every published dataset + figures + brief; fail if output changed
	$(PYTHON) -m $(PACKAGE) run --config $(CONFIG) --out build/brief.md
	$(PYTHON) -m $(PACKAGE) figures --config $(CONFIG)
	$(PYTHON) -m $(PACKAGE) run --config config/riverside-demo.toml --out build/riverside-brief.md
	$(PYTHON) -m $(PACKAGE) figures --config config/riverside-demo.toml
	$(MAKE) sensitivity PYTHON="$(PYTHON)"
	git diff --exit-code -- $(PUBLISHED_DIR)
	@echo "reproduce: all published datasets and figures regenerated byte-for-byte from raw inputs."

sensitivity: ## R29/R34: regenerate the per-city threshold-sensitivity + statistical-power notes
	$(PYTHON) tools/sensitivity_note.py --config $(CONFIG)
	$(PYTHON) tools/sensitivity_note.py --config config/riverside-demo.toml
	@echo "sensitivity: wrote $(PUBLISHED_DIR)/<city>-sensitivity.md (deterministic; no embedded date)."
	@echo "             Snapping/dedupe threshold grid + 'how many reports until rankable' power note."

demo: ## Demonstrability: run the full pipeline over fixtures and render a sample brief
	@mkdir -p build
	$(PYTHON) -m $(PACKAGE) run --config $(CONFIG) --out build/demo-brief.md
	$(PYTHON) -m $(PACKAGE) analyze --config $(CONFIG)
	@echo "demo: sample brief written to build/demo-brief.md"
	@echo "      (recovers the planted hotspot seg-06 from tests/fixtures — a known answer)."

teach: ## EXP-12 teaching module: execute the bilingual "lie with heat maps" notebooks
	@# The Jupyter execution stack lives in the isolated `teaching` extra (NOT in
	@# `dev`), so the pip-audit security gate's dependency surface is unchanged —
	@# same pattern as `make mutation`. Install it on demand, then execute every
	@# teaching notebook into the gitignored, clean-able notebooks/_build/.
	@$(PYTHON) -c "import nbconvert" 2>/dev/null || $(PIP) install -e ".[teaching]"
	@mkdir -p notebooks/_build
	@# `--record_timing=False` strips the volatile per-cell execution timestamps so
	@# the executed notebooks are byte-identical across runs (deterministic, like
	@# `make reproduce`). The notebooks are seeded/known-answer over the synthetic
	@# Davis fixtures — no RNG, no network, no new analysis dependency.
	$(PYTHON) -m nbconvert --to notebook --execute \
		--ExecutePreprocessor.record_timing=False \
		--output-dir notebooks/_build notebooks/teaching/*.ipynb
	@echo "teach: executed the EXP-12 teaching notebooks into notebooks/_build/ (gitignored)."
	@echo "       Facilitator guide: docs/teaching/FACILITATOR-GUIDE.md (EN) / .es.md (ES)."

publish: ## Build the open GeoJSON + aggregated public dataset (privacy-checked)
	$(PYTHON) -m $(PACKAGE) publish --config $(CONFIG)
	@echo "publish: wrote $(PUBLISHED_DIR)/<city>.geojson + metadata."
	@echo "         HR4 check passed: no precise raw report leaked into the public artifact."

serve: ## Serve the local synthetic methods UI (read-only) at /web/davis-demo.html
	$(PYTHON) -m $(PACKAGE) serve --dir .

bench: ## Performance benchmark: time the pipeline + statistics on a city-scale synthetic dataset
	$(PYTHON) tools/benchmark.py

bench-suite: ## EXP-09 planted-truth benchmark suite: regenerate cities + score nearmiss on all of them
	$(PYTHON) benchmarks/generator.py
	$(PYTHON) benchmarks/scorer.py

bench-suite-verify: ## Regenerate the benchmark suite and fail if the committed frozen cities changed
	$(PYTHON) benchmarks/generator.py
	git diff --exit-code -- benchmarks/cities
	@echo "bench-suite-verify: every frozen city regenerates byte-for-byte from its config."

bikemaps: ## Fetch REAL near-miss reports from BikeMaps.org (CITY=victoria) into BIKEMAPS_OUT
	@mkdir -p $(dir $(BIKEMAPS_OUT))
	$(PYTHON) tools/fetch_bikemaps.py --city $(CITY) --out $(BIKEMAPS_OUT)
	@echo "bikemaps: real reports in $(BIKEMAPS_OUT) (intake schema)."
	@echo "          Next: real streets + exposure, then 'nearmiss run' — see docs/REAL-DATA.md."

simra: ## Convert a downloaded SimRa directory (SIMRA_DIR) into intake reports at SIMRA_OUT
	@mkdir -p $(dir $(SIMRA_OUT))
	$(PYTHON) tools/fetch_simra.py --dir $(SIMRA_DIR) --out $(SIMRA_OUT)
	@echo "simra: real reports in $(SIMRA_OUT) (intake schema)."
	@echo "       SimRa ships as a directory, not a live API — pass CITY=berlin|london|munich"
	@echo "       to bbox-filter, or see docs/REAL-DATA.md for the full recipe."

osm-streets: ## Fetch the REAL OSM street network (CITY=victoria) into OSM_STREETS_OUT
	@mkdir -p $(dir $(OSM_STREETS_OUT))
	$(PYTHON) tools/fetch_osm_streets.py --city $(CITY) --out $(OSM_STREETS_OUT)
	@echo "osm-streets: real street network in $(OSM_STREETS_OUT) (split at intersections)."
	@echo "             Remaining real input: exposure — see docs/REAL-DATA.md."

real: ## Assemble all REAL inputs for a committed config (CITY=davis|sacramento; COUNTS=path optional)
	@mkdir -p $(REAL_DIR)
	$(PYTHON) tools/fetch_osm_streets.py --city $(CITY) --out $(REAL_DIR)/streets.geojson
	$(PYTHON) tools/fetch_bikemaps.py    --city $(CITY) --out $(REAL_DIR)/reports.json
ifneq ($(COUNTS),)
	$(PYTHON) tools/build_exposure.py --streets $(REAL_DIR)/streets.geojson --counts "$(COUNTS)" \
		--source "$(CITY) bike counts" --out $(REAL_DIR)/exposure.json
else
	@echo '{"segments": []}' > $(REAL_DIR)/exposure.json
	@echo "real: no COUNTS given — exposure left empty (all segments 'exposure unknown')."
	@echo "      Provide COUNTS=path to a bike-count file to normalize. See docs/REAL-DATA.md."
endif
	@echo "real: inputs assembled in $(REAL_DIR)/. Now: nearmiss run --config config/$(CITY).toml"

release-build: ## Build the reproducible sdist + wheel into dist/ (used by .github/workflows/release.yml)
	rm -rf dist/
	$(PYTHON) -m build --sdist --wheel
	@echo "release-build: wrote dist/ (sdist + wheel)."

clean: ## Remove build/test/cache artifacts — NEVER data/raw/ (HR4)
	rm -rf build/ dist/ web/node_modules \
		.pytest_cache/ .mypy_cache/ .ruff_cache/ \
		.coverage coverage.xml htmlcov/ notebooks/_build/
	find . -type d -name '__pycache__' -prune -exec rm -rf {} +
	find . -type d -name '*.egg-info' -prune -exec rm -rf {} +
	@echo "clean: build and cache artifacts removed."
	@echo "       data/raw/ (private precise reports) and $(PUBLISHED_DIR) left untouched."
