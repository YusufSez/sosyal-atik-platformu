(function () {
  var configEl = document.getElementById("kurum-analiz-config");
  if (!configEl || typeof L === "undefined") return;

  var config;
  try {
    config = JSON.parse(configEl.textContent);
  } catch (e) {
    console.error("Harita yapılandırması okunamadı", e);
    return;
  }

  var noktalar = config.isi_noktalari || [];
  var map = L.map("kurumIsiHaritasi").setView([39.0, 35.0], 6);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: "© OpenStreetMap",
  }).addTo(map);

  if (noktalar.length) {
    L.heatLayer(noktalar, {
      radius: 22,
      blur: 18,
      maxZoom: 12,
      gradient: { 0.2: "#3b82f6", 0.5: "#10b981", 0.8: "#f59e0b", 1: "#ef4444" },
    }).addTo(map);
    var bounds = noktalar.map(function (p) {
      return [p[0], p[1]];
    });
    map.fitBounds(bounds, { padding: [40, 40], maxZoom: 10 });
  }
})();
