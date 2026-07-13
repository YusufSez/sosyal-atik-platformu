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
    atik: { 0.2: "#3b82f6", 0.5: "#6366f1", 0.8: "#a855f7", 1: "#7c3aed" },
    kaynak: { 0.2: "#6ee7b7", 0.5: "#10b981", 0.8: "#059669", 1: "#047857" },
    teslim: { 0.2: "#fcd34d", 0.5: "#f59e0b", 0.8: "#ea580c", 1: "#dc2626" },
  };

  var noktalar = config.isi_noktalari || [];
  var map = L.map("belediyeIsiHaritasi").setView([39.0, 35.0], 6);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: "© OpenStreetMap",
  }).addTo(map);

  if (noktalar.length) {
    L.heatLayer(noktalar, {
      radius: 22,
      blur: 18,
      maxZoom: 12,
      gradient: gradients[yogunluk] || gradients.atik,
    }).addTo(map);
    var bounds = noktalar.map(function (p) {
      return [p[0], p[1]];
    });
    map.fitBounds(bounds, { padding: [40, 40], maxZoom: 10 });
  }
})();
