(function () {
  var configEl = document.getElementById("detay-config");
  if (!configEl) return;

  var config;
  try {
    config = JSON.parse(configEl.textContent);
  } catch (e) {
    console.error("Detay yapılandırması okunamadı", e);
    return;
  }

  var param = config.type === "atik" ? "atik_id" : "kaynak_id";

  function guncelleSayac() {
    fetch("/api/goruntulenme_sayisi?" + param + "=" + config.id)
      .then(function (r) {
        return r.json();
      })
      .then(function (d) {
        var el = document.getElementById("goruntulenmeSayisi");
        if (el) el.textContent = d.count || 0;
      });
  }

  if (config.authenticated) {
    var body = { atik_id: null, kaynak_id: null };
    if (config.type === "atik") body.atik_id = config.id;
    else body.kaynak_id = config.id;

    csrfFetch("/api/goruntulenme_ekle", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    })
      .then(guncelleSayac)
      .catch(guncelleSayac);
  } else {
    guncelleSayac();
  }
})();
