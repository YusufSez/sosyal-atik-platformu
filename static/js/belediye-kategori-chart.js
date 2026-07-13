(function () {
  var el = document.getElementById("belediye-kategori-config");
  var canvas = document.getElementById("belediyeKategoriChart");
  if (!el || !canvas || typeof Chart === "undefined") return;

  var config;
  try {
    config = JSON.parse(el.textContent);
  } catch (e) {
    return;
  }

  new Chart(canvas, {
    type: "bar",
    data: {
      labels: config.labels || [],
      datasets: [
        {
          label: "İlan sayısı",
          data: config.values || [],
          backgroundColor: [
            "#0f766e",
            "#10b981",
            "#3b82f6",
            "#8b5cf6",
            "#f59e0b",
            "#ef4444",
            "#64748b",
          ],
          borderRadius: 6,
        },
      ],
    },
    options: {
      responsive: true,
      plugins: {
        legend: { display: false },
      },
      scales: {
        y: { beginAtZero: true, ticks: { precision: 0 } },
      },
    },
  });
})();
