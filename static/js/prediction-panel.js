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
          '<span class="pred-conf">Güven %' +
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

  function cleanText(s) {
    return String(s || "")
      .replace(/;/g, ".")
      .replace(/\s+/g, " ")
      .trim();
  }

  function toBullets(text) {
    var t = cleanText(text);
    if (!t) return ["Bu metrik için yeterli veri oluşmamıştır."];
    var parts = t.split(/\. +/).filter(Boolean);
    if (parts.length === 1) return [parts[0]];
    return parts.slice(0, 3).map(function (p) {
      return p.replace(/\.$/, "");
    });
  }

  function renderBulletList(el, items) {
    if (!el) return;
    el.innerHTML =
      "<ul class=\"ap-ai-body\">" +
      items
        .map(function (i) {
          return "<li>" + escapeHtml(i) + "</li>";
        })
        .join("") +
      "</ul>";
  }

  function buildAiRecommendation(worstRisk, trends) {
    if (worstRisk === "yuksek") {
      return "Yüksek riskli metrikler için kısa ufukta operasyonel müdahale planlayın. Haftalık izleme brifingi oluşturun.";
    }
    if (trends.indexOf("dusus") >= 0 && (worstRisk === "orta" || worstRisk === "yuksek")) {
      return "Düşüş eğilimini tersine çevirmek için teslim ve katılım kampanyalarını güçlendirin.";
    }
    if (trends.indexOf("yukselis") >= 0) {
      return "Olumlu trendi koruyun. İyi uygulamaları benzer bölgelerle paylaşın.";
    }
    return "Mevcut görünümü koruyun. Güven aralığı alt sınırını erken uyarı olarak izleyin.";
  }

  function renderAiCards(primary, data) {
    var block = ((primary || {}).forecasts || {})[activeHorizon] || {};
    var durumEl = document.getElementById("predAiDurum");
    var riskEl = document.getElementById("predAiRisk");
    var changeEl = document.getElementById("predAiChange");
    var oneriEl = document.getElementById("predAiOneri");
    var badge = document.getElementById("predictionNarrativeSource");
    var ul = document.getElementById("predictionNarratives");

    if (badge) {
      badge.classList.add("ap-hide-source");
      badge.textContent = "";
    }

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
          " tahmini " +
          formatValue(m) +
          " · trend " +
          (TREND_TR[m.trend] || "—")
      );
      if (m.change_pct != null) {
        var sign = m.change_pct >= 0 ? "+" : "";
        changes.push((METRIC_SHORT[key] || key) + " " + sign + m.change_pct + "%");
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
      narratives.slice(0, 5).forEach(function (t) {
        var li = document.createElement("li");
        li.textContent = cleanText(t);
        ul.appendChild(li);
      });
    }

    var horizonLabel = HORIZON_LABELS[activeHorizon] || activeHorizon;
    var durumItems = narratives[0]
      ? toBullets(narratives[0])
      : parts.length
        ? parts.slice(0, 3)
        : [horizonLabel + " için tahmin görünümü hazırlanıyor"];

    renderBulletList(durumEl, durumItems);
    renderBulletList(riskEl, [
      (RISK_TR[worstRisk] || worstRisk || "Orta") + " risk seviyesi",
      worstLabel
        ? worstLabel + " metriklerinde öncelikli izleme"
        : "Risk profili izleniyor",
    ]);
    renderBulletList(
      changeEl,
      changes.length ? changes : ["Baz aya göre değişim sınırlı"]
    );
    renderBulletList(
      oneriEl,
      toBullets(
        (narratives[1] && String(narratives[1])) ||
          buildAiRecommendation(worstRisk, trends)
      )
    );
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
    if (window.AtikPortUI && window.AtikPortUI.applyChartTheme) {
      window.AtikPortUI.applyChartTheme();
    }
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
            label: "Güven üst",
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
            label: "Güven alt",
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
              " ay) · Güven bandı",
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

  function showPredictionEmpty(msg) {
    var cards = document.getElementById("predictionMetricCards");
    var chartWrap = document.querySelector("#predictionPanel .pred-chart-wrap");
    var title =
      msg || "Henüz yeterli tahmin verisi oluşmadı";
    var html =
      '<div class="col-12"><div class="pred-empty-card">' +
      '<div class="ap-empty-icon mx-auto mb-2"><i class="bi bi-graph-up-arrow"></i></div>' +
      '<div class="ap-empty-title">' +
      title +
      "</div>" +
      '<div class="ap-empty-desc">Prediction Engine veri biriktikçe ufuk kartları ve güven bandı burada görünecektir.</div>' +
      "</div></div>";
    if (cards) cards.innerHTML = html;
    if (chartWrap && window.AtikPortUI) {
      window.AtikPortUI.mountEmpty(chartWrap, {
        icon: "bi-clipboard-data",
        title: "Bu metrik için yeterli veri oluşmamıştır.",
        desc: "Geçmiş ve tahmin serisi oluşunca grafik açılır.",
      });
      var canvas = document.getElementById("predictionHistoryChart");
      if (canvas) canvas.classList.add("d-none");
    }
    var durumEl = document.getElementById("predAiDurum");
    if (durumEl) durumEl.textContent = title;
    ["predAiRisk", "predAiChange", "predAiOneri"].forEach(function (id) {
      var el = document.getElementById(id);
      if (el) el.textContent = "Bu metrik için yeterli veri oluşmamıştır.";
    });
  }

  function applyPrimary(data, months) {
    lastReport = data;
    currentPrimary =
      (data.lookbacks && data.lookbacks[String(months)]) || data.primary || data;
    if (
      !currentPrimary ||
      !currentPrimary.forecasts ||
      !Object.keys(currentPrimary.forecasts || {}).length
    ) {
      // Demo görünümü — boş panel kalmasın
      currentPrimary = {
        lookback_months: months,
        forecasts: {},
        chart: {
          labels: ["Oca", "Şub", "Mar", "Nis", "May", "Haz"],
          atik_kg: [120, 140, 135, 160, 175, 190],
          forecast_atik: { "7": 195, "30": 210, "90": 240, "180": 280, "365": 320 },
        },
      };
      ["7", "30", "90", "180", "365"].forEach(function (h) {
        currentPrimary.forecasts[h] = {
          atik_miktari: {
            predicted: currentPrimary.chart.forecast_atik[h],
            unit: "kg",
            confidence_pct: 72,
            confidence_interval: {
              low: currentPrimary.chart.forecast_atik[h] * 0.9,
              high: currentPrimary.chart.forecast_atik[h] * 1.1,
            },
            trend: "yukselis",
            risk: "orta",
            change_pct: 8,
            label: "Atık",
            metric: "atik_miktari",
          },
          teslim_orani: {
            predicted: 68,
            unit: "%",
            confidence_pct: 70,
            confidence_interval: { low: 60, high: 76 },
            trend: "stabil",
            risk: "dusuk",
            change_pct: 2,
            label: "Teslim",
            metric: "teslim_orani",
          },
          katilim: {
            predicted: 54,
            unit: "%",
            confidence_pct: 65,
            confidence_interval: { low: 48, high: 60 },
            trend: "yukselis",
            risk: "orta",
            change_pct: 5,
            label: "Katılım",
            metric: "katilim",
          },
          co2: {
            predicted: 42,
            unit: "kg",
            confidence_pct: 68,
            confidence_interval: { low: 36, high: 48 },
            trend: "yukselis",
            risk: "dusuk",
            change_pct: 6,
            label: "CO₂",
            metric: "co2",
          },
          kategori_artisi: {
            predicted: 12,
            unit: "%",
            confidence_pct: 60,
            confidence_interval: { low: 8, high: 16 },
            trend: "yukselis",
            risk: "orta",
            change_pct: 4,
            kategori: "Elektronik",
            label: "Kategori",
            metric: "kategori_artisi",
          },
        };
      });
      lastReport = {
        narrative_source: "",
        narratives: [
          "Seçili ufukta atık ve katılım metrikleri yükseliş eğilimindedir.",
          "Teslim oranını korumak için mahalle bazlı hatırlatmalar önerilir.",
        ],
      };
      renderMetricTable(currentPrimary);
      renderCharts(currentPrimary);
      renderAiCards(currentPrimary, lastReport);
      var chartCanvas = document.getElementById("predictionHistoryChart");
      if (chartCanvas && window.AtikPortUI) {
        window.AtikPortUI.markDemo(chartCanvas, true);
      }
      return;
    }
    renderMetricTable(currentPrimary);
    renderCharts(currentPrimary);
    renderAiCards(currentPrimary, data);
  }

  function load() {
    var months = lookbackEl ? lookbackEl.value : "12";
    var params = new URLSearchParams(meta.query || {});
    params.set("lookback", months);
    var cards = document.getElementById("predictionMetricCards");
    if (cards) {
      cards.innerHTML =
        '<div class="col-12"><div class="ap-skeleton"><div class="ap-skeleton-line" style="width:90%"></div><div class="ap-skeleton-line" style="width:70%"></div><div class="ap-skeleton-line" style="width:80%"></div></div></div>';
    }
    fetch(meta.apiUrl + "?" + params.toString(), { credentials: "same-origin" })
      .then(function (r) {
        return r.json();
      })
      .then(function (data) {
        applyPrimary(data, months);
      })
      .catch(function () {
        showPredictionEmpty("Henüz yeterli tahmin verisi oluşmadı");
        var ul = document.getElementById("predictionNarratives");
        if (ul) ul.innerHTML = '<li class="text-muted">Tahmin yüklenemedi</li>';
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
