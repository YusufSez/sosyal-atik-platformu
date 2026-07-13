(function () {
  var cfgEl = document.getElementById("ops-center-config");
  if (!cfgEl) return;

  var cfg;
  try {
    cfg = JSON.parse(cfgEl.textContent);
  } catch (e) {
    return;
  }

  var UI = window.AtikPortUI || null;
  var DEMO = (UI && UI.DEMO) || {};

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

  function loadHeatMap() {
    var mapEl = document.getElementById("opsHeatMap");
    var emptyEl = document.getElementById("opsHeatMapEmpty");
    if (!mapEl || typeof L === "undefined") return;

    var params = new URLSearchParams();
    var q = cfg.query || {};
    if (q.il) params.set("il", q.il);
    if (q.ilce) params.set("ilce", q.ilce);
    if (q.mahalle) params.set("mahalle", q.mahalle);
    params.set("yogunluk", "atik");

    var center = cfg.mapCenter || { lat: 40.77, lng: 30.4, zoom: 11 };

    fetch((cfg.heatmapUrl || "/belediye/api/heatmap") + "?" + params.toString(), {
      credentials: "same-origin",
    })
      .then(function (r) {
        return r.json();
      })
      .then(function (noktalar) {
        var UI = window.AtikPortUI;
        if (UI && UI.applyChartTheme) UI.applyChartTheme();
        var map = L.map(mapEl).setView(
          [center.lat || 40.77, center.lng || 30.4],
          center.zoom || 11
        );
        L.tileLayer(
          (UI && UI.leafletTileUrl && UI.leafletTileUrl()) ||
            "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
          {
            attribution:
              (UI && UI.leafletAttribution && UI.leafletAttribution()) ||
              "© OpenStreetMap",
          }
        ).addTo(map);

        var pts = Array.isArray(noktalar) ? noktalar : [];
        var demoHeat = false;
        if (!pts.length) {
          demoHeat = true;
          var baseLat = center.lat || 40.77;
          var baseLng = center.lng || 30.4;
          pts = [
            [baseLat, baseLng, 0.9],
            [baseLat + 0.02, baseLng + 0.01, 0.7],
            [baseLat - 0.015, baseLng + 0.02, 0.55],
            [baseLat + 0.01, baseLng - 0.02, 0.8],
            [baseLat - 0.02, baseLng - 0.01, 0.45],
            [baseLat + 0.025, baseLng - 0.015, 0.6],
          ];
        }
        if (emptyEl) emptyEl.classList.add("d-none");
        mapEl.classList.remove("d-none");
        if (pts.length && L.heatLayer) {
          L.heatLayer(pts, {
            radius: 24,
            blur: 18,
            maxZoom: 14,
            gradient: {
              0.2: "#bbf7d0",
              0.45: "#86efac",
              0.65: "#22c55e",
              0.85: "#16a34a",
              1: "#14532d",
            },
          }).addTo(map);
          map.fitBounds(
            pts.map(function (p) {
              return [p[0], p[1]];
            }),
            { padding: [30, 30], maxZoom: 13 }
          );
          if (demoHeat && UI && UI.markDemo) UI.markDemo(mapEl, true);
        }
        setTimeout(function () {
          map.invalidateSize();
        }, 120);
      })
      .catch(function () {
        mapEl.classList.add("d-none");
        if (emptyEl) emptyEl.classList.remove("d-none");
      });
  }

  function buildCategoryData() {
    var DEMO = (UI && UI.DEMO) || {};
    var counts = {};
    (cfg.activities || []).forEach(function (a) {
      var k = (a && a.kategori) || "Diğer";
      counts[k] = (counts[k] || 0) + 1;
    });
    if (cfg.kritik && !counts[cfg.kritik]) {
      counts[cfg.kritik] = Math.max(1, counts[cfg.kritik] || 0);
    }
    var labels = Object.keys(counts);
    if (!labels.length || !(UI && UI.sum(Object.values(counts)))) {
      return {
        labels: (DEMO.category && DEMO.category.labels) || [
          "Plastik",
          "Cam",
          "Metal",
          "Organik",
          "Elektronik",
        ],
        values: (DEMO.category && DEMO.category.values) || [28, 18, 15, 22, 17],
        demo: true,
      };
    }
    return {
      labels: labels,
      values: labels.map(function (k) {
        return counts[k];
      }),
      demo: false,
    };
  }

  function renderCharts() {
    if (typeof Chart === "undefined") return;
    if (window.AtikPortUI && window.AtikPortUI.applyChartTheme) {
      window.AtikPortUI.applyChartTheme();
    }
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
      if (UI) UI.markDemo(catCanvas, !!cat.demo);
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
      var trendVals = [
        m.bugun || 0,
        m.ilan24 || 0,
        m.teslim24 || 0,
        m.aktif || 0,
        m.teslim || 0,
        m.bekleyen || 0,
      ];
      var trendDemo = !(UI && UI.hasNumericSeries(trendVals));
      if (trendDemo) {
        trendVals = (DEMO.trend && DEMO.trend.values) || [12, 15, 11, 18, 16, 9];
      }
      if (UI) UI.markDemo(trendCanvas, trendDemo);
      new Chart(trendCanvas, {
        type: "line",
        data: {
          labels: trendDemo
            ? (DEMO.trend && DEMO.trend.labels) || [
                "Pzt",
                "Sal",
                "Çar",
                "Per",
                "Cum",
                "Cmt",
                "Paz",
              ]
            : ["Bugün", "Son 24s ilan", "Son 24s teslim", "Aktif", "Teslim", "Bekleyen"],
          datasets: [
            {
              label: "Operasyon hacmi",
              data: trendVals,
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
      var demo = teslim + aktif + bekleyen <= 0;
      var data = demo
        ? (DEMO.delivery && DEMO.delivery.values) || [62, 24, 14]
        : [teslim, aktif, bekleyen];
      if (UI) UI.markDemo(deliveryCanvas, demo);
      var denom = data[0] + data[1];
      var rate = denom > 0 ? Math.round((1000 * data[0]) / denom) / 10 : 0;
      if (caption) {
        caption.textContent = demo
          ? "Örnek teslim oranı görünümü · gerçek veri birikince güncellenir"
          : "Teslim oranı %" +
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
              data: data,
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
