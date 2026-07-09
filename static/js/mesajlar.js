(function () {
  var mesajKutusu = document.getElementById("mesajKutusu");
  if (!mesajKutusu) return;

  var aliciId = parseInt(mesajKutusu.dataset.aliciId, 10);
  var currentUserId = parseInt(mesajKutusu.dataset.currentUserId, 10);
  var kaynakId = parseInt(mesajKutusu.dataset.kaynakId, 10);
  var atikId = parseInt(mesajKutusu.dataset.atikId, 10);
  var conversationId = aliciId + "-" + kaynakId + "-" + atikId;
  var mesajForm = document.getElementById("mesajForm");
  var mesajInput = document.getElementById("mesajInput");
  var typingIndicator = document.getElementById("typingIndicator");
  var renderedIds = {};
  var typingDebounce = null;
  var stopTypingTimer = null;
  var socket = null;

  function getSocket() {
    if (socket) return socket;
    if (typeof window.getMessageSocket === "function") {
      socket = window.getMessageSocket();
    } else if (typeof io !== "undefined") {
      socket = io({ withCredentials: true });
      socket.emit("join");
    }
    return socket;
  }

  function matchesConversation(msg) {
    return msg.conversation_id === conversationId;
  }

  function markMessagesRead(messageIds) {
    var sock = getSocket();
    if (!sock || !messageIds.length) return;
    sock.emit("message_read", { message_ids: messageIds });
  }

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

  function appendReadReceipt(meta) {
    if (meta.querySelector(".read-receipt")) return;
    var receipt = document.createElement("span");
    receipt.className = "read-receipt text-success ms-2";
    receipt.textContent = "Görüldü";
    meta.appendChild(receipt);
  }

  function buildMessageNode(msg) {
    var div = document.createElement("div");
    div.className =
      "mb-3 chat-bubble-wrap " + (msg.sender_id === currentUserId ? "text-end" : "text-start");
    div.dataset.messageId = msg.message_id || msg.id;

    var header = document.createElement("div");
    header.className =
      "small mb-1 " + (msg.sender_id === currentUserId ? "text-primary" : "text-secondary");
    header.textContent = msg.sender_name || msg.sender_username;

    var p = document.createElement("p");
    p.className =
      "d-inline-block m-0 p-2 text-white rounded chat-bubble " +
      (msg.sender_id === currentUserId ? "bg-primary" : "bg-secondary");
    p.textContent = msg.message || msg.content;

    var meta = document.createElement("div");
    meta.className = "small text-muted mt-1";

    var time = document.createElement("span");
    time.textContent = msg.created_at_local || msg.timestamp;
    meta.appendChild(time);

    if (msg.sender_id === currentUserId && msg.is_read) {
      appendReadReceipt(meta);
    }

    if (msg.sender_id !== currentUserId) {
      var reportBtn = document.createElement("button");
      reportBtn.type = "button";
      reportBtn.className = "btn btn-link btn-sm text-danger p-0 ms-2 align-baseline";
      reportBtn.textContent = "Şikayet Et";
      reportBtn.addEventListener("click", function () {
        mesajSikayet(msg.message_id || msg.id);
      });
      meta.appendChild(reportBtn);
    }

    div.appendChild(header);
    div.appendChild(document.createElement("br"));
    div.appendChild(p);
    div.appendChild(meta);
    return div;
  }

  function appendMessage(msg, scroll) {
    var id = msg.message_id || msg.id;
    if (id && renderedIds[id]) return;
    if (id) renderedIds[id] = true;
    mesajKutusu.appendChild(buildMessageNode(msg));
    if (scroll !== false) {
      mesajKutusu.scrollTop = mesajKutusu.scrollHeight;
    }
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
        renderedIds = {};
        data.forEach(function (msg) {
          appendMessage(
            {
              id: msg.id,
              sender_id: msg.sender_id,
              sender_username: msg.sender_username,
              content: msg.content,
              timestamp: msg.timestamp,
              is_read: msg.is_read,
            },
            false
          );
        });
        mesajKutusu.scrollTop = mesajKutusu.scrollHeight;
      });
  }

  function emitTyping() {
    var sock = getSocket();
    if (!sock) return;
    sock.emit("typing", {
      receiver_id: aliciId,
      conversation_id: conversationId,
    });
  }

  function emitStopTyping() {
    var sock = getSocket();
    if (!sock) return;
    sock.emit("stop_typing", {
      receiver_id: aliciId,
      conversation_id: conversationId,
    });
  }

  function setupSocketHandlers() {
    var sock = getSocket();
    if (!sock) return;

    sock.on("new_message", function (msg) {
      if (!matchesConversation(msg)) return;
      appendMessage(msg);
      if (msg.receiver_id === currentUserId) {
        markMessagesRead([msg.message_id]);
      }
    });

    sock.on("message_sent", function (msg) {
      if (!matchesConversation(msg)) return;
      appendMessage(msg);
    });

    sock.on("message_read", function (data) {
      if (!data || data.conversation_id !== conversationId) return;
      (data.message_ids || []).forEach(function (id) {
        var node = mesajKutusu.querySelector('[data-message-id="' + id + '"]');
        if (!node) return;
        var meta = node.querySelector(".small.text-muted");
        if (meta) appendReadReceipt(meta);
      });
    });

    sock.on("typing", function (data) {
      if (!data || data.conversation_id !== conversationId) return;
      if (data.sender_id !== aliciId) return;
      if (typingIndicator) {
        typingIndicator.textContent = (data.sender_name || "Kullanıcı") + " yazıyor...";
        typingIndicator.classList.remove("d-none");
      }
    });

    sock.on("stop_typing", function (data) {
      if (!data || data.conversation_id !== conversationId) return;
      if (data.sender_id !== aliciId) return;
      if (typingIndicator) typingIndicator.classList.add("d-none");
    });
  }

  fetchMessages();
  setupSocketHandlers();

  if (mesajInput) {
    mesajInput.addEventListener("input", function () {
      clearTimeout(typingDebounce);
      typingDebounce = setTimeout(function () {
        if (mesajInput.value.trim()) {
          emitTyping();
          clearTimeout(stopTypingTimer);
          stopTypingTimer = setTimeout(emitStopTyping, 3000);
        } else {
          emitStopTyping();
        }
      }, 500);
    });
  }

  if (!mesajForm) return;

  mesajForm.addEventListener("submit", function (e) {
    e.preventDefault();
    e.stopPropagation();

    var content = mesajInput.value.trim();
    if (!content) return;

    emitStopTyping();

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
        if (result.data.message) {
          appendMessage(result.data.message);
        }
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
