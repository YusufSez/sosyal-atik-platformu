(function () {
    const statusEl = document.getElementById("socket-status");
    const messageEl = document.getElementById("socket-message");
    if (!statusEl || !messageEl || typeof io !== "function") {
        return;
    }

    function setStatus(text, badgeClass, message) {
        statusEl.textContent = text;
        statusEl.className = `badge ${badgeClass}`;
        messageEl.textContent = message;
    }

    setStatus("Bağlanıyor...", "bg-secondary", "SocketIO bağlantısı kuruluyor...");

    const socket = io({
        path: "/socket.io/",
        transports: ["websocket", "polling"],
        withCredentials: true,
    });

    socket.on("connect", function () {
        setStatus("Bağlandı", "bg-success", "SocketIO bağlantısı aktif.");
    });

    socket.on("disconnect", function () {
        setStatus("Bağlantı kesildi", "bg-danger", "SocketIO bağlantısı kesildi.");
    });

    socket.on("connect_error", function () {
        setStatus("Bağlantı kesildi", "bg-danger", "Bağlantı kurulamadı veya oturum geçersiz.");
    });
})();
