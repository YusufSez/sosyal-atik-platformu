(function () {
  var el = document.getElementById("ministry-dashboard-config");
  if (!el) return;

  var config;
  try {
    config = JSON.parse(el.textContent);
  } catch (e) {
    return;
  }

  function renkHex(renk) {
    if (renk === "yesil") return "#16a34a";
    if (renk === "sari") return "#f59e0b";
    if (renk === "kirmizi") return "#dc2626";
    return "#94a3b8";
  }

  if (typeof L !== "undefined") {
    var UI = window.AtikPortUI;
    var map = L.map("ministryIsiHaritasi").setView([39.0, 35.0], 6);
    L.tileLayer(
      (UI && UI.leafletTileUrl && UI.leafletTileUrl()) ||
        "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
      {
        attribution:
          (UI && UI.leafletAttribution && UI.leafletAttribution()) ||
          "© OpenStreetMap",
      }
    ).addTo(map);

    var heat = config.heat || [];
    if (heat.length && typeof L.heatLayer === "function") {
      L.heatLayer(heat, {
        radius: 28,
        blur: 22,
        maxZoom: 10,
        gradient: {
          0.2: "#bbf7d0",
          0.45: "#86efac",
          0.65: "#fbbf24",
          0.85: "#f97316",
          1: "#dc2626",
        },
      }).addTo(map);
    }

    var byIl = {};
    (config.il_merkezleri || []).forEach(function (c) {
      if (c && c.il) byIl[c.il] = c;
    });

    var allProvinces = window.ATIKPORT_IL_MERKEZLERI || [];
    allProvinces.forEach(function (base) {
      var c = byIl[base.il] || {};
      var hasData = !!(byIl[base.il] && (c.puan != null || c.intensity != null || c.renk));
      var color = hasData ? renkHex(c.renk) : "#94a3b8";
      if (hasData && !c.renk) {
        color =
          (c.intensity || 0) >= 0.7
            ? "#16a34a"
            : (c.intensity || 0) >= 0.4
              ? "#f59e0b"
              : "#dc2626";
      }
      var puan = c.puan != null ? c.puan : hasData ? Math.round((c.intensity || 0) * 100) : null;
      var lat = c.lat != null ? c.lat : base.lat;
      var lng = c.lng != null ? c.lng : base.lng;
      L.circleMarker([lat, lng], {
        radius: hasData ? 7 + Math.min(1, (c.intensity || (puan || 0) / 100)) * 8 : 5,
        color: color,
        fillColor: color,
        fillOpacity: hasData ? 0.7 : 0.35,
        weight: hasData ? 1.5 : 1,
      })
        .bindPopup(
          "<strong>" +
            base.il +
            "</strong><br>" +
            (hasData
              ? "Performans: " +
                (c.performans || "—") +
                (puan != null ? " (" + puan + ")" : "") +
                "<br>Kullanıcı: " +
                (c.kullanici || "—")
              : "Bu il için henüz yeterli veri oluşmamıştır.")
        )
        .addTo(map);
    });
  }

  function buildBar(canvasId, rows, color) {
    var canvas = document.getElementById(canvasId);
    if (!canvas || typeof Chart === "undefined") return;
    var UI = window.AtikPortUI || null;
    if (UI && UI.applyChartTheme) UI.applyChartTheme();
    var labels = (rows || []).map(function (r) {
      return r.il;
    });
    var values = (rows || []).map(function (r) {
      return r.puan;
    });
    var demo = !labels.length;
    if (demo) {
      labels = ((UI && UI.DEMO && UI.DEMO.bars && UI.DEMO.bars.labels) || []).slice();
      values = ((UI && UI.DEMO && UI.DEMO.bars && UI.DEMO.bars.values) || []).slice();
      if (!labels.length) {
        if (UI) UI.markDemo(canvas, true);
        return;
      }
      if (UI) UI.markDemo(canvas, true);
    } else if (config.demoSource && UI) {
      UI.markDemo(canvas, true);
    }
    new Chart(canvas, {
      type: "bar",
      data: {
        labels: labels,
        datasets: [
          {
            label: "Puan",
            data: values,
            backgroundColor: color,
            borderRadius: 6,
          },
        ],
      },
      options: {
        indexAxis: "y",
        responsive: true,
        maintainAspectRatio: true,
        plugins: { legend: { display: false } },
        scales: { x: { beginAtZero: true, max: 100 } },
      },
    });
  }

  buildBar("ministryTopChart", config.top || [], "#10b981");
  buildBar("ministryBottomChart", config.bottom || [], "#f59e0b");
})();
