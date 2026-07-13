(function () {
  var cfgEl = document.getElementById("sustainability-chart-config");
  if (!cfgEl || typeof Chart === "undefined") return;
  var cfg;
  try {
    cfg = JSON.parse(cfgEl.textContent);
  } catch (e) {
    return;
  }

  var radar = cfg.radar || {};
  var history = cfg.history || {};
  var accent = "#0f766e";

  var radarCanvas = document.getElementById("sustainabilityRadarChart");
  if (radarCanvas && (radar.labels || []).length) {
    new Chart(radarCanvas, {
      type: "radar",
      data: {
        labels: radar.labels,
        datasets: [
          {
            label: "Kategori puanı",
            data: radar.values || [],
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
            pointLabels: { font: { size: 10 } },
          },
        },
        plugins: { legend: { display: false } },
      },
    });
  }

  var histCanvas = document.getElementById("sustainabilityHistoryChart");
  if (histCanvas && (history.labels || []).length) {
    new Chart(histCanvas, {
      type: "line",
      data: {
        labels: history.labels,
        datasets: [
          {
            label: "Aylık puan",
            data: history.puanlar || [],
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
})();
