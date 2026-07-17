/* Auditable nationwide FARS context — framework-free, bilingual, and driven
 * only by a hash-bound release index and its checked-in public projections.
 * Suppressed cells never acquire a numeric value in this UI. */
(function () {
  "use strict";

  var INDEX_URL = "/data/published/fars-state-mode-index-v2.json";
  var DATA_ROOT = "/data/published/";
  var DEFAULT_2024_DATA_URL = DATA_ROOT + "fars-2024-state-mode-r2.json";
  var BOUNDARY_URL = "/data/published/us-state-boundaries-2024.json";
  var EXPECTED_INDEX_BYTES = 5273;
  var EXPECTED_INDEX_SHA256 = "594b13a65f5b88661db8acb21c73fc55ddc61ba94e5a659cdd27463c178f50f5";
  var EXPECTED_BOUNDARY_ARTIFACT_BYTES = 323232;
  var EXPECTED_BOUNDARY_ARTIFACT_SHA256 = "705219b3339077f1d03466391bb286fe7f1841298fc0bcce948de1d8c66df25d";
  var EXPECTED_BOUNDARY_SOURCE_URL =
    "https://www2.census.gov/geo/tiger/GENZ2024/kml/cb_2024_us_state_20m.zip";
  var EXPECTED_BOUNDARY_SOURCE_SHA256 = "37337db59415f010c594fba96a48aa6e950e633dc0e555cc7b1ce8edd794c673";
  var EXPECTED_BOUNDARY_SOURCE_BYTES = 158066;
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
  var boundaryArtifact = null;
  var boundaryPromise = null;
  var rows = [];
  var artifactPromises = {};
  var profileArtifacts = null;
  var profileState = "";
  var requestSerial = 0;
  var profileRequestSerial = 0;
  var languageRequestSerial = 0;
  var requestedModeFromUrl = null;
  var viewState = {
    view: "map",
    primaryMode: "pedalcyclist",
    secondaryMode: "pedestrian",
    selectedState: null,
    compareA: null,
    compareB: null,
    scale: "linear",
    saved: [],
  };
  var VALID_VIEWS = { map: true, matrix: true, rank: true, scatter: true, compare: true };
  var SVG_NS = "http://www.w3.org/2000/svg";

  function t(key) {
    return i18n.t(key);
  }

  function tpl(text, values) {
    return text.replace(/\{(\w+)\}/g, function (_, key) {
      return values[key];
    });
  }

  function renderTranslation(element, key) {
    var translated = t(key);
    if (element.tagName === "UL") {
      var listPattern = /^(?:<li>[^<>]*<\/li>)+$/;
      if (!listPattern.test(translated)) {
        element.textContent = translated;
        return;
      }
      element.textContent = "";
      (translated.match(/<li>[^<>]*<\/li>/g) || []).forEach(function (item) {
        var listItem = document.createElement("li");
        listItem.textContent = item.slice(4, -5);
        element.appendChild(listItem);
      });
      return;
    }

    var strongParts = /^([^<>]*)<strong>([^<>]*)<\/strong>([^<>]*)$/.exec(translated);
    if (!strongParts) {
      element.textContent = translated;
      return;
    }
    element.textContent = "";
    element.appendChild(document.createTextNode(strongParts[1]));
    var emphasis = document.createElement("strong");
    emphasis.textContent = strongParts[2];
    element.appendChild(emphasis);
    element.appendChild(document.createTextNode(strongParts[3]));
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

  function validateBoundaryRing(ring, label) {
    assert(Array.isArray(ring) && ring.length >= 4, label + " must contain at least four positions");
    ring.forEach(function (position) {
      assert(
        Array.isArray(position) &&
          position.length === 2 &&
          Number.isFinite(position[0]) &&
          Number.isFinite(position[1]),
        label + " positions must be finite [longitude, latitude] pairs"
      );
      assert(position[0] >= -180 && position[0] <= 180, label + " longitude is outside WGS84 bounds");
      assert(position[1] >= -90 && position[1] <= 90, label + " latitude is outside WGS84 bounds");
    });
    assert(
      ring[0][0] === ring[ring.length - 1][0] && ring[0][1] === ring[ring.length - 1][1],
      label + " must be closed"
    );
  }

  function validateBoundaryArtifact(data) {
    assertExactKeys(data, ["type", "name", "source", "features"], "boundary top level");
    assert(data.type === "FeatureCollection", "boundary type must be FeatureCollection");
    assert(
      data.name === "2024 Census cartographic boundaries for the 50 states and DC",
      "boundary title is not reviewed"
    );
    assertExactKeys(
      data.source,
      ["name", "vintage", "resolution", "distribution_url", "raw_zip_sha256", "raw_zip_size_bytes", "conversion"],
      "boundary source"
    );
    assert(
      data.source.name === "U.S. Census Bureau 2024 Cartographic Boundary Files",
      "boundary source name is not reviewed"
    );
    assert(data.source.vintage === 2024, "boundary vintage is not reviewed");
    assert(data.source.resolution === "1:20,000,000", "boundary resolution is not reviewed");
    assert(data.source.distribution_url === EXPECTED_BOUNDARY_SOURCE_URL, "boundary source URL is not reviewed");
    assert(data.source.raw_zip_sha256 === EXPECTED_BOUNDARY_SOURCE_SHA256, "boundary source checksum is not reviewed");
    assert(data.source.raw_zip_size_bytes === EXPECTED_BOUNDARY_SOURCE_BYTES, "boundary source size is not reviewed");
    assert(
      data.source.conversion ===
        "KML polygons to RFC 7946 GeoJSON; coordinates rounded to 6 decimals; 50 states and DC retained",
      "boundary conversion is not reviewed"
    );
    assert(Array.isArray(data.features) && data.features.length === 51, "boundaries must contain 50 states and DC");

    data.features.forEach(function (feature, index) {
      assertExactKeys(feature, ["type", "id", "properties", "geometry"], "boundary feature");
      assert(feature.type === "Feature", "boundary member must be a Feature");
      assertExactKeys(
        feature.properties,
        ["state_fips", "state_abbreviation", "state_name"],
        "boundary properties"
      );
      var expected = EXPECTED_STATES[index].split("|");
      assert(String(Number(feature.properties.state_fips)) === expected[0], "boundary FIPS order is not reviewed");
      assert(feature.properties.state_abbreviation === expected[1], "boundary abbreviation is not reviewed");
      assert(feature.properties.state_name === expected[2], "boundary state name is not reviewed");
      assert(feature.id === expected[1], "boundary feature ID is not reviewed");
      assertExactKeys(feature.geometry, ["type", "coordinates"], "boundary geometry");
      assert(
        feature.geometry.type === "Polygon" || feature.geometry.type === "MultiPolygon",
        "boundary geometry type is not supported"
      );
      var polygons = feature.geometry.type === "Polygon" ? [feature.geometry.coordinates] : feature.geometry.coordinates;
      assert(Array.isArray(polygons) && polygons.length > 0, "boundary geometry must contain polygons");
      polygons.forEach(function (polygon, polygonIndex) {
        assert(Array.isArray(polygon) && polygon.length > 0, "boundary polygon must contain rings");
        polygon.forEach(function (ring, ringIndex) {
          validateBoundaryRing(ring, "boundary polygon " + polygonIndex + " ring " + ringIndex);
        });
      });
    });
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

  function loadBoundaryArtifact() {
    if (!boundaryPromise) {
      boundaryPromise = fetch(BOUNDARY_URL)
        .then(function (response) {
          return verifiedJson(
            response,
            EXPECTED_BOUNDARY_ARTIFACT_BYTES,
            EXPECTED_BOUNDARY_ARTIFACT_SHA256,
            "boundary artifact"
          );
        })
        .then(validateBoundaryArtifact)
        .catch(function (error) {
          boundaryPromise = null;
          throw error;
        });
    }
    return boundaryPromise;
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

  function svgElement(tag, attributes, textValue) {
    var element = document.createElementNS(SVG_NS, tag);
    Object.keys(attributes || {}).forEach(function (key) {
      element.setAttribute(key, String(attributes[key]));
    });
    if (textValue != null) element.textContent = textValue;
    return element;
  }

  function stateRecord(abbreviation) {
    if (!artifact || !abbreviation) return null;
    return (
      artifact.states.find(function (state) {
        return state.state_abbreviation === abbreviation;
      }) || null
    );
  }

  function rowFor(abbreviation, mode) {
    return (
      rows.find(function (row) {
        return row.stateAbbreviation === abbreviation && row.mode === mode;
      }) || null
    );
  }

  function rowsForState(abbreviation) {
    return rows.filter(function (row) {
      return row.stateAbbreviation === abbreviation;
    });
  }

  function focusMode() {
    var select = document.getElementById("mode-filter");
    return (select && select.value) || viewState.primaryMode;
  }

  function statusText(status) {
    return status === "published" ? t("cell_published") : t("cell_not_published");
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
    var mode = document.getElementById("ledger-mode-filter").value;
    var status = document.getElementById("status-filter").value;
    return rows.filter(function (row) {
      return (
        (!state || row.stateAbbreviation === state) &&
        (!mode || row.mode === mode) &&
        (!status || row.status === status)
      );
    });
  }

  function selectState(abbreviation, mode) {
    if (!isValidState(abbreviation)) return;
    var activeElement = document.activeElement;
    var activeControl = activeElement && activeElement.closest && activeElement.closest("[data-focus-key]");
    var focusKey = activeControl ? activeControl.getAttribute("data-focus-key") : null;
    viewState.selectedState = abbreviation;
    viewState.compareA = abbreviation;
    if (mode) {
      requestedModeFromUrl = null;
      viewState.primaryMode = mode;
    }
    var stateSelect = document.getElementById("state-filter");
    if (stateSelect) stateSelect.value = abbreviation;
    var modeSelect = document.getElementById("mode-filter");
    if (mode && modeSelect) modeSelect.value = mode;
    renderAll();
    loadStateProfile(abbreviation);
    if (focusKey) {
      var replacement = document.querySelector('[data-focus-key="' + focusKey + '"]');
      if (replacement && replacement.focus) replacement.focus();
    }
    syncUrl();
  }

  function renderTable() {
    if (!artifact) return;
    var selectedState = document.getElementById("state-filter").value;
    var selected = selectedRows();
    var body = document.getElementById("coverage-body");
    var caption = document.getElementById("coverage-caption");
    var status = document.getElementById("coverage-status");
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
      if (viewState.selectedState === row.stateAbbreviation) tr.classList.add("is-selected");
      tr.appendChild(cell("td", String(row.year)));
      var stateHeader = cell("th", row.stateName + " (" + row.stateAbbreviation + ")");
      stateHeader.scope = "row";
      tr.appendChild(stateHeader);
      tr.appendChild(cell("td", modeLabel(row.mode)));
      var statusCell = document.createElement("td");
      statusCell.appendChild(
        cell(
          "span",
          statusText(row.status),
          "cell-status" + (row.status === "published" ? "" : " is-withheld")
        )
      );
      tr.appendChild(statusCell);
      tr.appendChild(cell("td", row.status === "published" ? number(row.count) : "—", "count-cell"));
      body.appendChild(tr);
    });
    caption.removeAttribute("data-i18n");
    status.removeAttribute("data-i18n");
    status.classList.remove("is-error");
    if (selectedState) {
      var definition = stateDefinition(selectedState);
      var stateTotal = rows.filter(function (row) {
        return row.stateAbbreviation === selectedState;
      }).length;
      var stateValues = {
        shown: number(selected.length),
        total: number(stateTotal),
        state: definition.name,
        year: String(artifact.dataset_year),
      };
      caption.textContent = tpl(t("caption_state"), stateValues);
      status.textContent = tpl(t("result_summary_state"), stateValues);
    } else {
      var values = { shown: number(selected.length), total: number(rows.length) };
      caption.textContent = tpl(t("caption"), values);
      status.textContent = tpl(t("result_summary"), values);
    }
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
    populateStateControl(viewState.selectedState || "");
    var modeSelect = document.getElementById("mode-filter");
    var selectedMode = requestedModeFromUrl || viewState.primaryMode;
    modeSelect.textContent = "";
    EXPECTED_MODES.forEach(function (mode) {
      var option = document.createElement("option");
      option.value = mode;
      option.textContent = modeLabel(mode);
      modeSelect.appendChild(option);
    });
    modeSelect.value = EXPECTED_MODES.indexOf(selectedMode) >= 0 ? selectedMode : "pedalcyclist";
    viewState.primaryMode = modeSelect.value;

    var ledgerModeSelect = document.getElementById("ledger-mode-filter");
    var selectedLedgerMode = ledgerModeSelect.value;
    ledgerModeSelect.textContent = "";
    var allModes = document.createElement("option");
    allModes.value = "";
    allModes.textContent = t("all_modes");
    allModes.setAttribute("data-i18n", "all_modes");
    ledgerModeSelect.appendChild(allModes);
    EXPECTED_MODES.forEach(function (mode) {
      var option = document.createElement("option");
      option.value = mode;
      option.textContent = modeLabel(mode);
      ledgerModeSelect.appendChild(option);
    });
    ledgerModeSelect.value =
      EXPECTED_MODES.indexOf(selectedLedgerMode) >= 0 ? selectedLedgerMode : "";

    var secondary = document.getElementById("secondary-mode");
    secondary.textContent = "";
    EXPECTED_MODES.forEach(function (mode) {
      var option = document.createElement("option");
      option.value = mode;
      option.textContent = modeLabel(mode);
      secondary.appendChild(option);
    });
    if (viewState.secondaryMode === focusMode()) {
      viewState.secondaryMode = focusMode() === "pedestrian" ? "pedalcyclist" : "pedestrian";
    }
    secondary.value = viewState.secondaryMode;

    ["compare-a", "compare-b"].forEach(function (id) {
      var select = document.getElementById(id);
      select.textContent = "";
      var placeholder = document.createElement("option");
      placeholder.value = "";
      placeholder.textContent = t("choose_state");
      select.appendChild(placeholder);
      artifact.states.forEach(function (state) {
        var option = document.createElement("option");
        option.value = state.state_abbreviation;
        option.textContent = state.state_name + " (" + state.state_abbreviation + ")";
        select.appendChild(option);
      });
    });
    document.getElementById("compare-a").value = viewState.compareA || "";
    document.getElementById("compare-b").value = viewState.compareB || "";
    document.querySelectorAll('input[name="scale"]').forEach(function (radio) {
      radio.checked = radio.value === viewState.scale;
    });
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
    var cases = document.getElementById("summary-cases");
    if (cases) cases.textContent = number(artifact.accounting.case_count);
    document.getElementById("summary-scope").textContent = t("scope_value");
    var cells = document.getElementById("summary-cells");
    if (cells) {
      cells.textContent = tpl(t("cells_value"), {
        published: number(artifact.accounting.published_cell_count),
        total: number(artifact.accounting.state_mode_cell_count),
      });
    }
    document.getElementById("summary-threshold").textContent = "k = " + number(artifact.metric.effective_k);
    document.getElementById("summary-retention").textContent = tpl(t("retention_value"), {
      published: number(artifact.accounting.published_crash_contribution_total),
      total: number(artifact.accounting.crash_contribution_total),
    });
    var source = document.getElementById("official-source");
    source.href = artifact.source.distribution_url;
    source.textContent = artifact.source.name;
    document.getElementById("source-revision").textContent = artifact.source.source_revision_id;
    var sourceChecksum = document.getElementById("source-checksum");
    if (sourceChecksum) sourceChecksum.textContent = artifact.source.raw_sha256;
    var algorithmVersion = document.getElementById("algorithm-version");
    if (algorithmVersion) algorithmVersion.textContent = artifact.metric.algorithm_version;
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
    var boundarySource = document.getElementById("boundary-source");
    if (boundarySource && boundaryArtifact) {
      boundarySource.href = boundaryArtifact.source.distribution_url;
      boundarySource.textContent = boundaryArtifact.source.name;
    }
    var boundaryChecksum = document.getElementById("boundary-checksum");
    if (boundaryChecksum && boundaryArtifact) {
      boundaryChecksum.textContent = EXPECTED_BOUNDARY_ARTIFACT_SHA256;
    }
  }

  function clearMetadata() {
    [
      "summary-year",
      "summary-cases",
      "summary-scope",
      "summary-cells",
      "summary-threshold",
      "summary-retention",
      "source-revision",
      "source-checksum",
      "algorithm-version",
      "release-stage",
      "semantic-regime",
      "mapping-versions",
      "state-code-system",
      "annual-contract",
      "boundary-checksum",
    ].forEach(function (id) {
      var element = document.getElementById(id);
      if (element) element.textContent = "—";
    });
    var source = document.getElementById("official-source");
    source.removeAttribute("href");
    source.textContent = "—";
    document.getElementById("artifact-download").removeAttribute("href");
    var boundarySource = document.getElementById("boundary-source");
    if (boundarySource) {
      boundarySource.removeAttribute("href");
      boundarySource.textContent = "—";
    }
  }

  function modeSummary(mode) {
    var modeRows = rows.filter(function (row) {
      return row.mode === mode;
    });
    var published = modeRows.filter(function (row) {
      return row.status === "published";
    });
    return {
      published: published.length,
      unpublished: modeRows.length - published.length,
      max: Math.max.apply(
        null,
        published
          .map(function (row) {
            return row.count;
          })
          .concat([1])
      ),
    };
  }

  function boundaryPolygons(feature) {
    return feature.geometry.type === "Polygon" ? [feature.geometry.coordinates] : feature.geometry.coordinates;
  }

  function eachBoundaryPosition(features, callback) {
    features.forEach(function (feature) {
      boundaryPolygons(feature).forEach(function (polygon) {
        polygon.forEach(function (ring) {
          ring.forEach(function (position) {
            callback(position, feature);
          });
        });
      });
    });
  }

  function albersLower48(position) {
    var radians = Math.PI / 180;
    var longitude = position[0] * radians;
    var latitude = position[1] * radians;
    var originLongitude = -96 * radians;
    var originLatitude = 38 * radians;
    var firstParallel = 29.5 * radians;
    var secondParallel = 45.5 * radians;
    var n = (Math.sin(firstParallel) + Math.sin(secondParallel)) / 2;
    var c = Math.cos(firstParallel) * Math.cos(firstParallel) + 2 * n * Math.sin(firstParallel);
    var rho = Math.sqrt(c - 2 * n * Math.sin(latitude)) / n;
    var rhoOrigin = Math.sqrt(c - 2 * n * Math.sin(originLatitude)) / n;
    var theta = n * (longitude - originLongitude);
    return [rho * Math.sin(theta), rhoOrigin - rho * Math.cos(theta)];
  }

  function insetRaw(position, state) {
    var longitude = position[0];
    if (state === "AK" && longitude > 0) longitude -= 360;
    return [longitude, -position[1]];
  }

  function fittedProjection(features, rawProjection, box) {
    var minX = Infinity;
    var maxX = -Infinity;
    var minY = Infinity;
    var maxY = -Infinity;
    eachBoundaryPosition(features, function (position, feature) {
      var point = rawProjection(position, feature.id);
      minX = Math.min(minX, point[0]);
      maxX = Math.max(maxX, point[0]);
      minY = Math.min(minY, point[1]);
      maxY = Math.max(maxY, point[1]);
    });
    var sourceWidth = Math.max(0.000001, maxX - minX);
    var sourceHeight = Math.max(0.000001, maxY - minY);
    var scale = Math.min(box.width / sourceWidth, box.height / sourceHeight);
    var xOffset = box.x + (box.width - sourceWidth * scale) / 2 - minX * scale;
    var yOffset = box.y + (box.height - sourceHeight * scale) / 2 - minY * scale;
    return function (position, state) {
      var raw = rawProjection(position, state);
      return [xOffset + raw[0] * scale, yOffset + raw[1] * scale];
    };
  }

  function projectedFeature(feature, projector) {
    var bounds = { minX: Infinity, maxX: -Infinity, minY: Infinity, maxY: -Infinity };
    var parts = [];
    boundaryPolygons(feature).forEach(function (polygon) {
      polygon.forEach(function (ring) {
        var commands = ring.map(function (position, index) {
          var point = projector(position, feature.id);
          bounds.minX = Math.min(bounds.minX, point[0]);
          bounds.maxX = Math.max(bounds.maxX, point[0]);
          bounds.minY = Math.min(bounds.minY, point[1]);
          bounds.maxY = Math.max(bounds.maxY, point[1]);
          return (index === 0 ? "M" : "L") + point[0].toFixed(2) + "," + point[1].toFixed(2);
        });
        parts.push(commands.join(" ") + " Z");
      });
    });
    return { path: parts.join(" "), bounds: bounds };
  }

  function mapColor(value, max) {
    var start = [220, 232, 235];
    var end = [20, 91, 115];
    var ratio = Math.sqrt(value / Math.max(1, max));
    var channels = start.map(function (channel, index) {
      return Math.round(channel + (end[index] - channel) * ratio);
    });
    return "rgb(" + channels.join(", ") + ")";
  }

  function renderMap() {
    if (!boundaryArtifact) return;
    var mode = focusMode();
    var summary = modeSummary(mode);
    var map = document.getElementById("us-map");
    map.textContent = "";
    var width = 960;
    var height = 560;
    var svg = svgElement("svg", {
      viewBox: "0 0 " + width + " " + height,
      role: "group",
      "aria-labelledby": "us-map-title us-map-description",
    });
    svg.appendChild(svgElement("title", { id: "us-map-title" }, document.getElementById("map-heading").textContent));
    svg.appendChild(
      svgElement(
        "desc",
        { id: "us-map-description" },
        tpl(t("map_caption"), {
          mode: modeLabel(mode),
          published: number(summary.published),
        })
      )
    );
    var definitions = svgElement("defs");
    var pattern = svgElement("pattern", {
      id: "map-unpublished-pattern",
      width: "8",
      height: "8",
      patternUnits: "userSpaceOnUse",
      patternTransform: "rotate(35)",
    });
    pattern.appendChild(svgElement("rect", { width: "8", height: "8", fill: "#f3f6f2" }));
    pattern.appendChild(
      svgElement("line", { x1: "0", y1: "0", x2: "0", y2: "8", stroke: "#5e706f", "stroke-width": "2" })
    );
    definitions.appendChild(pattern);
    svg.appendChild(definitions);

    var mainland = boundaryArtifact.features.filter(function (feature) {
      return feature.id !== "AK" && feature.id !== "HI";
    });
    var alaska = boundaryArtifact.features.filter(function (feature) {
      return feature.id === "AK";
    });
    var hawaii = boundaryArtifact.features.filter(function (feature) {
      return feature.id === "HI";
    });
    var mainlandProjector = fittedProjection(mainland, albersLower48, { x: 45, y: 24, width: 870, height: 390 });
    var alaskaProjector = fittedProjection(alaska, insetRaw, { x: 55, y: 408, width: 260, height: 125 });
    var hawaiiProjector = fittedProjection(hawaii, insetRaw, { x: 355, y: 448, width: 175, height: 72 });

    [
      { x: 45, y: 398, width: 280, height: 145, label: "Alaska" },
      { x: 342, y: 435, width: 200, height: 98, label: "Hawaii" },
    ].forEach(function (frame) {
      svg.appendChild(
        svgElement("rect", {
          x: frame.x,
          y: frame.y,
          width: frame.width,
          height: frame.height,
          rx: "4",
          class: "map-inset-frame",
        })
      );
      svg.appendChild(svgElement("text", { x: frame.x + 8, y: frame.y + 16, class: "map-inset-label" }, frame.label));
    });

    boundaryArtifact.features.forEach(function (feature, featureIndex) {
      var projector = feature.id === "AK" ? alaskaProjector : feature.id === "HI" ? hawaiiProjector : mainlandProjector;
      var projected = projectedFeature(feature, projector);
      var row = rowFor(feature.id, mode);
      var published = row.status === "published";
      var label = tpl(t(published ? "map_state_published" : "map_state_unpublished"), {
        state: feature.properties.state_name,
        count: published ? number(row.count) : "",
        mode: modeLabel(mode),
      });
      var group = svgElement("g", {
        class: "map-state-group",
        tabindex:
          viewState.selectedState === feature.id || (!viewState.selectedState && featureIndex === 0)
            ? "0"
            : "-1",
        role: "button",
        "aria-label": label,
        "aria-describedby": "map-keyboard-hint",
        "aria-current": viewState.selectedState === feature.id ? "true" : "false",
        "data-state": feature.id,
        "data-focus-key": "map:" + feature.id,
      });
      var path = svgElement("path", {
        d: projected.path,
        class:
          "map-state" +
          (published ? "" : " is-unpublished") +
          (viewState.selectedState === feature.id ? " is-selected" : ""),
        "fill-rule": "evenodd",
      });
      if (published) path.style.setProperty("--state-fill", mapColor(row.count, summary.max));
      group.appendChild(svgElement("title", {}, label));
      group.appendChild(path);
      var stateWidth = projected.bounds.maxX - projected.bounds.minX;
      var stateHeight = projected.bounds.maxY - projected.bounds.minY;
      var centerX = (projected.bounds.minX + projected.bounds.maxX) / 2;
      var centerY = (projected.bounds.minY + projected.bounds.maxY) / 2;
      if (viewState.selectedState === feature.id) {
        group.appendChild(
          svgElement("path", {
            d: "M" + (centerX - 19) + "," + (centerY + 19) + " L" + (centerX - 5) + "," + (centerY + 5),
            class: "clearance-cursor clearance-cursor-a",
            "aria-hidden": "true",
          })
        );
        group.appendChild(
          svgElement("path", {
            d: "M" + (centerX + 19) + "," + (centerY - 19) + " L" + (centerX + 5) + "," + (centerY - 5),
            class: "clearance-cursor clearance-cursor-b",
            "aria-hidden": "true",
          })
        );
      }
      if (["DC", "DE", "RI"].indexOf(feature.id) >= 0) {
        var locator = svgElement("circle", {
          cx: centerX,
          cy: centerY,
          r: feature.id === "DC" ? 5 : 3.5,
          class: "map-state-locator" + (published ? "" : " is-unpublished"),
          "aria-hidden": "true",
        });
        if (published) locator.style.setProperty("--state-fill", mapColor(row.count, summary.max));
        group.appendChild(locator);
      }
      group.addEventListener("click", function () {
        selectState(feature.id, mode);
      });
      group.addEventListener("keydown", function (event) {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          selectState(feature.id, mode);
          return;
        }
        if (
          event.key === "ArrowRight" ||
          event.key === "ArrowDown" ||
          event.key === "ArrowLeft" ||
          event.key === "ArrowUp" ||
          event.key === "Home" ||
          event.key === "End"
        ) {
          event.preventDefault();
          var groups = Array.from(svg.querySelectorAll(".map-state-group"));
          var currentIndex = groups.indexOf(group);
          var nextIndex = currentIndex;
          if (event.key === "Home") nextIndex = 0;
          else if (event.key === "End") nextIndex = groups.length - 1;
          else if (event.key === "ArrowRight" || event.key === "ArrowDown") {
            nextIndex = (currentIndex + 1) % groups.length;
          } else {
            nextIndex = (currentIndex - 1 + groups.length) % groups.length;
          }
          groups.forEach(function (candidate, index) {
            candidate.setAttribute("tabindex", index === nextIndex ? "0" : "-1");
          });
          groups[nextIndex].focus();
        }
      });
      svg.appendChild(group);
      if (stateWidth * stateHeight > 550 || viewState.selectedState === feature.id) {
        svg.appendChild(
          svgElement(
            "text",
            { x: centerX, y: centerY + 4, "text-anchor": "middle", class: "map-state-label" },
            feature.id
          )
        );
      }
    });
    map.appendChild(svg);
    document.getElementById("map-caption").textContent = tpl(t("map_caption"), {
      mode: modeLabel(mode),
      published: number(summary.published),
    });
  }

  function renderMatrix() {
    var head = document.getElementById("matrix-head");
    var body = document.getElementById("matrix-body");
    head.textContent = "";
    body.textContent = "";
    var headerRow = document.createElement("tr");
    var corner = cell("th", t("state_label"));
    corner.scope = "col";
    headerRow.appendChild(corner);
    EXPECTED_MODES.forEach(function (mode) {
      var summary = modeSummary(mode);
      var th = document.createElement("th");
      th.scope = "col";
      var modeButton = cell("button", "", "matrix-mode-button");
      modeButton.type = "button";
      modeButton.setAttribute("data-focus-key", "matrix-mode:" + mode);
      modeButton.appendChild(cell("span", modeLabel(mode), "matrix-mode-label"));
      modeButton.appendChild(
        cell(
          "span",
          tpl(t("matrix_coverage"), { published: number(summary.published), total: number(artifact.states.length) }),
          "matrix-mode-coverage"
        )
      );
      modeButton.addEventListener("click", function () {
        requestedModeFromUrl = null;
        viewState.primaryMode = mode;
        document.getElementById("mode-filter").value = mode;
        renderAll();
        var replacement = document.querySelector('[data-focus-key="matrix-mode:' + mode + '"]');
        if (replacement) replacement.focus();
        syncUrl();
      });
      th.appendChild(modeButton);
      headerRow.appendChild(th);
    });
    head.appendChild(headerRow);

    var statusFilter = document.getElementById("status-filter").value;
    artifact.states.forEach(function (state, stateIndex) {
      var tr = document.createElement("tr");
      if (viewState.selectedState === state.state_abbreviation) tr.classList.add("is-selected");
      var stateTh = document.createElement("th");
      stateTh.scope = "row";
      stateTh.textContent = state.state_name + " (" + state.state_abbreviation + ")";
      tr.appendChild(stateTh);

      EXPECTED_MODES.forEach(function (mode, modeIndex) {
        var row = rowFor(state.state_abbreviation, mode);
        var td = document.createElement("td");
        td.className = "matrix-cell";
        if (row.status !== "published") td.classList.add("is-unpublished");
        if (statusFilter && row.status !== statusFilter) {
          td.classList.add("is-filtered");
        }
        if (viewState.selectedState === row.stateAbbreviation && focusMode() === mode) {
          td.classList.add("is-selected");
        }
        if (row.status === "published") {
          var max = modeSummary(mode).max;
          td.style.setProperty("--cell-alpha", String(0.12 + 0.78 * (row.count / max)));
        }
        var cellButton = cell(
          "button",
          row.status === "published" ? number(row.count) : "—",
          "matrix-cell-button"
        );
        cellButton.type = "button";
        cellButton.setAttribute("data-state", row.stateAbbreviation);
        cellButton.setAttribute("data-mode", row.mode);
        cellButton.setAttribute("data-matrix-row", String(stateIndex));
        cellButton.setAttribute("data-matrix-col", String(modeIndex));
        cellButton.setAttribute("data-focus-key", "matrix:" + row.stateAbbreviation + ":" + row.mode);
        cellButton.setAttribute("aria-describedby", "matrix-keyboard-hint");
        cellButton.setAttribute(
          "aria-current",
          viewState.selectedState === row.stateAbbreviation && focusMode() === row.mode ? "true" : "false"
        );
        cellButton.tabIndex =
          (viewState.selectedState === row.stateAbbreviation && focusMode() === row.mode) ||
          (!viewState.selectedState && stateIndex === 0 && modeIndex === 0)
            ? 0
            : -1;
        cellButton.setAttribute(
          "aria-label",
          tpl(t(row.status === "published" ? "matrix_cell_published" : "matrix_cell_unpublished"), {
            state: row.stateName,
            mode: modeLabel(mode),
            count: row.status === "published" ? number(row.count) : "",
          })
        );
        cellButton.addEventListener("click", function () {
          selectState(row.stateAbbreviation, row.mode);
        });
        cellButton.addEventListener("keydown", function (event) {
          var rowOffset = 0;
          var columnOffset = 0;
          if (event.key === "ArrowRight") columnOffset = 1;
          else if (event.key === "ArrowLeft") columnOffset = -1;
          else if (event.key === "ArrowDown") rowOffset = 1;
          else if (event.key === "ArrowUp") rowOffset = -1;
          else if (event.key === "Home") columnOffset = -modeIndex;
          else if (event.key === "End") columnOffset = EXPECTED_MODES.length - 1 - modeIndex;
          else return;
          event.preventDefault();
          var nextRow = (stateIndex + rowOffset + artifact.states.length) % artifact.states.length;
          var nextColumn = (modeIndex + columnOffset + EXPECTED_MODES.length) % EXPECTED_MODES.length;
          var next = body.querySelector(
            '[data-matrix-row="' + nextRow + '"][data-matrix-col="' + nextColumn + '"]'
          );
          if (!next) return;
          body.querySelectorAll(".matrix-cell-button").forEach(function (candidate) {
            candidate.tabIndex = candidate === next ? 0 : -1;
          });
          next.focus();
        });
        td.appendChild(cellButton);
        tr.appendChild(td);
      });
      body.appendChild(tr);
    });
    document.getElementById("matrix-caption").textContent = tpl(t("matrix_caption"), {
      states: number(artifact.states.length),
      published: number(artifact.accounting.published_cell_count),
      total: number(artifact.accounting.state_mode_cell_count),
    });
  }

  function rankedRows(mode) {
    return rows
      .filter(function (row) {
        return row.mode === mode && row.status === "published";
      })
      .sort(function (a, b) {
        return b.count - a.count || a.stateName.localeCompare(b.stateName);
      });
  }

  function renderRank() {
    var mode = focusMode();
    var ranked = rankedRows(mode);
    var max = ranked.length ? ranked[0].count : 1;
    document.getElementById("rank-heading").textContent = tpl(t("rank_title"), { mode: modeLabel(mode) });
    var list = document.getElementById("rank-list");
    list.textContent = "";
    ranked.forEach(function (row, index) {
      var li = document.createElement("li");
      li.className = "rank-item";
      var button = document.createElement("button");
      button.type = "button";
      button.tabIndex =
        viewState.selectedState === row.stateAbbreviation ||
        (!ranked.some(function (candidate) {
          return candidate.stateAbbreviation === viewState.selectedState;
        }) && index === 0)
          ? 0
          : -1;
      button.setAttribute("data-state", row.stateAbbreviation);
      button.setAttribute("data-focus-key", "rank:" + row.stateAbbreviation + ":" + mode);
      button.setAttribute("aria-describedby", "rank-keyboard-hint");
      button.setAttribute("aria-current", viewState.selectedState === row.stateAbbreviation ? "true" : "false");
      button.appendChild(cell("span", String(index + 1), "rank-number"));
      button.appendChild(cell("span", row.stateName + " (" + row.stateAbbreviation + ")", "rank-state"));
      var track = cell("span", "", "rank-track");
      var bar = cell("span", "", "rank-bar");
      bar.style.inlineSize = ((row.count / max) * 100).toFixed(2) + "%";
      track.appendChild(bar);
      button.appendChild(track);
      button.appendChild(cell("span", number(row.count), "rank-count"));
      button.setAttribute(
        "aria-label",
        tpl(t("rank_item"), {
          rank: number(index + 1),
          state: row.stateName,
          count: number(row.count),
          mode: modeLabel(mode),
        })
      );
      button.addEventListener("click", function () {
        selectState(row.stateAbbreviation, mode);
      });
      button.addEventListener("keydown", function (event) {
        if (
          event.key !== "ArrowDown" &&
          event.key !== "ArrowRight" &&
          event.key !== "ArrowUp" &&
          event.key !== "ArrowLeft" &&
          event.key !== "Home" &&
          event.key !== "End"
        ) {
          return;
        }
        event.preventDefault();
        var buttons = Array.from(list.querySelectorAll("button[data-focus-key]"));
        var currentIndex = buttons.indexOf(button);
        var nextIndex = currentIndex;
        if (event.key === "Home") nextIndex = 0;
        else if (event.key === "End") nextIndex = buttons.length - 1;
        else if (event.key === "ArrowDown" || event.key === "ArrowRight") {
          nextIndex = (currentIndex + 1) % buttons.length;
        } else {
          nextIndex = (currentIndex - 1 + buttons.length) % buttons.length;
        }
        buttons.forEach(function (candidate, candidateIndex) {
          candidate.tabIndex = candidateIndex === nextIndex ? 0 : -1;
        });
        buttons[nextIndex].focus();
      });
      li.appendChild(button);
      list.appendChild(li);
    });

    var unpublished = rows
      .filter(function (row) {
        return row.mode === mode && row.status !== "published";
      })
      .sort(function (a, b) {
        return a.stateName.localeCompare(b.stateName);
      });
    document.getElementById("rank-unpublished-summary").textContent = tpl(t("rank_unpublished"), {
      count: number(unpublished.length),
      mode: modeLabel(mode),
    });
    var unpublishedList = document.getElementById("rank-unpublished");
    unpublishedList.textContent = "";
    unpublished.forEach(function (row) {
      unpublishedList.appendChild(cell("li", row.stateName + " (" + row.stateAbbreviation + ")"));
    });
  }

  function plotScale(value, max, start, end, logScale) {
    if (logScale) {
      var floor = Math.log10(10);
      var ceiling = Math.max(floor + 0.001, Math.log10(max));
      return start + ((Math.log10(Math.max(10, value)) - floor) / (ceiling - floor)) * (end - start);
    }
    return start + (value / Math.max(1, max)) * (end - start);
  }

  function renderScatter() {
    var primary = focusMode();
    if (viewState.secondaryMode === primary) {
      viewState.secondaryMode = primary === "pedestrian" ? "pedalcyclist" : "pedestrian";
      document.getElementById("secondary-mode").value = viewState.secondaryMode;
    }
    var secondary = viewState.secondaryMode;
    document.getElementById("scatter-heading").textContent = tpl(t("scatter_title"), {
      x: modeLabel(primary),
      y: modeLabel(secondary),
    });
    var pairs = artifact.states.map(function (state) {
      return {
        state: state,
        x: rowFor(state.state_abbreviation, primary),
        y: rowFor(state.state_abbreviation, secondary),
      };
    });
    var comparable = pairs.filter(function (pair) {
      return pair.x.status === "published" && pair.y.status === "published";
    });
    var maxX = Math.max.apply(
      null,
      comparable
        .map(function (pair) {
          return pair.x.count;
        })
        .concat([1])
    );
    var maxY = Math.max.apply(
      null,
      comparable
        .map(function (pair) {
          return pair.y.count;
        })
        .concat([1])
    );
    var width = 860;
    var height = 500;
    var margin = { top: 35, end: 35, bottom: 72, start: 82 };
    var plot = document.getElementById("scatter-plot");
    plot.textContent = "";
    var svg = svgElement("svg", {
      viewBox: "0 0 " + width + " " + height,
      role: "group",
      "aria-labelledby": "scatter-svg-title scatter-svg-desc",
    });
    svg.appendChild(
      svgElement("title", { id: "scatter-svg-title" }, document.getElementById("scatter-heading").textContent)
    );
    svg.appendChild(
      svgElement(
        "desc",
        { id: "scatter-svg-desc" },
        tpl(t("scatter_caption"), {
          comparable: number(comparable.length),
          excluded: number(pairs.length - comparable.length),
        })
      )
    );
    var logScale = viewState.scale === "log";
    for (var tick = 0; tick <= 4; tick += 1) {
      var xValue = logScale ? 10 * Math.pow(maxX / 10, tick / 4) : (maxX * tick) / 4;
      var yValue = logScale ? 10 * Math.pow(maxY / 10, tick / 4) : (maxY * tick) / 4;
      var xPos = plotScale(xValue, maxX, margin.start, width - margin.end, logScale);
      var yPos = plotScale(yValue, maxY, height - margin.bottom, margin.top, logScale);
      svg.appendChild(
        svgElement("line", {
          x1: xPos,
          y1: margin.top,
          x2: xPos,
          y2: height - margin.bottom,
          class: "plot-grid",
        })
      );
      svg.appendChild(
        svgElement("line", {
          x1: margin.start,
          y1: yPos,
          x2: width - margin.end,
          y2: yPos,
          class: "plot-grid",
        })
      );
      svg.appendChild(
        svgElement(
          "text",
          { x: xPos, y: height - margin.bottom + 22, "text-anchor": "middle", class: "plot-tick" },
          number(Math.round(xValue))
        )
      );
      svg.appendChild(
        svgElement(
          "text",
          { x: margin.start - 12, y: yPos + 4, "text-anchor": "end", class: "plot-tick" },
          number(Math.round(yValue))
        )
      );
    }
    svg.appendChild(
      svgElement("line", {
        x1: margin.start,
        y1: height - margin.bottom,
        x2: width - margin.end,
        y2: height - margin.bottom,
        class: "plot-axis",
      })
    );
    svg.appendChild(
      svgElement("line", {
        x1: margin.start,
        y1: margin.top,
        x2: margin.start,
        y2: height - margin.bottom,
        class: "plot-axis",
      })
    );
    svg.appendChild(
      svgElement(
        "text",
        {
          x: (margin.start + width - margin.end) / 2,
          y: height - 22,
          "text-anchor": "middle",
          class: "plot-label",
        },
        modeLabel(primary)
      )
    );
    var yLabelPosition = (margin.top + height - margin.bottom) / 2;
    svg.appendChild(
      svgElement(
        "text",
        {
          x: 22,
          y: yLabelPosition,
          "text-anchor": "middle",
          class: "plot-label",
          transform: "rotate(-90 22 " + yLabelPosition + ")",
        },
        modeLabel(secondary)
      )
    );

    comparable.forEach(function (pair, pairIndex) {
      var x = plotScale(pair.x.count, maxX, margin.start, width - margin.end, logScale);
      var y = plotScale(pair.y.count, maxY, height - margin.bottom, margin.top, logScale);
      var point = svgElement("circle", {
        cx: x,
        cy: y,
        r: viewState.selectedState === pair.state.state_abbreviation ? 8 : 6,
        class: "plot-point" + (viewState.selectedState === pair.state.state_abbreviation ? " is-selected" : ""),
        tabindex:
          viewState.selectedState === pair.state.state_abbreviation ||
          (!comparable.some(function (candidate) {
            return candidate.state.state_abbreviation === viewState.selectedState;
          }) && pairIndex === 0)
            ? "0"
            : "-1",
        role: "button",
        "data-state": pair.state.state_abbreviation,
        "data-focus-key": "scatter:" + pair.state.state_abbreviation,
        "aria-describedby": "scatter-keyboard-hint",
        "aria-current": viewState.selectedState === pair.state.state_abbreviation ? "true" : "false",
        "aria-label": tpl(t("scatter_point"), {
          state: pair.state.state_name,
          xmode: modeLabel(primary),
          xcount: number(pair.x.count),
          ymode: modeLabel(secondary),
          ycount: number(pair.y.count),
        }),
      });
      point.addEventListener("click", function () {
        selectState(pair.state.state_abbreviation, primary);
      });
      point.addEventListener("keydown", function (event) {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          selectState(pair.state.state_abbreviation, primary);
          return;
        }
        if (
          event.key === "ArrowRight" ||
          event.key === "ArrowDown" ||
          event.key === "ArrowLeft" ||
          event.key === "ArrowUp" ||
          event.key === "Home" ||
          event.key === "End"
        ) {
          event.preventDefault();
          var points = Array.from(svg.querySelectorAll(".plot-point"));
          var currentIndex = points.indexOf(point);
          var nextIndex = currentIndex;
          if (event.key === "Home") nextIndex = 0;
          else if (event.key === "End") nextIndex = points.length - 1;
          else if (event.key === "ArrowRight" || event.key === "ArrowDown") {
            nextIndex = (currentIndex + 1) % points.length;
          } else {
            nextIndex = (currentIndex - 1 + points.length) % points.length;
          }
          points.forEach(function (candidate, index) {
            candidate.setAttribute("tabindex", index === nextIndex ? "0" : "-1");
          });
          points[nextIndex].focus();
        }
      });
      if (viewState.selectedState === pair.state.state_abbreviation) {
        svg.appendChild(
          svgElement("line", {
            x1: x - 19,
            y1: y + 19,
            x2: x - 6,
            y2: y + 6,
            class: "clearance-cursor clearance-cursor-a",
            "aria-hidden": "true",
          })
        );
        svg.appendChild(
          svgElement("line", {
            x1: x + 19,
            y1: y - 19,
            x2: x + 6,
            y2: y - 6,
            class: "clearance-cursor clearance-cursor-b",
            "aria-hidden": "true",
          })
        );
      }
      svg.appendChild(point);
      if (viewState.selectedState === pair.state.state_abbreviation) {
        svg.appendChild(
          svgElement("text", { x: x + 12, y: y - 10, class: "plot-selected-label" }, pair.state.state_abbreviation)
        );
      }
    });
    if (!comparable.length) {
      svg.appendChild(
        svgElement("text", { x: width / 2, y: height / 2, "text-anchor": "middle", class: "plot-empty" }, t("scatter_empty"))
      );
    }
    plot.appendChild(svg);

    var tableHead = document.getElementById("scatter-table-head");
    var tableBody = document.getElementById("scatter-table-body");
    tableHead.textContent = "";
    tableBody.textContent = "";
    var header = document.createElement("tr");
    header.appendChild(cell("th", t("th_state")));
    header.lastChild.scope = "col";
    header.appendChild(cell("th", modeLabel(primary)));
    header.lastChild.scope = "col";
    header.appendChild(cell("th", modeLabel(secondary)));
    header.lastChild.scope = "col";
    tableHead.appendChild(header);
    pairs.forEach(function (pair) {
      var tr = document.createElement("tr");
      var th = cell("th", pair.state.state_name + " (" + pair.state.state_abbreviation + ")");
      th.scope = "row";
      tr.appendChild(th);
      tr.appendChild(cell("td", pair.x.status === "published" ? number(pair.x.count) : statusText(pair.x.status)));
      tr.appendChild(cell("td", pair.y.status === "published" ? number(pair.y.count) : statusText(pair.y.status)));
      tableBody.appendChild(tr);
    });
    document.getElementById("scatter-caption").textContent = tpl(t("scatter_caption"), {
      comparable: number(comparable.length),
      excluded: number(pairs.length - comparable.length),
    });
  }

  function renderComparison() {
    var container = document.getElementById("state-comparison");
    container.textContent = "";
    var first = stateRecord(viewState.compareA);
    var second = stateRecord(viewState.compareB);
    if (!first || !second) {
      container.appendChild(cell("p", t("compare_empty")));
      document.getElementById("save-comparison").disabled = true;
      return;
    }
    document.getElementById("save-comparison").disabled = false;
    var table = cell("table", "", "comparison-table");
    table.appendChild(cell("caption", t("compare_h"), "visually-hidden"));
    var head = document.createElement("thead");
    var headRow = document.createElement("tr");
    var modeHeader = cell("th", t("mode_label"));
    modeHeader.scope = "col";
    headRow.appendChild(modeHeader);
    [first, second].forEach(function (state) {
      var stateHeader = cell("th", state.state_name + " (" + state.state_abbreviation + ")");
      stateHeader.scope = "col";
      headRow.appendChild(stateHeader);
    });
    head.appendChild(headRow);
    table.appendChild(head);
    var body = document.createElement("tbody");
    EXPECTED_MODES.forEach(function (mode) {
      var a = rowFor(first.state_abbreviation, mode);
      var b = rowFor(second.state_abbreviation, mode);
      var max = Math.max(a.count || 0, b.count || 0, 1);
      var comparisonRow = cell("tr", "", "comparison-row");
      var modeCell = cell("th", modeLabel(mode), "comparison-mode");
      modeCell.scope = "row";
      comparisonRow.appendChild(modeCell);
      [
        { state: first, value: a, second: false },
        { state: second, value: b, second: true },
      ].forEach(function (item) {
        var block = cell("td", "", "comparison-value" + (item.second ? " is-second" : ""));
        block.appendChild(
          cell(
            "strong",
            item.value.status === "published" ? number(item.value.count) : statusText(item.value.status)
          )
        );
        var track = cell("span", "", "comparison-track");
        track.setAttribute("aria-hidden", "true");
        var bar = cell("span", "");
        bar.style.inlineSize =
          item.value.status === "published" ? ((item.value.count / max) * 100).toFixed(2) + "%" : "0%";
        track.appendChild(bar);
        block.appendChild(track);
        comparisonRow.appendChild(block);
      });
      body.appendChild(comparisonRow);
    });
    table.appendChild(body);
    container.appendChild(table);
  }

  function renderInspector() {
    var heading = document.getElementById("inspector-heading");
    var content = document.getElementById("inspector-content");
    var state = stateRecord(viewState.selectedState);
    content.textContent = "";
    if (!state) {
      heading.textContent = t("inspector_h");
      content.appendChild(cell("p", t("inspector_empty")));
      return;
    }
    heading.textContent = state.state_name + " (" + state.state_abbreviation + ")";
    var meta = cell("div", "", "inspector-meta");
    meta.appendChild(cell("span", String(artifact.dataset_year)));
    meta.appendChild(cell("span", t("release_stage_" + artifact.source.release_stage)));
    meta.appendChild(cell("span", "FARS " + state.state_code));
    content.appendChild(meta);
    var dl = cell("dl", "", "inspector-modes");
    rowsForState(state.state_abbreviation).forEach(function (row) {
      var wrapper = document.createElement("div");
      wrapper.appendChild(cell("dt", modeLabel(row.mode)));
      var dd = cell("dd", row.status === "published" ? number(row.count) : statusText(row.status));
      if (row.status !== "published") dd.className = "is-unpublished";
      wrapper.appendChild(dd);
      dl.appendChild(wrapper);
    });
    content.appendChild(dl);
    var mode = focusMode();
    var current = rowFor(state.state_abbreviation, mode);
    if (current && current.status === "published") {
      var ranked = rankedRows(mode);
      var index = ranked.findIndex(function (row) {
        return row.stateAbbreviation === state.state_abbreviation;
      });
      content.appendChild(
        cell(
          "p",
          tpl(t("inspector_rank"), {
            mode: modeLabel(mode),
            rank: number(index + 1),
            total: number(ranked.length),
          }),
          "inspector-rank"
        )
      );
    }
    var actions = cell("div", "", "inspector-actions");
    var compareButton = cell("button", t("compare_with"));
    compareButton.type = "button";
    compareButton.addEventListener("click", function () {
      viewState.compareA = state.state_abbreviation;
      viewState.view = "compare";
      renderAll();
      syncUrl();
      var compareA = document.getElementById("compare-a");
      if (compareA) compareA.focus();
    });
    var saveButton = cell("button", t("add_to_brief"));
    saveButton.type = "button";
    saveButton.addEventListener("click", function () {
      saveState(state.state_abbreviation);
    });
    actions.appendChild(compareButton);
    actions.appendChild(saveButton);
    content.appendChild(actions);
  }

  function announceBrief(message) {
    document.getElementById("brief-status").textContent = message;
  }

  function saveState(abbreviation) {
    if (!abbreviation || !isValidState(abbreviation) || viewState.saved.indexOf(abbreviation) >= 0) return;
    viewState.saved.push(abbreviation);
    viewState.saved = viewState.saved.slice(0, 4);
    renderBrief();
    syncUrl();
    announceBrief(t("brief_saved"));
  }

  function renderBrief() {
    var container = document.getElementById("brief-items");
    container.textContent = "";
    var validSaved = viewState.saved.filter(function (abbreviation) {
      return Boolean(stateRecord(abbreviation));
    });
    viewState.saved = validSaved;
    if (!validSaved.length) {
      container.appendChild(cell("p", t("brief_empty"), "brief-empty"));
      return;
    }
    var mode = focusMode();
    validSaved.forEach(function (abbreviation, savedIndex) {
      var state = stateRecord(abbreviation);
      var row = rowFor(abbreviation, mode);
      var card = cell("article", "", "brief-card");
      card.appendChild(cell("h3", state.state_name + " (" + abbreviation + ")"));
      card.appendChild(
        cell(
          "p",
          row.status === "published"
            ? tpl(t("brief_count"), {
                count: number(row.count),
                mode: modeLabel(mode),
                year: String(artifact.dataset_year),
              })
            : tpl(t("brief_unpublished"), { mode: modeLabel(mode) })
        )
      );
      card.appendChild(
        cell(
          "p",
          artifact.source.name + " · " + t("release_stage_" + artifact.source.release_stage),
          "brief-source"
        )
      );
      var remove = cell("button", "×", "remove-brief");
      remove.type = "button";
      remove.setAttribute("aria-label", tpl(t("remove_brief"), { state: state.state_name }));
      remove.addEventListener("click", function () {
        viewState.saved = viewState.saved.filter(function (value) {
          return value !== abbreviation;
        });
        renderBrief();
        syncUrl();
        announceBrief(t("brief_removed"));
        var remainingRemoveButtons = container.querySelectorAll(".remove-brief");
        var focusTarget = remainingRemoveButtons[Math.min(savedIndex, remainingRemoveButtons.length - 1)];
        if (!focusTarget) focusTarget = document.getElementById("clear-brief");
        if (focusTarget) focusTarget.focus();
      });
      card.appendChild(remove);
      container.appendChild(card);
    });
  }

  function applyView() {
    document.querySelectorAll("[data-panel]").forEach(function (panel) {
      panel.hidden = panel.getAttribute("data-panel") !== viewState.view;
    });
    document.querySelectorAll("[data-view]").forEach(function (button) {
      button.setAttribute("aria-pressed", button.getAttribute("data-view") === viewState.view ? "true" : "false");
    });
  }

  function normalizeViewState() {
    viewState.selectedState = stateRecord(viewState.selectedState) ? viewState.selectedState : null;
    viewState.compareA = stateRecord(viewState.compareA)
      ? viewState.compareA
      : viewState.selectedState || "CA";
    viewState.compareB = stateRecord(viewState.compareB) ? viewState.compareB : "TX";
    if (viewState.compareA === viewState.compareB) {
      viewState.compareB = viewState.compareA === "TX" ? "CA" : "TX";
    }
    viewState.saved = viewState.saved.filter(function (abbreviation) {
      return Boolean(stateRecord(abbreviation));
    });
  }

  function renderAll() {
    if (!artifact) return;
    normalizeViewState();
    renderArtifactControls();
    renderMetadata();
    renderMap();
    renderMatrix();
    renderRank();
    renderScatter();
    renderComparison();
    renderInspector();
    renderBrief();
    renderTable();
    applyView();
  }

  function applyTranslations() {
    document.documentElement.lang = lang;
    document.title = t("title");
    document.querySelectorAll("[data-i18n]").forEach(function (element) {
      renderTranslation(element, element.getAttribute("data-i18n"));
    });
    document.querySelectorAll("[data-i18n-aria]").forEach(function (element) {
      element.setAttribute("aria-label", t(element.getAttribute("data-i18n-aria")));
    });
    document.querySelectorAll("[data-lang]").forEach(function (button) {
      button.setAttribute("aria-pressed", button.getAttribute("data-lang") === lang ? "true" : "false");
    });
    updateProofRail(currentRelease ? currentRelease.dataset_year : null);
    renderAll();
    if (profileArtifacts && profileState) renderStateProfile();
  }

  function clearVisualizations(message) {
    ["us-map", "matrix-head", "matrix-body", "rank-list", "rank-unpublished", "scatter-plot", "scatter-table-head", "scatter-table-body", "state-comparison", "inspector-content", "brief-items"].forEach(
      function (id) {
        var element = document.getElementById(id);
        if (element) element.textContent = "";
      }
    );
    ["map-caption", "matrix-caption", "scatter-caption", "rank-unpublished-summary"].forEach(function (id) {
      var element = document.getElementById(id);
      if (element) element.textContent = message || "";
    });
  }

  function showLoading() {
    artifact = null;
    rows = [];
    clearMetadata();
    clearVisualizations(t("loading"));
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
    clearVisualizations(t("load_error"));
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

  function exactOptionalParameter(params, name, validator, message) {
    if (!params.has(name)) return null;
    var values = params.getAll(name);
    assert(values.length === 1, "requested " + name + " must be unambiguous");
    assert(validator(values[0]), message);
    return values[0];
  }

  function restoreStudioStateFromUrl(selectedState) {
    var params = new URLSearchParams(window.location.search);
    var requestedView = exactOptionalParameter(
      params,
      "view",
      function (value) {
        return hasOwn(VALID_VIEWS, value);
      },
      "requested view is unsupported"
    );
    var primary = exactOptionalParameter(
      params,
      "mode",
      function (value) {
        return EXPECTED_MODES.indexOf(value) >= 0;
      },
      "requested mode is unsupported"
    );
    var secondary = exactOptionalParameter(
      params,
      "secondary",
      function (value) {
        return EXPECTED_MODES.indexOf(value) >= 0;
      },
      "requested secondary mode is unsupported"
    );
    var scale = exactOptionalParameter(
      params,
      "scale",
      function (value) {
        return value === "linear" || value === "log";
      },
      "requested scale is unsupported"
    );
    var compareA = exactOptionalParameter(params, "a", isValidState, "requested comparison state A is unsupported");
    var compareB = exactOptionalParameter(params, "b", isValidState, "requested comparison state B is unsupported");
    var saved = exactOptionalParameter(
      params,
      "saved",
      function (value) {
        if (!/^[A-Z]{2}(,[A-Z]{2}){0,3}$/.test(value)) return false;
        var abbreviations = value.split(",");
        return (
          new Set(abbreviations).size === abbreviations.length &&
          abbreviations.every(function (abbreviation) {
            return isValidState(abbreviation);
          })
        );
      },
      "requested saved-state list is unsupported"
    );
    if (requestedView) viewState.view = requestedView;
    if (primary) {
      viewState.primaryMode = primary;
      requestedModeFromUrl = primary;
    }
    if (secondary) viewState.secondaryMode = secondary;
    if (scale) viewState.scale = scale;
    viewState.selectedState = selectedState || null;
    viewState.compareA = compareA || selectedState || null;
    viewState.compareB = compareB;
    viewState.saved = saved ? saved.split(",") : [];
  }

  function syncUrl() {
    if (!window.history || !window.history.replaceState) return;
    var params = new URLSearchParams();
    var selectedYear = currentRelease
      ? currentRelease.dataset_year
      : Number(document.getElementById("year-filter").value || (releaseIndex && releaseIndex.default_year));
    if (isSupportedYear(selectedYear)) params.set("year", String(selectedYear));
    params.set("lang", lang);
    if (viewState.view !== "map") params.set("view", viewState.view);
    if (viewState.primaryMode !== "pedalcyclist") params.set("mode", viewState.primaryMode);
    if (viewState.secondaryMode !== "pedestrian") params.set("secondary", viewState.secondaryMode);
    if (viewState.selectedState) params.set("state", viewState.selectedState);
    if (viewState.compareA && viewState.compareA !== "CA") params.set("a", viewState.compareA);
    if (viewState.compareB && viewState.compareB !== "TX") params.set("b", viewState.compareB);
    if (viewState.scale !== "linear") params.set("scale", viewState.scale);
    if (viewState.saved.length) params.set("saved", viewState.saved.join(","));
    var query = params.toString();
    window.history.replaceState(null, "", window.location.pathname + (query ? "?" + query : "") + window.location.hash);
  }

  function updateYearUrl(year) {
    assert(currentRelease && currentRelease.dataset_year === year, "cannot share an inactive release year");
    syncUrl();
  }

  function updateStateUrl(state) {
    viewState.selectedState = state || null;
    if (state) viewState.compareA = state;
    syncUrl();
  }

  function updateLanguageUrl() {
    syncUrl();
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
        renderAll();
        loadStateProfile(state);
      } else if (event.target && event.target.id === "mode-filter") {
        requestedModeFromUrl = null;
        viewState.primaryMode = event.target.value;
        renderAll();
        syncUrl();
      } else {
        renderAll();
        syncUrl();
      }
    });
    document.getElementById("ledger-mode-filter").addEventListener("change", function () {
      renderTable();
    });
    form.addEventListener("reset", function (event) {
      event.preventDefault();
      if (!releaseIndex) return;
      requestedModeFromUrl = null;
      document.getElementById("state-filter").value = "";
      document.getElementById("mode-filter").value = "pedalcyclist";
      document.getElementById("ledger-mode-filter").value = "";
      document.getElementById("status-filter").value = "";
      viewState.view = "map";
      viewState.primaryMode = "pedalcyclist";
      viewState.secondaryMode = "pedestrian";
      viewState.selectedState = null;
      viewState.compareA = null;
      viewState.compareB = null;
      viewState.scale = "linear";
      ++profileRequestSerial;
      updateStateUrl("");
      showProfileEmpty();
      loadRelease(releaseForYear(releaseIndex.default_year), true);
    });
    document.querySelectorAll("[data-view]").forEach(function (button) {
      button.addEventListener("click", function () {
        viewState.view = button.getAttribute("data-view");
        applyView();
        syncUrl();
      });
    });
    document.getElementById("secondary-mode").addEventListener("change", function (event) {
      viewState.secondaryMode = event.target.value;
      renderScatter();
      syncUrl();
    });
    document.querySelectorAll('input[name="scale"]').forEach(function (radio) {
      radio.addEventListener("change", function () {
        if (!radio.checked) return;
        viewState.scale = radio.value;
        renderScatter();
        syncUrl();
      });
    });
    document.getElementById("compare-a").addEventListener("change", function (event) {
      var state = event.target.value;
      if (state && !isValidState(state)) return;
      viewState.compareA = state || null;
      viewState.selectedState = state || null;
      document.getElementById("state-filter").value = state;
      renderAll();
      loadStateProfile(state);
      syncUrl();
    });
    document.getElementById("compare-b").addEventListener("change", function (event) {
      var state = event.target.value;
      if (state && !isValidState(state)) return;
      viewState.compareB = state || null;
      renderAll();
      syncUrl();
    });
    document.getElementById("save-comparison").addEventListener("click", function () {
      saveState(viewState.compareA);
      saveState(viewState.compareB);
    });
    document.getElementById("clear-brief").addEventListener("click", function () {
      viewState.saved = [];
      renderBrief();
      syncUrl();
      announceBrief(t("brief_cleared"));
    });
    document.getElementById("print-brief").addEventListener("click", function () {
      window.print();
    });
    document.getElementById("copy-view").addEventListener("click", function () {
      syncUrl();
      var value = window.location.href;
      if (window.navigator.clipboard && window.navigator.clipboard.writeText) {
        window.navigator.clipboard.writeText(value).then(
          function () {
            announceBrief(t("view_copied"));
          },
          function () {
            announceBrief(t("copy_failed"));
          }
        );
      } else {
        var input = document.createElement("textarea");
        input.value = value;
        input.setAttribute("readonly", "");
        document.body.appendChild(input);
        input.select();
        var copied = document.execCommand && document.execCommand("copy");
        input.remove();
        announceBrief(copied ? t("view_copied") : t("copy_failed"));
      }
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
    validateBoundaryArtifact: validateBoundaryArtifact,
    indexUrl: INDEX_URL,
    dataUrl: DEFAULT_2024_DATA_URL,
    boundaryUrl: BOUNDARY_URL,
    getState: function () {
      return JSON.parse(JSON.stringify(viewState));
    },
  };

  bindEvents();
  Promise.all([i18n.load("en"), i18n.load(lang)])
    .then(function () {
      i18n.setLang(lang);
      applyTranslations();
      return Promise.all([fetch(INDEX_URL), loadBoundaryArtifact()]);
    })
    .then(function (loaded) {
      boundaryArtifact = loaded[1];
      return verifiedJson(loaded[0], EXPECTED_INDEX_BYTES, EXPECTED_INDEX_SHA256, "release index");
    })
    .then(function (data) {
      releaseIndex = validateIndex(data);
      populateYearControl(releaseIndex.default_year);
      updateProofRail(null);
      validateRequestedLanguage();
      var year = requestedYear();
      var state = requestedState();
      restoreStudioStateFromUrl(state);
      populateYearControl(year);
      populateStateControl(state);
      var selectedRelease = loadRelease(releaseForYear(year), false);
      var selectedProfile = state ? loadStateProfile(state) : Promise.resolve();
      return Promise.all([selectedRelease, selectedProfile]).then(function () {
        if (artifact) {
          syncUrl();
        }
      });
    })
    .catch(function () {
      ++profileRequestSerial;
      showError();
      showProfileError();
    });
})();
