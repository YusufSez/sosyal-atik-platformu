(function () {
  document.addEventListener("click", function (e) {
    var btn = e.target.closest(".sikayet-btn");
    if (!btn) return;
    e.preventDefault();

    var kaynakId = btn.dataset.kaynakId ? parseInt(btn.dataset.kaynakId, 10) : null;
    var atikId = btn.dataset.atikId ? parseInt(btn.dataset.atikId, 10) : null;
    var sebep = prompt("Şikayet sebebinizi yazın:");
    if (!sebep) return;

    csrfFetch("/api/sikayet", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ kaynak_id: kaynakId, atik_id: atikId, sebep: sebep }),
    }).then(function () {
      alert("Şikayetiniz alındı.");
    });
  });
})();
