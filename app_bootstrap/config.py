import os
import secrets
import sys
from datetime import timedelta

from constants import ITEMS_PER_PAGE, MAX_UPLOAD_BYTES
from services.database_config import is_sqlite_uri, resolve_database_uri
from utils import env_to_bool

_WEAK_SECRET_KEYS = frozenset({
    "degistirin-gizli-anahtar",
    "degistirin-gizli-anahtar-en-az-32-karakter-olmalidir",
    "secret",
    "changeme",
    "dev",
    "test",
})


def skip_startup_hooks() -> bool:
    """Alembic / flask db komutlarında tablo sorgularını atla."""
    if env_to_bool(os.getenv("SKIP_APP_BOOTSTRAP"), default=False):
        return True
    cli = " ".join(sys.argv).lower()
    if " db " in f" {cli} ":
        return True
    return False


def _validate_secret_key(secret_key, is_testing):
    if is_testing:
        return
    if len(secret_key) < 32:
        raise RuntimeError("SECRET_KEY en az 32 karakter olmalıdır. .env dosyanızı güncelleyin.")
    if secret_key.lower() in _WEAK_SECRET_KEYS:
        raise RuntimeError("SECRET_KEY zayıf/varsayılan değer kullanılamaz. Güçlü bir anahtar tanımlayın.")


def _is_production_runtime(app) -> bool:
    if app.config.get("TESTING"):
        return False
    if app.config.get("DEBUG"):
        return False
    if skip_startup_hooks():
        return False
    return True


def validate_production_runtime(app) -> None:
    """Production ortamında zorunlu güvenlik ayarlarını doğrular."""
    if not _is_production_runtime(app):
        return
    missing = []
    if not app.config.get("FORCE_HTTPS"):
        missing.append("FORCE_HTTPS=true")
    if app.config.get("DEBUG"):
        missing.append("DEBUG=False")
    if not (app.config.get("SITE_URL") or "").strip():
        missing.append("SITE_URL")
    cors = (os.getenv("SOCKETIO_CORS_ORIGINS") or "").strip()
    if not cors:
        missing.append("SOCKETIO_CORS_ORIGINS")
    if missing:
        raise RuntimeError(
            "Production ortamında zorunlu yapılandırma eksik: "
            + ", ".join(missing)
        )


