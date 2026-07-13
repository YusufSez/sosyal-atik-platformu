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
  var map = L.map("belediyeIsiHaritasi").setView(
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

  if (noktalar.length && L.heatLayer) {
    L.heatLayer(noktalar, {
      radius: 28,
      blur: 20,
      maxZoom: 15,
      minOpacity: 0.35,
      gradient: gradients[yogunluk] || gradients.atik,
    }).addTo(map);
    var bounds = noktalar.map(function (p) {
      return [p[0], p[1]];
    });
    map.fitBounds(bounds, { padding: [40, 40], maxZoom: 13 });
  }
  setTimeout(function () {
    map.invalidateSize();
  }, 120);
})();
