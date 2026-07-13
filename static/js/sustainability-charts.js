(function () {
  var cfgEl = document.getElementById("sustainability-chart-config");
  if (!cfgEl || typeof Chart === "undefined") return;
  var cfg;
  try {
    cfg = JSON.parse(cfgEl.textContent);
  } catch (e) {
    return;
  }

  var UI = window.AtikPortUI || null;
  if (UI && UI.applyChartTheme) UI.applyChartTheme();
  var demoSource = !!cfg.demoSource;
  var radar = cfg.radar || {};
  var history = cfg.history || {};
  var accent = "#0f766e";

  function seriesFilled(labels, values) {
    return (
      Array.isArray(labels) &&
      labels.length > 0 &&
      Array.isArray(values) &&
      values.length > 0 &&
      values.some(function (v) {
        return v != null && v !== "" && !isNaN(Number(v));
      })
    );
  }

  var radarCanvas = document.getElementById("sustainabilityRadarChart");
  if (radarCanvas) {
    var labels = radar.labels || [];
    var values = radar.values || [];
    var hasRadar = seriesFilled(labels, values);
    if (!hasRadar) {
      if (!demoSource && UI) {
        UI.mountEmpty(radarCanvas.parentElement, {
          icon: "bi-radar",
          title: "Bu metrik için yeterli veri oluşmamıştır.",
          desc: "Radar görünümü kategori puanları oluşunca açılır.",
        });
        radarCanvas.classList.add("d-none");
      }
    } else {
      function paintRadar() {
        if (UI) UI.markDemo(radarCanvas, demoSource);
        new Chart(radarCanvas, {
          type: "radar",
          data: {
            labels: labels,
            datasets: [
              {
                label: "Kategori puanı",
                data: values,
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
      }
      if (UI && UI.whenCanvasReady) UI.whenCanvasReady(radarCanvas, paintRadar);
      else paintRadar();
    }
  }

  var histCanvas = document.getElementById("sustainabilityHistoryChart");
  if (histCanvas) {
    var hLabels = history.labels || [];
    // Alias: puanlar (sustainability) | values (chart_demo_bundle)
    var hValues = history.puanlar || history.values || [];
    var hasHist = seriesFilled(hLabels, hValues);
    if (!hasHist) {
      if (!demoSource && UI) {
        UI.mountEmpty(histCanvas.parentElement, {
          icon: "bi-graph-up",
          title: "Bu metrik için yeterli veri oluşmamıştır.",
        });
        histCanvas.classList.add("d-none");
      }
    } else {
      function paintHist() {
        if (UI) UI.markDemo(histCanvas, demoSource);
        new Chart(histCanvas, {
          type: "line",
          data: {
            labels: hLabels,
            datasets: [
              {
                label: "Aylık puan",
                data: hValues,
                borderColor: accent,
                backgroundColor: "rgba(15, 118, 110, 0.12)",
                fill: true,
                tension: 0.3,
              },
            ],
          },
          options: {
            responsive: true,
            maintainAspectRatio: true,
            scales: {
              y: { min: 0, max: 100, beginAtZero: true },
            },
            plugins: {
              legend: { display: false },
              title: {
                display: !!history.change_pct || history.change_pct === 0,
                text:
                  "Trend: " +
                  (history.trend || "—") +
                  (history.change_pct != null ? " (" + history.change_pct + "%)" : ""),
              },
            },
          },
        });
      }
      if (UI && UI.whenCanvasReady) UI.whenCanvasReady(histCanvas, paintHist);
      else paintHist();
    }
  }
})();
