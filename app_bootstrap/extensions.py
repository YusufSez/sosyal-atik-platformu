import os

from extensions import csrf, db, limiter, login_manager, mail, migrate, socketio
from models import User


def init_extensions(app):
    """Flask eklentilerini ve login manager'ı başlatır."""
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    mail.init_app(app)
    login_manager.login_view = "auth.giris"
    login_manager.login_message = "Bu sayfaya erişmek için lütfen giriş yapın."
    login_manager.login_message_category = "warning"
    csrf.init_app(app)
    limiter.init_app(app)
    if app.config.get("TESTING"):
        limiter.enabled = False

    from production_config import resolve_socketio_cors_origins, resolve_socketio_message_queue

    socketio_async_mode = (
        "threading"
        if app.config.get("TESTING")
        else os.getenv("SOCKETIO_ASYNC_MODE", "eventlet")
    )
    socketio_kwargs = {
        "async_mode": socketio_async_mode,
        "manage_session": False,
        "cors_allowed_origins": resolve_socketio_cors_origins(
            is_testing=bool(app.config.get("TESTING")),
            debug=bool(app.config.get("DEBUG")),
        ),
    }
    message_queue = resolve_socketio_message_queue()
    if message_queue:
        socketio_kwargs["message_queue"] = message_queue

    socketio.init_app(app, **socketio_kwargs)
    import socket_events  # noqa: F401 — event handler kaydı

    @login_manager.user_loader
    def load_user(user_id):
        if user_id is None:
            return None
        try:
            uid = int(user_id)
        except (TypeError, ValueError):
            return None
        if uid <= 0:
            return None
        return db.session.get(User, uid)
