(function () {
  var panel = document.getElementById("predictionPanel");
  var configEl = document.getElementById("prediction-panel-config");
  if (!panel || !configEl) return;

  var meta;
  try {
    meta = JSON.parse(configEl.textContent);
  } catch (e) {
    return;
  }

  var lookbackEl = document.getElementById("predictionLookback");
  var historyChart = null;
  var forecastChart = null;

  function setText(sel, text) {
    var el = panel.querySelector('[data-pred="' + sel + '"]');
    if (el) el.textContent = text;
  }

  function renderCards(primary) {
    var f = primary.forecasts || {};
    [7, 30, 90].forEach(function (d) {
      var block = f[String(d)] || {};
      var atik = block.atik_miktari || {};
      var kaynak = block.kaynak_paylasimi || {};
      var teslim = block.teslim_orani || {};
      var kat = block.en_yogun_kategori || {};
      setText(
        "atik-" + d,
        "Atık: " + (atik.predicted != null ? atik.predicted : "—") + " kg"
      );
      setText(
        "kaynak-" + d,
        "Kaynak: " + (kaynak.predicted != null ? kaynak.predicted : "—") + " ilan"
      );
      setText(
        "teslim-" + d,
        "Teslim: %" + (teslim.predicted != null ? teslim.predicted : "—")
      );
      setText(
        "kat-" + d,
        "Kategori: " + (kat.en_yogun_kategori || "—") +
          (kat.change_pct != null ? " (" + (kat.change_pct >= 0 ? "+" : "") + kat.change_pct + "%)" : "")
      );
    });
  }

  function renderNarratives(data) {
    var ul = document.getElementById("predictionNarratives");
    var badge = document.getElementById("predictionNarrativeSource");
    if (badge) badge.textContent = data.narrative_source || "rules";
    if (!ul) return;
    var items = data.narratives || [];
    ul.innerHTML = "";
    if (!items.length) {
      ul.innerHTML = '<li class="text-muted">Yorum yok</li>';
      return;
    }
    items.forEach(function (t) {
      var li = document.createElement("li");
      li.textContent = t;
      ul.appendChild(li);
    });
  }

  function renderCharts(primary) {
    if (typeof Chart === "undefined") return;
    var chart = primary.chart || {};
    var labels = chart.labels || [];

    if (historyChart) historyChart.destroy();
    if (forecastChart) forecastChart.destroy();

    historyChart = new Chart(document.getElementById("predictionHistoryChart"), {
      type: "line",
      data: {
        labels: labels,
        datasets: [
          {
            label: "Atık kg",
            data: chart.atik_kg || [],
            borderColor: "#8b5cf6",
            tension: 0.25,
          },
          {
            label: "Kaynak adet",
            data: chart.kaynak_adet || [],
            borderColor: "#10b981",
            tension: 0.25,
          },
          {
            label: "Teslim %",
            data: chart.teslim_orani || [],
            borderColor: "#f59e0b",
            tension: 0.25,
          },
        ],
      },
      options: {
        responsive: true,
        plugins: { title: { display: true, text: "Tarihsel seri (" + primary.lookback_months + " ay)" } },
      },
    });

    forecastChart = new Chart(document.getElementById("predictionForecastChart"), {
      type: "bar",
      data: {
        labels: ["7 gün", "30 gün", "90 gün"],
        datasets: [
          {
            label: "Atık kg tahmini",
            data: [
              (chart.forecast_atik || {})["7"],
              (chart.forecast_atik || {})["30"],
              (chart.forecast_atik || {})["90"],
            ],
            backgroundColor: "#8b5cf6",
          },
          {
            label: "Kaynak adet tahmini",
            data: [
              (chart.forecast_kaynak || {})["7"],
              (chart.forecast_kaynak || {})["30"],
              (chart.forecast_kaynak || {})["90"],
            ],
            backgroundColor: "#10b981",
          },
        ],
      },
      options: {
        responsive: true,
        plugins: { title: { display: true, text: "İleriye dönük tahmin" } },
        scales: { y: { beginAtZero: true } },
      },
    });
  }

  function applyPrimary(data, months) {
    var primary =
      (data.lookbacks && data.lookbacks[String(months)]) || data.primary || data;
    renderCards(primary);
    renderCharts(primary);
    renderNarratives(data);
  }

  function load() {
    var months = lookbackEl ? lookbackEl.value : "12";
    var params = new URLSearchParams(meta.query || {});
    params.set("lookback", months);
    fetch(meta.apiUrl + "?" + params.toString(), { credentials: "same-origin" })
      .then(function (r) {
        return r.json();
      })
      .then(function (data) {
        applyPrimary(data, months);
      })
      .catch(function () {
        var ul = document.getElementById("predictionNarratives");
        if (ul) ul.innerHTML = '<li class="text-danger">Tahmin yüklenemedi</li>';
      });
  }

  if (lookbackEl) lookbackEl.addEventListener("change", load);
  load();
})();
