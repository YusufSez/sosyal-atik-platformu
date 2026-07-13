(function () {
  var cfgEl = document.getElementById("ops-center-config");
  if (!cfgEl) return;

  var cfg;
  try {
    cfg = JSON.parse(cfgEl.textContent);
  } catch (e) {
    return;
  }

  var updated = document.getElementById("opsLastUpdated");
  if (updated) {
    try {
      updated.textContent = new Date().toLocaleString("tr-TR", {
        day: "2-digit",
        month: "2-digit",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      });
    } catch (e2) {
      updated.textContent = new Date().toISOString();
    }
  }

  // Activity filter tabs
  var tabs = document.getElementById("opsActivityTabs");
  var list = document.getElementById("opsActivityList");
  if (tabs && list) {
    tabs.addEventListener("click", function (e) {
      var btn = e.target.closest("[data-filter]");
      if (!btn) return;
      var filter = btn.getAttribute("data-filter");
      tabs.querySelectorAll("[data-filter]").forEach(function (b) {
        var on = b === btn;
        b.classList.toggle("btn-success", on);
        b.classList.toggle("btn-outline-success", !on);
      });
      list.querySelectorAll(".ops-activity-item").forEach(function (item) {
        var group = item.getAttribute("data-group");
        item.style.display =
          filter === "all" || group === filter ? "" : "none";
      });
    });
  }

  // Heat map via existing API
  function loadHeatMap() {
    var mapEl = document.getElementById("opsHeatMap");
    if (!mapEl || typeof L === "undefined") return;

    var params = new URLSearchParams();
    var q = cfg.query || {};
    if (q.il) params.set("il", q.il);
    if (q.ilce) params.set("ilce", q.ilce);
    if (q.mahalle) params.set("mahalle", q.mahalle);
    params.set("yogunluk", "atik");

    fetch((cfg.heatmapUrl || "/belediye/api/heatmap") + "?" + params.toString(), {
      credentials: "same-origin",
    })
      .then(function (r) {
        return r.json();
      })
      .then(function (noktalar) {
        var map = L.map(mapEl).setView([39.0, 35.0], 6);
        L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
          attribution: "© OpenStreetMap",
        }).addTo(map);

        var pts = Array.isArray(noktalar) ? noktalar : [];
        if (pts.length && L.heatLayer) {
          L.heatLayer(pts, {
            radius: 22,
            blur: 18,
            maxZoom: 12,
            gradient: {
              0.2: "#5eead4",
              0.5: "#14b8a6",
              0.8: "#0f766e",
              1: "#115e59",
            },
          }).addTo(map);
          map.fitBounds(
            pts.map(function (p) {
              return [p[0], p[1]];
            }),
            { padding: [30, 30], maxZoom: 11 }
          );
        }
        setTimeout(function () {
          map.invalidateSize();
        }, 120);
      })
      .catch(function () {
        mapEl.innerHTML =
          '<div class="p-4 text-muted small">Harita yüklenemedi. Isı Haritası sayfasını açın.</div>';
      });
  }

  function buildCategoryData() {
    var counts = {};
    (cfg.activities || []).forEach(function (a) {
      var k = (a && a.kategori) || "Diğer";
      counts[k] = (counts[k] || 0) + 1;
    });
    if (cfg.kritik && !counts[cfg.kritik]) {
      counts[cfg.kritik] = Math.max(1, counts[cfg.kritik] || 0);
    }
    var labels = Object.keys(counts);
    if (!labels.length) {
      labels = ["Veri yok"];
      return { labels: labels, values: [0] };
    }
    return {
      labels: labels,
      values: labels.map(function (k) {
        return counts[k];
      }),
    };
  }

  function renderCharts() {
    if (typeof Chart === "undefined") return;
    var m = cfg.metrics || {};
    var accent = "#0f766e";
    var palette = [
      "#0f766e",
      "#14b8a6",
      "#3b82f6",
      "#8b5cf6",
      "#f59e0b",
      "#ef4444",
      "#64748b",
    ];

    var cat = buildCategoryData();
    var catCanvas = document.getElementById("opsCategoryChart");
    if (catCanvas) {
      new Chart(catCanvas, {
        type: "doughnut",
        data: {
          labels: cat.labels,
          datasets: [
            {
              data: cat.values,
              backgroundColor: palette,
              borderWidth: 0,
            },
          ],
        },
        options: {
          responsive: true,
          maintainAspectRatio: true,
          plugins: {
            legend: { position: "bottom", labels: { boxWidth: 12 } },
          },
        },
      });
    }

    var trendCanvas = document.getElementById("opsTrendChart");
    if (trendCanvas) {
      new Chart(trendCanvas, {
        type: "line",
        data: {
          labels: ["Bugün", "Son 24s ilan", "Son 24s teslim", "Aktif", "Teslim", "Bekleyen"],
          datasets: [
            {
              label: "Operasyon hacmi",
              data: [
                m.bugun || 0,
                m.ilan24 || 0,
                m.teslim24 || 0,
                m.aktif || 0,
                m.teslim || 0,
                m.bekleyen || 0,
              ],
              borderColor: accent,
              backgroundColor: "rgba(15, 118, 110, 0.12)",
              fill: true,
              tension: 0.35,
              pointRadius: 4,
            },
          ],
        },
        options: {
          responsive: true,
          plugins: { legend: { display: false } },
          scales: { y: { beginAtZero: true, ticks: { precision: 0 } } },
        },
      });
    }

    var deliveryCanvas = document.getElementById("opsDeliveryChart");
    var caption = document.getElementById("opsDeliveryCaption");
    if (deliveryCanvas) {
      var teslim = Number(m.teslim || 0);
      var aktif = Number(m.aktif || 0);
      var bekleyen = Number(m.bekleyen || 0);
      var denom = teslim + aktif;
      var rate = denom > 0 ? Math.round((1000 * teslim) / denom) / 10 : 0;
      if (caption) {
        caption.textContent =
          "Teslim oranı %" +
          rate +
          " · " +
          teslim +
          " teslim / " +
          (aktif + teslim) +
          " toplam · bekleyen " +
          bekleyen;
      }
      new Chart(deliveryCanvas, {
        type: "doughnut",
        data: {
          labels: ["Teslim", "Aktif", "Bekleyen"],
          datasets: [
            {
              data: [teslim, aktif, bekleyen],
              backgroundColor: ["#10b981", "#3b82f6", "#f59e0b"],
              borderWidth: 0,
            },
          ],
        },
        options: {
          responsive: true,
          cutout: "68%",
          plugins: {
            legend: { position: "bottom", labels: { boxWidth: 12 } },
          },
        },
      });
    }
  }

  loadHeatMap();
  renderCharts();
})();
