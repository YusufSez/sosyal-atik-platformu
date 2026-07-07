(function () {
  if (typeof L === "undefined") return;

  function defaultUserIcon() {
    return L.divIcon({
      className: "leaflet-map-marker",
      html: '<div class="map-marker map-marker-user" aria-hidden="true">📍</div>',
      iconSize: [26, 26],
      iconAnchor: [13, 13],
    });
  }

  window.MapLocate = {
    init: function (map, options) {
      options = options || {};
      var userMarker = null;
      var lastPos = null;
      var zoom = options.zoom || 14;
      var popupText = options.popupText || "Sen buradasın";

      function setUserMarker(lat, lng) {
        var icon = options.userIcon || defaultUserIcon();
        if (userMarker) {
          userMarker.setLatLng([lat, lng]);
        } else {
          userMarker = L.marker([lat, lng], { icon: icon }).addTo(map).bindPopup(popupText);
        }
        lastPos = [lat, lng];
      }

      function acquireLocation(opts) {
        opts = opts || {};
        if (!navigator.geolocation) {
          if (opts.onError) opts.onError();
          else window.alert("Tarayıcı konum desteklemiyor.");
          return;
        }

        var btn = document.querySelector("[data-map-locate]");
        if (btn) btn.disabled = true;

        navigator.geolocation.getCurrentPosition(
          function (pos) {
            var lat = pos.coords.latitude;
            var lng = pos.coords.longitude;
            setUserMarker(lat, lng);
            if (opts.fly) {
              map.flyTo([lat, lng], zoom, { duration: 0.8 });
            }
            if (typeof opts.onSuccess === "function") {
              opts.onSuccess(lat, lng);
            }
            if (btn) btn.disabled = false;
          },
          function () {
            if (typeof opts.onError === "function") {
              opts.onError();
            } else {
              window.alert("Konum izni verilmedi veya konum alınamadı.");
            }
            if (btn) btn.disabled = false;
          },
          { enableHighAccuracy: true, timeout: 10000, maximumAge: 60000 }
        );
      }

      var btn = document.querySelector("[data-map-locate]");
      if (btn) {
        btn.addEventListener("click", function () {
          acquireLocation({ fly: true });
        });
      }

      return {
        setUserMarker: setUserMarker,
        acquireLocation: acquireLocation,
        getLastPosition: function () {
          return lastPos;
        },
      };
    },
  };
})();
