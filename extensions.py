from flask_login import current_user
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_mail import Mail
from flask_migrate import Migrate
from flask_socketio import SocketIO

from constants import RATE_AI_ANALIZ
from production_config import resolve_rate_limit_storage_uri
from utils.env import load_app_dotenv

# factory.py ile aynı politika (çakışan ikinci kör load_dotenv yok)
load_app_dotenv()


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
    storage_uri=resolve_rate_limit_storage_uri(),
)

ai_analiz_limit = limiter.shared_limit(
    RATE_AI_ANALIZ,
    scope="ai_analiz",
    methods=["POST"],
    key_func=rate_limit_user_or_ip,
)

socketio = SocketIO()
