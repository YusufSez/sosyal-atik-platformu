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
  var lastReport = null;
  var activeHorizon = "7";

  var METRIC_ORDER = [
    "atik_miktari",
    "teslim_orani",
    "katilim",
    "co2",
    "kategori_artisi",
  ];
  var METRIC_SHORT = {
    atik_miktari: "Atık",
    teslim_orani: "Teslim",
    katilim: "Katılım",
    co2: "CO₂",
    kategori_artisi: "Kategori",
  };
  var METRIC_ICON = {
    atik_miktari: "bi-recycle",
    teslim_orani: "bi-box-seam",
    katilim: "bi-people",
    co2: "bi-cloud",
    kategori_artisi: "bi-tags",
  };
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
  var RISK_RANK = { dusuk: 1, orta: 2, yuksek: 3 };

  function escapeHtml(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function formatValue(m) {
    if (!m || m.predicted == null) return "—";
    var unit = m.unit || "";
    if (unit === "%") return "%" + m.predicted;
    if (m.metric === "kategori_artisi" || m.metric_key === "kategori_artisi") {
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

  function trendArrow(trend) {
    if (trend === "yukselis") {
      return '<span class="pred-trend up"><i class="bi bi-arrow-up-right"></i> Yükseliş</span>';
    }
    if (trend === "dusus") {
      return '<span class="pred-trend down"><i class="bi bi-arrow-down-right"></i> Düşüş</span>';
    }
    return '<span class="pred-trend flat"><i class="bi bi-arrow-right"></i> Stabil</span>';
  }

  function setActiveTab(horizon) {
    activeHorizon = String(horizon);
    if (!tabsEl) return;
    tabsEl.querySelectorAll("[data-horizon]").forEach(function (btn) {
      var on = btn.getAttribute("data-horizon") === activeHorizon;
      btn.classList.toggle("is-active", on);
      btn.setAttribute("aria-selected", on ? "true" : "false");
    });
    var badge = document.getElementById("predictionChartHorizonBadge");
    if (badge) badge.textContent = HORIZON_LABELS[activeHorizon] || activeHorizon;
  }

  function renderMetricTable(primary) {
    var tbody = document.getElementById("predictionMetricsBody");
    var cards = document.getElementById("predictionMetricCards");
    if (!cards && !tbody) return;

    var block = ((primary || {}).forecasts || {})[activeHorizon] || {};
    if (tbody) tbody.innerHTML = "";
    if (cards) cards.innerHTML = "";

    METRIC_ORDER.forEach(function (key) {
      var m = block[key];
      if (!m) return;
      m.metric_key = key;

      if (tbody) {
        var tr = document.createElement("tr");
        tr.innerHTML =
          "<td>" +
          escapeHtml(METRIC_SHORT[key] || m.label || key) +
          "</td><td>" +
          escapeHtml(formatValue(m)) +
          "</td><td>%" +
          (m.confidence_pct != null ? m.confidence_pct : "—") +
          "</td><td>" +
          escapeHtml(formatCI(m)) +
          "</td><td>" +
          escapeHtml(TREND_TR[m.trend] || m.trend || "—") +
          "</td><td>" +
          escapeHtml(RISK_TR[m.risk] || m.risk || "—") +
          "</td><td>" +
          escapeHtml(m.ai_yorum || "—") +
          "</td>";
        tbody.appendChild(tr);
      }

      if (cards) {
        var col = document.createElement("div");
        col.className = "col-6 col-md-4 col-xl";
        col.innerHTML =
          '<div class="pred-metric-card">' +
          '<div class="pred-metric-top">' +
          '<div class="pred-metric-label">' +
          escapeHtml(METRIC_SHORT[key] || m.label || key) +
          "</div>" +
          '<div class="pred-metric-icon"><i class="bi ' +
          (METRIC_ICON[key] || "bi-bar-chart") +
          '"></i></div>' +
          "</div>" +
          '<div class="pred-metric-value">' +
          escapeHtml(formatValue(m)) +
          "</div>" +
          '<div class="pred-metric-meta">' +
          trendArrow(m.trend) +
          '<span class="badge ' +
          (RISK_CLASS[m.risk] || "text-bg-secondary") +
          '">Risk: ' +
          escapeHtml(RISK_TR[m.risk] || m.risk || "—") +
          "</span>" +
          '<span class="pred-conf">Confidence %' +
          (m.confidence_pct != null ? m.confidence_pct : "—") +
          "</span>" +
          "</div>" +
          "</div>";
        cards.appendChild(col);
      }
    });

    if (cards && !cards.children.length) {
      cards.innerHTML =
        '<div class="col-12"><div class="pred-metric-card text-muted">Veri yok</div></div>';
    }
  }

  function buildAiRecommendation(worstRisk, trends) {
    if (worstRisk === "yuksek") {
      return "Yüksek riskli metrikler için kısa ufukta operasyonel müdahale planlayın; haftalık izleme brifingi oluşturun.";
    }
    if (trends.indexOf("dusus") >= 0 && (worstRisk === "orta" || worstRisk === "yuksek")) {
      return "Düşüş eğilimini tersine çevirmek için teslim ve katılım kampanyalarını güçlendirin.";
    }
    if (trends.indexOf("yukselis") >= 0) {
      return "Olumlu trendi koruyun; iyi uygulamaları benzer bölgelerle paylaşın ve kapasiteyi ölçekleyin.";
    }
    return "Mevcut görünümü koruyun; bir sonraki ufukta sapma olursa güven aralığı alt sınırını erken uyarı olarak kullanın.";
  }

  function renderAiCards(primary, data) {
    var block = ((primary || {}).forecasts || {})[activeHorizon] || {};
    var durumEl = document.getElementById("predAiDurum");
    var riskEl = document.getElementById("predAiRisk");
    var changeEl = document.getElementById("predAiChange");
    var oneriEl = document.getElementById("predAiOneri");
    var badge = document.getElementById("predictionNarrativeSource");
    var ul = document.getElementById("predictionNarratives");

    if (badge) badge.textContent = (data && data.narrative_source) || "rules";

    var parts = [];
    var changes = [];
    var trends = [];
    var worstRisk = "dusuk";
    var worstLabel = "";

    METRIC_ORDER.forEach(function (key) {
      var m = block[key];
      if (!m) return;
      parts.push(
        (METRIC_SHORT[key] || key) +
          ": " +
          formatValue(m) +
          " (" +
          (TREND_TR[m.trend] || "—") +
          ")"
      );
      if (m.change_pct != null) {
        var sign = m.change_pct >= 0 ? "+" : "";
        changes.push(
          (METRIC_SHORT[key] || key) + " " + sign + m.change_pct + "%"
        );
      }
      if (m.trend) trends.push(m.trend);
      if ((RISK_RANK[m.risk] || 0) >= (RISK_RANK[worstRisk] || 0)) {
        worstRisk = m.risk || worstRisk;
        worstLabel = METRIC_SHORT[key] || key;
      }
    });

    var narratives = (data && data.narratives) || [];
    if (ul) {
      ul.innerHTML = "";
      if (!narratives.length) {
        ul.innerHTML = '<li class="text-muted">Yorum yok</li>';
      } else {
        narratives.forEach(function (t) {
          var li = document.createElement("li");
          li.textContent = t;
          ul.appendChild(li);
        });
      }
    }

    var horizonLabel = HORIZON_LABELS[activeHorizon] || activeHorizon;
    var durumText =
      (narratives[0] && String(narratives[0])) ||
      (parts.length
        ? horizonLabel + " ufku — " + parts.slice(0, 3).join(" · ")
        : "Yorum henüz oluşmadı.");

    if (durumEl) durumEl.textContent = durumText;
    if (riskEl) {
      riskEl.innerHTML =
        '<span class="badge ' +
        (RISK_CLASS[worstRisk] || "text-bg-secondary") +
        ' me-1">' +
        escapeHtml(RISK_TR[worstRisk] || worstRisk || "—") +
        "</span> " +
        (worstLabel
          ? escapeHtml(worstLabel) + " metriklerinde öncelikli izleme."
          : "Risk profili hesaplanıyor.");
    }
    if (changeEl) {
      changeEl.textContent = changes.length
        ? changes.join(" · ")
        : "Baz aya göre değişim verisi sınırlı.";
    }
    if (oneriEl) {
      oneriEl.textContent =
        (narratives[1] && String(narratives[1])) ||
        buildAiRecommendation(worstRisk, trends);
    }
  }

  function renderNarratives(data) {
    renderAiCards(currentPrimary, data);
  }

  function buildConfidenceBand(primary) {
    var chart = (primary && primary.chart) || {};
    var histLabels = chart.labels || [];
    var histAtik = chart.atik_kg || [];
    var horizonLabels = HORIZONS.map(function (h) {
      return HORIZON_LABELS[h];
    });
    var labels = histLabels.concat(horizonLabels);
    var histLen = histLabels.length;
    var lastHist =
      histAtik.length > 0 ? histAtik[histAtik.length - 1] : null;

    var historySeries = histAtik.concat(HORIZONS.map(function () {
      return null;
    }));

    var forecastSeries = [];
    var upperSeries = [];
    var lowerSeries = [];
    var i;
    for (i = 0; i < histLen - 1; i++) {
      forecastSeries.push(null);
      upperSeries.push(null);
      lowerSeries.push(null);
    }
    if (histLen > 0) {
      forecastSeries.push(lastHist);
      upperSeries.push(lastHist);
      lowerSeries.push(lastHist);
    }

    HORIZONS.forEach(function (h) {
      var m = (((primary.forecasts || {})[h] || {}).atik_miktari) || {};
      var pred = m.predicted;
      var ci = m.confidence_interval || {};
      forecastSeries.push(pred != null ? pred : null);
      upperSeries.push(ci.high != null ? ci.high : pred);
      lowerSeries.push(ci.low != null ? ci.low : pred);
    });

    return {
      labels: labels,
      history: historySeries,
      forecast: forecastSeries,
      upper: upperSeries,
      lower: lowerSeries,
      histLen: histLen,
    };
  }

  function renderCharts(primary) {
    if (typeof Chart === "undefined") return;
    var band = buildConfidenceBand(primary);
    var accent = "#0f766e";
    var forecastColor = "#0369a1";

    if (historyChart) historyChart.destroy();
    if (forecastChart) forecastChart.destroy();

    var canvas = document.getElementById("predictionHistoryChart");
    if (!canvas) return;

    historyChart = new Chart(canvas, {
      type: "line",
      data: {
        labels: band.labels,
        datasets: [
          {
            label: "Confidence üst",
            data: band.upper,
            borderColor: "rgba(15, 118, 110, 0.15)",
            backgroundColor: "rgba(15, 118, 110, 0.14)",
            pointRadius: 0,
            borderWidth: 0,
            fill: "+1",
            tension: 0.25,
            order: 3,
          },
          {
            label: "Confidence alt",
            data: band.lower,
            borderColor: "rgba(15, 118, 110, 0.15)",
            backgroundColor: "rgba(15, 118, 110, 0.0)",
            pointRadius: 0,
            borderWidth: 0,
            fill: false,
            tension: 0.25,
            order: 2,
          },
          {
            label: "Geçmiş (Atık kg)",
            data: band.history,
            borderColor: accent,
            backgroundColor: accent,
            pointRadius: 3,
            borderWidth: 2.5,
            tension: 0.25,
            spanGaps: false,
            order: 1,
          },
          {
            label: "Tahmin (Atık kg)",
            data: band.forecast,
            borderColor: forecastColor,
            backgroundColor: forecastColor,
            borderDash: [6, 4],
            pointRadius: 3,
            borderWidth: 2,
            tension: 0.25,
            spanGaps: false,
            order: 0,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: "index", intersect: false },
        plugins: {
          legend: {
            position: "bottom",
            labels: {
              filter: function (item) {
                return (
                  item.text === "Geçmiş (Atık kg)" ||
                  item.text === "Tahmin (Atık kg)"
                );
              },
            },
          },
          title: {
            display: true,
            text:
              "Geçmiş + ufuk tahmini (" +
              ((primary && primary.lookback_months) || "—") +
              " ay) · Confidence band",
          },
          tooltip: {
            callbacks: {
              afterBody: function (items) {
                var idx = items[0] && items[0].dataIndex;
                if (idx == null || idx < band.histLen) return "";
                var h = HORIZONS[idx - band.histLen];
                if (!h) return "";
                var m =
                  (((primary.forecasts || {})[h] || {}).atik_miktari) || {};
                return (
                  "Güven %" +
                  (m.confidence_pct != null ? m.confidence_pct : "—") +
                  " · Risk " +
                  (RISK_TR[m.risk] || m.risk || "—")
                );
              },
            },
          },
        },
        scales: {
          y: {
            beginAtZero: true,
            title: { display: true, text: "kg" },
          },
          x: {
            ticks: {
              maxRotation: 45,
              minRotation: 0,
              autoSkip: true,
              maxTicksLimit: 14,
            },
          },
        },
      },
    });

    // Uyum için gizli forecast chart (eski yapı)
    var fc = document.getElementById("predictionForecastChart");
    if (fc) {
      forecastChart = new Chart(fc, {
        type: "bar",
        data: { labels: [], datasets: [] },
        options: { responsive: false, plugins: { legend: { display: false } } },
      });
    }
  }

  function refreshHorizonViews() {
    if (!currentPrimary) return;
    renderMetricTable(currentPrimary);
    renderAiCards(currentPrimary, lastReport || {});
    renderCharts(currentPrimary);
  }

  function applyPrimary(data, months) {
    lastReport = data;
    currentPrimary =
      (data.lookbacks && data.lookbacks[String(months)]) || data.primary || data;
    renderMetricTable(currentPrimary);
    renderCharts(currentPrimary);
    renderAiCards(currentPrimary, data);
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
        var durumEl = document.getElementById("predAiDurum");
        if (durumEl) durumEl.textContent = "Tahmin yüklenemedi";
        var ul = document.getElementById("predictionNarratives");
        if (ul) ul.innerHTML = '<li class="text-danger">Tahmin yüklenemedi</li>';
      });
  }

  if (tabsEl) {
    tabsEl.addEventListener("click", function (e) {
      var btn = e.target.closest("[data-horizon]");
      if (!btn) return;
      setActiveTab(btn.getAttribute("data-horizon"));
      refreshHorizonViews();
    });
  }

  if (lookbackEl) lookbackEl.addEventListener("change", load);
  setActiveTab(activeHorizon);
  load();
})();
