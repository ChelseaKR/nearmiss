/* nearmiss source-only submission prototype — framework-free and accessible.
 *
 * Builds a report that conforms to schema/report.schema.json and hands it to the
 * operator for the moderation queue. The production artifact excludes this
 * form; locally it produces downloadable/copyable JSON for `nearmiss submit`
 * (which enqueues it PENDING). A separately reviewed deployment can set a
 * `data-endpoint` on the <form> to POST it instead.
 *
 * Privacy posture (HR4): we collect NO identity — no name, email, account, or
 * phone field exists. The note warns against including identifiers. Nothing is
 * published as-is; the report only ever becomes public after human approval and
 * the normal aggregate-and-withhold publish path.
 */
(function () {
  "use strict";

  var form = document.getElementById("report-form");
  var statusEl = document.getElementById("form-status");
  var resultEl = document.getElementById("result");
  var jsonEl = document.getElementById("submission-json");
  var geoStatus = document.getElementById("geo-status");

  // The form's user-facing status text is single-sourced from the same gettext
  // catalogs as the rest of the site (web/locales/<lang>.json via po2json), under
  // the "web.submit." namespace. ?lang=xx selects the locale; English is the
  // fallback. t("key") mirrors app.js so call sites read the same.
  var i18n = window.NearmissI18n.create("web.submit.");
  var lang = window.NearmissI18n.langFromQuery("en");

  function t(key) {
    return i18n.t(key);
  }
  function tpl(s, obj) {
    return s.replace(/\{(\w+)\}/g, function (_, k) {
      return obj[k];
    });
  }

  function setStatus(msg, isError) {
    statusEl.textContent = msg;
    statusEl.classList.toggle("is-error", !!isError);
  }

  // RFC3339 timestamp WITH the local offset, matching the schema's date-time +
  // explicit offset requirement (the event time is local wall-clock time).
  function nowWithOffset() {
    var d = new Date();
    var pad = function (n) {
      return String(n).padStart(2, "0");
    };
    var off = -d.getTimezoneOffset(); // minutes east of UTC
    var sign = off >= 0 ? "+" : "-";
    var oh = pad(Math.floor(Math.abs(off) / 60));
    var om = pad(Math.abs(off) % 60);
    return (
      d.getFullYear() +
      "-" +
      pad(d.getMonth() + 1) +
      "-" +
      pad(d.getDate()) +
      "T" +
      pad(d.getHours()) +
      ":" +
      pad(d.getMinutes()) +
      ":" +
      pad(d.getSeconds()) +
      sign +
      oh +
      ":" +
      om
    );
  }

  // RFC4122 v4 UUID. Prefer the platform CSPRNG; fall back to Math.random only
  // for very old browsers (the id carries no identity, so this is safe).
  function uuid() {
    if (window.crypto && window.crypto.randomUUID) return window.crypto.randomUUID();
    return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, function (c) {
      var r = (Math.random() * 16) | 0;
      var v = c === "x" ? r : (r & 0x3) | 0x8;
      return v.toString(16);
    });
  }

  function checked(name) {
    var el = form.querySelector('input[name="' + name + '"]:checked');
    return el ? el.value : null;
  }

  // "Use my current location" — geolocation is opt-in and never silently stored.
  var geoBtn = document.getElementById("use-location");
  if (geoBtn) {
    geoBtn.addEventListener("click", function () {
      if (!navigator.geolocation) {
        geoStatus.textContent = t("geo_unavailable");
        return;
      }
      geoStatus.textContent = t("geo_locating");
      navigator.geolocation.getCurrentPosition(
        function (pos) {
          document.getElementById("lat").value = pos.coords.latitude.toFixed(6);
          document.getElementById("lon").value = pos.coords.longitude.toFixed(6);
          geoStatus.textContent = t("geo_filled");
        },
        function () {
          geoStatus.textContent = t("geo_denied");
        },
        { enableHighAccuracy: true, timeout: 10000 }
      );
    });
  }

  function buildReport() {
    var lat = parseFloat(document.getElementById("lat").value);
    var lon = parseFloat(document.getElementById("lon").value);
    var address = document.getElementById("address").value.trim();
    var hasCoords = !isNaN(lat) && !isNaN(lon);

    var problems = [];
    if (!hasCoords && !address) problems.push(t("need_location"));
    if (hasCoords && (lat < -90 || lat > 90 || lon < -180 || lon > 180))
      problems.push(t("need_coords"));
    if (!checked("hazard_type")) problems.push(t("need_hazard"));
    if (!checked("severity")) problems.push(t("need_severity"));
    if (problems.length) {
      setStatus(tpl(t("status_missing"), { fields: problems.join("; ") }), true);
      return null;
    }

    var report = {
      schema_version: "1.0.0",
      id: uuid(),
      occurred_at: nowWithOffset(),
      mode: document.getElementById("mode").value || "cyclist",
      hazard_type: checked("hazard_type"),
      severity: checked("severity"),
      language: document.getElementById("language").value || "en",
    };
    if (hasCoords) report.location = { lat: lat, lon: lon };
    if (!hasCoords && address) report.address = address;
    var note = document.getElementById("note").value.trim();
    if (note) report.note = note;
    return report;
  }

  function showResult(report) {
    jsonEl.value = JSON.stringify(report, null, 2);
    resultEl.hidden = false;
    setStatus(t("status_ready"), false);
    resultEl.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function postToEndpoint(endpoint, report) {
    setStatus(t("status_sending"), false);
    fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(report),
    })
      .then(function (resp) {
        if (!resp.ok) throw new Error("HTTP " + resp.status);
        setStatus(t("status_received"), false);
        form.reset();
      })
      .catch(function () {
        // Fall back to the offline path so a curbside submission is never lost.
        setStatus(t("status_send_failed"), true);
        showResult(report);
      });
  }

  form.addEventListener("submit", function (e) {
    e.preventDefault();
    var report = buildReport();
    if (!report) return;
    var endpoint = form.getAttribute("data-endpoint");
    if (endpoint) postToEndpoint(endpoint, report);
    else showResult(report);
  });

  var dl = document.getElementById("download-submission");
  if (dl) {
    dl.addEventListener("click", function () {
      var blob = new Blob([jsonEl.value], { type: "application/json" });
      var url = URL.createObjectURL(blob);
      var a = document.createElement("a");
      a.href = url;
      a.download = "nearmiss-submission.json";
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    });
  }

  var copy = document.getElementById("copy-submission");
  if (copy) {
    copy.addEventListener("click", function () {
      jsonEl.select();
      var ok = false;
      try {
        if (navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard.writeText(jsonEl.value);
          ok = true;
        } else {
          ok = document.execCommand("copy");
        }
      } catch (err) {
        ok = false;
      }
      setStatus(ok ? t("status_copied") : t("status_copy_manual"), !ok);
    });
  }

  // Load the English fallback and the requested locale so the form's status text
  // is localized the moment the user acts. Handlers above read t() lazily, so no
  // re-wiring is needed once the catalogs resolve.
  i18n
    .load("en")
    .then(function () {
      return lang === "en" ? null : i18n.load(lang);
    })
    .then(function () {
      i18n.setLang(lang);
    });
})();
