/* Auditable nationwide FARS context — framework-free, bilingual, and driven
 * only by a hash-bound release index and its checked-in public projections.
 * Suppressed cells never acquire a numeric value in this UI. */
(function () {
  "use strict";

  var INDEX_URL = "/data/published/fars-state-mode-index-v2.json";
  var DATA_ROOT = "/data/published/";
  var DEFAULT_2024_DATA_URL = DATA_ROOT + "fars-2024-state-mode-r2.json";
  var EXPECTED_INDEX_BYTES = 5273;
  var EXPECTED_INDEX_SHA256 = "594b13a65f5b88661db8acb21c73fc55ddc61ba94e5a659cdd27463c178f50f5";
  var SUPPORTED_YEARS = [2020, 2021, 2022, 2023, 2024];
  var EXPECTED_MODES = [
    "motor_vehicle_occupant",
    "motorcyclist",
    "pedalcyclist",
    "pedestrian",
    "other_road_user",
    "unknown",
  ];
  var EXPECTED_INDEX_SCHEMA_VERSION = "1.0.0";
  var EXPECTED_INDEX_ARTIFACT_TYPE = "nearmiss.public.fars_state_context_index";
  var EXPECTED_ARTIFACT_SCHEMA_VERSION = "1.0.0";
  var EXPECTED_ARTIFACT_TYPE = "nearmiss.public.fars_state_context";
  var EXPECTED_ALGORITHM_VERSION = "state-involved-mode-v1";
  var EXPECTED_YEAR_CONTRACTS = {
    2020: {
      contract_revision: 1,
      contract_sha256: "c6294413066bb2e83b2aea02408dcfa2fa40441dda7de115983a45fb8aab132c",
      crash_mapping_version: "1.0.0",
      person_mapping_version: "1.0.0",
      semantic_regime_id: "fars_per_typ_2020_2021_v1",
      state_code_system: "nhtsa_fars_state_2020",
    },
    2021: {
      contract_revision: 1,
      contract_sha256: "5c2c198cd4e3eee80f9e27874e3f42521b0e0b7cbc53a8bd0bf2684ef66a855e",
      crash_mapping_version: "1.0.0",
      person_mapping_version: "1.0.0",
      semantic_regime_id: "fars_per_typ_2020_2021_v1",
      state_code_system: "nhtsa_fars_state_2021",
    },
    2022: {
      contract_revision: 1,
      contract_sha256: "18713f23f657334459febf729e4005bfd9e94492da37afb0255d9e5fd4159158",
      crash_mapping_version: "1.0.0",
      person_mapping_version: "1.0.0",
      semantic_regime_id: "fars_per_typ_2022_2024_v1",
      state_code_system: "nhtsa_fars_state_2022",
    },
    2023: {
      contract_revision: 1,
      contract_sha256: "557a8edf2418c7794d349c932ae2237db6cad7165f62c80a2e7f3b15baeca143",
      crash_mapping_version: "1.0.0",
      person_mapping_version: "1.0.0",
      semantic_regime_id: "fars_per_typ_2022_2024_v1",
      state_code_system: "nhtsa_fars_state_2023",
    },
    2024: {
      contract_revision: 2,
      contract_sha256: "2a24d2cad5341a8ffbe77272b59ccaf0c983a2e9beb763551bb3df7f4ef02b63",
      crash_mapping_version: "1.0.0",
      person_mapping_version: "1.0.0",
      semantic_regime_id: "fars_per_typ_2022_2024_v1",
      state_code_system: "nhtsa_fars_state_2024",
    },
  };
  var EXPECTED_RELEASE_STAGES = {
    2020: "final",
    2021: "final",
    2022: "final",
    2023: "final",
    2024: "annual_report_file",
  };
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
  var releaseIndex = null;
  var currentRelease = null;
  var artifact = null;
  var rows = [];
  var artifactPromises = {};
  var profileArtifacts = null;
  var profileState = "";
  var requestSerial = 0;
  var profileRequestSerial = 0;
  var languageRequestSerial = 0;

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
    if (!condition) throw new Error("Invalid public FARS release: " + message);
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

  function isSha256(value) {
    return typeof value === "string" && /^[0-9a-f]{64}$/.test(value);
  }

  function isSupportedYear(value) {
    return Number.isInteger(value) && SUPPORTED_YEARS.indexOf(value) >= 0;
  }

  function stateParts(value) {
    var parts = value.split("|");
    return { code: parts[0], abbreviation: parts[1], name: parts[2] };
  }

  function stateDefinition(abbreviation) {
    return (
      EXPECTED_STATES.map(stateParts).find(function (state) {
        return state.abbreviation === abbreviation;
      }) || null
    );
  }

  function isValidState(abbreviation) {
    return typeof abbreviation === "string" && stateDefinition(abbreviation) !== null;
  }

  function expectedSourceUrl(year) {
    return (
      "https://static.nhtsa.gov/nhtsa/downloads/FARS/" +
      year +
      "/National/FARS" +
      year +
      "NationalCSV.zip"
    );
  }

  function expectedTitle(year) {
    return year + " US fatal-crash burden by state and involved mode";
  }

  function expectedCaveat(year) {
    return (
      "Counts are distinct " +
      year +
      " FARS fatal crashes with at least one person in the involved mode, " +
      "counted at most once per crash per mode. They are fatal-crash burden context, not " +
      "exposure-normalized risk, incidence, causation, nonfatal crashes, near misses, record " +
      "linkage, outcome validation, or a safety ranking. Mode cells overlap and are non-additive. " +
      "A suppressed_or_zero cell combines a true zero with a positive count below k=10 and must " +
      "never be read as zero. k=10 is a stability and publication guard for already-public FARS " +
      "data, not a confidentiality guarantee. The official " +
      year +
      " National archive covers the 50 states and District " +
      "of Columbia; Puerto Rico requires a separately verified source."
    );
  }

  function validateIndex(data) {
    assertExactKeys(
      data,
      ["schema_version", "artifact_type", "visibility", "default_year", "contract", "releases"],
      "release index"
    );
    assert(data.schema_version === EXPECTED_INDEX_SCHEMA_VERSION, "index schema version is unsupported");
    assert(data.artifact_type === EXPECTED_INDEX_ARTIFACT_TYPE, "index artifact type is unsupported");
    assert(data.visibility === "public", "index visibility must be public");

    var contract = data.contract;
    assertExactKeys(
      contract,
      [
        "algorithm_version",
        "artifact_schema_version",
        "artifact_type",
        "contribution_unit",
        "dimension",
        "effective_k",
        "modes",
        "modes_non_additive",
        "state_count",
      ],
      "index contract"
    );
    assert(contract.algorithm_version === EXPECTED_ALGORITHM_VERSION, "index algorithm is unsupported");
    assert(contract.artifact_schema_version === EXPECTED_ARTIFACT_SCHEMA_VERSION, "artifact schema is unsupported");
    assert(contract.artifact_type === EXPECTED_ARTIFACT_TYPE, "indexed artifact type is unsupported");
    assert(contract.contribution_unit === "distinct_crash_once_per_involved_mode", "contribution unit is unsupported");
    assert(contract.dimension === "involved_mode", "index dimension is unsupported");
    assert(contract.effective_k === 10, "index publication floor is unsupported");
    assert(contract.modes_non_additive === true, "index must mark modes non-additive");
    assert(contract.state_count === 51, "index must cover 50 states and DC");
    assert(sameOrderedValues(contract.modes, EXPECTED_MODES), "index mode inventory is unsupported");

    assert(Array.isArray(data.releases) && data.releases.length >= 1 && data.releases.length <= 5, "index release inventory is invalid");
    var years = [];
    data.releases.forEach(function (release) {
      assertExactKeys(
        release,
        ["artifact_bytes", "artifact_path", "artifact_sha256", "contract", "dataset_year", "geography", "source"],
        "index release"
      );
      var year = release.dataset_year;
      assert(isSupportedYear(year), "release year is not supported");
      years.push(year);
      assert(
        Number.isInteger(release.artifact_bytes) && release.artifact_bytes >= 1 && release.artifact_bytes <= 262144,
        "release byte length is invalid"
      );
      assert(isSha256(release.artifact_sha256), "release artifact digest is invalid");

      assertExactKeys(
        release.contract,
        [
          "contract_revision",
          "contract_sha256",
          "crash_mapping_version",
          "person_mapping_version",
          "semantic_regime_id",
          "state_code_system",
        ],
        "release annual contract"
      );
      assert(
        Object.keys(EXPECTED_YEAR_CONTRACTS[year]).every(function (field) {
          return release.contract[field] === EXPECTED_YEAR_CONTRACTS[year][field];
        }),
        "release annual contract provenance is not reviewed"
      );
      var expectedPath =
        "fars-" +
        year +
        "-state-mode" +
        (release.contract.contract_revision === 1 ? "" : "-r" + release.contract.contract_revision) +
        ".json";
      assert(release.artifact_path === expectedPath, "release path is not canonical");

      assertExactKeys(
        release.source,
        ["distribution_url", "raw_sha256", "raw_size_bytes", "source_revision_id"],
        "release source"
      );
      assert(release.source.distribution_url === expectedSourceUrl(year), "release source URL is not fixed-year National FARS");
      assert(isSha256(release.source.raw_sha256), "release raw digest is invalid");
      assert(
        Number.isInteger(release.source.raw_size_bytes) &&
          release.source.raw_size_bytes >= 1 &&
          release.source.raw_size_bytes <= 268435456,
        "release raw byte size is invalid"
      );
      assert(
        typeof release.source.source_revision_id === "string" &&
          /^reviewed-[0-9]{8}-[0-9a-f]{12}$/.test(release.source.source_revision_id),
        "release source revision is invalid"
      );

      assertExactKeys(
        release.geography,
        ["coverage", "state_crosswalk_sha256", "state_crosswalk_version"],
        "release geography"
      );
      assert(
        release.geography.coverage === "official_" + year + "_national_50_states_and_dc",
        "release geography coverage is invalid"
      );
      assert(
        release.geography.state_crosswalk_version === "fars-usps-50-states-dc-" + year + "-v1",
        "release crosswalk version is invalid"
      );
      assert(isSha256(release.geography.state_crosswalk_sha256), "release crosswalk digest is invalid");
    });
    assert(
      years.every(function (year, index) {
        return index === 0 || year > years[index - 1];
      }),
      "release years must be unique and ascending"
    );
    assert(data.default_year === years[years.length - 1], "default year must be the newest published release");
    return data;
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
    });
    assert(accounting.case_count >= 30000 && accounting.case_count <= 45000, "case count is outside the national bound");
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
      (accounting.positive_suppressed_cell_count === 0 && accounting.suppressed_crash_contribution_total === 0) ||
        (accounting.positive_suppressed_cell_count >= 2 &&
          accounting.suppressed_crash_contribution_total >= accounting.positive_suppressed_cell_count &&
          accounting.suppressed_crash_contribution_total <
            accounting.positive_suppressed_cell_count * data.metric.effective_k),
      "suppressed contribution total is inconsistent with k"
    );
    assert(
      accounting.published_crash_contribution_total + accounting.suppressed_crash_contribution_total ===
        accounting.crash_contribution_total,
      "accounting contribution totals do not reconcile"
    );
    assert(
      accounting.crash_contribution_total >= accounting.case_count &&
        accounting.crash_contribution_total <= accounting.case_count * EXPECTED_MODES.length,
      "accounting contributions are outside the case-count bound"
    );
  }

  function validateArtifact(data, release, contract) {
    assert(release && contract, "artifact validation requires its indexed release");
    assertExactKeys(
      data,
      ["schema_version", "artifact_type", "visibility", "title", "dataset_year", "source", "geography", "metric", "accounting", "caveat", "states"],
      "artifact top level"
    );
    var year = release.dataset_year;
    assert(data.visibility === "public", "artifact visibility must be public");
    assert(data.dataset_year === year, "artifact year does not match its index entry");
    assert(data.schema_version === contract.artifact_schema_version, "artifact schema version is unsupported");
    assert(data.artifact_type === contract.artifact_type, "artifact type is unsupported");
    assert(data.title === expectedTitle(year), "artifact title does not match its year");
    assert(data.caveat === expectedCaveat(year), "artifact caveat does not match its year");

    assertExactKeys(
      data.source,
      ["name", "release_stage", "distribution_url", "source_revision_id", "raw_size_bytes", "raw_sha256"],
      "artifact source"
    );
    assert(
      data.source.release_stage === EXPECTED_RELEASE_STAGES[year],
      "artifact release stage is not the reviewed annual stage"
    );
    assert(data.source.name === "NHTSA Fatality Analysis Reporting System (FARS)", "source name is unsupported");
    ["distribution_url", "source_revision_id", "raw_size_bytes", "raw_sha256"].forEach(function (field) {
      assert(data.source[field] === release.source[field], "artifact source." + field + " drifted from the index");
    });

    assertExactKeys(
      data.geography,
      ["type", "coverage", "state_count", "state_crosswalk_version", "state_crosswalk_sha256"],
      "artifact geography"
    );
    assert(data.geography.type === "fars_state_code", "geography must use source-native FARS state codes");
    assert(data.geography.state_count === contract.state_count, "geography must contain 50 states and DC");
    ["coverage", "state_crosswalk_version", "state_crosswalk_sha256"].forEach(function (field) {
      assert(data.geography[field] === release.geography[field], "artifact geography." + field + " drifted from the index");
    });

    assertExactKeys(
      data.metric,
      ["algorithm_version", "dimension", "contribution_unit", "effective_k", "modes_non_additive", "modes"],
      "artifact metric"
    );
    assert(data.metric.algorithm_version === contract.algorithm_version, "metric algorithm drifted from the index");
    assert(data.metric.dimension === contract.dimension, "metric dimension drifted from the index");
    assert(data.metric.contribution_unit === contract.contribution_unit, "metric contribution unit drifted from the index");
    assert(data.metric.modes_non_additive === contract.modes_non_additive, "mode additivity flag drifted from the index");
    assert(data.metric.effective_k === contract.effective_k, "publication floor drifted from the index");
    assert(sameOrderedValues(data.metric.modes, contract.modes), "mode inventory or order drifted from the index");

    assert(Array.isArray(data.states) && data.states.length === contract.state_count, "states must contain 50 states and DC");
    var observed = { states: data.states.length, cells: 0, published: 0, withheld: 0, publishedContributions: 0 };
    data.states.forEach(function (state, stateIndex) {
      assertExactKeys(state, ["state_code", "state_abbreviation", "state_name", "cells"], "artifact state");
      assert(typeof state.state_code === "string", "state code must remain a source-native string");
      assert(
        [state.state_code, state.state_abbreviation, state.state_name].join("|") === EXPECTED_STATES[stateIndex],
        "state crosswalk or canonical ordering is unsupported"
      );
      assert(Array.isArray(state.cells) && state.cells.length === contract.modes.length, "each state needs six mode cells");
      var cellModes = [];
      state.cells.forEach(function (cell) {
        assert(isObject(cell), "each cell must be an object");
        cellModes.push(cell.involved_mode);
        observed.cells += 1;
        if (cell.status === "published") {
          assertExactKeys(cell, ["involved_mode", "status", "crash_count"], "published cell");
          assert(
            isNonNegativeInteger(cell.crash_count) &&
              cell.crash_count >= data.metric.effective_k &&
              cell.crash_count <= data.accounting.case_count,
            "published count is outside its fixed-year bounds"
          );
          observed.published += 1;
          observed.publishedContributions += cell.crash_count;
        } else {
          assertExactKeys(cell, ["involved_mode", "status"], "suppressed-or-zero cell");
          assert(cell.status === "suppressed_or_zero", "cell status is unsupported");
          assert(!hasOwn(cell, "crash_count"), "suppressed-or-zero cells must not contain a count");
          observed.withheld += 1;
        }
      });
      assert(sameOrderedValues(cellModes, contract.modes), "state cells do not follow the canonical mode order");
    });
    validateAccounting(data, observed);
    return data;
  }

  function verifiedJson(response, expectedBytes, expectedSha256, label) {
    var payload;
    if (!response.ok) throw new Error("HTTP " + response.status);
    assert(typeof response.arrayBuffer === "function", label + " response cannot provide exact bytes");
    return response
      .arrayBuffer()
      .then(function (buffer) {
        payload = buffer;
        assert(payload && payload.byteLength === expectedBytes, label + " byte length is not reviewed");
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
        assert(actual === expectedSha256, label + " SHA-256 is not reviewed");
        assert(typeof window.TextDecoder === "function", "UTF-8 decoder support is required");
        return JSON.parse(new window.TextDecoder("utf-8", { fatal: true }).decode(payload));
      });
  }

  function loadArtifact(release) {
    var year = release.dataset_year;
    if (!hasOwn(artifactPromises, year)) {
      artifactPromises[year] = fetch(DATA_ROOT + release.artifact_path)
        .then(function (response) {
          return verifiedJson(response, release.artifact_bytes, release.artifact_sha256, "annual artifact");
        })
        .then(function (data) {
          return validateArtifact(data, release, releaseIndex.contract);
        })
        .catch(function (error) {
          delete artifactPromises[year];
          throw error;
        });
    }
    return artifactPromises[year];
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

  function clearProfileTable() {
    document.getElementById("profile-early-body").textContent = "";
    document.getElementById("profile-late-body").textContent = "";
    document.getElementById("state-profile-wrap").hidden = true;
  }

  function setProfileStatus(key, className) {
    var status = document.getElementById("state-profile-status");
    document
      .getElementById("state-profile")
      .setAttribute("aria-busy", className === "is-loading" ? "true" : "false");
    status.setAttribute("data-i18n", key);
    status.textContent = t(key);
    status.className = "state-profile-status" + (className ? " " + className : "");
  }

  function showProfileEmpty() {
    profileArtifacts = null;
    profileState = "";
    clearProfileTable();
    setProfileStatus("profile_empty", "");
  }

  function showProfileLoading() {
    profileArtifacts = null;
    profileState = "";
    clearProfileTable();
    setProfileStatus("profile_loading", "is-loading");
  }

  function showProfileError() {
    profileArtifacts = null;
    profileState = "";
    clearProfileTable();
    setProfileStatus("profile_error", "is-error");
  }

  function profileStateFromArtifact(data, abbreviation) {
    return (
      data.states.find(function (state) {
        return state.state_abbreviation === abbreviation;
      }) || null
    );
  }

  function renderRegimeGroup(body, labelKey, years) {
    body.textContent = "";
    var labelRow = document.createElement("tr");
    labelRow.className = "profile-regime-label";
    var label = cell("th", t(labelKey));
    label.id = body.id + "-label";
    label.colSpan = 7;
    label.scope = "rowgroup";
    body.setAttribute("aria-labelledby", label.id);
    labelRow.appendChild(label);
    body.appendChild(labelRow);

    years.forEach(function (year) {
      var data = profileArtifacts[year];
      var state = profileStateFromArtifact(data, profileState);
      assert(state, "selected profile state is missing from an annual artifact");
      var row = document.createElement("tr");
      row.className = "profile-year-row";
      row.dataset.year = String(year);
      row.appendChild(cell("th", String(year)));
      row.firstElementChild.scope = "row";
      EXPECTED_MODES.forEach(function (mode, modeIndex) {
        var result = state.cells[modeIndex];
        assert(result.involved_mode === mode, "profile mode order drifted after validation");
        var value;
        if (result.status === "published") {
          value = cell("td", number(result.crash_count), "profile-value");
        } else {
          value = cell("td", t("cell_not_published"), "profile-withheld");
        }
        value.dataset.status = result.status;
        value.dataset.mode = mode;
        row.appendChild(value);
      });
      body.appendChild(row);
    });
  }

  function renderStateProfile() {
    if (!profileArtifacts || !profileState) return;
    var definition = stateDefinition(profileState);
    assert(definition, "selected profile state is unsupported");
    renderRegimeGroup(
      document.getElementById("profile-early-body"),
      "profile_regime_early",
      [2020, 2021]
    );
    renderRegimeGroup(
      document.getElementById("profile-late-body"),
      "profile_regime_late",
      [2022, 2023, 2024]
    );
    var caption = document.getElementById("profile-caption");
    caption.removeAttribute("data-i18n");
    caption.textContent = tpl(t("profile_caption"), { state: definition.name });
    document.getElementById("state-profile-wrap").hidden = false;
    var status = document.getElementById("state-profile-status");
    status.removeAttribute("data-i18n");
    status.className = "state-profile-status is-ready";
    status.textContent = tpl(t("profile_ready"), { state: definition.name });
    document.getElementById("state-profile").setAttribute("aria-busy", "false");
  }

  function loadStateProfile(abbreviation) {
    var serial = ++profileRequestSerial;
    if (!abbreviation) {
      showProfileEmpty();
      return Promise.resolve();
    }
    if (!isValidState(abbreviation)) {
      showProfileError();
      return Promise.resolve();
    }
    showProfileLoading();
    return Promise.all(
      releaseIndex.releases.map(function (release) {
        return loadArtifact(release);
      })
    )
      .then(function (artifacts) {
        if (
          serial !== profileRequestSerial ||
          document.getElementById("state-filter").value !== abbreviation
        ) {
          return;
        }
        profileArtifacts = {};
        artifacts.forEach(function (data) {
          profileArtifacts[data.dataset_year] = data;
        });
        profileState = abbreviation;
        renderStateProfile();
      })
      .catch(function () {
        if (
          serial === profileRequestSerial &&
          document.getElementById("state-filter").value === abbreviation
        ) {
          showProfileError();
        }
      });
  }

  function selectedRows() {
    var state = document.getElementById("state-filter").value;
    var mode = document.getElementById("mode-filter").value;
    var status = document.getElementById("status-filter").value;
    if (!state) return [];
    return rows.filter(function (row) {
      return (
        row.stateAbbreviation === state &&
        (!mode || row.mode === mode) &&
        (!status || row.status === status)
      );
    });
  }

  function renderTable() {
    if (!artifact) return;
    var selectedState = document.getElementById("state-filter").value;
    var selected = selectedRows();
    var body = document.getElementById("coverage-body");
    var caption = document.getElementById("coverage-caption");
    var status = document.getElementById("coverage-status");
    body.textContent = "";
    if (!selectedState) {
      var directionRow = document.createElement("tr");
      var directionCell = cell("td", t("ledger_empty"));
      directionCell.colSpan = 5;
      directionRow.appendChild(directionCell);
      body.appendChild(directionRow);
      caption.setAttribute("data-i18n", "ledger_caption_empty");
      caption.textContent = t("ledger_caption_empty");
      status.setAttribute("data-i18n", "ledger_empty");
      status.textContent = t("ledger_empty");
      status.classList.remove("is-error");
      return;
    }
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
    var definition = stateDefinition(selectedState);
    var stateTotal = rows.filter(function (row) {
      return row.stateAbbreviation === selectedState;
    }).length;
    var values = {
      shown: number(selected.length),
      total: number(stateTotal),
      state: definition.name,
      year: String(artifact.dataset_year),
    };
    caption.removeAttribute("data-i18n");
    status.removeAttribute("data-i18n");
    caption.textContent = tpl(t("caption_state"), values);
    status.textContent = tpl(t("result_summary_state"), values);
  }

  function populateStateControl(selectedState) {
    var stateSelect = document.getElementById("state-filter");
    while (stateSelect.options.length > 1) stateSelect.remove(1);
    EXPECTED_STATES.map(stateParts).forEach(function (state) {
      var option = document.createElement("option");
      option.value = state.abbreviation;
      option.textContent = state.name + " (" + state.abbreviation + ")";
      stateSelect.appendChild(option);
    });
    stateSelect.value = selectedState;
  }

  function renderArtifactControls() {
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

  function populateYearControl(selectedYear) {
    var select = document.getElementById("year-filter");
    select.textContent = "";
    releaseIndex.releases.forEach(function (release) {
      var option = document.createElement("option");
      option.value = String(release.dataset_year);
      option.textContent = String(release.dataset_year);
      option.defaultSelected = release.dataset_year === releaseIndex.default_year;
      select.appendChild(option);
    });
    select.value = String(selectedYear);
  }

  function updateProofRail(selectedYear) {
    if (!releaseIndex) return;
    var published = new Set(
      releaseIndex.releases.map(function (release) {
        return release.dataset_year;
      })
    );
    document.querySelectorAll(".proof-rail li[data-year]").forEach(function (item) {
      var year = Number(item.getAttribute("data-year"));
      var result = item.querySelector(".proof-result");
      var isPublished = published.has(year);
      item.classList.toggle("is-current", year === selectedYear);
      result.classList.toggle("is-pending", !isPublished);
      result.setAttribute("data-i18n", isPublished ? "result_published" : "result_pending");
      result.textContent = t(isPublished ? "result_published" : "result_pending");
    });
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
    document.getElementById("release-stage").textContent = t("release_stage_" + artifact.source.release_stage);
    document.getElementById("semantic-regime").textContent = currentRelease.contract.semantic_regime_id;
    document.getElementById("mapping-versions").textContent = tpl(t("mapping_value"), {
      crash: currentRelease.contract.crash_mapping_version,
      person: currentRelease.contract.person_mapping_version,
    });
    document.getElementById("state-code-system").textContent = currentRelease.contract.state_code_system;
    document.getElementById("annual-contract").textContent = tpl(t("contract_value"), {
      revision: number(currentRelease.contract.contract_revision),
      sha: currentRelease.contract.contract_sha256,
    });
    document.getElementById("artifact-download").href = DATA_ROOT + currentRelease.artifact_path;
  }

  function clearMetadata() {
    [
      "summary-year",
      "summary-scope",
      "summary-threshold",
      "summary-retention",
      "source-revision",
      "release-stage",
      "semantic-regime",
      "mapping-versions",
      "state-code-system",
      "annual-contract",
    ].forEach(function (id) {
      document.getElementById(id).textContent = "—";
    });
    var source = document.getElementById("official-source");
    source.removeAttribute("href");
    source.textContent = "—";
    document.getElementById("artifact-download").removeAttribute("href");
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
    updateProofRail(currentRelease ? currentRelease.dataset_year : null);
    if (artifact) {
      renderArtifactControls();
      renderMetadata();
      renderTable();
    }
    if (profileArtifacts && profileState) renderStateProfile();
  }

  function showLoading() {
    artifact = null;
    rows = [];
    clearMetadata();
    var status = document.getElementById("coverage-status");
    status.setAttribute("data-i18n", "loading");
    status.textContent = t("loading");
    status.classList.remove("is-error");
    var body = document.getElementById("coverage-body");
    body.textContent = "";
    var row = document.createElement("tr");
    var message = cell("td", t("loading"));
    message.setAttribute("data-i18n", "loading");
    message.colSpan = 5;
    row.appendChild(message);
    body.appendChild(row);
    var caption = document.getElementById("coverage-caption");
    caption.setAttribute("data-i18n", "caption_loading");
    caption.textContent = t("caption_loading");
  }

  function showError() {
    artifact = null;
    rows = [];
    clearMetadata();
    var status = document.getElementById("coverage-status");
    status.setAttribute("data-i18n", "load_error");
    status.textContent = t("load_error");
    status.classList.add("is-error");
    var body = document.getElementById("coverage-body");
    body.textContent = "";
    var row = document.createElement("tr");
    var message = cell("td", t("load_error"));
    message.setAttribute("data-i18n", "load_error");
    message.colSpan = 5;
    row.appendChild(message);
    body.appendChild(row);
    var caption = document.getElementById("coverage-caption");
    caption.setAttribute("data-i18n", "caption_error");
    caption.textContent = t("caption_error");
  }

  function releaseForYear(year) {
    if (!releaseIndex) return null;
    return (
      releaseIndex.releases.find(function (release) {
        return release.dataset_year === year;
      }) || null
    );
  }

  function requestedYear() {
    var params = new URLSearchParams(window.location.search);
    if (!params.has("year")) return releaseIndex.default_year;
    var values = params.getAll("year");
    assert(values.length === 1, "requested year must be unambiguous");
    var value = values[0];
    assert(/^[0-9]{4}$/.test(value), "requested year is invalid");
    var year = Number(value);
    assert(releaseForYear(year), "requested year is not published");
    return year;
  }

  function validateRequestedLanguage() {
    var params = new URLSearchParams(window.location.search);
    if (!params.has("lang")) return;
    var values = params.getAll("lang");
    assert(values.length === 1, "requested language must be unambiguous");
    assert(values[0] === "en" || values[0] === "es", "requested language is unsupported");
  }

  function requestedState() {
    var params = new URLSearchParams(window.location.search);
    if (!params.has("state")) return "";
    var values = params.getAll("state");
    assert(values.length === 1, "requested state must be unambiguous");
    var value = values[0];
    assert(/^[A-Z]{2}$/.test(value), "requested state is invalid");
    assert(isValidState(value), "requested state is not a reviewed jurisdiction");
    return value;
  }

  function updateYearUrl(year) {
    var url = new URL(window.location.href);
    url.searchParams.set("year", String(year));
    window.history.replaceState(null, "", url.pathname + url.search + url.hash);
  }

  function updateStateUrl(state) {
    var url = new URL(window.location.href);
    if (state) {
      url.searchParams.set("state", state);
      url.searchParams.set("year", document.getElementById("year-filter").value);
      url.searchParams.set("lang", lang);
    } else {
      url.searchParams.delete("state");
    }
    window.history.replaceState(null, "", url.pathname + url.search + url.hash);
  }

  function updateLanguageUrl(next) {
    var url = new URL(window.location.href);
    url.searchParams.set("lang", next);
    window.history.replaceState(null, "", url.pathname + url.search + url.hash);
  }

  function loadRelease(release, updateUrl) {
    var serial = ++requestSerial;
    currentRelease = release;
    document.getElementById("year-filter").value = String(release.dataset_year);
    updateProofRail(release.dataset_year);
    showLoading();
    return loadArtifact(release)
      .then(function (data) {
        if (serial !== requestSerial) return;
        artifact = data;
        rows = flatten(artifact);
        if (updateUrl) updateYearUrl(release.dataset_year);
        document.getElementById("coverage-status").classList.remove("is-error");
        applyTranslations();
      })
      .catch(function () {
        if (serial === requestSerial) {
          showError();
          if (document.getElementById("state-filter").value) showProfileError();
        }
      });
  }

  function bindEvents() {
    var form = document.getElementById("coverage-filters");
    form.addEventListener("submit", function (event) {
      event.preventDefault();
    });
    form.addEventListener("change", function (event) {
      if (event.target && event.target.id === "year-filter") {
        var release = releaseForYear(Number(event.target.value));
        if (!release) {
          showError();
          return;
        }
        loadRelease(release, true);
      } else if (event.target && event.target.id === "state-filter") {
        var state = event.target.value;
        if (state && !isValidState(state)) {
          ++profileRequestSerial;
          showError();
          showProfileError();
          return;
        }
        updateStateUrl(state);
        renderTable();
        loadStateProfile(state);
      } else {
        renderTable();
      }
    });
    form.addEventListener("reset", function (event) {
      event.preventDefault();
      if (!releaseIndex) return;
      document.getElementById("state-filter").value = "";
      document.getElementById("mode-filter").value = "";
      document.getElementById("status-filter").value = "";
      ++profileRequestSerial;
      updateStateUrl("");
      showProfileEmpty();
      loadRelease(releaseForYear(releaseIndex.default_year), true);
    });
    document.querySelectorAll("[data-lang]").forEach(function (button) {
      button.addEventListener("click", function () {
        var next = button.getAttribute("data-lang");
        if (next !== "en" && next !== "es") return;
        var serial = ++languageRequestSerial;
        i18n.load(next).then(function () {
          if (serial !== languageRequestSerial) return;
          lang = next;
          i18n.setLang(lang);
          updateLanguageUrl(lang);
          applyTranslations();
        });
      });
    });
  }

  window.NearmissUSCoverage = {
    validateIndex: validateIndex,
    validateArtifact: function (data, release, contract) {
      return validateArtifact(
        data,
        release || currentRelease,
        contract || (releaseIndex && releaseIndex.contract)
      );
    },
    indexUrl: INDEX_URL,
    dataUrl: DEFAULT_2024_DATA_URL,
  };

  bindEvents();
  Promise.all([i18n.load("en"), i18n.load(lang)])
    .then(function () {
      i18n.setLang(lang);
      applyTranslations();
      return fetch(INDEX_URL);
    })
    .then(function (response) {
      return verifiedJson(response, EXPECTED_INDEX_BYTES, EXPECTED_INDEX_SHA256, "release index");
    })
    .then(function (data) {
      releaseIndex = validateIndex(data);
      populateYearControl(releaseIndex.default_year);
      updateProofRail(null);
      validateRequestedLanguage();
      var year = requestedYear();
      var state = requestedState();
      populateYearControl(year);
      populateStateControl(state);
      var selectedRelease = loadRelease(releaseForYear(year), false);
      if (!state) return selectedRelease;
      updateStateUrl(state);
      return Promise.all([selectedRelease, loadStateProfile(state)]);
    })
    .catch(function () {
      ++profileRequestSerial;
      showError();
      showProfileError();
    });
})();
