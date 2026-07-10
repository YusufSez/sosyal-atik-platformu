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
  var oldestLoadedId = 0;
  var hasMoreOlder = false;
  var loadingOlder = false;
  var pendingNewCount = 0;
  var socket = null;
  var conversationJoined = false;

  function getSocket() {
    if (socket) return socket;
    if (typeof window.getMessageSocket === "function") {
      socket = window.getMessageSocket();
    }
    return socket;
  }

  function localCanonicalId() {
    if (canonicalId) return canonicalId;
    var low = Math.min(currentUserId, aliciId);
    var high = Math.max(currentUserId, aliciId);
    return low + "-" + high + "-" + kaynakId + "-" + atikId;
  }

  function isNearBottom() {
    if (window.MessageScrollHelper) {
      return window.MessageScrollHelper.isNearBottom(mesajKutusu, 80);
    }
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
    var canon = localCanonicalId();
    if (msg.canonical_conversation_id && canon) {
      return msg.canonical_conversation_id === canon;
    }
    if (msg.conversation_id === conversationId) return true;
    if (msg.sender_id === aliciId || msg.receiver_id === aliciId) {
      return msg.canonical_conversation_id === canon;
    }
    return false;
  }

  function joinConversationRoom() {
    var sock = getSocket();
    if (!sock) return;
    var payload = { partner_id: aliciId, kaynak_id: kaynakId, atik_id: atikId };
    if (typeof window.registerConversation === "function") {
      window.registerConversation(aliciId, kaynakId, atikId);
    }
    sock.emit("join_conversation", payload, function (res) {
      if (res && res.error) {
        console.warn("join_conversation failed:", res.error);
        return;
      }
      conversationJoined = true;
      if (res && res.canonical_conversation_id) {
        canonicalId = res.canonical_conversation_id;
        mesajKutusu.dataset.canonicalId = canonicalId;
      }
      if (res && res.partner) {
        updatePartnerPresence(res.partner);
      }
    });
  }

  function ensureConversationJoined() {
    var sock = getSocket();
    if (!sock) {
      setTimeout(ensureConversationJoined, 150);
      return;
    }
    if (sock.connected) {
      joinConversationRoom();
    } else {
      sock.once("connect", joinConversationRoom);
    }
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
        var unreadIds = res.messages
          .filter(function (m) {
            return m.receiver_id === currentUserId && !m.is_read;
          })
          .map(function (m) {
            return m.message_id;
          });
        if (unreadIds.length) markMessagesRead(unreadIds);
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

  function insertMessage(msg, autoScroll, prependOnly) {
    var id = msg.message_id || msg.id;
    if (!id || renderedIds[id]) return false;
    renderedIds[id] = true;
    if (id > lastMessageId) lastMessageId = id;
    if (!oldestLoadedId || id < oldestLoadedId) oldestLoadedId = id;

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

    if (prependOnly) {
      return true;
    }

    if (autoScroll !== false && isNearBottom()) {
      scrollToBottom();
    } else if (autoScroll !== false && msg.sender_id !== currentUserId) {
      showNewMessageButton();
    }
    return true;
  }

  function normalizeFetchPayload(data) {
    if (Array.isArray(data)) {
      return {
        messages: data,
        has_more: false,
        oldest_id: data.length ? data[0].id : null,
      };
    }
    return data || { messages: [], has_more: false, oldest_id: null };
  }

  function mapFetchedMessage(msg) {
    return {
      id: msg.id,
      message_id: msg.id,
      sender_id: msg.sender_id,
      sender_username: msg.sender_username,
      content: msg.content,
      message: msg.content,
      timestamp: msg.timestamp,
      is_read: msg.is_read,
      read_at_local: msg.read_at_local,
    };
  }

  function prependOlderMessages(messages) {
    if (!messages.length) return;
    var previousHeight = mesajKutusu.scrollHeight;
    var previousTop = mesajKutusu.scrollTop;
    messages.forEach(function (msg) {
      insertMessage(msg, false, true);
    });
    mesajKutusu.scrollTop = mesajKutusu.scrollHeight - previousHeight + previousTop;
    oldestLoadedId = messages[0].id || messages[0].message_id || oldestLoadedId;
  }

  function fetchMessages() {
    fetch("/mesajlar_getir/" + aliciId + "/" + kaynakId + "/" + atikId, {
      headers: { "X-Requested-With": "XMLHttpRequest" },
    })
      .then(function (response) {
        return response.json();
      })
      .then(function (data) {
        var payload = normalizeFetchPayload(data);
        mesajKutusu.innerHTML = "";
        renderedIds = {};
        lastMessageId = 0;
        oldestLoadedId = 0;
        hasMoreOlder = !!payload.has_more;
        (payload.messages || []).forEach(function (msg) {
          insertMessage(mapFetchedMessage(msg), false);
        });
        if (payload.oldest_id) {
          oldestLoadedId = payload.oldest_id;
        }
        scrollToBottom();
      });
  }

  function loadOlderMessages() {
    if (!hasMoreOlder || loadingOlder || !oldestLoadedId) return;
    loadingOlder = true;
    fetch(
      "/mesajlar_getir/" +
        aliciId +
        "/" +
        kaynakId +
        "/" +
        atikId +
        "?before_id=" +
        oldestLoadedId,
      { headers: { "X-Requested-With": "XMLHttpRequest" } }
    )
      .then(function (response) {
        return response.json();
      })
      .then(function (data) {
        var payload = normalizeFetchPayload(data);
        hasMoreOlder = !!payload.has_more;
        prependOlderMessages((payload.messages || []).map(mapFetchedMessage));
        if (payload.oldest_id) {
          oldestLoadedId = payload.oldest_id;
        }
      })
      .finally(function () {
        loadingOlder = false;
      });
  }

  function emitTypingStart() {
    var sock = getSocket();
    if (!sock || !sock.connected) return;
    sock.emit("typing_start", {
      partner_id: aliciId,
      kaynak_id: kaynakId,
      atik_id: atikId,
    });
  }

  function emitTypingStop() {
    var sock = getSocket();
    if (!sock || !sock.connected) return;
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
    typingHideTimer = setTimeout(hideTypingIndicator, 3000);
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

  function onSocketConnect() {
    ensureConversationJoined();
    syncAfterReconnect();
  }

  function onSocketReconnect() {
    conversationJoined = false;
    ensureConversationJoined();
    syncAfterReconnect();
  }

  function bindSocketEvents(sock) {
    if (!sock) return false;

    sock.off("connect", onSocketConnect);
    sock.on("connect", onSocketConnect);

    sock.off("reconnect", onSocketReconnect);
    sock.on("reconnect", onSocketReconnect);

    sock.off("new_message", onNewMessage);
    sock.on("new_message", onNewMessage);

    sock.off("message_sent", onMessageSent);
    sock.on("message_sent", onMessageSent);

    sock.off("message_read", onMessageRead);
    sock.on("message_read", onMessageRead);

    sock.off("typing_start", onTypingStart);
    sock.on("typing_start", onTypingStart);

    sock.off("typing_stop", onTypingStop);
    sock.on("typing_stop", onTypingStop);

    sock.off("friend_online", onFriendOnline);
    sock.on("friend_online", onFriendOnline);

    sock.off("friend_offline", onFriendOffline);
    sock.on("friend_offline", onFriendOffline);

    return true;
  }

  function initializeMessaging() {
    var sock = getSocket();
    if (!sock) return false;
    bindSocketEvents(sock);
    if (sock.connected) {
      ensureConversationJoined();
    }
    return true;
  }

  function tryInitializeMessaging() {
    if (initializeMessaging()) return;
    var attempts = 0;
    var timer = setInterval(function () {
      attempts += 1;
      if (initializeMessaging() || attempts >= 40) {
        clearInterval(timer);
      }
    }, 50);
  }

  window.bindSocketEvents = bindSocketEvents;
  window.initializeMessaging = initializeMessaging;

  function onNewMessage(msg) {
    if (!matchesConversation(msg)) return;
    if (msg.sender_id === currentUserId) return;
    insertMessage(msg);
    if (msg.receiver_id === currentUserId && msg.message_id) {
      markMessagesRead([msg.message_id]);
    }
  }

  function onMessageSent(msg) {
    if (!matchesConversation(msg)) return;
    if (msg.sender_id !== currentUserId) return;
    insertMessage(msg);
  }

  function onMessageRead(data) {
    if (!data) return;
    var canon = localCanonicalId();
    if (
      data.canonical_conversation_id &&
      canon &&
      data.canonical_conversation_id !== canon
    ) {
      return;
    }
    if (
      !data.canonical_conversation_id &&
      data.conversation_id &&
      data.conversation_id !== conversationId
    ) {
      return;
    }
    updateReadReceipts(data.message_ids);
  }

  function onTypingStart(data) {
    if (!data || data.sender_id !== aliciId) return;
    if (!matchesConversation(data)) return;
    showTypingIndicator(data.sender_name);
  }

  function onTypingStop(data) {
    if (!data || data.sender_id !== aliciId) return;
    if (!matchesConversation(data)) return;
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
    if (mesajKutusu.scrollTop < 80) {
      loadOlderMessages();
    }
    if (isNearBottom()) {
      pendingNewCount = 0;
      if (yeniMesajBtn) yeniMesajBtn.classList.add("d-none");
    }
  });

  window.addEventListener("atikport:message-socket-ready", initializeMessaging);
  tryInitializeMessaging();
  fetchMessages();

  window.addEventListener("pagehide", function () {
    if (typeof window.leaveConversation === "function") {
      window.leaveConversation({
        partner_id: aliciId,
        kaynak_id: kaynakId,
        atik_id: atikId,
      });
    }
  });

  if (mesajInput) {
    mesajInput.addEventListener("input", function () {
      clearTimeout(typingDebounce);
      clearTimeout(stopTypingTimer);
      if (!mesajInput.value.trim()) {
        emitTypingStop();
        return;
      }
      emitTypingStart();
      typingDebounce = setTimeout(emitTypingStart, 300);
      stopTypingTimer = setTimeout(emitTypingStop, 2500);
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
