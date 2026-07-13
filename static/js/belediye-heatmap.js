(function () {
  var configEl = document.getElementById("belediye-heatmap-config");
  if (!configEl || typeof L === "undefined") return;

  var config;
  try {
    config = JSON.parse(configEl.textContent);
  } catch (e) {
    console.error("Belediye harita yapılandırması okunamadı", e);
    return;
  }

  var yogunluk = config.yogunluk || "atik";
  var gradients = {
    atik: {
      0.2: "#bbf7d0",
      0.45: "#86efac",
      0.65: "#22c55e",
      0.85: "#16a34a",
      1: "#14532d",
    },
    kaynak: { 0.2: "#6ee7b7", 0.5: "#10b981", 0.8: "#059669", 1: "#047857" },
    teslim: { 0.2: "#fcd34d", 0.5: "#f59e0b", 0.8: "#ea580c", 1: "#dc2626" },
  };

  var noktalar = config.isi_noktalari || [];
  var center = config.mapCenter || {};
  var mapEl = document.getElementById("belediyeIsiHaritasi");
  if (!mapEl) return;

  var map = L.map(mapEl, { preferCanvas: true }).setView(
    [center.lat || 39.0, center.lng || 35.0],
    center.zoom || (noktalar.length ? 11 : 6)
  );
  var UI = window.AtikPortUI;
  L.tileLayer(
    (UI && UI.leafletTileUrl && UI.leafletTileUrl()) ||
      "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
    {
      attribution:
        (UI && UI.leafletAttribution && UI.leafletAttribution()) ||
        "© OpenStreetMap",
    }
  ).addTo(map);

  function containerReady(el) {
    if (!el) return false;
    var rect = el.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0;
  }

  function addHeatOrFallback(pts) {
    if (!pts.length) return;
    try {
      if (typeof L.heatLayer === "function") {
        L.heatLayer(pts, {
          radius: 28,
          blur: 20,
          maxZoom: 15,
          minOpacity: 0.35,
          gradient: gradients[yogunluk] || gradients.atik,
        }).addTo(map);
        map.fitBounds(
          pts.map(function (p) {
            return [p[0], p[1]];
          }),
          { padding: [40, 40], maxZoom: 13 }
        );
        return;
      }
    } catch (e) {
      /* heat başarısız */
    }
    pts.forEach(function (p) {
      L.circleMarker([p[0], p[1]], {
        radius: 6 + Math.min(10, (p[2] || 0.5) * 10),
        color: "#0f766e",
        fillColor: "#14b8a6",
        fillOpacity: 0.55,
        weight: 1,
      }).addTo(map);
    });
    map.fitBounds(
      pts.map(function (p) {
        return [p[0], p[1]];
      }),
      { padding: [40, 40], maxZoom: 13 }
    );
  }

  function afterReady(tries) {
    tries = tries == null ? 40 : tries;
    map.invalidateSize();
    if (!containerReady(mapEl)) {
      if (tries <= 0) return;
      requestAnimationFrame(function () {
        afterReady(tries - 1);
      });
      return;
    }
    addHeatOrFallback(noktalar);
    map.invalidateSize();
  }

  map.whenReady(function () {
    requestAnimationFrame(function () {
      requestAnimationFrame(afterReady);
    });
  });
})();
