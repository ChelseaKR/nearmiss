(function () {
  "use strict";

  // The safe sample carries a per-segment denominator (bike_count) so the computed
  // rate path runs on it. No segment reaches the small-sample threshold, so the
  // sample stops at Tier 1 and says why — it never hands out an elevated-rate sentence.
  var SAMPLE_ROWS = [
    { report_id: "S-001", latitude: "38.5449", longitude: "-121.7405", occurred_at: "2026-05-02", hazard_type: "close_pass", corridor_id: "mercer-8", bike_count: "1200" },
    { report_id: "S-002", latitude: "38.5450", longitude: "-121.7407", occurred_at: "2026-05-04", hazard_type: "close_pass", corridor_id: "mercer-8", bike_count: "1200" },
    { report_id: "S-003", latitude: "38.5451", longitude: "-121.7406", occurred_at: "2026-05-08", hazard_type: "sightline", corridor_id: "mercer-8", bike_count: "1200" },
    { report_id: "S-004", latitude: "38.5462", longitude: "-121.7420", occurred_at: "2026-05-09", hazard_type: "surface", corridor_id: "pine-2", bike_count: "950" },
    { report_id: "S-005", latitude: "38.5463", longitude: "-121.7421", occurred_at: "2026-05-10", hazard_type: "surface", corridor_id: "pine-2", bike_count: "950" },
    { report_id: "S-006", latitude: "38.5470", longitude: "-121.7430", occurred_at: "2026-05-11", hazard_type: "dooring", corridor_id: "oak-4", bike_count: "400" },
  ];

  var FIELD_GROUPS = {
    latitude: ["latitude", "lat", "y"],
    longitude: ["longitude", "lon", "lng", "x"],
    address: ["address", "location", "street_address"],
    date: ["occurred_at", "date", "timestamp", "reported_at", "datetime"],
    hazard: ["hazard_type", "incident_type", "type", "category"],
    segment: ["segment_id", "corridor_id", "street_segment", "location_id"],
    exposure: ["exposure", "exposure_estimate", "exposure_count", "denominator", "bike_count", "bicycle_count", "trips", "aadt", "aadb", "volume"],
  };

  // Thresholds mirror the engine's config defaults (src/nearmiss/config.py) so the
  // browser screen never holds a lower bar than the published pipeline.
  var RATE_PER = 1000;
  var SMALL_N = 5; // below this the engine labels a rate "uncertain"
  var MIN_PUBLISH_N = 3; // k-anonymity floor: 0 < n < this is withheld

  var CLAIMS = {
    0: {
      claim: "Available evidence is insufficient to rank or characterize {place}.",
      supports: "A transparent coverage-gap finding and a targeted plan to collect or repair data.",
      cannot: "A safety ranking, elevated-risk statement, causal claim, or treatment recommendation.",
      next: "Collect location-complete reports or obtain a usable denominator before prioritizing the corridor.",
    },
    1: {
      claim: "Repeated community reports at {place} warrant investigation.",
      supports: "A field audit, targeted count, listening session, or request for an independent evidence source.",
      cannot: "That the place is more dangerous than another place, that anyone caused the events, or that a treatment will work.",
      next: "Conduct a documented field audit or collect aligned exposure data.",
    },
    2: {
      // Tier 2 is never a flat sentence: it is issued only from a computed basis
      // (count, denominator, interval, comparison) and carries those numbers.
      claim: "The observed report rate at {place} is elevated in the stated observation window: {basis}",
      supports: "Scoping a treatment conversation or deeper study when the denominator, interval, and sensitivity checks travel with the claim.",
      cannot: "Causation, individual fault, a guaranteed safety benefit, or an unqualified comparison outside the analysis window.",
      next: "Seek an independent evidence track and preregister how any follow-up change will be evaluated.",
    },
    3: {
      // Agreement with the independent source is declared, not evaluated here, so
      // the sentence is conditional on that review rather than asserting it.
      claim: "If the declared independent outcome source agrees on review, it supports prioritizing {place} for further action. The computed basis is an elevated report rate: {basis}",
      supports: "Advancing a named decision while preserving each source, uncertainty statement, and evaluation commitment.",
      cannot: "That one intervention is proven to be best, that observational agreement establishes cause, or that future harm will certainly decline.",
      next: "Name the decision owner, requested action, baseline, follow-up window, and comparison strategy.",
    },
  };
  var HANDOFF_PREFIX = "nearmiss:studio-handoff:";
  var HANDOFF_SCHEMA = "nearmiss.studio_handoff.v2";

  function normalizeField(value) {
    return String(value || "")
      .trim()
      .toLowerCase()
      .replace(/[\s-]+/g, "_")
      .replace(/[^a-z0-9_]/g, "");
  }

  function parseCsv(text) {
    var rows = [];
    var row = [];
    var field = "";
    var quoted = false;
    for (var index = 0; index < text.length; index += 1) {
      var character = text[index];
      if (quoted) {
        if (character === '"' && text[index + 1] === '"') {
          field += '"';
          index += 1;
        } else if (character === '"') {
          quoted = false;
        } else {
          field += character;
        }
      } else if (character === '"') {
        quoted = true;
      } else if (character === ",") {
        row.push(field);
        field = "";
      } else if (character === "\n") {
        row.push(field.replace(/\r$/, ""));
        rows.push(row);
        row = [];
        field = "";
      } else {
        field += character;
      }
    }
    if (quoted) throw new Error("CSV contains an unclosed quoted field.");
    if (field || row.length) {
      row.push(field.replace(/\r$/, ""));
      rows.push(row);
    }
    rows = rows.filter(function (values) {
      return values.some(function (value) {
        return value.trim() !== "";
      });
    });
    if (rows.length < 2) throw new Error("CSV needs a header and at least one data row.");
    var headers = rows[0].map(normalizeField);
    if (!headers.every(Boolean) || new Set(headers).size !== headers.length) {
      throw new Error("CSV headers must be non-empty and unique.");
    }
    return rows.slice(1).map(function (values) {
      var record = {};
      headers.forEach(function (header, headerIndex) {
        record[header] = values[headerIndex] === undefined ? "" : values[headerIndex].trim();
      });
      return record;
    });
  }

  function parseEvidence(text, fileName) {
    var lowerName = String(fileName || "").toLowerCase();
    if (lowerName.endsWith(".json") || text.trim().startsWith("[") || text.trim().startsWith("{")) {
      var parsed = JSON.parse(text);
      var records = Array.isArray(parsed)
        ? parsed
        : Array.isArray(parsed.reports)
          ? parsed.reports
          : Array.isArray(parsed.features)
            ? parsed.features.map(function (feature) {
                return Object.assign({}, feature.properties || {}, {
                  longitude: feature.geometry && feature.geometry.type === "Point" ? feature.geometry.coordinates[0] : "",
                  latitude: feature.geometry && feature.geometry.type === "Point" ? feature.geometry.coordinates[1] : "",
                });
              })
            : null;
      if (!records || !records.length || !records.every(function (record) { return record && typeof record === "object" && !Array.isArray(record); })) {
        throw new Error("JSON must contain a non-empty array of report objects, reports, or point features.");
      }
      return records.map(function (record) {
        var normalized = {};
        Object.keys(record).forEach(function (key) {
          normalized[normalizeField(key)] = record[key];
        });
        return normalized;
      });
    }
    return parseCsv(text);
  }

  function findField(headers, group) {
    return FIELD_GROUPS[group].find(function (candidate) {
      return headers.indexOf(candidate) >= 0;
    }) || "";
  }

  function populatedCount(rows, field) {
    if (!field) return 0;
    return rows.filter(function (row) {
      return row[field] !== null && row[field] !== undefined && String(row[field]).trim() !== "";
    }).length;
  }

  function suppressionEstimate(rows, segmentField, floor) {
    if (!segmentField) return { known: false, groups: 0, withheldGroups: 0, withheldRows: 0 };
    var counts = {};
    rows.forEach(function (row) {
      var value = String(row[segmentField] || "").trim();
      if (value) counts[value] = (counts[value] || 0) + 1;
    });
    var values = Object.keys(counts).map(function (key) { return counts[key]; });
    return {
      known: values.length > 0,
      groups: values.length,
      withheldGroups: values.filter(function (count) { return count < floor; }).length,
      withheldRows: values.filter(function (count) { return count < floor; }).reduce(function (total, count) { return total + count; }, 0),
    };
  }


  // --- Rate functions: a direct port of src/honest_rates/rates.py -----------------
  // Byar's approximation to the exact Poisson interval (Breslow & Day 1987), the
  // quasi-Poisson widening for overdispersion (RR-02), and the Wilson interval.
  // tests/fixtures/rates/interval_vectors.json pins this port to the Python
  // functions the engine publishes with; web/workflow_check.mjs replays it.
  var Z95 = 1.959963984540054;

  function poissonCi(count, z) {
    var zz = z === undefined ? Z95 : z;
    if (count < 0) throw new Error("count must be non-negative");
    var low;
    if (count === 0) {
      low = 0;
    } else {
      low = count * Math.pow(1 - 1 / (9 * count) - zz / (3 * Math.sqrt(count)), 3);
    }
    var c1 = count + 1;
    var high = c1 * Math.pow(1 - 1 / (9 * c1) + zz / (3 * Math.sqrt(c1)), 3);
    return [Math.max(0, low), high];
  }

  function pearsonDispersion(counts, exposures) {
    if (counts.length !== exposures.length) throw new Error("counts and exposures must align");
    var pairs = [];
    for (var index = 0; index < counts.length; index += 1) {
      if (exposures[index] > 0) pairs.push([counts[index], exposures[index]]);
    }
    var n = pairs.length;
    if (n < 2) return 1;
    var totalY = 0;
    var totalE = 0;
    pairs.forEach(function (pair) {
      totalY += pair[0];
      totalE += pair[1];
    });
    if (totalY <= 0 || totalE <= 0) return 1;
    var theta = totalY / totalE;
    var chi2 = 0;
    pairs.forEach(function (pair) {
      var expected = theta * pair[1];
      chi2 += Math.pow(pair[0] - expected, 2) / expected;
    });
    return chi2 / (n - 1);
  }

  function quasiPoissonCi(count, dispersion, z) {
    var bounds = poissonCi(count, z);
    var scale = dispersion > 1 ? Math.sqrt(dispersion) : 1;
    if (scale === 1) return bounds;
    var widenedLow = count - (count - bounds[0]) * scale;
    var widenedHigh = count + (bounds[1] - count) * scale;
    return [Math.max(0, widenedLow), widenedHigh];
  }

  function rateWithCi(count, exposure, per, z, dispersion) {
    if (!(exposure > 0)) throw new Error("exposure must be positive to compute a rate");
    var scale = (per === undefined ? RATE_PER : per) / exposure;
    var bounds = quasiPoissonCi(count, dispersion === undefined ? 1 : dispersion, z);
    return [count * scale, bounds[0] * scale, bounds[1] * scale];
  }

  function wilsonCi(successes, trials, z) {
    var zz = z === undefined ? Z95 : z;
    if (trials <= 0) return [0, 0];
    if (successes < 0 || successes > trials) throw new Error("successes must be in [0, trials]");
    var p = successes / trials;
    var denom = 1 + (zz * zz) / trials;
    var centre = (p + (zz * zz) / (2 * trials)) / denom;
    var half = (zz * Math.sqrt((p * (1 - p)) / trials + (zz * zz) / (4 * trials * trials))) / denom;
    return [Math.max(0, centre - half), Math.min(1, centre + half)];
  }

  function parseExposure(value) {
    if (value === null || value === undefined) return NaN;
    var text = String(value).trim().replace(/,/g, "");
    if (!text) return NaN;
    var number = Number(text);
    return Number.isFinite(number) && number > 0 ? number : NaN;
  }

  function formatNumber(value) {
    return Number(value).toFixed(2).replace(/\.?0+$/, "");
  }

  function segmentValues(rows, segmentField) {
    if (!segmentField) return [];
    var seen = {};
    rows.forEach(function (row) {
      var value = String(row[segmentField] === undefined || row[segmentField] === null ? "" : row[segmentField]).trim();
      if (value) seen[value] = true;
    });
    return Object.keys(seen).sort();
  }

  // What the Studio can actually compute about a rate from the rows it has: one
  // denominator per segment from the file's own column, a Byar interval per
  // segment (the dispersion is computed and reported alongside), and a comparison of the
  // chosen segment against the other segments in the same file. Every way this
  // can fail is named in `reason`/`claimReason` instead of being filled in.
  function rateEvidence(rows, segmentField, exposureField, chosenSegment) {
    var evidence = {
      exposureField: exposureField,
      segmentField: segmentField,
      computable: false,
      reason: "",
      segments: [],
      excluded: [],
      dispersion: 1,
      place: null,
      comparison: null,
      elevated: false,
      claimReason: "",
      basis: null,
    };
    if (!exposureField) {
      evidence.reason =
        "No denominator column was found (recognized names: " + FIELD_GROUPS.exposure.join(", ") + "). Without one, no rate exists to compare.";
      evidence.claimReason = evidence.reason;
      return evidence;
    }
    if (!segmentField) {
      evidence.reason = "A denominator column (" + exposureField + ") was found, but no segment or corridor identifier, so nothing ties it to a place.";
      evidence.claimReason = evidence.reason;
      return evidence;
    }
    var groups = {};
    rows.forEach(function (row) {
      var id = String(row[segmentField] === undefined || row[segmentField] === null ? "" : row[segmentField]).trim();
      if (!id) return;
      if (!groups[id]) groups[id] = { id: id, count: 0, values: [] };
      groups[id].count += 1;
      groups[id].values.push(parseExposure(row[exposureField]));
    });
    Object.keys(groups).sort().forEach(function (id) {
      var group = groups[id];
      var usable = group.values.filter(Number.isFinite);
      var distinct = Array.from(new Set(usable));
      if (usable.length === group.values.length && distinct.length === 1) {
        evidence.segments.push({ id: id, count: group.count, exposure: distinct[0] });
      } else {
        evidence.excluded.push({
          id: id,
          count: group.count,
          problem: distinct.length > 1 ? "rows disagree on its denominator" : "its denominator is missing or not a positive number",
        });
      }
    });
    if (!evidence.segments.length) {
      evidence.reason = "The denominator column (" + exposureField + ") carries no usable value: " + describeExcluded(evidence.excluded) + ".";
      evidence.claimReason = evidence.reason;
      return evidence;
    }
    evidence.dispersion = pearsonDispersion(
      evidence.segments.map(function (segment) { return segment.count; }),
      evidence.segments.map(function (segment) { return segment.exposure; })
    );
    // Intervals are the Byar Poisson interval, the engine's published default
    // (config.overdispersion_adjust is off). The dispersion is still computed and
    // reported, and the chosen segment's lower bound under the sqrt(phi) widening
    // travels with the claim as a sensitivity statement (RR-02).
    evidence.segments.forEach(function (segment) {
      var bounds = rateWithCi(segment.count, segment.exposure, RATE_PER, Z95, 1);
      segment.rate = bounds[0];
      segment.low = bounds[1];
      segment.high = bounds[2];
      segment.widenedLow = evidence.dispersion > 1
        ? rateWithCi(segment.count, segment.exposure, RATE_PER, Z95, evidence.dispersion)[1]
        : null;
      segment.publishable = !(segment.count > 0 && segment.count < MIN_PUBLISH_N);
      segment.confidence = segment.count < SMALL_N ? "uncertain" : "certain";
    });
    evidence.computable = true;
    evidence.reason =
      evidence.segments.length + " of " + (evidence.segments.length + evidence.excluded.length) + " segments carry one positive " + exposureField + " value" +
      (evidence.excluded.length ? "; excluded: " + describeExcluded(evidence.excluded) : "") + ".";

    if (!chosenSegment) {
      evidence.claimReason = "Choose which segment in the file is the named place; a rate cannot be attached to a place the file does not identify.";
      return evidence;
    }
    var place = evidence.segments.find(function (segment) { return segment.id === chosenSegment; });
    if (!place) {
      var excluded = evidence.excluded.find(function (segment) { return segment.id === chosenSegment; });
      evidence.claimReason = excluded
        ? "The chosen segment " + chosenSegment + " has no usable denominator: " + excluded.problem + "."
        : "The chosen segment " + chosenSegment + " is not in the file.";
      return evidence;
    }
    evidence.place = place;
    var others = evidence.segments.filter(function (segment) { return segment.id !== chosenSegment; });
    if (!others.length) {
      evidence.claimReason = "No other segment in the file carries a denominator, so there is nothing to compare " + place.id + " against.";
      return evidence;
    }
    var pooledCount = others.reduce(function (total, segment) { return total + segment.count; }, 0);
    var pooledExposure = others.reduce(function (total, segment) { return total + segment.exposure; }, 0);
    evidence.comparison = {
      segments: others.length,
      count: pooledCount,
      exposure: pooledExposure,
      rate: (pooledCount / pooledExposure) * RATE_PER,
    };
    if (!place.publishable) {
      evidence.claimReason = place.id + " has " + place.count + " reports, below the k=" + MIN_PUBLISH_N + " privacy floor, so no rate is published for it.";
    } else if (place.count < SMALL_N) {
      evidence.claimReason = place.id + " has " + place.count + " reports, below the small-sample threshold of " + SMALL_N + "; its rate is uncertain and cannot carry an elevated-rate claim.";
    } else if (place.low > evidence.comparison.rate) {
      evidence.elevated = true;
      evidence.claimReason = "The interval's lower bound (" + formatNumber(place.low) + ") exceeds the pooled rate of the other segments (" + formatNumber(evidence.comparison.rate) + "), so the rate is elevated relative to them.";
      evidence.basis = {
        segment: place.id,
        count: place.count,
        exposure: place.exposure,
        unit: exposureField,
        per: RATE_PER,
        rate: place.rate,
        low: place.low,
        high: place.high,
        dispersion: evidence.dispersion,
        widenedLow: place.widenedLow,
        comparisonSegments: others.length,
        comparisonRate: evidence.comparison.rate,
      };
    } else {
      evidence.claimReason = "The interval (" + formatNumber(place.low) + "–" + formatNumber(place.high) + ") covers the pooled rate of the other segments (" + formatNumber(evidence.comparison.rate) + "), so the rate is not distinguishable from theirs.";
    }
    return evidence;
  }

  function describeExcluded(excluded) {
    return excluded.map(function (segment) { return segment.id + " (" + segment.problem + ")"; }).join("; ");
  }

  function describePlaceRate(evidence) {
    var place = evidence.place;
    return (
      place.id + ": " + place.count + " reports over " + formatNumber(place.exposure) + " " + evidence.exposureField +
      " = " + formatNumber(place.rate) + " per " + RATE_PER + " (95% Byar interval " + formatNumber(place.low) + "–" + formatNumber(place.high) + "). " +
      "Other " + evidence.comparison.segments + " segment" + (evidence.comparison.segments === 1 ? "" : "s") + " pooled: " +
      formatNumber(evidence.comparison.rate) + " per " + RATE_PER + ". " + evidence.claimReason + " " + describeDispersion(evidence.dispersion, place.widenedLow, evidence.comparison.rate)
    );
  }

  function describeDispersion(dispersion, widenedLow, comparisonRate) {
    if (!(dispersion > 1)) {
      return "Dispersion φ=" + formatNumber(dispersion) + ": no overdispersion detected.";
    }
    var survives = typeof widenedLow === "number" && widenedLow > comparisonRate;
    return (
      "Dispersion φ=" + formatNumber(dispersion) + " (counts more variable than Poisson; interval not widened, matching the engine's published default). " +
      "Sensitivity: widened by √φ the lower bound would be " + formatNumber(widenedLow) + " per " + RATE_PER + ", which " +
      (survives ? "still clears" : "does not clear") + " the comparison" +
      (survives ? "." : " — treat any elevated-rate sentence as fragile until reports are deduplicated.")
    );
  }

  // A basis is the computed record a tier-2/3 sentence is issued from. Anything
  // missing or inconsistent means no such sentence is issued at all.
  function validBasis(basis) {
    if (!basis || typeof basis !== "object") return false;
    var numbers = ["count", "exposure", "per", "rate", "low", "high", "dispersion", "comparisonSegments", "comparisonRate"];
    if (basis.widenedLow !== null && !(typeof basis.widenedLow === "number" && Number.isFinite(basis.widenedLow))) return false;
    if (!numbers.every(function (key) { return typeof basis[key] === "number" && Number.isFinite(basis[key]); })) return false;
    if (typeof basis.segment !== "string" || !basis.segment.trim()) return false;
    if (typeof basis.unit !== "string" || !basis.unit.trim()) return false;
    if (!Number.isInteger(basis.count) || basis.count < SMALL_N) return false;
    if (!Number.isInteger(basis.comparisonSegments) || basis.comparisonSegments < 1) return false;
    if (basis.exposure <= 0 || basis.per <= 0 || basis.dispersion < 0) return false;
    if (!(basis.low <= basis.rate && basis.rate <= basis.high)) return false;
    if (!(basis.low > basis.comparisonRate)) return false;
    return true;
  }

  function describeBasis(basis) {
    return (
      basis.count + " reports over " + formatNumber(basis.exposure) + " " + basis.unit + " (" + formatNumber(basis.rate) + " per " + basis.per +
      "; 95% interval " + formatNumber(basis.low) + "–" + formatNumber(basis.high) + ") against " + formatNumber(basis.comparisonRate) + " per " + basis.per +
      " pooled across the other " + basis.comparisonSegments + " segment" + (basis.comparisonSegments === 1 ? "" : "s") + " in the same file."
    );
  }

  function assessReadiness(rows, options) {
    if (!Array.isArray(rows) || !rows.length) throw new Error("No report rows were available to assess.");
    var headers = Array.from(new Set(rows.flatMap(function (row) { return Object.keys(row); })));
    var latitude = findField(headers, "latitude");
    var longitude = findField(headers, "longitude");
    var address = findField(headers, "address");
    var date = findField(headers, "date");
    var hazard = findField(headers, "hazard");
    var segment = findField(headers, "segment");
    var exposure = findField(headers, "exposure");
    var located = latitude && longitude
      ? Math.min(populatedCount(rows, latitude), populatedCount(rows, longitude))
      : populatedCount(rows, address);
    var dated = populatedCount(rows, date);
    var classified = populatedCount(rows, hazard);
    var suppression = suppressionEstimate(rows, segment, MIN_PUBLISH_N);
    var rate = rateEvidence(rows, segment, exposure, String(options.segment || "").trim());
    var hasLocation = located === rows.length;
    var hasDate = dated === rows.length;
    var enoughReports = rows.length >= MIN_PUBLISH_N;
    var tier = hasLocation && enoughReports ? 1 : 0;
    // Tier 2 is earned by computation: the chosen segment's interval clears the
    // other segments' pooled rate. The alignment box and the review box are
    // declarations the browser cannot verify; they gate the tier but never create it.
    if (tier >= 1 && hasDate && rate.elevated && options.hasExposure && options.hasReview) tier = 2;
    if (tier >= 2 && options.hasOfficial) tier = 3;
    var findings = [
      {
        ready: hasLocation,
        label: "Location coverage",
        detail: located + " of " + rows.length + " rows have " + (latitude && longitude ? "coordinate pairs" : address ? "an address" : "no recognized location field") + ".",
      },
      {
        ready: hasDate,
        label: "Observation window",
        detail: dated + " of " + rows.length + " rows have a recognized date or timestamp.",
      },
      {
        ready: Boolean(hazard) && classified > 0,
        label: "Conflict pattern",
        detail: hazard ? classified + " rows carry a recognized hazard or incident type." : "No recognized hazard-type field was found.",
      },
      {
        ready: rate.computable && Boolean(options.hasExposure),
        label: "Exposure denominator",
        detail: rate.computable
          ? "Denominator column " + rate.exposureField + ": " + rate.reason + (options.hasExposure
              ? " Alignment with the observation window is declared by the preparer; this browser cannot verify its unit, source, or dates."
              : " Its alignment with the observation window was not declared, so no rate comparison is permitted.")
          : rate.reason + " The declaration box cannot substitute for the column.",
      },
      {
        ready: rate.elevated,
        label: "Rate at the named place",
        detail: rate.place && rate.comparison ? describePlaceRate(rate) : rate.claimReason,
      },
      {
        ready: Boolean(options.hasOfficial),
        label: "Independent evidence",
        detail: options.hasOfficial ? "An official outcome source was declared; agreement is not evaluated here and must be reviewed before Tier 3 language is used." : "No independent official outcome source was declared.",
      },
      {
        ready: suppression.known && suppression.withheldRows === 0,
        label: "Privacy-floor estimate",
        detail: suppression.known
          ? suppression.withheldGroups + " of " + suppression.groups + " groups fall below a provisional k=" + MIN_PUBLISH_N + " floor, affecting " + suppression.withheldRows + " rows."
          : "No segment or corridor identifier was found, so suppression cannot yet be estimated.",
      },
    ];
    var summaries = {
      0: "The file has a coverage gap that prevents a defensible corridor signal.",
      1: rate.computable
        ? "The file can support a community-signal finding. A rate was computed, but it does not support an elevated-rate claim: " + rate.claimReason
        : "The file can support a community-signal finding, but not an exposure-normalized comparison: " + rate.claimReason,
      2: "The computed rate at " + (rate.place ? rate.place.id : "the chosen segment") + " is elevated relative to the other segments in this file. Denominator alignment is declared, not verified, and sensitivity checks remain.",
      3: "The computed elevated rate at " + (rate.place ? rate.place.id : "the chosen segment") + " can be triangulated once the declared independent source is reviewed for agreement.",
    };
    var next = {
      0: "Repair missing locations and dates, then rerun the readiness check.",
      1: "Conduct a field audit or add a temporally aligned exposure denominator.",
      2: "Verify the independent outcome track and preregister the comparison window.",
      3: "Name the decision owner, requested action, and follow-up measurement plan.",
    };
    return {
      rowCount: rows.length,
      tier: tier,
      summary: summaries[tier],
      next: next[tier],
      findings: findings,
      fields: { latitude: latitude, longitude: longitude, address: address, date: date, hazard: hazard, segment: segment, exposure: exposure },
      suppression: suppression,
      rate: rate,
      basis: tier >= 2 ? rate.basis : null,
    };
  }

  function compileClaim(tier, place, use, basis) {
    var numericTier = Number(tier);
    var template = CLAIMS[numericTier] || CLAIMS[0];
    var safePlace = String(place || "the named corridor").trim() || "the named corridor";
    var useActions = {
      field_audit: "Frame the request as an investigation step, with the evidence gap stated.",
      staff_memo: "Carry the source, observation window, and strongest caveat into the memo.",
      grant: "Describe the evidence as support for investigation or prioritization, not proof of benefit.",
      evaluation: "Freeze the metric and baseline before any intervention is assessed.",
    };
    var declared = [];
    var claimBasis = null;
    if (numericTier >= 2) {
      if (!validBasis(basis)) {
        throw new Error(
          "Tier " + numericTier + " language needs a computed rate basis (count, denominator, interval, and comparison). None was supplied, so no elevated-rate sentence is issued."
        );
      }
      claimBasis = basis;
      declared.push("denominator alignment with the observation window");
      if (numericTier >= 3) declared.push("agreement of the independent outcome source");
    }
    return {
      tier: numericTier,
      claim: template.claim.replace("{place}", safePlace).replace("{basis}", claimBasis ? describeBasis(claimBasis) : ""),
      supports: template.supports,
      cannot: template.cannot,
      next: template.next + " " + (useActions[use] || useActions.field_audit),
      basis: claimBasis,
      computed: claimBasis
        ? "Computed in this browser from the file's " + claimBasis.unit + " column for segment " + claimBasis.segment + ". " +
          describeDispersion(claimBasis.dispersion, claimBasis.widenedLow, claimBasis.comparisonRate)
        : "",
      declared: declared.length ? "Declared by the preparer, not verified here: " + declared.join("; ") + "." : "",
    };
  }

  function textReport(result, decision, corridor, owner) {
    var lines = [
      "NearMiss readiness report",
      "Decision: " + decision,
      "Place: " + corridor,
      "Owner: " + owner,
      "Evidence tier: " + result.tier,
      "Rows inspected locally: " + result.rowCount,
      "",
      result.summary,
      "",
    ];
    result.findings.forEach(function (finding) {
      lines.push((finding.ready ? "READY" : "GAP") + " — " + finding.label + ": " + finding.detail);
    });
    lines.push("", "Recommended next step: " + result.next);
    return lines.join("\n");
  }

  function copyText(value, status) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      return navigator.clipboard.writeText(value).then(function () {
        status.textContent = "Copied.";
      }, function () {
        status.textContent = "Copy failed. Select the text manually.";
      });
    }
    var textarea = document.createElement("textarea");
    textarea.value = value;
    textarea.setAttribute("readonly", "");
    document.body.appendChild(textarea);
    textarea.select();
    var copied = document.execCommand && document.execCommand("copy");
    textarea.remove();
    status.textContent = copied ? "Copied." : "Copy failed. Select the text manually.";
    return Promise.resolve();
  }

  function handoffId() {
    if (window.crypto && typeof window.crypto.randomUUID === "function") {
      return window.crypto.randomUUID();
    }
    if (window.crypto && typeof window.crypto.getRandomValues === "function") {
      var bytes = new Uint8Array(16);
      window.crypto.getRandomValues(bytes);
      return Array.from(bytes).map(function (byte) {
        return byte.toString(16).padStart(2, "0");
      }).join("");
    }
    return Date.now().toString(36) + Math.random().toString(36).slice(2);
  }

  function saveHandoff(value) {
    try {
      var id = handoffId();
      window.sessionStorage.setItem(HANDOFF_PREFIX + id, JSON.stringify(value));
      return id;
    } catch (_error) {
      return "";
    }
  }

  function boot() {
    var readinessForm = document.getElementById("readiness-form");
    if (!readinessForm) return;
    var currentRows = null;
    var currentResult = null;
    var currentClaim = null;
    var status = document.getElementById("readiness-status");
    var fileInput = document.getElementById("evidence-file");
    var placeSegment = document.getElementById("place-segment");
    var placeSegmentNote = document.getElementById("place-segment-note");
    var claimTier = document.getElementById("claim-tier");
    var claimTierNote = document.getElementById("claim-tier-note");
    var claimPlace = document.getElementById("claim-place");
    var generateClaim = document.getElementById("generate-claim");
    var readinessResult = document.getElementById("readiness-result");
    var claimStatus = document.getElementById("claim-result");
    var contextParams = new URLSearchParams(window.location.search);

    function setClaimBoundary(tier, note) {
      claimTier.value = String(tier);
      claimTierNote.textContent = note;
      generateClaim.disabled = false;
    }

    function populateSegments(rows) {
      var headers = Array.from(new Set(rows.flatMap(function (row) { return Object.keys(row); })));
      var segmentField = findField(headers, "segment");
      var values = segmentValues(rows, segmentField);
      var previous = placeSegment.value;
      placeSegment.textContent = "";
      var placeholder = document.createElement("option");
      placeholder.value = "";
      placeholder.textContent = values.length ? "Choose the segment that is this place" : "No segment or corridor identifier in the file";
      placeSegment.appendChild(placeholder);
      values.forEach(function (value) {
        var option = document.createElement("option");
        option.value = value;
        option.textContent = value;
        placeSegment.appendChild(option);
      });
      placeSegment.disabled = !values.length;
      if (values.indexOf(previous) >= 0) placeSegment.value = previous;
      placeSegmentNote.textContent = values.length
        ? values.length + " segment identifier" + (values.length === 1 ? "" : "s") + " read from the " + segmentField + " column."
        : "A rate can only be attached to a place the file identifies; add a segment_id or corridor_id column.";
    }

    function invalidateReadiness(message) {
      currentResult = null;
      currentClaim = null;
      readinessResult.hidden = true;
      claimStatus.hidden = true;
      claimTier.value = "0";
      claimTierNote.textContent = "Run the readiness check to set this tier.";
      generateClaim.disabled = true;
      if (message) status.textContent = message;
    }

    if (
      contextParams.getAll("source").length === 1 &&
      contextParams.get("source") === "atlas" &&
      contextParams.getAll("state").length === 1 &&
      /^[A-Z]{2}$/.test(contextParams.get("state") || "") &&
      contextParams.getAll("year").length === 1 &&
      /^20(?:20|21|22|23|24)$/.test(contextParams.get("year") || "")
    ) {
      document.getElementById("decision").value = "Plan the local evidence needed after official context review";
      document.getElementById("corridor").value = contextParams.get("state") + " county or corridor question";
      claimPlace.value = contextParams.get("state") + " county or corridor";
      currentResult = { tier: 0 };
      setClaimBoundary(0, "Tier 0 is fixed because Atlas counts are background context, not local evidence.");
      status.textContent =
        "Official " + contextParams.get("year") + " state context carried in. Add local evidence before making a county or corridor claim.";
    }

    document.getElementById("load-sample").addEventListener("click", function () {
      invalidateReadiness("");
      currentRows = SAMPLE_ROWS.map(function (row) { return Object.assign({}, row); });
      populateSegments(currentRows);
      status.textContent = "Safe sample loaded: " + currentRows.length + " fictional rows.";
    });

    fileInput.addEventListener("change", function () {
      currentRows = null;
      invalidateReadiness("File selection changed. Run the readiness check again.");
      var file = fileInput.files && fileInput.files[0];
      if (!file) return;
      file.text().then(function (text) {
        populateSegments(parseEvidence(text, file.name));
      }).catch(function (error) {
        populateSegments([]);
        status.textContent = error.message;
      });
    });
    placeSegment.addEventListener("change", function () {
      if (currentResult) invalidateReadiness("Place segment changed. Run the readiness check again.");
    });
    ["has-exposure", "has-official", "has-review"].forEach(function (id) {
      document.getElementById(id).addEventListener("change", function () {
        invalidateReadiness("Evidence declarations changed. Run the readiness check again.");
      });
    });
    document.getElementById("corridor").addEventListener("input", function () {
      claimPlace.value = document.getElementById("corridor").value;
      if (currentResult) {
        invalidateReadiness("Place changed. Run the readiness check again.");
      }
    });

    readinessForm.addEventListener("submit", function (event) {
      event.preventDefault();
      status.textContent = "Checking the selected evidence locally…";
      var file = fileInput.files && fileInput.files[0];
      var source = file
        ? file.text().then(function (text) { return parseEvidence(text, file.name); })
        : Promise.resolve(currentRows);
      source.then(function (rows) {
        if (!rows) throw new Error("Choose a CSV or JSON file, or load the safe sample.");
        currentRows = rows;
        populateSegments(rows);
        currentResult = assessReadiness(rows, {
          segment: placeSegment.value,
          hasExposure: document.getElementById("has-exposure").checked,
          hasOfficial: document.getElementById("has-official").checked,
          hasReview: document.getElementById("has-review").checked,
        });
        document.getElementById("evidence-tier").textContent = "Tier " + currentResult.tier;
        document.getElementById("readiness-summary").textContent = currentResult.summary;
        document.getElementById("readiness-next").textContent = currentResult.next;
        var list = document.getElementById("readiness-findings");
        list.textContent = "";
        currentResult.findings.forEach(function (finding) {
          var item = document.createElement("li");
          var state = document.createElement("span");
          state.className = "finding-status " + (finding.ready ? "is-ready" : "is-gap");
          state.textContent = finding.ready ? "Ready" : "Gap";
          var title = document.createElement("strong");
          title.textContent = finding.label;
          var detail = document.createElement("p");
          detail.textContent = finding.detail;
          item.appendChild(state);
          item.appendChild(title);
          item.appendChild(detail);
          list.appendChild(item);
        });
        readinessResult.hidden = false;
        setClaimBoundary(
          currentResult.tier,
          "Set by this browser-local readiness result. Change the evidence and rerun to update it."
        );
        claimPlace.value = document.getElementById("corridor").value;
        status.textContent = "Readiness check complete. No file data left this browser.";
        document.getElementById("readiness-result-heading").focus();
      }).catch(function (error) {
        status.textContent = error.message;
      });
    });

    document.getElementById("copy-readiness").addEventListener("click", function () {
      if (!currentResult) return;
      copyText(
        textReport(
          currentResult,
          document.getElementById("decision").value,
          document.getElementById("corridor").value,
          document.getElementById("owner").value
        ),
        status
      );
    });

    var claimForm = document.getElementById("claim-form");
    claimForm.addEventListener("submit", function (event) {
      event.preventDefault();
      if (!currentResult) {
        status.textContent = "Run the readiness check before generating a claim.";
        return;
      }
      try {
        currentClaim = compileClaim(
          currentResult.tier,
          claimPlace.value,
          document.getElementById("claim-use").value,
          currentResult.basis
        );
      } catch (error) {
        currentClaim = null;
        claimStatus.hidden = true;
        status.textContent = error.message;
        return;
      }
      document.getElementById("claim-output").textContent = currentClaim.claim;
      document.getElementById("claim-provenance").textContent = [currentClaim.computed, currentClaim.declared]
        .filter(Boolean)
        .join(" ") || "No computation was needed for this tier; the sentence is bounded by the readiness findings.";
      document.getElementById("claim-supports").textContent = currentClaim.supports;
      document.getElementById("claim-cannot").textContent = currentClaim.cannot;
      document.getElementById("claim-next").textContent = currentClaim.next;
      var handoff = saveHandoff({
        schema: HANDOFF_SCHEMA,
        tier: currentClaim.tier,
        place: claimPlace.value,
        use: document.getElementById("claim-use").value,
        basis: currentClaim.basis,
      });
      var buildDossier = document.getElementById("build-dossier");
      if (handoff) {
        buildDossier.href = "/dossier/?source=studio&handoff=" + encodeURIComponent(handoff);
        buildDossier.textContent = "Open a dossier draft";
        buildDossier.removeAttribute("aria-disabled");
      } else {
        buildDossier.href = "/dossier/";
        buildDossier.textContent = "Dossier handoff unavailable in this browser";
        buildDossier.setAttribute("aria-disabled", "true");
      }
      claimStatus.hidden = false;
      document.getElementById("claim-result-heading").focus();
    });

    document.getElementById("copy-claim").addEventListener("click", function () {
      if (!currentClaim) return;
      copyText(
        [
          "Permitted claim: " + currentClaim.claim,
          currentClaim.computed,
          currentClaim.declared,
          "Supports: " + currentClaim.supports,
          "Does not support: " + currentClaim.cannot,
          "Next action: " + currentClaim.next,
        ].filter(Boolean).join("\n"),
        status
      );
    });
  }

  window.NearmissStudio = {
    parseCsv: parseCsv,
    parseEvidence: parseEvidence,
    assessReadiness: assessReadiness,
    compileClaim: compileClaim,
    rateEvidence: rateEvidence,
    validBasis: validBasis,
    describeBasis: describeBasis,
    segmentValues: segmentValues,
    rates: {
      Z95: Z95,
      poissonCi: poissonCi,
      pearsonDispersion: pearsonDispersion,
      quasiPoissonCi: quasiPoissonCi,
      rateWithCi: rateWithCi,
      wilsonCi: wilsonCi,
    },
    thresholds: { ratePer: RATE_PER, smallN: SMALL_N, minPublishN: MIN_PUBLISH_N },
    handoffPrefix: HANDOFF_PREFIX,
    handoffSchema: HANDOFF_SCHEMA,
    sampleRows: SAMPLE_ROWS,
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
