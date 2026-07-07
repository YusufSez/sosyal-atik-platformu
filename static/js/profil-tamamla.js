(function () {
  var configEl = document.getElementById("profil-config");
  if (!configEl) return;

  var config;
  try {
    config = JSON.parse(configEl.textContent);
  } catch (e) {
    console.error("Profil yapılandırması okunamadı", e);
    return;
  }

  var illerData = config.iller || {};
  var seciliIlce = config.secili_ilce || "";
  var ilSelect = document.getElementById("il");
  var ilceSelect = document.getElementById("ilce");

  function ilceleriDoldur(ilAdi, secili) {
    ilceSelect.innerHTML = '<option value="">İlçe Seçiniz</option>';
    if (ilAdi && illerData[ilAdi]) {
      illerData[ilAdi].forEach(function (ilceName) {
        var option = document.createElement("option");
        option.value = ilceName;
        option.textContent = ilceName;
        if (secili && secili === ilceName) option.selected = true;
        ilceSelect.appendChild(option);
      });
    }
  }

  ilSelect.addEventListener("change", function () {
    ilceleriDoldur(this.value, "");
  });

  if (ilSelect.value) {
    ilceleriDoldur(ilSelect.value, seciliIlce);
  }

  var konumBtn = document.getElementById("konumBtn");
  if (konumBtn) {
    konumBtn.addEventListener("click", function () {
      var durum = document.getElementById("konumDurum");
      if (!navigator.geolocation) {
        durum.textContent = "Tarayıcı konum desteklemiyor.";
        return;
      }
      durum.textContent = "Konum alınıyor...";
      navigator.geolocation.getCurrentPosition(
        function (pos) {
          document.getElementById("latitude").value = pos.coords.latitude;
          document.getElementById("longitude").value = pos.coords.longitude;
          durum.textContent = "Konum kaydedildi.";
        },
        function () {
          durum.textContent = "Konum izni verilmedi.";
        }
      );
    });
  }

  if (window.jQuery && jQuery.fn.mask) {
    jQuery(function () {
      jQuery("#telefon").mask("(000) 000 00 00");
    });
  }
})();
