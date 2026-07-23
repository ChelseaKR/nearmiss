(function () {
  "use strict";

  var SAMPLE_ROWS = [
    { report_id: "S-001", latitude: "38.5449", longitude: "-121.7405", occurred_at: "2026-05-02", hazard_type: "close_pass", corridor_id: "mercer-8" },
    { report_id: "S-002", latitude: "38.5450", longitude: "-121.7407", occurred_at: "2026-05-04", hazard_type: "close_pass", corridor_id: "mercer-8" },
    { report_id: "S-003", latitude: "38.5451", longitude: "-121.7406", occurred_at: "2026-05-08", hazard_type: "sightline", corridor_id: "mercer-8" },
    { report_id: "S-004", latitude: "38.5462", longitude: "-121.7420", occurred_at: "2026-05-09", hazard_type: "surface", corridor_id: "pine-2" },
    { report_id: "S-005", latitude: "38.5463", longitude: "-121.7421", occurred_at: "2026-05-10", hazard_type: "surface", corridor_id: "pine-2" },
    { report_id: "S-006", latitude: "38.5470", longitude: "-121.7430", occurred_at: "2026-05-11", hazard_type: "dooring", corridor_id: "oak-4" },
  ];

  var FIELD_GROUPS = {
    latitude: ["latitude", "lat", "y"],
    longitude: ["longitude", "lon", "lng", "x"],
    address: ["address", "location", "street_address"],
    date: ["occurred_at", "date", "timestamp", "reported_at", "datetime"],
    hazard: ["hazard_type", "incident_type", "type", "category"],
    segment: ["segment_id", "corridor_id", "street_segment", "location_id"],
  };

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
      claim: "The observed report rate at {place} is elevated in the stated observation window.",
      supports: "Scoping a treatment conversation or deeper study when the denominator, interval, and sensitivity checks travel with the claim.",
      cannot: "Causation, individual fault, a guaranteed safety benefit, or an unqualified comparison outside the analysis window.",
      next: "Seek an independent evidence track and preregister how any follow-up change will be evaluated.",
    },
    3: {
      claim: "Independent evidence supports prioritizing {place} for further action.",
      supports: "Advancing a named decision while preserving each source, uncertainty statement, and evaluation commitment.",
      cannot: "That one intervention is proven to be best, that observational agreement establishes cause, or that future harm will certainly decline.",
      next: "Name the decision owner, requested action, baseline, follow-up window, and comparison strategy.",
    },
  };
  var HANDOFF_PREFIX = "nearmiss:studio-handoff:";

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

  function assessReadiness(rows, options) {
    if (!Array.isArray(rows) || !rows.length) throw new Error("No report rows were available to assess.");
    var headers = Array.from(new Set(rows.flatMap(function (row) { return Object.keys(row); })));
    var latitude = findField(headers, "latitude");
    var longitude = findField(headers, "longitude");
    var address = findField(headers, "address");
    var date = findField(headers, "date");
    var hazard = findField(headers, "hazard");
    var segment = findField(headers, "segment");
    var located = latitude && longitude
      ? Math.min(populatedCount(rows, latitude), populatedCount(rows, longitude))
      : populatedCount(rows, address);
    var dated = populatedCount(rows, date);
    var classified = populatedCount(rows, hazard);
    var suppression = suppressionEstimate(rows, segment, 3);
    var hasLocation = located === rows.length;
    var hasDate = dated === rows.length;
    var enoughReports = rows.length >= 3;
    var tier = hasLocation && enoughReports ? 1 : 0;
    if (tier >= 1 && options.hasExposure && rows.length >= 10 && hasDate && options.hasReview) tier = 2;
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
        ready: Boolean(options.hasExposure),
        label: "Exposure denominator",
        detail: options.hasExposure ? "An aligned denominator was declared; its unit and dates still need review." : "No aligned denominator was declared, so the result cannot be called a rate.",
      },
      {
        ready: Boolean(options.hasOfficial),
        label: "Independent evidence",
        detail: options.hasOfficial ? "An official outcome source was declared; agreement must still be evaluated." : "No independent official outcome source was declared.",
      },
      {
        ready: suppression.known && suppression.withheldRows === 0,
        label: "Privacy-floor estimate",
        detail: suppression.known
          ? suppression.withheldGroups + " of " + suppression.groups + " groups fall below a provisional k=3 floor, affecting " + suppression.withheldRows + " rows."
          : "No segment or corridor identifier was found, so suppression cannot yet be estimated.",
      },
    ];
    var summaries = {
      0: "The file has a coverage gap that prevents a defensible corridor signal.",
      1: "The file can support a community-signal finding, but not an exposure-normalized comparison.",
      2: "The declared inputs can support an elevated-rate analysis after contract and sensitivity checks pass.",
      3: "The declared inputs can support a triangulated-priority analysis after source agreement is verified.",
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
      fields: { latitude: latitude, longitude: longitude, address: address, date: date, hazard: hazard, segment: segment },
      suppression: suppression,
    };
  }

  function compileClaim(tier, place, use) {
    var numericTier = Number(tier);
    var template = CLAIMS[numericTier] || CLAIMS[0];
    var safePlace = String(place || "the named corridor").trim() || "the named corridor";
    var useActions = {
      field_audit: "Frame the request as an investigation step, with the evidence gap stated.",
      staff_memo: "Carry the source, observation window, and strongest caveat into the memo.",
      grant: "Describe the evidence as support for investigation or prioritization, not proof of benefit.",
      evaluation: "Freeze the metric and baseline before any intervention is assessed.",
    };
    return {
      tier: numericTier,
      claim: template.claim.replace("{place}", safePlace),
      supports: template.supports,
      cannot: template.cannot,
      next: template.next + " " + (useActions[use] || useActions.field_audit),
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
      status.textContent = "Safe sample loaded: " + currentRows.length + " fictional rows.";
    });

    fileInput.addEventListener("change", function () {
      currentRows = null;
      invalidateReadiness("File selection changed. Run the readiness check again.");
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
        currentResult = assessReadiness(rows, {
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
      currentClaim = compileClaim(
        currentResult.tier,
        claimPlace.value,
        document.getElementById("claim-use").value
      );
      document.getElementById("claim-output").textContent = currentClaim.claim;
      document.getElementById("claim-supports").textContent = currentClaim.supports;
      document.getElementById("claim-cannot").textContent = currentClaim.cannot;
      document.getElementById("claim-next").textContent = currentClaim.next;
      var handoff = saveHandoff({
        schema: "nearmiss.studio_handoff.v1",
        tier: currentClaim.tier,
        place: claimPlace.value,
        use: document.getElementById("claim-use").value,
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
          "Supports: " + currentClaim.supports,
          "Does not support: " + currentClaim.cannot,
          "Next action: " + currentClaim.next,
        ].join("\n"),
        status
      );
    });
  }

  window.NearmissStudio = {
    parseCsv: parseCsv,
    parseEvidence: parseEvidence,
    assessReadiness: assessReadiness,
    compileClaim: compileClaim,
    handoffPrefix: HANDOFF_PREFIX,
    sampleRows: SAMPLE_ROWS,
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
