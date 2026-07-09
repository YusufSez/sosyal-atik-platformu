import os
import secrets
from datetime import timedelta

from dotenv import load_dotenv
from flask import Flask
from werkzeug.middleware.proxy_fix import ProxyFix

load_dotenv()

from constants import ITEMS_PER_PAGE, MAX_UPLOAD_BYTES
from extensions import csrf, db, limiter, login_manager, mail, migrate
from models import User
import models  # noqa: F401 — Alembic tüm modelleri keşfetsin
from security import apply_force_https_exemptions, init_security
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


def _skip_startup_hooks() -> bool:
    """Alembic / flask db komutlarında tablo sorgularını atla."""
    import sys

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


def create_app(config_overrides=None):
    app = Flask(__name__)
    basedir = os.path.abspath(os.path.dirname(__file__))
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
        app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {}
    else:
        app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
            "pool_pre_ping": True,
            "pool_recycle": 300,
        }
    app.config["UPLOAD_FOLDER"] = os.path.join(app.root_path, "static", "item_pics")
    app.config["GEMINI_API_KEY"] = os.getenv("GEMINI_API_KEY")
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
    os.makedirs(os.path.join(app.root_path, "static", "profile_pics"), exist_ok=True)
    os.makedirs(app.config["BACKUP_DIR"], exist_ok=True)
    os.makedirs(os.path.join(app.root_path, app.config["LOG_DIR"]), exist_ok=True)

    from services.logging_setup import init_logging, register_error_handlers

    init_logging(app)
    register_error_handlers(app)

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

    from flask_wtf.csrf import CSRFError
    from flask_limiter.errors import RateLimitExceeded

    @app.errorhandler(RateLimitExceeded)
    def handle_rate_limit(error):
        from flask import jsonify, render_template, request

        message = "Çok fazla istek gönderdiniz. Lütfen bir süre bekleyip tekrar deneyin."
        arka_plan = (
            request.path.startswith("/api/")
            or request.path.startswith("/mesajlar_getir/")
            or request.path == "/bildirimleri_getir"
            or request.is_json
            or request.headers.get("X-Requested-With") == "XMLHttpRequest"
            or "application/json" in (request.headers.get("Accept") or "")
        )
        if arka_plan:
            return jsonify({"error": message}), 429
        return render_template("errors/429.html"), 429

    @app.errorhandler(CSRFError)
    def handle_csrf_error(error):
        from flask import flash, jsonify, redirect, request, url_for

        from utils import safe_redirect_url

        message = "Güvenlik doğrulaması başarısız. Sayfayı yenileyip tekrar deneyin."
        if request.path.startswith("/api/") or request.is_json or request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return jsonify({"error": message}), 400
        flash(message, "danger")
        return redirect(safe_redirect_url(request.referrer))

    if behind_proxy:
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    init_security(app)

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    from blueprints.gamification import gamification_bp
    from blueprints.kurum import kurum_bp
    from blueprints.admin import admin_bp
    from blueprints.api import api_bp
    from blueprints.atik import atik_bp
    from blueprints.auth import auth_bp
    from blueprints.ilan import ilan_bp
    from blueprints.impact import impact_bp
    from blueprints.kaynak import kaynak_bp
    from blueprints.main import main_bp
    from blueprints.messages import messages_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(kaynak_bp)
    app.register_blueprint(atik_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(messages_bp)
    app.register_blueprint(ilan_bp)
    app.register_blueprint(impact_bp)
    app.register_blueprint(kurum_bp)
    app.register_blueprint(gamification_bp)
    app.register_blueprint(admin_bp)

    apply_force_https_exemptions(app)

    with app.app_context():
        from services.db_bootstrap import bootstrap_database

        bootstrap_database(app)
        if _skip_startup_hooks():
            pass
        else:
            from services.admin_bootstrap import bootstrap_admin_from_env
            from services.backup import maybe_run_scheduled_backup
            from services.ilan_images import backfill_ilan_resimleri

            bootstrap_admin_from_env()
            backfill_ilan_resimleri()
            try:
                backup_path = maybe_run_scheduled_backup(app)
                if backup_path:
                    app.logger.info("Otomatik veritabanı yedeği oluşturuldu: %s", backup_path)
            except Exception as exc:
                app.logger.warning("Otomatik yedekleme başarısız: %s", exc)

    from utils import format_datetime, unescape_stored_text
    from services.impact import format_etki_sayi
    from services.ilan_images import ilan_fotograf_listesi, kapak_resim

    @app.template_filter("format_dt")
    def format_dt_filter(value, fmt="%d.%m.%Y %H:%M"):
        return format_datetime(value, fmt)

    @app.template_filter("display_text")
    def display_text_filter(value):
        return unescape_stored_text(value)

    @app.template_filter("format_etki")
    def format_etki_filter(value, birim=""):
        return format_etki_sayi(value, birim)

    @app.template_filter("kapak_resim")
    def kapak_resim_filter(ilan):
        return kapak_resim(ilan)

    @app.template_filter("ilan_fotograflari")
    def ilan_fotograflari_filter(ilan):
        return ilan_fotograf_listesi(ilan)

    from content.kurumsal import FOOTER_COLUMNS, NAVBAR_KURUMSAL, SOSYAL_MEDYA
    from utils import local_now

    @app.context_processor
    def inject_site_footer():
        return {
            "footer_columns": FOOTER_COLUMNS,
            "navbar_kurumsal": NAVBAR_KURUMSAL,
            "sosyal_medya": SOSYAL_MEDYA,
            "now_year": local_now().year,
        }

    return app
