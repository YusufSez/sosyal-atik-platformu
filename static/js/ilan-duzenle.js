(function () {
  document.querySelectorAll(".ilan-foto-sil-btn").forEach(function (btn) {
    btn.addEventListener("click", function (e) {
      e.preventDefault();
      e.stopPropagation();
      var cb = document.getElementById(btn.dataset.checkbox);
      if (!cb) return;
      cb.checked = !cb.checked;
      var kart = btn.closest(".ilan-foto-sil-kart");
      kart.classList.toggle("silindi-isaretli", cb.checked);
      btn.setAttribute("aria-pressed", cb.checked ? "true" : "false");
      if (cb.checked) {
        btn.innerHTML = '<i class="bi bi-arrow-counterclockwise"></i> Geri Al';
        btn.classList.remove("btn-danger");
        btn.classList.add("btn-secondary");
      } else {
        btn.innerHTML = '<i class="bi bi-trash"></i> Sil';
        btn.classList.remove("btn-secondary");
        btn.classList.add("btn-danger");
      }
    });
  });

  var konumBtn = document.getElementById("konumBtn");
  if (konumBtn) {
    konumBtn.addEventListener("click", function () {
      var durum = document.getElementById("konumDurum");
      if (!navigator.geolocation) {
        durum.textContent = "Konum desteklenmiyor.";
        return;
      }
      durum.textContent = "Alınıyor...";
      navigator.geolocation.getCurrentPosition(
        function (pos) {
          document.getElementById("latitude").value = pos.coords.latitude;
          document.getElementById("longitude").value = pos.coords.longitude;
          durum.textContent = "Konum güncellendi.";
        },
        function () {
          durum.textContent = "İzin verilmedi.";
        }
      );
    });
  }
})();
