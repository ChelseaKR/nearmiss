/* nearmiss public submission form — framework-free, accessible, serverless-honest.
 *
 * Builds a report that conforms to schema/report.schema.json and hands it to the
 * contributor for the moderation queue. The static site has no backend, so by
 * default the form produces a downloadable/copyable JSON the maintainers feed to
 * `nearmiss submit` (which enqueues it PENDING). A deployment that has a
 * serverless intake can set `data-endpoint` on the <form> to POST it instead.
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
        geoStatus.textContent = "Geolocation isn't available — type a location instead.";
        return;
      }
      geoStatus.textContent = "Locating…";
      navigator.geolocation.getCurrentPosition(
        function (pos) {
          document.getElementById("lat").value = pos.coords.latitude.toFixed(6);
          document.getElementById("lon").value = pos.coords.longitude.toFixed(6);
          geoStatus.textContent = "Location filled in. You can adjust it.";
        },
        function () {
          geoStatus.textContent = "Couldn't get your location — type a place instead.";
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
    if (!hasCoords && !address) problems.push("a location (use my location, lat/lon, or an address)");
    if (hasCoords && (lat < -90 || lat > 90 || lon < -180 || lon > 180))
      problems.push("a valid latitude (−90..90) and longitude (−180..180)");
    if (!checked("hazard_type")) problems.push("a hazard type");
    if (!checked("severity")) problems.push("a severity");
    if (problems.length) {
      setStatus("Please provide: " + problems.join("; ") + ".", true);
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
    setStatus("Your submission is ready below — it still needs human review before it counts.", false);
    resultEl.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function postToEndpoint(endpoint, report) {
    setStatus("Sending your submission for review…", false);
    fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(report),
    })
      .then(function (resp) {
        if (!resp.ok) throw new Error("HTTP " + resp.status);
        setStatus("Thank you. Your near-miss was received and is awaiting review.", false);
        form.reset();
      })
      .catch(function () {
        // Fall back to the offline path so a curbside submission is never lost.
        setStatus(
          "Couldn't reach the server — here is your submission to send manually instead.",
          true
        );
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
      setStatus(ok ? "Copied to clipboard." : "Select the text and copy it manually.", !ok);
    });
  }
})();
