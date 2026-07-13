/* Auditable nationwide FARS context — framework-free, bilingual, and driven
 * only by the checked-in public projection. Suppressed cells never acquire a
 * numeric value in this UI: absence remains an explicit publication status. */
(function () {
  "use strict";

  var DATA_URL = "../data/published/fars-2024-state-mode.json";
  var EXPECTED_MODES = [
    "motor_vehicle_occupant",
    "motorcyclist",
    "pedalcyclist",
    "pedestrian",
    "other_road_user",
    "unknown",
  ];
  var EXPECTED_SCHEMA_VERSION = "1.0.0";
  var EXPECTED_ARTIFACT_TYPE = "nearmiss.public.fars_state_context";
  var EXPECTED_TITLE = "2024 US fatal-crash burden by state and involved mode";
  var EXPECTED_SOURCE_URL = "https://static.nhtsa.gov/nhtsa/downloads/FARS/2024/National/FARS2024NationalCSV.zip";
  var EXPECTED_SOURCE_REVISION = "reviewed-20260712-5112727a8c0d";
  var EXPECTED_SOURCE_SIZE = 32672161;
  var EXPECTED_SOURCE_SHA256 = "5112727a8c0dc91ffee27ca05bddb073934f2d192ce4fae997da767dccdbe04f";
  var EXPECTED_PUBLIC_ARTIFACT_BYTES = 27590;
  var EXPECTED_PUBLIC_ARTIFACT_SHA256 = "29b5dc2673987cc7bedd0a83b2147e724e1fb2a2cb1458053af3d017ac8d6578";
  var EXPECTED_CROSSWALK_VERSION = "fars-usps-50-states-dc-2024-v1";
  var EXPECTED_CROSSWALK_SHA256 = "6744b12717b0bd52a79c73aba3037286dde9257698a2aa0630f995c8a82ba25c";
  var EXPECTED_ALGORITHM_VERSION = "state-involved-mode-v1";
  var EXPECTED_GEOGRAPHY_COVERAGE = "official_2024_national_50_states_and_dc";
  var EXPECTED_ACCOUNTING = {
    case_count: 36127,
    state_count: 51,
    state_mode_cell_count: 306,
    published_cell_count: 206,
    suppressed_or_zero_cell_count: 100,
    positive_candidate_cell_count: 292,
    positive_suppressed_cell_count: 86,
    crash_contribution_total: 48524,
    published_crash_contribution_total: 48154,
    suppressed_crash_contribution_total: 370,
  };
  var EXPECTED_CAVEAT =
    "Counts are distinct 2024 FARS fatal crashes with at least one person in the involved mode, " +
    "counted at most once per crash per mode. They are fatal-crash burden context, not " +
    "exposure-normalized risk, incidence, causation, nonfatal crashes, near misses, record " +
    "linkage, outcome validation, or a safety ranking. Mode cells overlap and are non-additive. " +
    "A suppressed_or_zero cell combines a true zero with a positive count below k=10 and must " +
    "never be read as zero. k=10 is a stability and publication guard for already-public FARS " +
    "data, not a confidentiality guarantee. The official 2024 National archive covers the 50 states and District " +
    "of Columbia; Puerto Rico requires a separately verified source.";
  var EXPECTED_STATES = [
    "1|AL|Alabama",
    "2|AK|Alaska",
    "4|AZ|Arizona",
    "5|AR|Arkansas",
    "6|CA|California",
    "8|CO|Colorado",
    "9|CT|Connecticut",
    "10|DE|Delaware",
    "11|DC|District of Columbia",
    "12|FL|Florida",
    "13|GA|Georgia",
    "15|HI|Hawaii",
    "16|ID|Idaho",
    "17|IL|Illinois",
    "18|IN|Indiana",
    "19|IA|Iowa",
    "20|KS|Kansas",
    "21|KY|Kentucky",
    "22|LA|Louisiana",
    "23|ME|Maine",
    "24|MD|Maryland",
    "25|MA|Massachusetts",
    "26|MI|Michigan",
    "27|MN|Minnesota",
    "28|MS|Mississippi",
    "29|MO|Missouri",
    "30|MT|Montana",
    "31|NE|Nebraska",
    "32|NV|Nevada",
    "33|NH|New Hampshire",
    "34|NJ|New Jersey",
    "35|NM|New Mexico",
    "36|NY|New York",
    "37|NC|North Carolina",
    "38|ND|North Dakota",
    "39|OH|Ohio",
    "40|OK|Oklahoma",
    "41|OR|Oregon",
    "42|PA|Pennsylvania",
    "44|RI|Rhode Island",
    "45|SC|South Carolina",
    "46|SD|South Dakota",
    "47|TN|Tennessee",
    "48|TX|Texas",
    "49|UT|Utah",
    "50|VT|Vermont",
    "51|VA|Virginia",
    "53|WA|Washington",
    "54|WV|West Virginia",
    "55|WI|Wisconsin",
    "56|WY|Wyoming",
  ];
  var lang = window.NearmissI18n.langFromQuery("en");
  var i18n = window.NearmissI18n.create("web.coverage.");
  var artifact = null;
  var rows = [];

  function t(key) {
    return i18n.t(key);
  }

  function tpl(text, values) {
    return text.replace(/\{(\w+)\}/g, function (_, key) {
      return values[key];
    });
  }

  function isObject(value) {
    return value !== null && typeof value === "object" && !Array.isArray(value);
  }

  function isNonNegativeInteger(value) {
    return Number.isInteger(value) && value >= 0;
  }

  function hasOwn(object, key) {
    return Object.prototype.hasOwnProperty.call(object, key);
  }

  function assert(condition, message) {
    if (!condition) throw new Error("Invalid public FARS artifact: " + message);
  }

  function assertExactKeys(object, expected, label) {
    assert(isObject(object), label + " must be an object");
    var actual = Object.keys(object).sort();
    var wanted = expected.slice().sort();
    assert(sameOrderedValues(actual, wanted), label + " has missing or unexpected fields");
  }

  function sameOrderedValues(actual, expected) {
    return (
      Array.isArray(actual) &&
      actual.length === expected.length &&
      actual.every(function (value, index) {
        return value === expected[index];
      })
    );
  }

  function validateAccounting(data, observed) {
    var accounting = data.accounting;
    var integerFields = [
      "case_count",
      "state_count",
      "state_mode_cell_count",
      "published_cell_count",
      "suppressed_or_zero_cell_count",
      "positive_candidate_cell_count",
      "positive_suppressed_cell_count",
      "crash_contribution_total",
      "published_crash_contribution_total",
      "suppressed_crash_contribution_total",
    ];
    assertExactKeys(accounting, integerFields, "accounting");
    integerFields.forEach(function (field) {
      assert(isNonNegativeInteger(accounting[field]), "accounting." + field + " must be a non-negative integer");
      assert(accounting[field] === EXPECTED_ACCOUNTING[field], "accounting." + field + " does not match the reviewed release");
    });
    assert(accounting.state_count === observed.states, "accounting state count does not match states");
    assert(accounting.state_mode_cell_count === observed.cells, "accounting cell count does not match cells");
    assert(accounting.published_cell_count === observed.published, "accounting published count does not match cells");
    assert(
      accounting.suppressed_or_zero_cell_count === observed.withheld,
      "accounting suppressed-or-zero count does not match cells"
    );
    assert(
      accounting.published_crash_contribution_total === observed.publishedContributions,
      "accounting published contributions do not match public counts"
    );
    assert(
      accounting.published_cell_count + accounting.suppressed_or_zero_cell_count === accounting.state_mode_cell_count,
      "accounting cell totals do not reconcile"
    );
    assert(
      accounting.positive_candidate_cell_count ===
        accounting.published_cell_count + accounting.positive_suppressed_cell_count,
      "accounting positive-cell totals do not reconcile"
    );
    assert(
      accounting.positive_suppressed_cell_count <= accounting.suppressed_or_zero_cell_count,
      "positive suppressed cells exceed suppressed-or-zero cells"
    );
    assert(
      accounting.suppressed_crash_contribution_total >= accounting.positive_suppressed_cell_count &&
        accounting.suppressed_crash_contribution_total <
          accounting.positive_suppressed_cell_count * data.metric.effective_k,
      "suppressed contribution total is inconsistent with k"
    );
    assert(
      accounting.published_crash_contribution_total + accounting.suppressed_crash_contribution_total ===
        accounting.crash_contribution_total,
      "accounting contribution totals do not reconcile"
    );
  }

  function validateArtifact(data) {
    assertExactKeys(
      data,
      ["schema_version", "artifact_type", "visibility", "title", "dataset_year", "source", "geography", "metric", "accounting", "caveat", "states"],
      "top level"
    );
    assert(data.visibility === "public", "visibility must be public");
    assert(data.dataset_year === 2024, "dataset year must be 2024");
    assert(data.schema_version === EXPECTED_SCHEMA_VERSION, "schema version is not supported");
    assert(data.artifact_type === EXPECTED_ARTIFACT_TYPE, "artifact type is not the public FARS context");
    assert(data.title === EXPECTED_TITLE, "artifact title is not the reviewed title");
    assert(data.caveat === EXPECTED_CAVEAT, "artifact caveat is not the reviewed caveat");

    assertExactKeys(
      data.source,
      ["name", "release_stage", "distribution_url", "source_revision_id", "raw_size_bytes", "raw_sha256"],
      "source"
    );
    assert(data.source.release_stage === "final", "only the final FARS release may be shown");
    assert(data.source.name === "NHTSA Fatality Analysis Reporting System (FARS)", "source name is not reviewed");
    assert(data.source.distribution_url === EXPECTED_SOURCE_URL, "source distribution URL does not match the reviewed archive");
    assert(data.source.source_revision_id === EXPECTED_SOURCE_REVISION, "source revision is not reviewed");
    assert(data.source.raw_size_bytes === EXPECTED_SOURCE_SIZE, "source byte size does not match the reviewed archive");
    assert(data.source.raw_sha256 === EXPECTED_SOURCE_SHA256, "source checksum does not match the reviewed archive");

    assertExactKeys(
      data.geography,
      ["type", "coverage", "state_count", "state_crosswalk_version", "state_crosswalk_sha256"],
      "geography"
    );
    assert(data.geography.type === "fars_state_code", "geography must use source-native FARS state codes");
    assert(data.geography.coverage === EXPECTED_GEOGRAPHY_COVERAGE, "coverage must be the official 2024 National 50-states-and-DC archive");
    assert(data.geography.state_count === 51, "coverage must contain 51 jurisdictions");
    assert(data.geography.state_crosswalk_version === EXPECTED_CROSSWALK_VERSION, "state crosswalk version is not reviewed");
    assert(data.geography.state_crosswalk_sha256 === EXPECTED_CROSSWALK_SHA256, "state crosswalk checksum is not reviewed");

    assertExactKeys(
      data.metric,
      ["algorithm_version", "dimension", "contribution_unit", "effective_k", "modes_non_additive", "modes"],
      "metric"
    );
    assert(data.metric.algorithm_version === EXPECTED_ALGORITHM_VERSION, "metric algorithm is not reviewed");
    assert(data.metric.dimension === "involved_mode", "metric dimension must be involved mode");
    assert(
      data.metric.contribution_unit === "distinct_crash_once_per_involved_mode",
      "metric contribution unit is not supported"
    );
    assert(data.metric.modes_non_additive === true, "mode counts must be marked non-additive");
    assert(data.metric.effective_k === 10, "effective k must equal the reviewed publication floor of 10");
    assert(sameOrderedValues(data.metric.modes, EXPECTED_MODES), "mode inventory or order is unexpected");

    assert(Array.isArray(data.states) && data.states.length === 51, "states must contain 50 states and DC");
    var observed = { states: data.states.length, cells: 0, published: 0, withheld: 0, publishedContributions: 0 };

    data.states.forEach(function (state, stateIndex) {
      assertExactKeys(state, ["state_code", "state_abbreviation", "state_name", "cells"], "state");
      assert(typeof state.state_code === "string", "state code must remain a source-native string");
      assert(typeof state.state_abbreviation === "string", "state abbreviation must be a string");
      assert(typeof state.state_name === "string", "state name must be a string");
      assert(
        [state.state_code, state.state_abbreviation, state.state_name].join("|") === EXPECTED_STATES[stateIndex],
        "state crosswalk or canonical ordering does not match the reviewed inventory"
      );

      assert(Array.isArray(state.cells) && state.cells.length === EXPECTED_MODES.length, "each state needs six mode cells");
      var cellModes = [];
      state.cells.forEach(function (cell) {
        assert(isObject(cell), "each cell must be an object");
        cellModes.push(cell.involved_mode);
        observed.cells += 1;
        if (cell.status === "published") {
          assertExactKeys(cell, ["involved_mode", "status", "crash_count"], "published cell");
          assert(
            isNonNegativeInteger(cell.crash_count) && cell.crash_count >= data.metric.effective_k,
            "published counts must meet effective k"
          );
          observed.published += 1;
          observed.publishedContributions += cell.crash_count;
        } else {
          assertExactKeys(cell, ["involved_mode", "status"], "suppressed-or-zero cell");
          assert(cell.status === "suppressed_or_zero", "cell status is not supported");
          assert(!hasOwn(cell, "crash_count"), "suppressed-or-zero cells must not contain a count");
          observed.withheld += 1;
        }
      });
      assert(sameOrderedValues(cellModes, EXPECTED_MODES), "each state's cells must follow the canonical mode order");
    });

    validateAccounting(data, observed);
    return data;
  }

  function verifiedArtifact(response) {
    var payload;
    if (!response.ok) throw new Error("HTTP " + response.status);
    assert(typeof response.arrayBuffer === "function", "artifact response cannot provide exact bytes");
    return response
      .arrayBuffer()
      .then(function (buffer) {
        payload = buffer;
        assert(payload && payload.byteLength === EXPECTED_PUBLIC_ARTIFACT_BYTES, "artifact byte length is not reviewed");
        assert(
          window.crypto && window.crypto.subtle && typeof window.crypto.subtle.digest === "function",
          "Web Crypto SHA-256 support is required"
        );
        return window.crypto.subtle.digest("SHA-256", payload);
      })
      .then(function (digest) {
        var actual = Array.from(new Uint8Array(digest))
          .map(function (byte) {
            return byte.toString(16).padStart(2, "0");
          })
          .join("");
        assert(actual === EXPECTED_PUBLIC_ARTIFACT_SHA256, "artifact SHA-256 is not the reviewed release");
        assert(typeof window.TextDecoder === "function", "UTF-8 decoder support is required");
        return JSON.parse(new window.TextDecoder("utf-8", { fatal: true }).decode(payload));
      });
  }

  function flatten(data) {
    var output = [];
    data.states.forEach(function (state) {
      state.cells.forEach(function (cell) {
        output.push({
          year: data.dataset_year,
          stateCode: state.state_code,
          stateAbbreviation: state.state_abbreviation,
          stateName: state.state_name,
          mode: cell.involved_mode,
          status: cell.status,
          count: cell.status === "published" ? cell.crash_count : null,
        });
      });
    });
    return output;
  }

  function modeLabel(mode) {
    return t("mode_" + mode);
  }

  function number(value) {
    return new Intl.NumberFormat(lang).format(value);
  }

  function cell(tag, value, className) {
    var element = document.createElement(tag);
    element.textContent = value;
    if (className) element.className = className;
    return element;
  }

  function selectedRows() {
    var state = document.getElementById("state-filter").value;
    var mode = document.getElementById("mode-filter").value;
    var status = document.getElementById("status-filter").value;
    return rows.filter(function (row) {
      return (!state || row.stateAbbreviation === state) && (!mode || row.mode === mode) && (!status || row.status === status);
    });
  }

  function renderTable() {
    if (!artifact) return;
    var selected = selectedRows();
    var body = document.getElementById("coverage-body");
    body.textContent = "";

    if (!selected.length) {
      var emptyRow = document.createElement("tr");
      var emptyCell = cell("td", t("no_results"));
      emptyCell.colSpan = 5;
      emptyRow.appendChild(emptyCell);
      body.appendChild(emptyRow);
    }

    selected.forEach(function (row) {
      var tr = document.createElement("tr");
      tr.dataset.status = row.status;
      tr.dataset.state = row.stateAbbreviation;
      tr.dataset.mode = row.mode;
      tr.appendChild(cell("td", String(row.year)));
      var stateHeader = cell("th", row.stateName + " (" + row.stateAbbreviation + ")");
      stateHeader.scope = "row";
      tr.appendChild(stateHeader);
      tr.appendChild(cell("td", modeLabel(row.mode)));
      var statusText = row.status === "published" ? t("cell_published") : t("cell_not_published");
      var statusCell = document.createElement("td");
      statusCell.appendChild(
        cell("span", statusText, "cell-status" + (row.status === "published" ? "" : " is-withheld"))
      );
      tr.appendChild(statusCell);
      tr.appendChild(cell("td", row.status === "published" ? number(row.count) : "—", "count-cell"));
      body.appendChild(tr);
    });

    var values = { shown: number(selected.length), total: number(rows.length) };
    document.getElementById("coverage-caption").textContent = tpl(t("caption"), values);
    document.getElementById("coverage-status").textContent = tpl(t("result_summary"), values);
  }

  function renderControls() {
    var stateSelect = document.getElementById("state-filter");
    var selectedState = stateSelect.value;
    while (stateSelect.options.length > 1) stateSelect.remove(1);
    artifact.states.forEach(function (state) {
      var option = document.createElement("option");
      option.value = state.state_abbreviation;
      option.textContent = state.state_name + " (" + state.state_abbreviation + ")";
      stateSelect.appendChild(option);
    });
    stateSelect.value = selectedState;

    var modeSelect = document.getElementById("mode-filter");
    var selectedMode = modeSelect.value;
    while (modeSelect.options.length > 1) modeSelect.remove(1);
    EXPECTED_MODES.forEach(function (mode) {
      var option = document.createElement("option");
      option.value = mode;
      option.textContent = modeLabel(mode);
      modeSelect.appendChild(option);
    });
    modeSelect.value = selectedMode;
  }

  function renderMetadata() {
    document.getElementById("summary-year").textContent = String(artifact.dataset_year);
    document.getElementById("summary-scope").textContent = t("scope_value");
    document.getElementById("summary-threshold").textContent = "k = " + number(artifact.metric.effective_k);
    document.getElementById("summary-retention").textContent = tpl(t("retention_value"), {
      published: number(artifact.accounting.published_crash_contribution_total),
      total: number(artifact.accounting.crash_contribution_total),
    });
    var source = document.getElementById("official-source");
    source.href = artifact.source.distribution_url;
    source.textContent = artifact.source.name;
    document.getElementById("source-revision").textContent = artifact.source.source_revision_id;
  }

  function applyTranslations() {
    document.documentElement.lang = lang;
    document.title = t("title");
    document.querySelectorAll("[data-i18n]").forEach(function (element) {
      element.innerHTML = t(element.getAttribute("data-i18n"));
    });
    document.querySelectorAll("[data-lang]").forEach(function (button) {
      button.setAttribute("aria-pressed", button.getAttribute("data-lang") === lang ? "true" : "false");
    });
    if (artifact) {
      renderControls();
      renderMetadata();
      renderTable();
    }
  }

  function showError() {
    var status = document.getElementById("coverage-status");
    status.textContent = t("load_error");
    status.classList.add("is-error");
    var body = document.getElementById("coverage-body");
    body.textContent = "";
    var row = document.createElement("tr");
    var message = cell("td", t("load_error"));
    message.colSpan = 5;
    row.appendChild(message);
    body.appendChild(row);
    document.getElementById("coverage-caption").textContent = t("caption_error");
  }

  function bindEvents() {
    document.getElementById("coverage-filters").addEventListener("submit", function (event) {
      event.preventDefault();
    });
    document.getElementById("coverage-filters").addEventListener("change", renderTable);
    document.getElementById("coverage-filters").addEventListener("reset", function () {
      window.setTimeout(renderTable, 0);
    });
    document.querySelectorAll("[data-lang]").forEach(function (button) {
      button.addEventListener("click", function () {
        var next = button.getAttribute("data-lang");
        i18n.load(next).then(function () {
          lang = next;
          i18n.setLang(lang);
          applyTranslations();
        });
      });
    });
  }

  window.NearmissUSCoverage = {
    validateArtifact: validateArtifact,
    dataUrl: DATA_URL,
  };

  bindEvents();
  Promise.all([i18n.load("en"), i18n.load(lang)])
    .then(function () {
      i18n.setLang(lang);
      applyTranslations();
      return fetch(DATA_URL);
    })
    .then(function (response) {
      return verifiedArtifact(response);
    })
    .then(function (data) {
      artifact = validateArtifact(data);
      rows = flatten(artifact);
      document.getElementById("coverage-status").classList.remove("is-error");
      applyTranslations();
    })
    .catch(showError);
})();
