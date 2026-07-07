import os
import secrets
from datetime import timedelta

from dotenv import load_dotenv
from flask import Flask
from werkzeug.middleware.proxy_fix import ProxyFix

load_dotenv()

from constants import ITEMS_PER_PAGE, MAX_UPLOAD_BYTES
from extensions import csrf, db, limiter, login_manager
from models import User
from security import init_security
from utils import ensure_schema, env_to_bool

_WEAK_SECRET_KEYS = frozenset({
    "degistirin-gizli-anahtar",
    "secret",
    "changeme",
    "dev",
    "test",
})


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
    app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{os.path.join(basedir, 'site.db')}"
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
    app.config["RECAPTCHA_SITE_KEY"] = os.getenv("RECAPTCHA_SITE_KEY", "")
    app.config["RECAPTCHA_SECRET_KEY"] = os.getenv("RECAPTCHA_SECRET_KEY", "")
    app.config["RECAPTCHA_ENABLED"] = env_to_bool(
        os.getenv("RECAPTCHA_ENABLED"),
        default=bool(os.getenv("RECAPTCHA_SECRET_KEY")),
    )

    if config_overrides:
        app.config.update(config_overrides)

    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
    os.makedirs(os.path.join(app.root_path, "static", "profile_pics"), exist_ok=True)

    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "auth.giris"
    login_manager.login_message = "Bu sayfaya erişmek için lütfen giriş yapın."
    login_manager.login_message_category = "warning"
    csrf.init_app(app)
    limiter.init_app(app)

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

    with app.app_context():
        db.create_all()
        ensure_schema()
        from services.ilan_images import backfill_ilan_resimleri
        backfill_ilan_resimleri()

    from utils import unescape_stored_text
    from services.impact import format_etki_sayi
    from services.ilan_images import ilan_fotograf_listesi, kapak_resim

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

    from datetime import datetime
    from content.kurumsal import FOOTER_COLUMNS, NAVBAR_KURUMSAL, SOSYAL_MEDYA

    @app.context_processor
    def inject_site_footer():
        return {
            "footer_columns": FOOTER_COLUMNS,
            "navbar_kurumsal": NAVBAR_KURUMSAL,
            "sosyal_medya": SOSYAL_MEDYA,
            "now_year": datetime.now().year,
        }

    return app
