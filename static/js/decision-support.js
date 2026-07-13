(function () {
  var el = document.getElementById("ds-center-config");
  if (!el || typeof Chart === "undefined") return;
  var cfg;
  try {
    cfg = JSON.parse(el.textContent);
  } catch (e) {
    return;
  }
  var UI = window.AtikPortUI || null;
  if (UI && UI.applyChartTheme) UI.applyChartTheme();
  var demoSource = !!cfg.demoSource;
  var accent = "#0f766e";
  var amber = "#b45309";

  function drawOrSkip(canvas, hasData, build) {
    if (!canvas) return;
    if (!hasData) {
      if (demoSource) return;
      if (UI && UI.wrapChartOrEmpty) {
        UI.wrapChartOrEmpty(canvas, false, {
          title: "Bu metrik için yeterli veri oluşmamıştır.",
          compact: true,
        });
      }
      return;
    }
    function run() {
      if (UI) UI.markDemo(canvas, demoSource);
      build();
    }
    if (UI && UI.whenCanvasReady) UI.whenCanvasReady(canvas, run);
    else run();
  }

  var part = cfg.participation || {};
  var partCanvas = document.getElementById("dsParticipationChart");
  drawOrSkip(partCanvas, (part.labels || []).length > 0, function () {
    new Chart(partCanvas, {
      type: "line",
      data: {
        labels: part.labels,
        datasets: [
          {
            label: "Aktif vatandaş",
            data: part.aktif || [],
            borderColor: accent,
            backgroundColor: "rgba(15,118,110,.12)",
            fill: true,
            tension: 0.3,
          },
          {
            label: "İlan",
            data: part.ilanlar || [],
            borderColor: amber,
            tension: 0.3,
          },
        ],
      },
      options: {
        responsive: true,
        plugins: { legend: { position: "bottom" } },
        scales: { y: { beginAtZero: true } },
      },
    });
  });

  var cat = cfg.category || {};
  var catCanvas = document.getElementById("dsCategoryChart");
  drawOrSkip(catCanvas, (cat.labels || []).length > 0, function () {
    new Chart(catCanvas, {
      type: "bar",
      data: {
        labels: cat.labels,
        datasets: [
          {
            label: "Önceki dönem",
            data: cat.previous || [],
            backgroundColor: "rgba(148,163,184,.7)",
          },
          {
            label: "Son dönem",
            data: cat.current || [],
            backgroundColor: accent,
          },
        ],
      },
      options: {
        responsive: true,
        plugins: { legend: { position: "bottom" } },
        scales: { y: { beginAtZero: true } },
      },
    });
  });

  var cmp = cfg.compare || {};
  var cmpCanvas = document.getElementById("dsCompareChart");
  drawOrSkip(cmpCanvas, (cmp.labels || []).length > 0, function () {
    new Chart(cmpCanvas, {
      type: "bar",
      data: {
        labels: cmp.labels,
        datasets: [
          {
            label: "Performans puanı",
            data: cmp.puanlar || [],
            backgroundColor: accent,
          },
        ],
      },
      options: {
        indexAxis: "y",
        responsive: true,
        plugins: { legend: { display: false } },
        scales: { x: { beginAtZero: true, max: 100 } },
      },
    });
  });
})();
