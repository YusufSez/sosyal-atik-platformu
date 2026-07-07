(function () {
  if (document.body.dataset.authenticated !== "1") return;

  async function bildirimleriGetir() {
    try {
      var response = await fetch("/bildirimleri_getir", {
        headers: { "X-Requested-With": "XMLHttpRequest" },
      });
      var bildirimler = await response.json();
      var liste = document.getElementById("bildirimListesi");
      var sayi = document.getElementById("bildirimSayisi");
      var bos = document.getElementById("bosBildirim");
      if (!liste || !sayi || !bos) return;

      var items = liste.querySelectorAll(".notification-item");
      for (var i = 0; i < items.length; i++) {
        items[i].remove();
      }

      if (bildirimler.length === 0) {
        bos.style.display = "block";
        sayi.classList.add("d-none");
        return;
      }

      bos.style.display = "none";
      var okunmamisSayisi = 0;
      for (var j = 0; j < bildirimler.length; j++) {
        if (!bildirimler[j].okundu) okunmamisSayisi++;
      }

      if (okunmamisSayisi > 0) {
        sayi.textContent = okunmamisSayisi;
        sayi.classList.remove("d-none");
      } else {
        sayi.classList.add("d-none");
      }

      for (var k = 0; k < bildirimler.length; k++) {
        (function (b) {
          var item = document.createElement("a");
          item.href = b.link || "#";
          item.className =
            "dropdown-item notification-item" + (!b.okundu ? " notification-unread" : "");

          var row = document.createElement("div");
          row.className = "d-flex justify-content-between";
          var strong = document.createElement("strong");
          strong.textContent = b.baslik;
          var time = document.createElement("small");
          time.className = "text-muted";
          time.textContent = b.timestamp;
          row.appendChild(strong);
          row.appendChild(time);

          var p = document.createElement("p");
          p.className = "mb-0 small text-muted";
          p.textContent = b.icerik;

          item.appendChild(row);
          item.appendChild(p);
          item.dataset.bildirimId = b.id;
          item.addEventListener("click", function () {
            if (!b.okundu) {
              csrfFetch("/bildirim_okundu_isaretle/" + b.id, { method: "POST" }).catch(
                function (err) {
                  console.error(err);
                }
              );
            }
          });
          liste.appendChild(item);
        })(bildirimler[k]);
      }
    } catch (err) {
      console.error("Bildirimler yuklenemedi:", err);
    }
  }

  var temizleBtn = document.getElementById("temizleBtn");
  if (temizleBtn) {
    temizleBtn.addEventListener("click", function (e) {
      e.preventDefault();
      csrfFetch("/bildirimleri_okundu_isaretle", { method: "POST" })
        .then(function () {
          bildirimleriGetir();
        })
        .catch(function (e) {
          console.error(e);
        });
    });
  }

  var temizleOkunanBtn = document.getElementById("temizleOkunanBtn");
  if (temizleOkunanBtn) {
    temizleOkunanBtn.addEventListener("click", function (e) {
      e.preventDefault();
      csrfFetch("/bildirimleri_temizle", { method: "POST" })
        .then(function () {
          bildirimleriGetir();
        })
        .catch(function (err) {
          console.error(err);
        });
    });
  }

  bildirimleriGetir();
  setInterval(bildirimleriGetir, 30000);
})();
