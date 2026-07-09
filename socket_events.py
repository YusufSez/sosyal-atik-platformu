"""Flask-SocketIO event handlers (altyapı — mesajlaşma henüz AJAX üzerinden)."""

from flask_login import current_user
from socketio.exceptions import ConnectionRefusedError

from extensions import socketio


@socketio.on("connect")
def handle_connect():
    """Yalnızca Flask-Login oturumu olan kullanıcılar bağlanabilir."""
    if not current_user.is_authenticated:
        raise ConnectionRefusedError("Giriş gerekli")


@socketio.on("disconnect")
def handle_disconnect():
    """Bağlantı kapanışı — şimdilik yalnızca altyapı kaydı."""
    pass
