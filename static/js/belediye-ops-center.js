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
  var demoSource = !!(cfg.demoSource || cfg.demoActive);
  var hasServerCharts = !!(
    charts &&
    (charts.category ||
      charts.waste_categories ||
      charts.trend ||
      charts.monthly_trend ||
      charts.teslim_history ||
      charts.delivery_history ||
      charts.radar)
  );

  function normalizeSeries(raw) {
    if (!raw) return null;
    if (Array.isArray(raw.labels) && Array.isArray(raw.values)) {
      return { labels: raw.labels, values: raw.values };
    }
    // MASTER waste_categories düz map: { Plastik: 29, ... }
    if (typeof raw === "object" && !Array.isArray(raw)) {
      var labels = Object.keys(raw).filter(function (k) {
        return (
          k !== "labels" &&
          k !== "values" &&
          typeof raw[k] !== "object"
        );
      });
      if (!labels.length) return null;
      return {
        labels: labels,
        values: labels.map(function (k) {
          return Number(raw[k]) || 0;
        }),
      };
    }
    return null;
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

  function containerReady(el) {
    if (!el) return false;
    if (el.classList.contains("d-none") || el.hasAttribute("hidden")) return false;
    var rect = el.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0;
  }

  function addCircleMarkers(map, pts) {
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

  function addHeatLayer(map, pts) {
    if (!pts.length) return false;
    try {
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
    } catch (e) {
      /* heat layer başarısız → circleMarker */
    }
    return addCircleMarkers(map, pts);
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
      pts = Array.isArray(pts) ? pts : [];

      var map = L.map(mapEl, { preferCanvas: true });
      L.tileLayer(
        (UI && UI.leafletTileUrl && UI.leafletTileUrl()) ||
          "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
        {
          attribution:
            (UI && UI.leafletAttribution && UI.leafletAttribution()) ||
            "© OpenStreetMap",
        }
      ).addTo(map);

      map.setView(
        [center.lat || 40.77, center.lng || 30.4],
        center.zoom || 11
      );

      function afterReady(tries) {
        tries = tries == null ? 40 : tries;
        map.invalidateSize();
        if (!containerReady(mapEl)) {
          if (tries <= 0) return;
          requestAnimationFrame(function () {
            afterReady(tries - 1);
          });
          return;
        }
        if (!pts.length) {
          if (demoSource || hasServerCharts) {
            hideEmpty(emptyEl);
            return;
          }
          mapEl.classList.add("d-none");
          showEmpty(emptyEl);
          return;
        }
        addHeatLayer(map, pts);
        if (demoSource && UI && UI.markDemo) UI.markDemo(mapEl, true);
        map.invalidateSize();
      }

      map.whenReady(function () {
        requestAnimationFrame(function () {
          requestAnimationFrame(afterReady);
        });
      });
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

  function canvasReady(canvas) {
    if (UI && UI.canvasReady) return UI.canvasReady(canvas);
    if (!canvas) return false;
    var rect = canvas.getBoundingClientRect();
    var parent = canvas.parentElement;
    var pw = parent ? parent.getBoundingClientRect().width : 0;
    return (rect.width > 0 || pw > 0) && (rect.height > 0 || canvas.height > 0);
  }

  function whenCanvasReady(canvas, fn, tries) {
    if (UI && UI.whenCanvasReady) {
      UI.whenCanvasReady(canvas, fn, tries);
      return;
    }
    tries = tries == null ? 20 : tries;
    if (canvasReady(canvas)) {
      fn();
      return;
    }
    if (tries <= 0) return;
    requestAnimationFrame(function () {
      whenCanvasReady(canvas, fn, tries - 1);
    });
  }

  function pickCategory() {
    var cat = normalizeSeries(charts.category || charts.waste_categories);
    if (cat && seriesOk(cat.labels, cat.values)) {
      return { labels: cat.labels, values: cat.values, fromServer: true };
    }
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
    // Sunucu veri yoksa: AtikPortUI.DEMO yalnızca Demo Mode açıkken (empty yasak)
    if (demoSource && DEMO.category) {
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
    var tr = normalizeSeries(charts.monthly_trend || charts.trend);
    if (tr && seriesOk(tr.labels, tr.values)) {
      return { labels: tr.labels, values: tr.values, fromServer: true };
    }
    if (demoSource && DEMO.trend) {
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
    var hist = normalizeSeries(charts.delivery_history || charts.teslim_history);
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
    if (demoSource && DEMO.delivery) {
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

  function markChartEmpty(canvas, hasData) {
    if (!canvas || !UI || !UI.wrapChartOrEmpty) return;
    if (demoSource || hasServerCharts) {
      UI.wrapChartOrEmpty(canvas, true, {});
      return;
    }
    UI.wrapChartOrEmpty(canvas, hasData, {
      icon: "bi-clipboard-data",
      title: "Bu metrik için yeterli veri oluşmamıştır.",
      desc: "Veri oluşunca grafik burada görünür.",
      compact: true,
    });
  }

  function renderCharts() {
    if (typeof Chart === "undefined") {
      if (!demoSource) {
        ["opsCategoryChart", "opsTrendChart", "opsDeliveryChart"].forEach(
          function (id) {
            markChartEmpty(document.getElementById(id), false);
          }
        );
      }
      return;
    }
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
    if (catCanvas) {
      markChartEmpty(catCanvas, !!cat.labels.length);
      if (cat.labels.length) {
        whenCanvasReady(catCanvas, function () {
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
        });
      }
    }

    var trend = pickTrend();
    var trendCanvas = document.getElementById("opsTrendChart");
    if (trendCanvas) {
      markChartEmpty(trendCanvas, !!trend.labels.length);
      if (trend.labels.length) {
        whenCanvasReady(trendCanvas, function () {
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
        });
      }
    }

    var delivery = pickDelivery();
    var deliveryCanvas = document.getElementById("opsDeliveryChart");
    var caption = document.getElementById("opsDeliveryCaption");
    if (deliveryCanvas) {
      markChartEmpty(deliveryCanvas, !!delivery.labels.length);
      if (delivery.labels.length) {
        whenCanvasReady(deliveryCanvas, function () {
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
        });
      }
    }

    var radar = normalizeSeries(charts.radar);
    var radarCanvas = document.getElementById("opsRadarChart");
    if (radarCanvas) {
      markChartEmpty(radarCanvas, !!(radar && radar.labels.length));
      if (radar && radar.labels.length) {
        whenCanvasReady(radarCanvas, function () {
          if (UI) UI.markDemo(radarCanvas, !!demoSource);
          new Chart(radarCanvas, {
            type: "radar",
            data: {
              labels: radar.labels,
              datasets: [
                {
                  label: "Operasyon skoru",
                  data: radar.values,
                  borderColor: accent,
                  backgroundColor: "rgba(15, 118, 110, 0.18)",
                  pointBackgroundColor: accent,
                  borderWidth: 2,
                },
              ],
            },
            options: {
              responsive: true,
              maintainAspectRatio: true,
              scales: {
                r: {
                  min: 0,
                  max: 100,
                  ticks: { stepSize: 20, backdrop: false },
                  pointLabels: { font: { size: 11 } },
                },
              },
              plugins: { legend: { display: false } },
            },
          });
        });
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
