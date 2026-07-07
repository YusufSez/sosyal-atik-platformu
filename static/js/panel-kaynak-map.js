(function () {
  function initMap() {
    var configEl = document.getElementById("kaynak-harita-config");
    if (!configEl || typeof L === "undefined") return;

    var config;
    try {
      config = JSON.parse(configEl.textContent);
    } catch (e) {
      console.error("Harita yapılandırması okunamadı", e);
      return;
    }

    var haritaNoktalari = config.harita_noktalari || [];
    var detayPrefix = config.detay_prefix || "/kaynak/";
    var mapEl = document.getElementById("map");
    if (!mapEl) return;

    function popupIcerik(nokta) {
      var html = "";
      nokta.ilanlar.forEach(function (i) {
        html +=
          '<div class="mb-1"><b>' +
          i.baslik +
          '</b><br><a href="' +
          detayPrefix +
          i.id +
          '">İncele</a></div>';
      });
      return html;
    }

    function markerKonumlari(noktalar) {
      var sonuc = [];
      noktalar.forEach(function (nokta) {
        if (nokta.ilanlar.length === 1) {
          sonuc.push({ lat: nokta.lat, lng: nokta.lng, nokta: nokta });
          return;
        }
        var adim = (2 * Math.PI) / nokta.ilanlar.length;
        var yaricap = 0.0015 * Math.min(nokta.ilanlar.length, 10);
        nokta.ilanlar.forEach(function (_, idx) {
          sonuc.push({
            lat: nokta.lat + yaricap * Math.cos(idx * adim),
            lng: nokta.lng + yaricap * Math.sin(idx * adim),
            nokta: nokta,
          });
        });
      });
      return sonuc;
    }

    var map = L.map(mapEl).setView([41.015, 28.979], 11);
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: "© OpenStreetMap",
    }).addTo(map);

    var bounds = [];
    var mapLocate = window.MapLocate ? MapLocate.init(map) : null;

    markerKonumlari(haritaNoktalari).forEach(function (m) {
      L.circleMarker([m.lat, m.lng], {
        radius: 10,
        color: "#0a58ca",
        fillColor: "#0d6efd",
        fillOpacity: 0.9,
        weight: 2,
      })
        .addTo(map)
        .bindPopup(popupIcerik(m.nokta));
      bounds.push([m.lat, m.lng]);
    });

    if (bounds.length > 0) {
      map.fitBounds(bounds, { padding: [30, 30], maxZoom: 14 });
    }

    if (mapLocate) {
      mapLocate.acquireLocation({ fly: false });
    }

    setTimeout(function () {
      map.invalidateSize();
      if (bounds.length > 0) {
        map.fitBounds(bounds, { padding: [30, 30], maxZoom: 14 });
      }
    }, 100);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initMap);
  } else {
    initMap();
  }
})();