def configure_app(app, config_overrides=None):
    """Flask config, dizinler ve ortam doğrulaması."""
    basedir = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
    is_testing = (config_overrides or {}).get("TESTING", False)
    secret_key = os.getenv("SECRET_KEY")
    if not secret_key:
        if is_testing:
            secret_key = secrets.token_hex(32)
        else:
            raise RuntimeError(
                "SECRET_KEY ortam değişkeni tanımlı değil. .env dosyanıza SECRET_KEY ekleyin."
            )
    _validate_secret_key(secret_key, is_testing)

    force_https = env_to_bool(os.getenv("FORCE_HTTPS"), default=False)
    behind_proxy = env_to_bool(os.getenv("BEHIND_PROXY"), default=False)

    app.config["SECRET_KEY"] = secret_key
    db_uri = resolve_database_uri(basedir)
    if config_overrides and config_overrides.get("SQLALCHEMY_DATABASE_URI"):
        db_uri = config_overrides["SQLALCHEMY_DATABASE_URI"]
    app.config["SQLALCHEMY_DATABASE_URI"] = db_uri
    if is_sqlite_uri(db_uri):
        if not (config_overrides and "SQLALCHEMY_ENGINE_OPTIONS" in config_overrides):
            app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {}
    else:
        app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
            "pool_pre_ping": True,
            "pool_recycle": 300,
        }
    app.config["UPLOAD_FOLDER"] = os.path.join(app.root_path, "static", "item_pics")
    app.config["SUPPORT_UPLOAD_FOLDER"] = os.path.join(
        app.root_path, "data", "support_attachments"
    )
    app.config["GEMINI_API_KEY"] = os.getenv("GEMINI_API_KEY")
    app.config["REDIS_URL"] = os.getenv("REDIS_URL") or None
    app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_BYTES
    app.config["ALLOW_SEED_ROUTE"] = env_to_bool(os.getenv("ALLOW_SEED_ROUTE"), default=False)
    app.config["DEBUG"] = env_to_bool(os.getenv("DEBUG"), default=False)
    app.config["ITEMS_PER_PAGE"] = ITEMS_PER_PAGE
    app.config["WTF_CSRF_TIME_LIMIT"] = None
    app.config["WTF_CSRF_SSL_STRICT"] = force_https
    app.config["FORCE_HTTPS"] = force_https
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["SESSION_COOKIE_SECURE"] = force_https
    app.config["REMEMBER_COOKIE_HTTPONLY"] = True
    app.config["REMEMBER_COOKIE_SAMESITE"] = "Lax"
    app.config["REMEMBER_COOKIE_SECURE"] = force_https
    app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=7)
    app.config["TURNSTILE_SITE_KEY"] = os.getenv("TURNSTILE_SITE_KEY", "")
    app.config["TURNSTILE_SECRET_KEY"] = os.getenv("TURNSTILE_SECRET_KEY", "")
    app.config["TURNSTILE_ENABLED"] = env_to_bool(
        os.getenv("TURNSTILE_ENABLED"),
        default=bool(os.getenv("TURNSTILE_SECRET_KEY")),
    )
    app.config["BACKUP_ENABLED"] = env_to_bool(os.getenv("BACKUP_ENABLED"), default=True)
    app.config["BACKUP_DIR"] = os.getenv("BACKUP_DIR", os.path.join(basedir, "backups"))
    app.config["BACKUP_RETENTION_DAYS"] = int(os.getenv("BACKUP_RETENTION_DAYS", "7"))
    app.config["BACKUP_INTERVAL_HOURS"] = int(os.getenv("BACKUP_INTERVAL_HOURS", "24"))
    app.config["LOG_DIR"] = os.getenv("LOG_DIR", "logs")
    app.config["SITE_NAME"] = os.getenv("SITE_NAME", "AI Tabanlı Atık ve Kaynak Paylaşım Platformu")
    app.config["MAIL_SERVER"] = os.getenv("MAIL_SERVER", "smtp-relay.brevo.com")
    app.config["MAIL_PORT"] = int(os.getenv("MAIL_PORT", "587"))
    app.config["MAIL_USE_TLS"] = env_to_bool(os.getenv("MAIL_USE_TLS"), default=True)
    app.config["MAIL_USE_SSL"] = env_to_bool(os.getenv("MAIL_USE_SSL"), default=False)
    app.config["MAIL_USERNAME"] = os.getenv("MAIL_USERNAME", "")
    app.config["MAIL_PASSWORD"] = os.getenv("MAIL_PASSWORD", "")
    app.config["MAIL_DEFAULT_SENDER"] = os.getenv("MAIL_DEFAULT_SENDER", "")
    app.config["BREVO_API_KEY"] = os.getenv("BREVO_API_KEY", "")
    app.config["EMAIL_TOKEN_MAX_AGE"] = int(os.getenv("EMAIL_TOKEN_MAX_AGE", "86400"))
    app.config["EMAIL_VERIFICATION_REQUIRED"] = env_to_bool(
        os.getenv("EMAIL_VERIFICATION_REQUIRED"), default=True
    )
    app.config["MAIL_SUPPRESS_SEND"] = env_to_bool(os.getenv("MAIL_SUPPRESS_SEND"), default=False)

    if config_overrides:
        app.config.update(config_overrides)

    if app.config.get("TESTING"):
        app.config["MAIL_SUPPRESS_SEND"] = True
        app.config["EMAIL_VERIFICATION_REQUIRED"] = False

    site_url = os.getenv("SITE_URL", "").strip().rstrip("/")
    app.config["SITE_URL"] = site_url
    if site_url:
        from urllib.parse import urlparse

        parsed = urlparse(site_url)
        if parsed.netloc:
            app.config["SERVER_NAME"] = parsed.netloc
            app.config["PREFERRED_URL_SCHEME"] = parsed.scheme or "https"

    if app.config.get("TURNSTILE_ENABLED") and not is_testing:
        import logging
        from urllib.parse import urlparse

        logger = logging.getLogger(__name__)
        site_url = os.getenv("SITE_URL", "").strip()
        if site_url:
            host = urlparse(site_url).hostname or ""
            if host:
                logger.info(
                    "Turnstile etkin. Cloudflare panelinde hostname olarak '%s' ekli olmalı.",
                    host,
                )
        else:
            logger.warning(
                "Turnstile etkin ancak SITE_URL tanımlı değil. "
                "Tarayıcıda kullandığınız alan adını Cloudflare Turnstile hostname listesine ekleyin. "
                "10.x.x.x gibi IP adresleri desteklenmez; localhost veya FQDN kullanın."
            )

    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
    os.makedirs(app.config["SUPPORT_UPLOAD_FOLDER"], exist_ok=True)
    os.makedirs(os.path.join(app.root_path, "static", "profile_pics"), exist_ok=True)
    os.makedirs(app.config["BACKUP_DIR"], exist_ok=True)
    os.makedirs(os.path.join(app.root_path, app.config["LOG_DIR"]), exist_ok=True)

    validate_production_runtime(app)

    return behind_proxy
