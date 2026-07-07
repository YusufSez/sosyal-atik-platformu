(function () {
  function initMap() {
    var configEl = document.getElementById("atik-harita-config");
    if (!configEl || typeof L === "undefined") return;

    var config;
    try {
      config = JSON.parse(configEl.textContent);
    } catch (e) {
      console.error("Harita yapılandırması okunamadı", e);
      return;
    }

    var haritaNoktalari = config.harita_noktalari || [];
    var detayPrefix = config.detay_prefix || "/atik/";
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

    var ilanSinirlar = [];
    var ibbKatmani = L.layerGroup().addTo(map);
    var mapLocate = window.MapLocate ? MapLocate.init(map, { popupText: "📍 Sen buradasın" }) : null;

    markerKonumlari(haritaNoktalari).forEach(function (m) {
      L.circleMarker([m.lat, m.lng], {
        radius: 10,
        color: "#146c43",
        fillColor: "#198754",
        fillOpacity: 0.9,
        weight: 2,
      })
        .addTo(map)
        .bindPopup(
          '<span class="badge bg-success">Kullanıcı İlanı</span><br>' + popupIcerik(m.nokta)
        );
      ilanSinirlar.push([m.lat, m.lng]);
    });

    function ilanlaraOrtala(ibbSinirlar) {
      if (ilanSinirlar.length === 1) {
        map.setView(ilanSinirlar[0], 14);
        return;
      }
      if (ilanSinirlar.length > 1) {
        map.fitBounds(ilanSinirlar, { padding: [40, 40], maxZoom: 14 });
        return;
      }
      if (ibbSinirlar && ibbSinirlar.length) {
        map.fitBounds(ibbSinirlar, { padding: [40, 40], maxZoom: 12 });
      }
    }

    function mesafeKm(lat1, lng1, lat2, lng2) {
      return (
        Math.round(
          Math.sqrt(Math.pow(lat2 - lat1, 2) + Math.pow(lng2 - lng1, 2)) * 111 * 10
        ) / 10
      );
    }

    function merkezleriEkle(merkezler, userLat, userLng) {
      ibbKatmani.clearLayers();
      var ibbSinirlar = [];
      if (userLat !== null && userLng !== null) {
        merkezler.forEach(function (m) {
          m.mesafe = mesafeKm(userLat, userLng, m.lat, m.lng);
        });
        merkezler.sort(function (a, b) {
          return a.mesafe - b.mesafe;
        });
      }
      merkezler.forEach(function (m) {
        if (typeof m.lat !== "number" || typeof m.lng !== "number") return;
        ibbSinirlar.push([m.lat, m.lng]);
        L.circleMarker([m.lat, m.lng], {
          radius: 7,
          color: "#dc3545",
          fillColor: "#ff4444",
          fillOpacity: 0.8,
          weight: 2,
        })
          .addTo(ibbKatmani)
          .bindPopup(
            "🔴 <b>İBB Atık Merkezi</b><br><b>" +
              m.ad +
              "</b><br>" +
              (m.adres || "") +
              (m.mesafe !== undefined ? "<br><small>~" + m.mesafe + " km</small>" : "")
          );
      });
      return ibbSinirlar;
    }

    function ibbMerkezleriniYukle(userLat, userLng) {
      fetch("/api/ibb_atik_merkezleri")
        .then(function (res) {
          return res.json();
        })
        .then(function (data) {
          if (data && data.length) {
            return merkezleriEkle(data, userLat, userLng);
          }
          return [];
        })
        .catch(function (err) {
          console.error("İBB harita hatası:", err);
          return [];
        })
        .then(function (ibbSinirlar) {
          ilanlaraOrtala(ibbSinirlar);
        });
    }

    if (mapLocate) {
      mapLocate.acquireLocation({
        fly: false,
        onSuccess: function (userLat, userLng) {
          ibbMerkezleriniYukle(userLat, userLng);
        },
        onError: function () {
          ibbMerkezleriniYukle(null, null);
        },
      });
    } else {
      ibbMerkezleriniYukle(null, null);
    }

    setTimeout(function () {
      map.invalidateSize();
      var ibbBounds = [];
      ibbKatmani.eachLayer(function (layer) {
        if (layer.getLatLng) {
          var ll = layer.getLatLng();
          ibbBounds.push([ll.lat, ll.lng]);
        }
      });
      ilanlaraOrtala(ibbBounds);
    }, 100);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initMap);
  } else {
    initMap();
  }
})();
