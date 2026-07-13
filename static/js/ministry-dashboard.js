(function () {
  var el = document.getElementById("ministry-dashboard-config");
  if (!el) return;

  var config;
  try {
    config = JSON.parse(el.textContent);
  } catch (e) {
    return;
  }

  if (typeof L !== "undefined") {
    var map = L.map("ministryIsiHaritasi").setView([39.0, 35.0], 6);
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: "© OpenStreetMap",
    }).addTo(map);

    var heat = config.heat || [];
    if (heat.length) {
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
      var color =
        c.intensity >= 0.7 ? "#059669" : c.intensity >= 0.4 ? "#f59e0b" : "#64748b";
      L.circleMarker([c.lat, c.lng], {
        radius: 8 + c.intensity * 10,
        color: color,
        fillColor: color,
        fillOpacity: 0.55,
        weight: 1,
      })
        .bindPopup(
          "<strong>" +
            c.il +
            "</strong><br>Yoğunluk: " +
            Math.round(c.intensity * 100) +
            "<br>Kullanıcı: " +
            c.kullanici
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
        plugins: { legend: { display: false } },
        scales: { x: { beginAtZero: true, max: 100 } },
      },
    });
  }

  buildBar("ministryTopChart", config.top || [], "#10b981");
  buildBar("ministryBottomChart", config.bottom || [], "#f59e0b");
})();
