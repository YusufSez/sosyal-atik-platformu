(function () {
  var el = document.getElementById("marketplace-map-config");
  if (!el || typeof L === "undefined") return;
  var config;
  try {
    config = JSON.parse(el.textContent);
  } catch (e) {
    return;
  }
  var points = config.points || [];
  var map = L.map("marketplaceMap").setView([39.0, 35.0], 6);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: "© OpenStreetMap",
  }).addTo(map);

  if (!points.length) return;
  var bounds = [];
  points.forEach(function (p) {
    var m = L.marker([p.lat, p.lng]).addTo(map);
    m.bindPopup("<strong>" + p.baslik + "</strong><br>" + (p.kategori || "") + " · " + p.durum);
    bounds.push([p.lat, p.lng]);
  });
  map.fitBounds(bounds, { padding: [40, 40], maxZoom: 12 });
})();
