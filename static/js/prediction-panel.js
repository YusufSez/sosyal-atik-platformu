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
  var tabsEl = document.getElementById("predictionHorizonTabs");
  var historyChart = null;
  var forecastChart = null;
  var currentPrimary = null;
  var activeHorizon = "7";
  var METRIC_ORDER = ["atik_miktari", "kategori_artisi", "teslim_orani", "katilim", "co2"];
  var HORIZONS = ["7", "30", "90", "180", "365"];
  var HORIZON_LABELS = {
    "7": "7 gün",
    "30": "30 gün",
    "90": "90 gün",
    "180": "6 ay",
    "365": "12 ay",
  };

  var TREND_TR = { yukselis: "Yükseliş", dusus: "Düşüş", stabil: "Stabil" };
  var RISK_TR = { dusuk: "Düşük", orta: "Orta", yuksek: "Yüksek" };
  var RISK_CLASS = {
    dusuk: "text-bg-success",
    orta: "text-bg-warning",
    yuksek: "text-bg-danger",
  };
  var TREND_CLASS = {
    yukselis: "text-success",
    dusus: "text-danger",
    stabil: "text-muted",
  };

  function formatValue(m) {
    if (!m || m.predicted == null) return "—";
    var unit = m.unit || "";
    if (unit === "%") return "%" + m.predicted;
    if (m.metric === "kategori_artisi") {
      var kat = m.kategori || m.en_yogun_kategori || "";
      return (kat ? kat + " · " : "") + "%" + m.predicted;
    }
    return m.predicted + (unit ? " " + unit : "");
  }

  function formatCI(m) {
    var ci = (m && m.confidence_interval) || {};
    if (ci.low == null || ci.high == null) return "—";
    var unit = (m && m.unit) || "";
    if (unit === "%") return "%" + ci.low + " – %" + ci.high;
    return ci.low + " – " + ci.high + (unit ? " " + unit : "");
  }

  function setActiveTab(horizon) {
    activeHorizon = String(horizon);
    if (!tabsEl) return;
    tabsEl.querySelectorAll("[data-horizon]").forEach(function (btn) {
      var on = btn.getAttribute("data-horizon") === activeHorizon;
      btn.classList.toggle("btn-success", on);
      btn.classList.toggle("btn-outline-secondary", !on);
    });
  }

  function renderMetricTable(primary) {
    var tbody = document.getElementById("predictionMetricsBody");
    var cards = document.getElementById("predictionMetricCards");
    if (!tbody) return;
    var block = ((primary || {}).forecasts || {})[activeHorizon] || {};
    tbody.innerHTML = "";
    if (cards) cards.innerHTML = "";

    METRIC_ORDER.forEach(function (key) {
      var m = block[key];
      if (!m) return;
      var tr = document.createElement("tr");
      tr.innerHTML =
        "<td class=\"fw-semibold\">" +
        (m.label || key) +
        "</td>" +
        "<td>" +
        formatValue(m) +
        "</td>" +
        "<td>%" +
        (m.confidence_pct != null ? m.confidence_pct : "—") +
        "</td>" +
        "<td class=\"small\">" +
        formatCI(m) +
        "</td>" +
        "<td class=\"" +
        (TREND_CLASS[m.trend] || "") +
        "\">" +
        (TREND_TR[m.trend] || m.trend || "—") +
        "</td>" +
        "<td><span class=\"badge " +
        (RISK_CLASS[m.risk] || "text-bg-secondary") +
        "\">" +
        (RISK_TR[m.risk] || m.risk || "—") +
        "</span></td>" +
        "<td class=\"small\">" +
        (m.ai_yorum || "—") +
        "</td>";
      tbody.appendChild(tr);

      if (cards) {
        var col = document.createElement("div");
        col.className = "col-12 col-sm-6 col-xl";
        col.innerHTML =
          '<div class="border rounded p-3 h-100">' +
          '<div class="small text-muted">' +
          (m.label || key) +
          "</div>" +
          '<div class="fw-semibold">' +
          formatValue(m) +
          "</div>" +
          '<div class="small mt-1">Güven %' +
          (m.confidence_pct != null ? m.confidence_pct : "—") +
          "</div>" +
          '<div class="small ' +
          (TREND_CLASS[m.trend] || "") +
          '">' +
          (TREND_TR[m.trend] || "—") +
          ' · <span class="badge ' +
          (RISK_CLASS[m.risk] || "text-bg-secondary") +
          '">' +
          (RISK_TR[m.risk] || "—") +
          "</span></div>" +
          '<div class="small text-muted mt-2">' +
          (m.ai_yorum || "") +
          "</div>" +
          "</div>";
        cards.appendChild(col);
      }
    });

    if (!tbody.children.length) {
      tbody.innerHTML = '<tr><td colspan="7" class="text-muted">Veri yok</td></tr>';
    }
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

  function chartColors() {
    return {
      atik: "#0f766e",
      co2: "#b45309",
      teslim: "#0369a1",
      katilim: "#4d7c0f",
      kategori: "#a16207",
    };
  }

  function renderCharts(primary) {
    if (typeof Chart === "undefined") return;
    var chart = primary.chart || {};
    var labels = chart.labels || [];
    var colors = chartColors();
    var horizonLabels =
      chart.horizon_labels || HORIZONS.map(function (h) {
        return HORIZON_LABELS[h];
      });

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
            borderColor: colors.atik,
            tension: 0.25,
            yAxisID: "y",
          },
          {
            label: "CO₂ kg",
            data: chart.co2_kg || [],
            borderColor: colors.co2,
            tension: 0.25,
            yAxisID: "y",
          },
          {
            label: "Teslim %",
            data: chart.teslim_orani || [],
            borderColor: colors.teslim,
            tension: 0.25,
            yAxisID: "y1",
          },
          {
            label: "Katılım %",
            data: chart.katilim || [],
            borderColor: colors.katilim,
            tension: 0.25,
            yAxisID: "y1",
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: true,
        interaction: { mode: "index", intersect: false },
        plugins: {
          title: {
            display: true,
            text: "Tarihsel seri (" + primary.lookback_months + " ay)",
          },
          legend: { position: "bottom" },
        },
        scales: {
          y: { beginAtZero: true, position: "left", title: { display: true, text: "kg" } },
          y1: {
            beginAtZero: true,
            position: "right",
            grid: { drawOnChartArea: false },
            max: 100,
            title: { display: true, text: "%" },
          },
        },
      },
    });

    forecastChart = new Chart(document.getElementById("predictionForecastChart"), {
      type: "bar",
      data: {
        labels: horizonLabels,
        datasets: [
          {
            label: "Atık kg",
            data: HORIZONS.map(function (h) {
              return (chart.forecast_atik || {})[h];
            }),
            backgroundColor: colors.atik,
          },
          {
            label: "CO₂ kg",
            data: HORIZONS.map(function (h) {
              return (chart.forecast_co2 || {})[h];
            }),
            backgroundColor: colors.co2,
          },
          {
            label: "Teslim %",
            data: HORIZONS.map(function (h) {
              return (chart.forecast_teslim || {})[h];
            }),
            backgroundColor: colors.teslim,
          },
          {
            label: "Katılım %",
            data: HORIZONS.map(function (h) {
              return (chart.forecast_katilim || {})[h];
            }),
            backgroundColor: colors.katilim,
          },
          {
            label: "Kategori artış %",
            data: HORIZONS.map(function (h) {
              return (chart.forecast_kategori || {})[h];
            }),
            backgroundColor: colors.kategori,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: true,
        plugins: {
          title: { display: true, text: "Ufuk bazlı tahmin" },
          legend: { position: "bottom" },
        },
        scales: { y: { beginAtZero: true } },
      },
    });
  }

  function applyPrimary(data, months) {
    currentPrimary =
      (data.lookbacks && data.lookbacks[String(months)]) || data.primary || data;
    renderMetricTable(currentPrimary);
    renderCharts(currentPrimary);
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

  if (tabsEl) {
    tabsEl.addEventListener("click", function (e) {
      var btn = e.target.closest("[data-horizon]");
      if (!btn) return;
      setActiveTab(btn.getAttribute("data-horizon"));
      if (currentPrimary) renderMetricTable(currentPrimary);
    });
  }

  if (lookbackEl) lookbackEl.addEventListener("change", load);
  setActiveTab(activeHorizon);
  load();
})();
