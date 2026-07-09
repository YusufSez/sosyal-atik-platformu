(function () {
  var container = document.getElementById("mesajlarimContainer");
  if (!container) return;

  function setup() {
    if (typeof window.getMessageSocket !== "function") return;
    var socket = window.getMessageSocket();
    if (!socket) return;

    socket.on("conversation_updated", function (data) {
      if (typeof window.handleConversationUpdated === "function") {
        window.handleConversationUpdated(data);
      }
    });

    socket.on("unread_count_updated", function (data) {
      if (typeof window.updateMessageBadge === "function" && data) {
        window.updateMessageBadge(data.message_unread || 0);
      }
    });
  }

  if (typeof window.getMessageSocket === "function") {
    setup();
  } else {
    document.addEventListener("DOMContentLoaded", setup);
  }
})();
