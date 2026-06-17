# ---------------------------------------------------------------------------
# nearmiss — Makefile
#
# The dataset and the analysis are the product, not an app. These targets are
# the operator surface for the architecture stages described in the README:
#
#   intake.py -> pipeline/ -> exposure.py -> stats/ -> publish.py -> brief.py -> server.py
#
# Every target is .PHONY (it names a job, not a file) and self-documents via
# the trailing `##` comment that `make help` greps. Commands are realistic for
# the documented stack (Python 3.11+, ruff, mypy --strict, pytest, a
# framework-free WCAG 2.2 AA web map, axe, pip-audit, gitleaks).
#
# Hard-rule reminders baked into these targets:
#   HR4 (privacy): `clean` NEVER deletes data/raw/ — precise raw reports are
#                  private and gitignored, and a clean must not destroy them.
#   HR5 (reproducible): `reproduce` regenerates EVERY brief figure and table
#                  from raw inputs; nothing published is hand-edited.
# ---------------------------------------------------------------------------

# Use bash with strict flags so a failing step in a recipe actually fails.
SHELL := bash
.SHELLFLAGS := -eu -o pipefail -c

# Tools — overridable on the command line (e.g. `make test PYTHON=python3.11`).
PYTHON  ?= python
PIP     ?= $(PYTHON) -m pip
PACKAGE := nearmiss
PKG_SRC := src/$(PACKAGE)
NPM     ?= npm

# Published, open artifacts (committed). Aggregated + jittered only; see
# schema/dataset.schema.md. data/raw/ is private and never appears here.
PUBLISHED_DIR  := data/published
PUBLISHED_GEO  := $(PUBLISHED_DIR)/nearmiss.geojson

# Built web map (gitignored output of the framework-free WCAG 2.2 AA UI).
WEB_DIST := web/dist

# `make` with no target prints help. Help must stay first and stay cheap.
.DEFAULT_GOAL := help

.PHONY: help install lock lint type test accessibility security verify \
        reproduce demo publish clean

help: ## Show this help — every target with its description
	@echo "nearmiss — open dataset + honest analysis of road near-misses"
	@echo ""
	@echo "Usage: make <target>"
	@echo ""
	@grep -hE '^[a-zA-Z0-9_-]+:.*?## ' $(MAKEFILE_LIST) \
		| sort \
		| awk 'BEGIN {FS = ":.*?## "} {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

install: ## Install the package (editable) with dev extras and pre-commit hooks
	$(PIP) install -e ".[dev]"
	pre-commit install

lock: ## Generate the hashed reproducible-install lockfile (requirements.lock)
	pip-compile --generate-hashes -o requirements.lock pyproject.toml
	@echo "lock: wrote requirements.lock (generated; do not edit by hand)."

lint: ## Lint with ruff (style + import order + bugbear), no autofix
	ruff check $(PKG_SRC) tests
	ruff format --check $(PKG_SRC) tests

type: ## Type-check with mypy --strict (no untyped escape hatches)
	mypy --strict $(PKG_SRC) tests

test: ## Run pytest against synthetic fixtures with KNOWN planted-hotspot answers
	pytest -q

accessibility: ## Build the web map and run axe on it (WCAG 2.2 AA merge gate)
	$(NPM) --prefix web ci
	$(NPM) --prefix web run build
	$(NPM) --prefix web run test:axe
	@echo "axe automated checks passed."
	@echo "NOTE: the merge gate also requires manual NVDA + VoiceOver review;"
	@echo "      see docs/accessibility/ACR.md (axe alone is necessary, not sufficient)."

security: ## Scan deps (pip-audit) and history for secrets (gitleaks)
	pip-audit --strict
	gitleaks detect --no-banner --redact --source .

verify: lint type test accessibility security ## Full merge gate: lint + type + test + accessibility + security
	@echo "verify: all merge gates green (lint, type, test, accessibility, security)."

reproduce: ## HR5: regenerate EVERY brief figure and table from raw inputs (deterministic)
	$(PYTHON) -m $(PACKAGE).pipeline  --input tests/fixtures  # dedupe -> geocode -> snap -> classify -> quality
	$(PYTHON) -m $(PACKAGE).exposure      # attach denominators (records source + date)
	$(PYTHON) -m $(PACKAGE).stats         # rates+CIs, bias, KDE, Getis-Ord Gi*
	jupyter nbconvert --to notebook --execute --inplace \
		--ExecutePreprocessor.timeout=1800 notebooks/*.ipynb
	$(PYTHON) -m $(PACKAGE).brief --check-figures-up-to-date
	@echo "reproduce: all brief figures and tables rebuilt from raw inputs."

demo: ## Demonstrability: run the pipeline over fixtures and render a sample brief
	$(PYTHON) -m $(PACKAGE).pipeline  --input tests/fixtures --out build/demo
	$(PYTHON) -m $(PACKAGE).exposure  --in build/demo
	$(PYTHON) -m $(PACKAGE).stats     --in build/demo
	$(PYTHON) -m $(PACKAGE).publish   --in build/demo --out build/demo/published
	$(PYTHON) -m $(PACKAGE).brief     --in build/demo --out build/demo/brief.md
	@echo "demo: sample brief written to build/demo/brief.md"
	@echo "      (recovers the planted hotspots from tests/fixtures — known answers)."

publish: ## Build open GeoJSON + aggregated/jittered public dataset + hashed data card
	$(PYTHON) -m $(PACKAGE).publish --out $(PUBLISHED_DIR) --jitter --aggregate
	$(PYTHON) -m $(PACKAGE).publish --verify-no-precise-reports $(PUBLISHED_GEO)
	@echo "publish: wrote $(PUBLISHED_GEO) + hashed manifest + data card."
	@echo "         HR4 check passed: no raw precise report leaked into the public artifact."

clean: ## Remove build/test/cache artifacts and the web build — NEVER data/raw/ (HR4)
	rm -rf build/ dist/ $(WEB_DIST) web/node_modules \
		.pytest_cache/ .mypy_cache/ .ruff_cache/ \
		.coverage coverage.xml htmlcov/ notebooks/_build/
	find . -type d -name '__pycache__' -prune -exec rm -rf {} +
	find . -type d -name '*.egg-info' -prune -exec rm -rf {} +
	@echo "clean: build and cache artifacts removed."
	@echo "       data/raw/ (private precise reports) and $(PUBLISHED_DIR) left untouched."
