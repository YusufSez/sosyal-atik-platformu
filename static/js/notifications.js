(function () {
  if (document.body.dataset.authenticated !== "1") return;

  var socket = null;
  var lastNotificationUnread = null;
  var joinedConversations = [];

  function getSocket() {
    if (!socket && typeof io !== "undefined") {
      socket = io({
        path: "/socket.io/",
        transports: ["websocket", "polling"],
        withCredentials: true,
        reconnection: true,
        reconnectionAttempts: Infinity,
        reconnectionDelay: 1000,
        reconnectionDelayMax: 5000,
      });

      socket.on("connect", function () {
        socket.emit("join");
        rejoinConversations();
      });

      socket.on("reconnect", function () {
        socket.emit("join");
        rejoinConversations();
        if (typeof window.bildirimleriGetir === "function") {
          window.bildirimleriGetir();
        }
      });

      socket.on("unread_count_updated", handleUnreadCountUpdated);
      socket.on("notification_sync", handleNotificationSync);
      socket.on("conversation_updated", handleConversationUpdated);
    }
    return socket;
  }

  function rejoinConversations() {
    if (!socket) return;
    joinedConversations.forEach(function (conv) {
      socket.emit("join_conversation", conv);
    });
  }

  function registerConversation(partnerId, kaynakId, atikId) {
    var payload = {
      partner_id: partnerId,
      kaynak_id: kaynakId || 0,
      atik_id: atikId || 0,
    };
    var key = payload.partner_id + "-" + payload.kaynak_id + "-" + payload.atik_id;
    if (joinedConversations.some(function (c) {
      return c.partner_id + "-" + c.kaynak_id + "-" + c.atik_id === key;
    })) {
      return;
    }
    joinedConversations.push(payload);
    if (socket && socket.connected) {
      socket.emit("join_conversation", payload);
    }
  }

  function updateMessageBadge(count) {
    var badge = document.getElementById("mesajUnreadBadge");
    if (!badge) return;
    if (count > 0) {
      badge.textContent = count;
      badge.classList.remove("d-none");
    } else {
      badge.classList.add("d-none");
    }
  }

  function updateNotificationBadge(count) {
    var sayi = document.getElementById("bildirimSayisi");
    if (!sayi) return;
    if (count > 0) {
      sayi.textContent = count;
      sayi.classList.remove("d-none");
    } else {
      sayi.classList.add("d-none");
    }
  }

  function handleUnreadCountUpdated(data) {
    if (!data) return;
    if (typeof data.message_unread === "number") {
      updateMessageBadge(data.message_unread);
    }
    if (typeof data.notification_unread === "number") {
      if (
        lastNotificationUnread !== null &&
        data.notification_unread > lastNotificationUnread
      ) {
        bildirimleriGetir();
      }
      lastNotificationUnread = data.notification_unread;
      updateNotificationBadge(data.notification_unread);
    }
  }

  function handleNotificationSync(data) {
    if (!data) return;
    if (typeof data.notification_unread === "number") {
      lastNotificationUnread = data.notification_unread;
      updateNotificationBadge(data.notification_unread);
    }
    bildirimleriGetir();
  }

  function handleConversationUpdated(data) {
    if (!data || !data.conversation_id) return;
    var list = document.getElementById("sohbetListesi");
    if (!list) return;

    var item = list.querySelector(
      '[data-conversation-id="' + data.conversation_id + '"]'
    );
    if (!item) {
      item = createConversationItem(data);
      if (!item) return;
      list.insertBefore(item, list.firstChild);
      var bos = document.getElementById("bosSohbetMesaji");
      if (bos) bos.style.display = "none";
      return;
    }

    updateConversationItem(item, data);
    list.insertBefore(item, list.firstChild);
  }

  function createConversationItem(data) {
    var li = document.createElement("li");
    li.className = "list-group-item d-flex justify-content-between align-items-center";
    li.dataset.conversationId = data.conversation_id;
    li.dataset.partnerId = data.partner_id;
    li.dataset.kaynakId = data.kaynak_id || 0;
    li.dataset.atikId = data.atik_id || 0;

    var left = document.createElement("div");
    var strong = document.createElement("strong");
    strong.textContent = data.partner_name || "Kullanıcı";
    left.appendChild(strong);

    if (data.unread_count > 0) {
      var badge = document.createElement("span");
      badge.className = "badge bg-danger ms-2 conversation-new-badge";
      badge.textContent = "Yeni";
      left.appendChild(badge);
    }

    var preview = document.createElement("p");
    preview.className = "mb-1 text-truncate text-truncate-md conversation-preview";
    preview.textContent = data.is_sent_by_me
      ? "Sen: " + data.last_message
      : data.last_message;
    left.appendChild(preview);

    var time = document.createElement("small");
    time.className = "text-muted conversation-time";
    time.textContent = data.last_message_at_local || "";
    left.appendChild(time);

    var link = document.createElement("a");
    link.className = "btn btn-primary btn-sm";
    link.textContent = "Mesajları Gör";
    link.href =
      "/mesajlar/" +
      data.partner_id +
      "/" +
      (data.kaynak_id || 0) +
      "/" +
      (data.atik_id || 0);

    li.appendChild(left);
    li.appendChild(link);
    return li;
  }

  function updateConversationItem(item, data) {
    var preview = item.querySelector(".conversation-preview");
    if (preview) {
      preview.textContent = data.is_sent_by_me
        ? "Sen: " + data.last_message
        : data.last_message;
    }
    var time = item.querySelector(".conversation-time");
    if (time) {
      time.textContent = data.last_message_at_local || "";
    }
    var badge = item.querySelector(".conversation-new-badge");
    if (data.unread_count > 0) {
      if (!badge) {
        badge = document.createElement("span");
        badge.className = "badge bg-danger ms-2 conversation-new-badge";
        var strong = item.querySelector("strong");
        if (strong) strong.insertAdjacentElement("afterend", badge);
      }
      badge.textContent = "Yeni";
      badge.classList.remove("d-none");
    } else if (badge) {
      badge.remove();
    }
  }

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
        lastNotificationUnread = 0;
        return;
      }

      bos.style.display = "none";
      var okunmamisSayisi = 0;
      for (var j = 0; j < bildirimler.length; j++) {
        if (!bildirimler[j].okundu) okunmamisSayisi++;
      }

      lastNotificationUnread = okunmamisSayisi;
      updateNotificationBadge(okunmamisSayisi);

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

  window.getMessageSocket = getSocket;
  window.registerConversation = registerConversation;
  window.bildirimleriGetir = bildirimleriGetir;
  window.updateMessageBadge = updateMessageBadge;
  window.handleConversationUpdated = handleConversationUpdated;

  getSocket();
  window.dispatchEvent(new CustomEvent("atikport:message-socket-ready"));
  bildirimleriGetir();
})();
