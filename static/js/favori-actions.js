(function () {
  function readConfig(id) {
    var el = document.getElementById(id);
    if (!el) return null;
    try {
      return JSON.parse(el.textContent);
    } catch (e) {
      console.error("JSON yapılandırması okunamadı:", id, e);
      return null;
    }
  }

  function favoriToggle(kaynakId, atikId, btn) {
    var girisUrl = document.body.dataset.girisUrl;
    if (document.body.dataset.authenticated !== "1") {
      if (girisUrl) window.location.href = girisUrl;
      return;
    }

    var data = {};
    if (kaynakId) data.kaynak_id = kaynakId;
    if (atikId) data.atik_id = atikId;

    csrfFetch("/api/favori_ekle", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    })
      .then(function (r) {
        return r.json();
      })
      .then(function (result) {
        if (!btn) return;
        var icon = btn.querySelector("i");
        if (!icon) return;
        if (result.status === "added") {
          icon.className = "bi bi-heart-fill text-danger";
          btn.classList.add("btn-outline-danger");
        } else {
          icon.className = "bi bi-heart";
          btn.classList.remove("btn-outline-danger");
        }
        if (result.status === "removed") {
          var card = btn ? btn.closest(".hover-card, .card, .list-group-item") : null;
          if (card) {
            card.remove();
          } else {
            location.reload();
          }
          return;
        }
      })
      .catch(function (e) {
        console.error(e);
      });
  }

  document.addEventListener("click", function (e) {
    var toggleBtn = e.target.closest(".favori-toggle-btn");
    if (toggleBtn) {
      e.preventDefault();
      var kaynakId = toggleBtn.dataset.kaynakId ? parseInt(toggleBtn.dataset.kaynakId, 10) : null;
      var atikId = toggleBtn.dataset.atikId ? parseInt(toggleBtn.dataset.atikId, 10) : null;
      favoriToggle(kaynakId, atikId, toggleBtn);
      return;
    }

    var kaldirBtn = e.target.closest(".favori-kaldir-btn");
    if (kaldirBtn) {
      e.preventDefault();
      var kId = kaldirBtn.dataset.kaynakId ? parseInt(kaldirBtn.dataset.kaynakId, 10) : null;
      var aId = kaldirBtn.dataset.atikId ? parseInt(kaldirBtn.dataset.atikId, 10) : null;
      favoriToggle(kId, aId, null);
    }
  });

  document.addEventListener("DOMContentLoaded", function () {
    if (document.body.dataset.authenticated !== "1") return;

    function kontrolEt(btn, param, id) {
      if (!id) return;
      fetch("/api/favori_kontrol?" + param + "=" + id)
        .then(function (r) {
          return r.json();
        })
        .then(function (result) {
          if (!result.is_favori) return;
          var icon = btn.querySelector("i");
          if (icon) icon.className = "bi bi-heart-fill text-danger";
          btn.classList.add("btn-outline-danger");
        });
    }

    document.querySelectorAll(".favori-toggle-btn[data-kaynak-id]").forEach(function (btn) {
      kontrolEt(btn, "kaynak_id", btn.dataset.kaynakId);
    });
    document.querySelectorAll(".favori-toggle-btn[data-atik-id]").forEach(function (btn) {
      kontrolEt(btn, "atik_id", btn.dataset.atikId);
    });
  });

  window.favoriToggle = favoriToggle;
  window.favoriToggleAtik = function (atikId, btn) {
    favoriToggle(null, atikId, btn);
  };
})();
