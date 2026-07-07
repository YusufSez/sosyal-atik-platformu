(function () {
  var mesajKutusu = document.getElementById("mesajKutusu");
  if (!mesajKutusu) return;

  var aliciId = parseInt(mesajKutusu.dataset.aliciId, 10);
  var currentUserId = parseInt(mesajKutusu.dataset.currentUserId, 10);
  var kaynakId = parseInt(mesajKutusu.dataset.kaynakId, 10);
  var atikId = parseInt(mesajKutusu.dataset.atikId, 10);
  var mesajForm = document.getElementById("mesajForm");
  var mesajInput = document.getElementById("mesajInput");

  function mesajSikayet(mesajId) {
    var sebep = prompt("Şikayet açıklamanız (isteğe bağlı):");
    if (sebep === null) return;

    csrfFetch("/api/mesaj_sikayet", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mesaj_id: mesajId, sebep: sebep || "" }),
    })
      .then(function (response) {
        return response.json().then(function (data) {
          return { ok: response.ok, data: data };
        });
      })
      .then(function (result) {
        if (!result.ok) {
          alert(result.data.error || "Şikayet gönderilemedi.");
          return;
        }
        alert("Şikayetiniz alındı. İncelenecektir.");
      })
      .catch(function () {
        alert("Şikayet gönderilemedi.");
      });
  }

  function fetchMessages() {
    fetch("/mesajlar_getir/" + aliciId + "/" + kaynakId + "/" + atikId, {
      headers: { "X-Requested-With": "XMLHttpRequest" },
    })
      .then(function (response) {
        return response.json();
      })
      .then(function (data) {
        mesajKutusu.innerHTML = "";
        data.forEach(function (msg) {
          var div = document.createElement("div");
          div.className =
            "mb-3 chat-bubble-wrap " + (msg.sender_id === currentUserId ? "text-end" : "text-start");

          var header = document.createElement("div");
          header.className = "small mb-1 " + (msg.sender_id === currentUserId ? "text-primary" : "text-secondary");
          header.textContent = msg.sender_username;

          var p = document.createElement("p");
          p.className =
            "d-inline-block m-0 p-2 text-white rounded chat-bubble " +
            (msg.sender_id === currentUserId ? "bg-primary" : "bg-secondary");
          p.textContent = msg.content;

          var meta = document.createElement("div");
          meta.className = "small text-muted mt-1";

          var time = document.createElement("span");
          time.textContent = msg.timestamp;

          meta.appendChild(time);

          if (msg.sender_id !== currentUserId) {
            var reportBtn = document.createElement("button");
            reportBtn.type = "button";
            reportBtn.className = "btn btn-link btn-sm text-danger p-0 ms-2 align-baseline";
            reportBtn.textContent = "Şikayet Et";
            reportBtn.addEventListener("click", function () {
              mesajSikayet(msg.id);
            });
            meta.appendChild(reportBtn);
          }

          div.appendChild(header);
          div.appendChild(document.createElement("br"));
          div.appendChild(p);
          div.appendChild(meta);
          mesajKutusu.appendChild(div);
        });
        mesajKutusu.scrollTop = mesajKutusu.scrollHeight;
      });
  }

  setInterval(fetchMessages, 5000);
  fetchMessages();

  if (!mesajForm) return;

  mesajForm.addEventListener("submit", function (e) {
    e.preventDefault();
    e.stopPropagation();

    var content = mesajInput.value.trim();
    if (!content) return;

    var submitBtn = mesajForm.querySelector('button[type="submit"]');
    var originalText = submitBtn ? submitBtn.innerHTML : "";

    if (submitBtn) {
      submitBtn.disabled = true;
      submitBtn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Gönderiliyor...';
    }

    csrfFetch("/send_message", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        alici_id: aliciId,
        content: content,
        kaynak_id: kaynakId,
        atik_id: atikId,
      }),
    })
      .then(function (response) {
        return response.json().then(function (data) {
          return { ok: response.ok, data: data };
        });
      })
      .then(function (result) {
        if (!result.ok) {
          throw new Error(result.data.error || "Mesaj gönderilemedi");
        }
        mesajInput.value = "";
        fetchMessages();
      })
      .catch(function (error) {
        alert(error.message || "Mesaj gönderilemedi. Lütfen tekrar deneyin.");
      })
      .finally(function () {
        if (submitBtn) {
          submitBtn.disabled = false;
          submitBtn.innerHTML = originalText;
        }
      });
  });
})();
