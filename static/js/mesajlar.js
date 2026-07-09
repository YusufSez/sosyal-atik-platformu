(function () {
  var mesajKutusu = document.getElementById("mesajKutusu");
  if (!mesajKutusu) return;

  var aliciId = parseInt(mesajKutusu.dataset.aliciId, 10);
  var currentUserId = parseInt(mesajKutusu.dataset.currentUserId, 10);
  var kaynakId = parseInt(mesajKutusu.dataset.kaynakId, 10);
  var atikId = parseInt(mesajKutusu.dataset.atikId, 10);
  var conversationId =
    mesajKutusu.dataset.conversationId || aliciId + "-" + kaynakId + "-" + atikId;
  var canonicalId = mesajKutusu.dataset.canonicalId || "";
  var mesajForm = document.getElementById("mesajForm");
  var mesajInput = document.getElementById("mesajInput");
  var typingIndicator = document.getElementById("typingIndicator");
  var yeniMesajBtn = document.getElementById("yeniMesajBtn");
  var partnerPresence = document.getElementById("partnerPresence");
  var renderedIds = {};
  var typingDebounce = null;
  var stopTypingTimer = null;
  var typingHideTimer = null;
  var lastMessageId = 0;
  var pendingNewCount = 0;
  var socket = null;

  function getSocket() {
    if (socket) return socket;
    if (typeof window.getMessageSocket === "function") {
      socket = window.getMessageSocket();
    }
    return socket;
  }

  function isNearBottom() {
    return mesajKutusu.scrollHeight - mesajKutusu.scrollTop - mesajKutusu.clientHeight < 80;
  }

  function scrollToBottom() {
    mesajKutusu.scrollTop = mesajKutusu.scrollHeight;
    pendingNewCount = 0;
    if (yeniMesajBtn) yeniMesajBtn.classList.add("d-none");
  }

  function showNewMessageButton() {
    pendingNewCount += 1;
    if (!yeniMesajBtn) return;
    yeniMesajBtn.textContent = pendingNewCount > 1 ? "Yeni mesaj (" + pendingNewCount + ")" : "Yeni mesaj";
    yeniMesajBtn.classList.remove("d-none");
  }

  function matchesConversation(msg) {
    if (!msg) return false;
    if (msg.canonical_conversation_id && canonicalId) {
      return msg.canonical_conversation_id === canonicalId;
    }
    return msg.conversation_id === conversationId;
  }

  function joinConversationRoom() {
    var sock = getSocket();
    if (!sock) return;
    sock.emit(
      "join_conversation",
      { partner_id: aliciId, kaynak_id: kaynakId, atik_id: atikId },
      function (res) {
        if (res && res.canonical_conversation_id) {
          canonicalId = res.canonical_conversation_id;
          mesajKutusu.dataset.canonicalId = canonicalId;
        }
        if (res && res.partner) {
          updatePartnerPresence(res.partner);
        }
      }
    );
  }

  function syncAfterReconnect() {
    var sock = getSocket();
    if (!sock || !lastMessageId) return;
    sock.emit(
      "sync_state",
      {
        partner_id: aliciId,
        kaynak_id: kaynakId,
        atik_id: atikId,
        after_message_id: lastMessageId,
      },
      function (res) {
        if (!res || !res.messages) return;
        res.messages.forEach(function (msg) {
          insertMessage(msg, false);
        });
        if (isNearBottom()) scrollToBottom();
      }
    );
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

  function receiptMarkup(msg) {
    if (msg.sender_id !== currentUserId) return "";
    if (msg.is_read) {
      return '<span class="read-receipt text-primary ms-2" title="' +
        (msg.read_at_local || "Okundu") + '">✓✓</span>';
    }
    return '<span class="read-receipt text-muted ms-2" title="Gönderildi">✓</span>';
  }

  function updateReadReceipts(messageIds) {
    (messageIds || []).forEach(function (id) {
      var node = mesajKutusu.querySelector('[data-message-id="' + id + '"]');
      if (!node) return;
      var meta = node.querySelector(".message-meta");
      if (!meta) return;
      var old = meta.querySelector(".read-receipt");
      if (old) old.remove();
      meta.insertAdjacentHTML("beforeend", '<span class="read-receipt text-primary ms-2" title="Okundu">✓✓</span>');
    });
  }

  function buildMessageNode(msg) {
    var id = msg.message_id || msg.id;
    var div = document.createElement("div");
    div.className =
      "mb-3 chat-bubble-wrap " + (msg.sender_id === currentUserId ? "text-end" : "text-start");
    div.dataset.messageId = id;

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
    meta.className = "small text-muted mt-1 message-meta";

    var time = document.createElement("span");
    time.textContent = msg.created_at_local || msg.timestamp;
    meta.appendChild(time);
    meta.insertAdjacentHTML("beforeend", receiptMarkup(msg));

    if (msg.sender_id !== currentUserId) {
      var reportBtn = document.createElement("button");
      reportBtn.type = "button";
      reportBtn.className = "btn btn-link btn-sm text-danger p-0 ms-2 align-baseline";
      reportBtn.textContent = "Şikayet Et";
      reportBtn.addEventListener("click", function () {
        mesajSikayet(id);
      });
      meta.appendChild(reportBtn);
    }

    div.appendChild(header);
    div.appendChild(document.createElement("br"));
    div.appendChild(p);
    div.appendChild(meta);
    return div;
  }

  function insertMessage(msg, autoScroll) {
    var id = msg.message_id || msg.id;
    if (!id || renderedIds[id]) return false;
    renderedIds[id] = true;
    if (id > lastMessageId) lastMessageId = id;

    var node = buildMessageNode(msg);
    var children = mesajKutusu.querySelectorAll("[data-message-id]");
    var inserted = false;
    for (var i = 0; i < children.length; i++) {
      var existingId = parseInt(children[i].dataset.messageId, 10);
      if (id < existingId) {
        mesajKutusu.insertBefore(node, children[i]);
        inserted = true;
        break;
      }
    }
    if (!inserted) mesajKutusu.appendChild(node);

    if (autoScroll !== false && isNearBottom()) {
      scrollToBottom();
    } else if (autoScroll !== false && msg.sender_id !== currentUserId) {
      showNewMessageButton();
    }
    return true;
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
        lastMessageId = 0;
        data.forEach(function (msg) {
          insertMessage(
            {
              id: msg.id,
              sender_id: msg.sender_id,
              sender_username: msg.sender_username,
              content: msg.content,
              timestamp: msg.timestamp,
              is_read: msg.is_read,
              read_at_local: msg.read_at_local,
            },
            false
          );
        });
        scrollToBottom();
      });
  }

  function emitTypingStart() {
    var sock = getSocket();
    if (!sock) return;
    sock.emit("typing_start", {
      partner_id: aliciId,
      kaynak_id: kaynakId,
      atik_id: atikId,
    });
  }

  function emitTypingStop() {
    var sock = getSocket();
    if (!sock) return;
    sock.emit("typing_stop", {
      partner_id: aliciId,
      kaynak_id: kaynakId,
      atik_id: atikId,
    });
  }

  function hideTypingIndicator() {
    if (typingIndicator) typingIndicator.classList.add("d-none");
  }

  function showTypingIndicator(name) {
    if (!typingIndicator) return;
    typingIndicator.textContent = (name || "Kullanıcı") + " yazıyor...";
    typingIndicator.classList.remove("d-none");
    clearTimeout(typingHideTimer);
    typingHideTimer = setTimeout(hideTypingIndicator, 2000);
  }

  function updatePartnerPresence(data) {
    if (!partnerPresence || !data) return;
    if (data.is_online) {
      partnerPresence.innerHTML = '<span class="text-success"><span class="presence-dot"></span> Çevrimiçi</span>';
      return;
    }
    if (data.last_seen_local) {
      partnerPresence.innerHTML =
        '<span class="text-muted">Son görülme: ' + data.last_seen_local + "</span>";
      return;
    }
    partnerPresence.innerHTML = '<span class="text-muted">Çevrimdışı</span>';
  }

  function setupSocketHandlers() {
    var sock = getSocket();
    if (!sock) return;

    if (!sock._mesajlarHandlersBound) {
      sock.on("connect", function () {
        joinConversationRoom();
        syncAfterReconnect();
      });

      sock.on("reconnect", function () {
        joinConversationRoom();
        syncAfterReconnect();
      });

      sock.on("new_message", onNewMessage);
      sock.on("message_sent", onMessageSent);
      sock.on("message_read", onMessageRead);
      sock.on("typing_start", onTypingStart);
      sock.on("typing_stop", onTypingStop);
      sock.on("friend_online", onFriendOnline);
      sock.on("friend_offline", onFriendOffline);

      sock._mesajlarHandlersBound = true;
    }
  }

  function onNewMessage(msg) {
    if (!matchesConversation(msg)) return;
    insertMessage(msg);
    if (msg.receiver_id === currentUserId) {
      markMessagesRead([msg.message_id]);
    }
  }

  function onMessageSent(msg) {
    if (!matchesConversation(msg)) return;
    insertMessage(msg);
  }

  function onMessageRead(data) {
    if (!data) return;
    if (
      data.conversation_id !== conversationId &&
      data.canonical_conversation_id !== canonicalId
    ) {
      return;
    }
    updateReadReceipts(data.message_ids);
  }

  function onTypingStart(data) {
    if (!data) return;
    if (
      data.conversation_id !== conversationId &&
      data.canonical_conversation_id !== canonicalId
    ) {
      return;
    }
    if (data.sender_id !== aliciId) return;
    showTypingIndicator(data.sender_name);
  }

  function onTypingStop(data) {
    if (!data) return;
    if (
      data.conversation_id !== conversationId &&
      data.canonical_conversation_id !== canonicalId
    ) {
      return;
    }
    if (data.sender_id !== aliciId) return;
    hideTypingIndicator();
  }

  function onFriendOnline(data) {
    if (!data || data.user_id !== aliciId) return;
    updatePartnerPresence(data);
  }

  function onFriendOffline(data) {
    if (!data || data.user_id !== aliciId) return;
    updatePartnerPresence(data);
  }

  if (yeniMesajBtn) {
    yeniMesajBtn.addEventListener("click", scrollToBottom);
  }

  mesajKutusu.addEventListener("scroll", function () {
    if (isNearBottom()) {
      pendingNewCount = 0;
      if (yeniMesajBtn) yeniMesajBtn.classList.add("d-none");
    }
  });

  fetchMessages();
  joinConversationRoom();
  setupSocketHandlers();

  if (mesajInput) {
    mesajInput.addEventListener("input", function () {
      clearTimeout(typingDebounce);
      if (!mesajInput.value.trim()) {
        emitTypingStop();
        return;
      }
      typingDebounce = setTimeout(function () {
        emitTypingStart();
        clearTimeout(stopTypingTimer);
        stopTypingTimer = setTimeout(emitTypingStop, 2000);
      }, 500);
    });
  }

  if (!mesajForm) return;

  mesajForm.addEventListener("submit", function (e) {
    e.preventDefault();
    e.stopPropagation();

    var content = mesajInput.value.trim();
    if (!content) return;

    emitTypingStop();

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
          insertMessage(result.data.message);
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
