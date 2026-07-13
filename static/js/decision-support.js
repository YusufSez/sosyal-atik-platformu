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
  var DEMO = (UI && UI.DEMO) || {};
  var accent = "#0f766e";
  var amber = "#b45309";

  function renderOrDemo(canvas, hasData, build) {
    if (!canvas) return;
    if (hasData) {
      if (UI) UI.markDemo(canvas, false);
      build(false);
      return;
    }
    if (UI) UI.markDemo(canvas, true);
    build(true);
  }

  var part = cfg.participation || {};
  var partCanvas = document.getElementById("dsParticipationChart");
  renderOrDemo(partCanvas, (part.labels || []).length > 0, function (demo) {
    if (!partCanvas) return;
    new Chart(partCanvas, {
      type: "line",
      data: {
        labels: demo
          ? (DEMO.history && DEMO.history.labels) || ["Oca", "Şub", "Mar", "Nis", "May", "Haz"]
          : part.labels,
        datasets: [
          {
            label: "Aktif vatandaş",
            data: demo
              ? (DEMO.history && DEMO.history.values) || [54, 58, 61, 63, 67, 70]
              : part.aktif || [],
            borderColor: accent,
            backgroundColor: "rgba(15,118,110,.12)",
            fill: true,
            tension: 0.3,
          },
          {
            label: "İlan",
            data: demo ? [40, 44, 42, 48, 51, 55] : part.ilanlar || [],
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
  renderOrDemo(catCanvas, (cat.labels || []).length > 0, function (demo) {
    if (!catCanvas) return;
    new Chart(catCanvas, {
      type: "bar",
      data: {
        labels: demo ? (DEMO.category && DEMO.category.labels) || [] : cat.labels,
        datasets: [
          {
            label: "Önceki dönem",
            data: demo ? [20, 14, 12, 18, 10] : cat.previous || [],
            backgroundColor: "rgba(148,163,184,.7)",
          },
          {
            label: "Son dönem",
            data: demo
              ? (DEMO.category && DEMO.category.values) || []
              : cat.current || [],
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
  renderOrDemo(cmpCanvas, (cmp.labels || []).length > 0, function (demo) {
    if (!cmpCanvas) return;
    new Chart(cmpCanvas, {
      type: "bar",
      data: {
        labels: demo ? (DEMO.bars && DEMO.bars.labels) || [] : cmp.labels,
        datasets: [
          {
            label: "Performans puanı",
            data: demo ? (DEMO.bars && DEMO.bars.values) || [] : cmp.puanlar || [],
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
