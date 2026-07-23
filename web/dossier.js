(function () {
  "use strict";

  var ALLOWED_TIERS = {
    0: "0 · Coverage gap",
    1: "1 · Community signal",
    2: "2 · Elevated rate",
    3: "3 · Triangulated priority",
  };
  var ALLOWED_MODES = {
    motor_vehicle_occupant: "motor-vehicle occupant",
    motorcyclist: "motorcyclist",
    pedalcyclist: "pedalcyclist",
    pedestrian: "pedestrian",
    other_road_user: "other road user",
    unknown: "unknown road-user mode",
  };
  var ALLOWED_STATES = new Set(
    "AL AK AZ AR CA CO CT DE DC FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY".split(" ")
  );
  var ALLOWED_USES = new Set(["field_audit", "staff_memo", "grant", "evaluation"]);
  var HANDOFF_PREFIX = "nearmiss:studio-handoff:";

  function exactParameter(params, name, validator) {
    if (!params.has(name)) return "";
    var values = params.getAll(name);
    if (values.length !== 1 || !validator(values[0])) return "";
    return values[0];
  }

  function safeText(value, fallback, maximum) {
    var normalized = String(value || "").replace(/\s+/g, " ").trim();
    return normalized && normalized.length <= maximum ? normalized : fallback;
  }

  function hasOnlyParameters(params, allowed) {
    return Array.from(params.keys()).every(function (name) {
      return allowed.has(name);
    });
  }

  function studioHandoff(params, storage) {
    if (!hasOnlyParameters(params, new Set(["source", "handoff"]))) return null;
    var id = exactParameter(params, "handoff", function (value) {
      return /^[A-Za-z0-9-]{16,64}$/.test(value);
    });
    if (!id || !storage || !window.NearmissStudio) return null;
    try {
      var raw = storage.getItem(HANDOFF_PREFIX + id);
      if (!raw) return null;
      var value = JSON.parse(raw);
      if (
        !value ||
        value.schema !== "nearmiss.studio_handoff.v1" ||
        !Number.isInteger(value.tier) ||
        !Object.prototype.hasOwnProperty.call(ALLOWED_TIERS, value.tier) ||
        !ALLOWED_USES.has(value.use)
      ) {
        return null;
      }
      var place = safeText(value.place, "", 120);
      if (!place) return null;
      var bounded = window.NearmissStudio.compileClaim(value.tier, place, value.use);
      return {
        source: "studio",
        tier: value.tier,
        place: place,
        claim: bounded.claim,
        action: bounded.next,
        cannot: bounded.cannot,
        sourceLabel: "Browser-local Studio handoff · tier set by readiness screen · no report data included",
      };
    } catch (_error) {
      return null;
    }
  }

  function dossierFromQuery(search, storage) {
    var params = new URLSearchParams(search || "");
    var source = exactParameter(params, "source", function (value) {
      return value === "atlas" || value === "studio";
    });
    if (source === "atlas") {
      if (!hasOnlyParameters(params, new Set(["source", "year", "mode", "states"]))) return null;
      var year = exactParameter(params, "year", function (value) { return /^20(?:20|21|22|23|24)$/.test(value); }) || "2024";
      var mode = exactParameter(params, "mode", function (value) { return Object.prototype.hasOwnProperty.call(ALLOWED_MODES, value); }) || "pedalcyclist";
      var states = exactParameter(params, "states", function (value) {
        var members = value.split(",");
        return (
          /^[A-Z]{2}(,[A-Z]{2}){0,3}$/.test(value) &&
          new Set(members).size === members.length &&
          members.every(function (state) { return ALLOWED_STATES.has(state); })
        );
      });
      return {
        source: "atlas",
        tier: 0,
        place: states ? states.split(",").join(", ") + " reference context" : "Selected state reference context",
        claim: "Reviewed " + year + " FARS counts provide official background for the selected " + ALLOWED_MODES[mode] + " context. They do not establish local risk.",
        action: "Add corridor-scale community reports and aligned exposure before requesting a local priority decision.",
        cannot: "Risk, rate, fault, causation, a county or corridor ranking, or treatment effectiveness.",
        sourceLabel: "NHTSA FARS " + year + " · saved states: " + (states || "none"),
      };
    }
    if (source === "studio") {
      var handoffStorage = storage;
      if (!handoffStorage) {
        try {
          handoffStorage = window.sessionStorage;
        } catch (_error) {
          handoffStorage = null;
        }
      }
      return studioHandoff(params, handoffStorage);
    }
    return null;
  }

  function evidenceTrack(titleText, detailText, statusText, limited) {
    var item = document.createElement("li");
    item.className = "evidence-track";
    var title = document.createElement("strong");
    title.textContent = titleText;
    var detail = document.createElement("span");
    detail.textContent = detailText;
    var state = document.createElement("span");
    state.className = "track-status " + (limited ? "is-limited" : "is-measured");
    state.textContent = statusText;
    item.appendChild(title);
    item.appendChild(detail);
    item.appendChild(state);
    return item;
  }

  function replaceTracks(items) {
    var tracks = document.getElementById("evidence-tracks");
    tracks.textContent = "";
    items.forEach(function (item) {
      tracks.appendChild(item);
    });
  }

  function canonicalPayload(data) {
    return JSON.stringify({
      artifact: "nearmiss.public.decision_dossier_preview",
      source: data ? data.source : "sample",
      tier: data ? data.tier : 2,
      place: data ? data.place : "Mercer Avenue at 8th Street",
      claim: data ? data.claim : "The observed report rate at Mercer Avenue at 8th Street is elevated in the stated observation window.",
      action: data ? data.action : "Conduct a daylight and evening field audit, then return with a scoped visibility and crossing-safety response within 60 days.",
    });
  }

  function fallbackFingerprint(value) {
    var hash = 2166136261;
    for (var index = 0; index < value.length; index += 1) {
      hash ^= value.charCodeAt(index);
      hash = Math.imul(hash, 16777619);
    }
    return "local-" + (hash >>> 0).toString(16).padStart(8, "0");
  }

  function fingerprint(value) {
    if (!window.crypto || !window.crypto.subtle || !window.TextEncoder) {
      return Promise.resolve(fallbackFingerprint(value));
    }
    return window.crypto.subtle.digest("SHA-256", new TextEncoder().encode(value)).then(function (buffer) {
      return Array.from(new Uint8Array(buffer)).map(function (byte) {
        return byte.toString(16).padStart(2, "0");
      }).join("");
    }, function () {
      return fallbackFingerprint(value);
    });
  }

  function copyText(value, status) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(value).then(function () {
        status.textContent = "Citation copied.";
      }, function () {
        status.textContent = "Copy failed. Select the citation manually.";
      });
      return;
    }
    var textarea = document.createElement("textarea");
    textarea.value = value;
    textarea.setAttribute("readonly", "");
    document.body.appendChild(textarea);
    textarea.select();
    var copied = document.execCommand && document.execCommand("copy");
    textarea.remove();
    status.textContent = copied ? "Citation copied." : "Copy failed. Select the citation manually.";
  }

  function boot() {
    var heading = document.getElementById("dossier-page-heading");
    if (!heading) return;
    var storage = null;
    try {
      storage = window.sessionStorage;
    } catch (_error) {
      storage = null;
    }
    var data = dossierFromQuery(window.location.search, storage);
    if (data) {
      document.getElementById("dossier-kicker").textContent = data.source === "atlas"
        ? "Official context handoff"
        : "Local Studio dossier draft";
      document.getElementById("sample-status-title").textContent = data.source === "atlas"
        ? "Official context is not a corridor finding."
        : "This draft contains no uploaded report data.";
      document.getElementById("sample-status-copy").textContent = data.source === "atlas"
        ? "The saved Atlas cells remain a separate reference track. Add local reports and exposure before making a corridor claim."
        : "The tier and task moved through browser-local session state. Claim language was regenerated here; the file inspected in Studio stayed in that browser tab.";
      document.getElementById("dossier-id").textContent = "DOSSIER DRAFT-" + data.source.toUpperCase();
      document.getElementById("dossier-tier").textContent = "EVIDENCE TIER " + data.tier;
      document.getElementById("dossier-status").textContent = "DRAFT · REVIEW REQUIRED";
      document.getElementById("dossier-place").textContent = data.place;
      document.getElementById("dossier-ask").textContent = "Requested next action: " + data.action;
      document.getElementById("dossier-claim").textContent = data.claim;
      document.getElementById("dossier-cannot").textContent = data.cannot;
      document.getElementById("verify-status").textContent = "Draft preview · review required";
      document.getElementById("verify-tier").textContent = ALLOWED_TIERS[data.tier];
      document.getElementById("verify-source").textContent = data.sourceLabel;
      document.getElementById("verification-heading").textContent = data.source === "atlas"
        ? "Reference boundary is explicit"
        : "Draft language is tier-bounded";
      document.getElementById("verification-note").textContent = data.source === "atlas"
        ? "This verifies that official counts remain labeled as context and are not presented as local risk."
        : "This checks the canonical draft language, not the evidence itself. A real dossier still requires source, privacy, statistical, and human review gates.";
      if (data.source === "atlas") {
        replaceTracks([
          evidenceTrack(
            "Official reference context",
            data.sourceLabel + ". Counts are not exposure-normalized risk.",
            "Context only",
            true
          ),
        ]);
        document.getElementById("dossier-why").textContent =
          "Saved state cells provide official background for the local evidence question; they do not identify a corridor.";
        document.getElementById("dossier-limitation").textContent =
          "State fatal-crash counts are not normalized by trips, miles, or local exposure and cannot be divided into county or corridor risk.";
        document.getElementById("dossier-measurement").textContent =
          "Add corridor-scale reports and an aligned exposure denominator before defining a local follow-up measure.";
      } else {
        replaceTracks([
          evidenceTrack(
            "Community reports",
            "The readiness tier and named place were carried from Studio; row-level records are not included in this dossier.",
            "Handoff only",
            true
          ),
          evidenceTrack(
            "Exposure",
            data.tier >= 2
              ? "Declared in Studio. Verify the unit, source, and observation-window alignment before publication."
              : "Not established by this handoff, so the draft makes no rate claim.",
            data.tier >= 2 ? "Declared" : "Missing",
            data.tier < 2
          ),
          evidenceTrack(
            "Independent outcomes",
            data.tier >= 3
              ? "Declared in Studio. Source agreement remains a review step outside this preview."
              : "Not established by this handoff; official context cannot upgrade the local claim.",
            data.tier >= 3 ? "Declared" : "Missing",
            data.tier < 3
          ),
        ]);
        document.getElementById("dossier-why").textContent =
          "The draft names the place and tier established by the readiness screen. It does not carry row-level evidence or create a ranking.";
        document.getElementById("dossier-limitation").textContent =
          "The browser-local handoff contains no source artifact, interval, or review receipt. Copy the readiness report from Studio for review.";
        document.getElementById("dossier-measurement").textContent =
          "Name the metric, baseline window, decision owner, and review date before this draft becomes a decision packet.";
        document.getElementById("verify-rule").textContent =
          "Canonical tier template; URL-supplied claim text is rejected";
      }
    }

    var payload = canonicalPayload(data);
    var fingerprintNode = document.getElementById("verify-fingerprint");
    fingerprint(payload).then(function (value) {
      fingerprintNode.textContent = value;
    });

    var status = document.getElementById("dossier-status-message");
    document.getElementById("copy-citation").addEventListener("click", function () {
      var citation = [
        "NearMiss Decision Dossier preview",
        "Place: " + document.getElementById("dossier-place").textContent,
        "Tier: " + document.getElementById("verify-tier").textContent,
        "Claim: " + document.getElementById("dossier-claim").textContent,
        "Source context: " + document.getElementById("verify-source").textContent,
        "URL: " + window.location.href,
        "Local fingerprint: " + fingerprintNode.textContent,
      ].join("\n");
      copyText(citation, status);
    });
    document.getElementById("print-dossier").addEventListener("click", function () {
      window.print();
    });
  }

  window.NearmissDossier = {
    dossierFromQuery: dossierFromQuery,
    canonicalPayload: canonicalPayload,
    fallbackFingerprint: fallbackFingerprint,
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
