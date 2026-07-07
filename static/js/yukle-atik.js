(function () {
  function konumGuncelle(lat, lng, mesaj) {
    document.getElementById("latitude").value = lat;
    document.getElementById("longitude").value = lng;
    document.getElementById("konumDurum").textContent = mesaj;
  }

  function konumAl() {
    if (!navigator.geolocation) {
      document.getElementById("konumDurum").textContent = "Tarayıcı konum desteklemiyor.";
      return;
    }
    navigator.geolocation.getCurrentPosition(
      function (pos) {
        konumGuncelle(pos.coords.latitude, pos.coords.longitude, "Konum alındı (GPS).");
      },
      function () {
        var lat = document.getElementById("latitude").value;
        var lng = document.getElementById("longitude").value;
        if (lat && lng) {
          document.getElementById("konumDurum").textContent = "Profil konumu kullanılacak.";
        } else {
          document.getElementById("konumDurum").textContent =
            "Konum izni verilmedi. Haritada görünmeyebilir.";
        }
      }
    );
  }

  var konumAlBtn = document.getElementById("konumAlBtn");
  if (konumAlBtn) {
    konumAlBtn.addEventListener("click", konumAl);
  }

  var latInput = document.getElementById("latitude");
  var lngInput = document.getElementById("longitude");
  if (latInput && lngInput) {
    if (latInput.value && lngInput.value) {
      document.getElementById("konumDurum").textContent = "Profil konumu yüklendi.";
    } else {
      konumAl();
    }
  }

  var atikForm = document.getElementById("atikForm");
  if (atikForm) {
    atikForm.addEventListener("submit", function (e) {
      if (!document.getElementById("latitude").value || !document.getElementById("longitude").value) {
        e.preventDefault();
        alert(
          'Haritada görünmesi için lütfen konum izni verin veya "Konumumu Kullan" butonuna tıklayın.'
        );
        konumAl();
      }
    });
  }
})();
