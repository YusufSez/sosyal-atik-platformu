/**
 * AtıkPort ortak UI yardımcıları — empty state, skeleton, demo chart verisi.
 * Backend / API değiştirmez.
 */
(function (global) {
  var DEMO = {
    category: {
      labels: ["Plastik", "Cam", "Metal", "Organik", "Elektronik"],
      values: [28, 18, 15, 22, 17],
    },
    trend: {
      labels: ["Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz"],
      values: [12, 15, 11, 18, 16, 9, 14],
    },
    delivery: { labels: ["Teslim", "Aktif", "Bekleyen"], values: [62, 24, 14] },
    radar: {
      labels: ["Geri dönüşüm", "Teslim", "Katılım", "Kaynak", "Karbon", "Süre", "AI"],
      values: [72, 68, 55, 61, 58, 64, 50],
    },
    history: {
      labels: ["Oca", "Şub", "Mar", "Nis", "May", "Haz"],
      values: [54, 58, 61, 63, 67, 70],
    },
    bars: {
      labels: ["İl A", "İl B", "İl C", "İl D", "İl E"],
      values: [88, 81, 76, 71, 65],
    },
  };

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
    var host = canvas.closest(".ops-panel-body, .ds-panel-body, .ss-radar-body, .pred-chart-wrap") || canvas.parentElement;
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

  global.AtikPortUI = {
    DEMO: DEMO,
    emptyHtml: emptyHtml,
    mountEmpty: mountEmpty,
    wrapChartOrEmpty: wrapChartOrEmpty,
    hasNumericSeries: hasNumericSeries,
    sum: sum,
    markDemo: markDemo,
  };
})(window);
