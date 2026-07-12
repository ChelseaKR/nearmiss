/* nearmiss share-card image generator — framework-free, client-side, offscreen
 * canvas. No map tiles, no network calls, no external services: it draws the
 * honest headline (how many streets are statistically significant hotspots) plus
 * the top three, straight onto a 1200×630 PNG that people can post.
 *
 * It never fetches anything itself. The page that already loaded the aggregated
 * published GeoJSON (app.js on the full site, embed.js in the widget) hands us the
 * same segment properties + dataset metadata, so the card can only ever show what
 * the page is already showing — no second source of truth, no drift.
 *
 * Usage:
 *   var data = NearmissShareCard.buildData(rows, meta); // rows = segment props[]
 *   NearmissShareCard.download(data);                   // toBlob → <a download>
 * or, in one step:
 *   NearmissShareCard.downloadFrom(rows, meta);
 *
 * A colour is never the only carrier of meaning on the card: significance is
 * stated in words and the rank is a number, matching the site's WCAG stance.
 */
(function () {
  "use strict";

  var W = 1200;
  var H = 630;
  var PAD = 72;

  var COLOR = {
    bg: "#ffffff",
    fg: "#15202b",
    muted: "#4a5560",
    accent: "#0b4f9c",
    hot: "#8a1c1c",
    line: "#c3ccd6",
  };
  // Concrete family list so canvas has something to fall back on everywhere.
  var FAMILY = 'system-ui, -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif';

  var CAVEAT = "exposure-normalized rates · open data";
  var URL_TEXT = "nearmiss.report";

  function hasRate(p) {
    return p && p.rate !== null && p.rate !== undefined;
  }

  function fmtRate(v) {
    return v === null || v === undefined ? "n/a" : Number(v).toFixed(2);
  }

  function slug(s) {
    return String(s || "")
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "");
  }

  // Normalize the same segment properties + dataset metadata the page already
  // holds into exactly what the card needs — nothing more is fetched or invented.
  function buildData(rowsOrProps, meta) {
    var props = (rowsOrProps || []).filter(hasRate);
    meta = meta || {};
    var significant = props
      .filter(function (p) {
        return p.getis_ord_significant;
      })
      .sort(function (a, b) {
        return (b.rate || 0) - (a.rate || 0);
      });
    // The headline is the count of significant hotspots. The list is the top
    // three of those; if none clear significance we still show the highest rates
    // so the card is never empty, but the headline stays honestly zero.
    var top = (significant.length ? significant : props.slice().sort(function (a, b) {
      return (b.rate || 0) - (a.rate || 0);
    })).slice(0, 3);
    return {
      city: meta.city || "",
      significantCount: significant.length,
      hasSignificant: significant.length > 0,
      hotspots: top.map(function (p) {
        return {
          name: p.name || p.segment_id || "",
          rate: p.rate,
          significant: !!p.getis_ord_significant,
        };
      }),
      caveat: CAVEAT,
      url: URL_TEXT,
    };
  }

  function wrap(ctx, text, maxWidth) {
    var words = String(text).split(/\s+/);
    var lines = [];
    var line = "";
    for (var i = 0; i < words.length; i++) {
      var candidate = line ? line + " " + words[i] : words[i];
      if (ctx.measureText(candidate).width > maxWidth && line) {
        lines.push(line);
        line = words[i];
      } else {
        line = candidate;
      }
    }
    if (line) lines.push(line);
    return lines;
  }

  // Draw the whole card onto a caller-supplied (usually offscreen) canvas.
  function render(canvas, data) {
    canvas.width = W;
    canvas.height = H;
    var ctx = canvas.getContext("2d");
    var maxText = W - PAD * 2;

    // Background + top accent band.
    ctx.fillStyle = COLOR.bg;
    ctx.fillRect(0, 0, W, H);
    ctx.fillStyle = COLOR.hot;
    ctx.fillRect(0, 0, W, 12);

    ctx.textBaseline = "alphabetic";
    ctx.textAlign = "left";

    // Brand + provenance line.
    ctx.fillStyle = COLOR.accent;
    ctx.font = "700 34px " + FAMILY;
    ctx.fillText("nearmiss", PAD, 84);
    ctx.fillStyle = COLOR.muted;
    ctx.font = "400 24px " + FAMILY;
    ctx.fillText("where the danger actually is", PAD + 190, 84);

    // Title: the city (or a neutral fallback).
    ctx.fillStyle = COLOR.fg;
    ctx.font = "700 60px " + FAMILY;
    var title = data.city ? data.city + " — road-hazard hotspots" : "Road-hazard hotspots";
    var titleLines = wrap(ctx, title, maxText);
    var y = 168;
    titleLines.slice(0, 2).forEach(function (ln) {
      ctx.fillText(ln, PAD, y);
      y += 66;
    });

    // Headline stat: how many statistically significant hotspots.
    ctx.fillStyle = data.hasSignificant ? COLOR.hot : COLOR.fg;
    ctx.font = "800 96px " + FAMILY;
    var big = String(data.significantCount);
    ctx.fillText(big, PAD, y + 74);
    var bigW = ctx.measureText(big).width;
    ctx.fillStyle = COLOR.fg;
    ctx.font = "600 34px " + FAMILY;
    ctx.fillText("statistically significant", PAD + bigW + 24, y + 48);
    ctx.fillText(
      data.significantCount === 1 ? "hotspot" : "hotspots",
      PAD + bigW + 24,
      y + 88
    );
    var listY = y + 150;

    // Top hotspots, ranked and numbered (rank carries meaning, not colour).
    ctx.font = "600 30px " + FAMILY;
    ctx.fillStyle = COLOR.muted;
    ctx.fillText(
      data.hasSignificant ? "Highest-rate significant hotspots" : "Highest rates (none reach significance)",
      PAD,
      listY
    );
    listY += 20;
    data.hotspots.forEach(function (h, i) {
      listY += 46;
      ctx.fillStyle = COLOR.accent;
      ctx.font = "700 32px " + FAMILY;
      var rank = i + 1 + ".";
      ctx.fillText(rank, PAD, listY);
      ctx.fillStyle = COLOR.fg;
      ctx.font = "400 32px " + FAMILY;
      var star = h.significant ? "★ " : "";
      var rateStr = "  —  rate " + fmtRate(h.rate) + "/1000";
      // Truncate an over-long name so the rate always stays on the card.
      var rateW = ctx.measureText(rateStr).width;
      ctx.font = "600 32px " + FAMILY;
      var starW = ctx.measureText(star).width;
      var nameMax = maxText - 44 - rateW - starW;
      var name = h.name;
      while (name.length > 1 && ctx.measureText(name + "…").width > nameMax) {
        name = name.slice(0, -1);
      }
      if (name !== h.name) name = name.replace(/\s+$/, "") + "…";
      ctx.fillStyle = h.significant ? COLOR.hot : COLOR.fg;
      ctx.font = "600 32px " + FAMILY;
      ctx.fillText(star + name, PAD + 44, listY);
      var drawn = ctx.measureText(star + name).width;
      ctx.fillStyle = COLOR.muted;
      ctx.font = "400 32px " + FAMILY;
      ctx.fillText(rateStr, PAD + 44 + drawn, listY);
    });

    // Footer: the honest caveat (left) and the URL (right).
    ctx.fillStyle = COLOR.line;
    ctx.fillRect(PAD, H - 96, W - PAD * 2, 2);
    ctx.fillStyle = COLOR.muted;
    ctx.font = "400 26px " + FAMILY;
    ctx.textBaseline = "middle";
    ctx.fillText(data.caveat, PAD, H - 52);
    ctx.fillStyle = COLOR.accent;
    ctx.font = "700 26px " + FAMILY;
    ctx.textAlign = "right";
    ctx.fillText(data.url, W - PAD, H - 52);
    ctx.textAlign = "left";
    ctx.textBaseline = "alphabetic";

    return canvas;
  }

  // Render offscreen and trigger a PNG download via a temporary <a download>.
  function download(data) {
    var canvas = document.createElement("canvas");
    render(canvas, data);
    var name = "nearmiss-" + (slug(data.city) || "share") + "-share.png";
    var finish = function (blob) {
      if (!blob) return;
      var url = URL.createObjectURL(blob);
      var a = document.createElement("a");
      a.href = url;
      a.download = name;
      a.rel = "noopener";
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      setTimeout(function () {
        URL.revokeObjectURL(url);
      }, 0);
    };
    if (canvas.toBlob) {
      canvas.toBlob(finish, "image/png");
    } else {
      // Very old engines: fall back to a data-URL href.
      var a2 = document.createElement("a");
      a2.href = canvas.toDataURL("image/png");
      a2.download = name;
      document.body.appendChild(a2);
      a2.click();
      document.body.removeChild(a2);
    }
  }

  function downloadFrom(rowsOrProps, meta) {
    download(buildData(rowsOrProps, meta));
  }

  window.NearmissShareCard = {
    buildData: buildData,
    render: render,
    download: download,
    downloadFrom: downloadFrom,
  };
  // Convenience global matching the item's named entry point.
  window.downloadShareCard = function (data) {
    download(data && data.hotspots ? data : buildData(data && data.rows, data && data.meta));
  };
})();
