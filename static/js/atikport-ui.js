/**
 * AtıkPort ortak UI yardımcıları — empty state, skeleton, demo, dark theme.
 * Backend / API değiştirmez.
 */
(function (global) {
  /* MASTER_DATASET (Sakarya + ulusal) ile hizalı istemci yedekleri */
  var DEMO = {
    category: {
      labels: ["Plastik", "Elektronik", "Cam", "Metal", "Organik", "Bitkisel yağ", "Diğer"],
      values: [29, 18, 16, 13, 12, 7, 5],
    },
    trend: {
      labels: ["Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz"],
      values: [12, 15, 14, 18, 17, 11, 16],
    },
    delivery: { labels: ["Teslim", "Aktif", "Bekleyen"], values: [82, 10, 8] },
    radar: {
      labels: ["Geri dönüşüm", "Teslim", "Katılım", "Kaynak", "Karbon", "Süre", "AI"],
      values: [72, 78, 68, 71, 66, 75, 69],
    },
    history: {
      labels: ["Oca", "Şub", "Mar", "Nis", "May", "Haz"],
      values: [68, 69.1, 70.2, 71.3, 72.4, 74],
    },
    bars: {
      labels: ["İzmir", "İstanbul", "Ankara", "Eskişehir", "Bursa"],
      values: [90, 88, 84, 83, 81],
    },
  };

  function isDark() {
    return document.documentElement.getAttribute("data-bs-theme") === "dark";
  }

  function leafletTileUrl() {
    return isDark()
      ? "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
      : "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png";
  }

  function leafletAttribution() {
    return isDark()
      ? '&copy; <a href="https://www.openstreetmap.org/copyright">OSM</a> &copy; <a href="https://carto.com/">CARTO</a>'
      : "© OpenStreetMap";
  }

  function applyChartTheme() {
    if (typeof Chart === "undefined") return;
    var dark = isDark();
    Chart.defaults.color = dark ? "#cbd5e1" : "#475569";
    Chart.defaults.borderColor = dark
      ? "rgba(148, 163, 184, 0.18)"
      : "rgba(15, 23, 42, 0.08)";
    Chart.defaults.plugins = Chart.defaults.plugins || {};
    Chart.defaults.plugins.legend = Chart.defaults.plugins.legend || {};
    Chart.defaults.plugins.legend.labels = Chart.defaults.plugins.legend.labels || {};
    Chart.defaults.plugins.legend.labels.color = dark ? "#e2e8f0" : "#334155";
    Chart.defaults.plugins.tooltip = Chart.defaults.plugins.tooltip || {};
    Chart.defaults.plugins.tooltip.backgroundColor = dark
      ? "rgba(15, 23, 42, 0.95)"
      : "rgba(15, 23, 42, 0.92)";
    Chart.defaults.plugins.tooltip.titleColor = "#f8fafc";
    Chart.defaults.plugins.tooltip.bodyColor = "#e2e8f0";
    Chart.defaults.plugins.tooltip.borderColor = dark
      ? "rgba(45, 212, 191, 0.35)"
      : "rgba(13, 148, 136, 0.35)";
    Chart.defaults.plugins.tooltip.borderWidth = 1;
    Chart.defaults.scale = Chart.defaults.scale || {};
    Chart.defaults.scale.grid = Chart.defaults.scale.grid || {};
    Chart.defaults.scale.grid.color = dark
      ? "rgba(148, 163, 184, 0.12)"
      : "rgba(15, 23, 42, 0.06)";
  }

  function escapeHtml(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function emptyHtml(opts) {
    opts = opts || {};
    return (
      '<div class="ap-empty-state' +
      (opts.compact ? " is-compact" : "") +
      '" role="status">' +
      '<div class="ap-empty-icon"><i class="bi ' +
      escapeHtml(opts.icon || "bi-clipboard-data") +
      '"></i></div>' +
      '<div class="ap-empty-title">' +
      escapeHtml(opts.title || "Bu metrik için yeterli veri oluşmamıştır.") +
      "</div>" +
      (opts.desc
        ? '<div class="ap-empty-desc">' + escapeHtml(opts.desc) + "</div>"
        : "") +
      "</div>"
    );
  }

  function mountEmpty(el, opts) {
    if (!el) return;
    el.innerHTML = emptyHtml(opts);
  }

  function wrapChartOrEmpty(canvas, hasData, opts) {
    if (!canvas) return false;
    var host = canvas.parentElement;
    if (!host) return false;
    if (hasData) {
      canvas.classList.remove("d-none");
      var old = host.querySelector(".ap-empty-state");
      if (old) old.remove();
      return true;
    }
    canvas.classList.add("d-none");
    if (!host.querySelector(".ap-empty-state")) {
      host.insertAdjacentHTML("beforeend", emptyHtml(opts || {}));
    }
    return false;
  }

  function sum(arr) {
    return (arr || []).reduce(function (a, b) {
      return a + (Number(b) || 0);
    }, 0);
  }

  function hasNumericSeries(arr) {
    return sum(arr) > 0;
  }

  function markDemo(canvas, on) {
    if (!canvas) return;
    var host =
      canvas.closest(
        ".ops-panel-body, .ds-panel-body, .ss-radar-body, .pred-chart-wrap, .ss-history-wrap"
      ) || canvas.parentElement;
    if (!host) return;
    var badge = host.querySelector(".ap-demo-badge");
    if (on) {
      if (!badge) {
        badge = document.createElement("span");
        badge.className = "ap-demo-badge";
        badge.textContent = "Örnek görünüm";
        host.style.position = host.style.position || "relative";
        host.appendChild(badge);
      }
    } else if (badge) {
      badge.remove();
    }
  }

  applyChartTheme();

  global.AtikPortUI = {
    DEMO: DEMO,
    isDark: isDark,
    leafletTileUrl: leafletTileUrl,
    leafletAttribution: leafletAttribution,
    applyChartTheme: applyChartTheme,
    emptyHtml: emptyHtml,
    mountEmpty: mountEmpty,
    wrapChartOrEmpty: wrapChartOrEmpty,
    hasNumericSeries: hasNumericSeries,
    sum: sum,
    markDemo: markDemo,
  };
})(window);
