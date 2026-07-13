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
  var DEMO = (UI && UI.DEMO) || {};
  var radar = cfg.radar || {};
  var history = cfg.history || {};
  var accent = "#0f766e";

  var radarCanvas = document.getElementById("sustainabilityRadarChart");
  if (radarCanvas) {
    var labels = radar.labels || [];
    var values = radar.values || [];
    var demo = !labels.length || !(UI && UI.hasNumericSeries(values));
    if (demo) {
      labels = (DEMO.radar && DEMO.radar.labels) || labels;
      values = (DEMO.radar && DEMO.radar.values) || values;
      if (UI) UI.markDemo(radarCanvas, true);
    }
    if (labels.length) {
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
    } else if (UI) {
      UI.mountEmpty(radarCanvas.parentElement, {
        icon: "bi-radar",
        title: "Bu metrik için yeterli veri oluşmamıştır.",
        desc: "Radar görünümü kategori puanları oluşunca açılır.",
      });
      radarCanvas.classList.add("d-none");
    }
  }

  var histCanvas = document.getElementById("sustainabilityHistoryChart");
  if (histCanvas) {
    var hLabels = history.labels || [];
    var hValues = history.puanlar || [];
    var hDemo = !hLabels.length || !(UI && UI.hasNumericSeries(hValues));
    if (hDemo) {
      hLabels = (DEMO.history && DEMO.history.labels) || hLabels;
      hValues = (DEMO.history && DEMO.history.values) || hValues;
      if (UI) UI.markDemo(histCanvas, true);
    }
    if (hLabels.length) {
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
              display: !hDemo && (!!history.change_pct || history.change_pct === 0),
              text:
                "Trend: " +
                (history.trend || "—") +
                (history.change_pct != null ? " (" + history.change_pct + "%)" : ""),
            },
          },
        },
      });
    } else if (UI) {
      UI.mountEmpty(histCanvas.parentElement, {
        icon: "bi-graph-up",
        title: "Bu metrik için yeterli veri oluşmamıştır.",
      });
      histCanvas.classList.add("d-none");
    }
  }
})();
