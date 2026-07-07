(function () {
  var konumAlBtn = document.getElementById("konumAlBtn");
  if (!konumAlBtn) return;

  konumAlBtn.addEventListener("click", function () {
    if (!navigator.geolocation) {
      document.getElementById("konumDurum").textContent = "Tarayıcı konum desteklemiyor.";
      return;
    }
    navigator.geolocation.getCurrentPosition(
      function (pos) {
        document.getElementById("latitude").value = pos.coords.latitude;
        document.getElementById("longitude").value = pos.coords.longitude;
        document.getElementById("konumDurum").textContent = "Konum alındı.";
      },
      function () {
        document.getElementById("konumDurum").textContent = "Konum izni verilmedi.";
      }
    );
  });
})();
