import os

from dotenv import load_dotenv
from flask_login import current_user
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_mail import Mail
from flask_migrate import Migrate

from constants import RATE_AI_ANALIZ

load_dotenv()


def _resolve_rate_limit_storage():
    uri = os.getenv("RATELIMIT_STORAGE_URI", "memory://")
    if uri.startswith(("redis://", "rediss://", "valkey://")):
        try:
            import redis

            client = redis.from_url(uri, socket_connect_timeout=1)
            client.ping()
            return uri
        except ImportError:
            import warnings

            warnings.warn(
                "RATELIMIT_STORAGE_URI Redis/Valkey kullanıyor ancak 'redis' paketi yüklü değil. "
                "memory:// ile devam ediliyor. Kurulum: pip install redis",
                stacklevel=2,
            )
            return "memory://"
        except Exception:
            import warnings

            warnings.warn(
                f"Redis'e bağlanılamadı ({uri}). Rate limit için memory:// kullanılıyor. "
                "Yerel geliştirmede .env içinde RATELIMIT_STORAGE_URI=memory:// kullanabilirsiniz.",
                stacklevel=2,
            )
            return "memory://"
    return uri


def rate_limit_user_or_ip():
    if current_user.is_authenticated:
        return str(current_user.id)
    return get_remote_address()


db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
csrf = CSRFProtect()
mail = Mail()
limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=_resolve_rate_limit_storage(),
)

ai_analiz_limit = limiter.shared_limit(
    RATE_AI_ANALIZ,
    scope="ai_analiz",
    methods=["POST"],
    key_func=rate_limit_user_or_ip,
)
