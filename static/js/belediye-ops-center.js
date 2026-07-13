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
  var charts = cfg.charts || {};
  var demoSource = !!cfg.demoSource;
  var hasServerCharts = !!(
    charts &&
    (charts.category ||
      charts.waste_categories ||
      charts.trend ||
      charts.monthly_trend ||
      charts.teslim_history ||
      charts.delivery_history)
  );

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

  function seriesOk(labels, values) {
    if (!Array.isArray(labels) || !Array.isArray(values)) return false;
    // Demo açıkken length==0 boş sayılmaz; labels varsa çiz
    if (demoSource) {
      return labels.length > 0 && values.length > 0;
    }
    return (
      labels.length > 0 &&
      values.length > 0 &&
      values.some(function (v) {
        return Number(v) !== 0 && v != null && v !== "";
      })
    );
  }

  function hideEmpty(el) {
    if (!el) return;
    el.classList.add("d-none");
    el.setAttribute("hidden", "hidden");
  }

  function showEmpty(el) {
    if (!el) return;
    // Demo / sunucu verisi varken placeholder YASAK
    if (demoSource || hasServerCharts) {
      hideEmpty(el);
      return;
    }
    el.classList.remove("d-none");
    el.removeAttribute("hidden");
  }

  function addHeatLayer(map, pts) {
    if (!pts.length) return false;
    if (typeof L !== "undefined" && typeof L.heatLayer === "function") {
      L.heatLayer(pts, {
        radius: 28,
        blur: 20,
        maxZoom: 15,
        minOpacity: 0.35,
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
      return true;
    }
    // leaflet-heat yoksa da boş gösterme — daire işaretçileri
    pts.forEach(function (p) {
      L.circleMarker([p[0], p[1]], {
        radius: 6 + Math.min(10, (p[2] || 0.5) * 10),
        color: "#0f766e",
        fillColor: "#14b8a6",
        fillOpacity: 0.55,
        weight: 1,
      }).addTo(map);
    });
    map.fitBounds(
      pts.map(function (p) {
        return [p[0], p[1]];
      }),
      { padding: [30, 30], maxZoom: 13 }
    );
    return true;
  }

  function loadHeatMap() {
    var mapEl = document.getElementById("opsHeatMap");
    var emptyEl = document.getElementById("opsHeatMapEmpty");
    if (!mapEl) return;
    if (typeof L === "undefined") {
      if (!demoSource) showEmpty(emptyEl);
      return;
    }

    var center = cfg.mapCenter || { lat: 40.77, lng: 30.4, zoom: 11 };

    function paint(pts) {
      hideEmpty(emptyEl);
      mapEl.classList.remove("d-none");
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

      pts = Array.isArray(pts) ? pts : [];
      if (!pts.length) {
        if (demoSource || hasServerCharts) {
          // Demo açıkken asla empty-state
          hideEmpty(emptyEl);
          setTimeout(function () {
            map.invalidateSize();
          }, 120);
          return;
        }
        mapEl.classList.add("d-none");
        showEmpty(emptyEl);
        return;
      }
      addHeatLayer(map, pts);
      if (demoSource && UI && UI.markDemo) UI.markDemo(mapEl, true);
      setTimeout(function () {
        map.invalidateSize();
      }, 120);
    }

    var embedded = cfg.heatmap || cfg.heat_points || [];
    if (Array.isArray(embedded) && embedded.length) {
      paint(embedded);
      return;
    }

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
        paint(noktalar);
      })
      .catch(function () {
        if (demoSource) {
          hideEmpty(emptyEl);
          mapEl.classList.remove("d-none");
        } else {
          mapEl.classList.add("d-none");
          showEmpty(emptyEl);
        }
      });
  }

  function pickCategory() {
    var cat = charts.category || charts.waste_categories;
    if (cat && seriesOk(cat.labels, cat.values)) {
      return { labels: cat.labels, values: cat.values, fromServer: true };
    }
    // Sunucu yoksa aktiviteler; DEMO yalnızca en son çare ve demoSource değilken
    var counts = {};
    (cfg.activities || []).forEach(function (a) {
      var k = (a && a.kategori) || "Diğer";
      counts[k] = (counts[k] || 0) + 1;
    });
    var labels = Object.keys(counts);
    var values = labels.map(function (k) {
      return counts[k];
    });
    if (seriesOk(labels, values)) {
      return { labels: labels, values: values, fromServer: false };
    }
    if (!demoSource && DEMO.category) {
      return {
        labels: DEMO.category.labels || [],
        values: DEMO.category.values || [],
        fromServer: false,
        clientDemo: true,
      };
    }
    return { labels: [], values: [], fromServer: false };
  }

  function pickTrend() {
    var tr = charts.monthly_trend || charts.trend;
    if (tr && seriesOk(tr.labels, tr.values)) {
      return { labels: tr.labels, values: tr.values, fromServer: true };
    }
    if (!demoSource && DEMO.trend) {
      return {
        labels: DEMO.trend.labels || [],
        values: DEMO.trend.values || [],
        fromServer: false,
        clientDemo: true,
      };
    }
    return { labels: [], values: [], fromServer: false };
  }

  function pickDelivery() {
    var hist = charts.delivery_history || charts.teslim_history;
    if (hist && seriesOk(hist.labels, hist.values)) {
      return { type: "line", labels: hist.labels, values: hist.values, fromServer: true };
    }
    var del = charts.delivery;
    if (del && Array.isArray(del.values) && del.values.length) {
      return {
        type: "doughnut",
        labels: del.labels || ["Teslim", "Aktif", "Bekleyen"],
        values: del.values,
        fromServer: true,
      };
    }
    if (!demoSource && DEMO.delivery) {
      return {
        type: "doughnut",
        labels: ["Teslim", "Aktif", "Bekleyen"],
        values: DEMO.delivery.values || [62, 24, 14],
        fromServer: false,
        clientDemo: true,
      };
    }
    return { type: "line", labels: [], values: [], fromServer: false };
  }

  function renderCharts() {
    if (typeof Chart === "undefined") return;
    if (UI && UI.applyChartTheme) UI.applyChartTheme();
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

    var cat = pickCategory();
    var catCanvas = document.getElementById("opsCategoryChart");
    if (catCanvas && cat.labels.length) {
      if (UI) UI.markDemo(catCanvas, !!(demoSource || cat.clientDemo));
      new Chart(catCanvas, {
        type: "doughnut",
        data: {
          labels: cat.labels,
          datasets: [
            { data: cat.values, backgroundColor: palette, borderWidth: 0 },
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

    var trend = pickTrend();
    var trendCanvas = document.getElementById("opsTrendChart");
    if (trendCanvas && trend.labels.length) {
      if (UI) UI.markDemo(trendCanvas, !!(demoSource || trend.clientDemo));
      new Chart(trendCanvas, {
        type: "line",
        data: {
          labels: trend.labels,
          datasets: [
            {
              label: "Operasyon hacmi",
              data: trend.values,
              borderColor: accent,
              backgroundColor: "rgba(15, 118, 110, 0.12)",
              fill: true,
              tension: 0.35,
              pointRadius: 3,
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

    var delivery = pickDelivery();
    var deliveryCanvas = document.getElementById("opsDeliveryChart");
    var caption = document.getElementById("opsDeliveryCaption");
    if (deliveryCanvas && delivery.labels.length) {
      if (UI) UI.markDemo(deliveryCanvas, !!(demoSource || delivery.clientDemo));
      if (delivery.type === "line") {
        new Chart(deliveryCanvas, {
          type: "line",
          data: {
            labels: delivery.labels,
            datasets: [
              {
                label: "Teslim oranı %",
                data: delivery.values,
                borderColor: accent,
                backgroundColor: "rgba(15, 118, 110, 0.12)",
                fill: true,
                tension: 0.35,
                pointRadius: 3,
              },
            ],
          },
          options: {
            responsive: true,
            plugins: { legend: { display: false } },
            scales: {
              y: { beginAtZero: true, max: 100, ticks: { precision: 0 } },
            },
          },
        });
        if (caption) {
          var last = delivery.values[delivery.values.length - 1];
          caption.textContent = "Son dönem teslim oranı: %" + last;
        }
      } else {
        new Chart(deliveryCanvas, {
          type: "doughnut",
          data: {
            labels: delivery.labels,
            datasets: [
              {
                data: delivery.values,
                backgroundColor: [accent, "#3b82f6", "#f59e0b"],
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
        if (caption) {
          var sum = delivery.values.reduce(function (a, b) {
            return a + Number(b || 0);
          }, 0);
          var pct = sum
            ? Math.round((Number(delivery.values[0] || 0) / sum) * 100)
            : 0;
          caption.textContent = "Teslim payı ≈ %" + pct;
        }
      }
    }
  }

  // Demo kaynaklıysa empty bloğu DOM'da gizle
  if (demoSource) {
    hideEmpty(document.getElementById("opsHeatMapEmpty"));
  }

  loadHeatMap();
  renderCharts();
})();
