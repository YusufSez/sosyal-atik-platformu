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
    if (renk === "yesil") return "#059669";
    if (renk === "sari") return "#f59e0b";
    if (renk === "kirmizi") return "#dc2626";
    return "#64748b";
  }

  if (typeof L !== "undefined") {
    var map = L.map("ministryIsiHaritasi").setView([39.0, 35.0], 6);
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: "© OpenStreetMap",
    }).addTo(map);

    var heat = config.heat || [];
    if (heat.length && typeof L.heatLayer === "function") {
      L.heatLayer(heat, {
        radius: 28,
        blur: 22,
        maxZoom: 10,
        gradient: {
          0.2: "#93c5fd",
          0.4: "#34d399",
          0.6: "#fbbf24",
          0.8: "#f97316",
          1: "#dc2626",
        },
      }).addTo(map);
    }

    (config.il_merkezleri || []).forEach(function (c) {
      var color = renkHex(c.renk) || (
        c.intensity >= 0.7 ? "#059669" : c.intensity >= 0.4 ? "#f59e0b" : "#64748b"
      );
      var puan = c.puan != null ? c.puan : Math.round((c.intensity || 0) * 100);
      L.circleMarker([c.lat, c.lng], {
        radius: 8 + Math.min(1, (c.intensity || puan / 100)) * 10,
        color: color,
        fillColor: color,
        fillOpacity: 0.6,
        weight: 1,
      })
        .bindPopup(
          "<strong>" +
            c.il +
            "</strong><br>Performans: " +
            (c.performans || "—") +
            " (" +
            puan +
            ")<br>Kullanıcı: " +
            (c.kullanici || "—")
        )
        .addTo(map);
    });
  }

  function buildBar(canvasId, rows, color) {
    var canvas = document.getElementById(canvasId);
    if (!canvas || typeof Chart === "undefined") return;
    var labels = (rows || []).map(function (r) {
      return r.il;
    });
    var values = (rows || []).map(function (r) {
      return r.puan;
    });
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
