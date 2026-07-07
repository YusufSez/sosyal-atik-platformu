"""Veritabanı şema başlatma — test / geliştirme SQLite; üretimde Alembic."""

import os

from extensions import db
from services.database_config import is_sqlite_uri
from utils import ensure_schema, env_to_bool


def _auto_create_default(app) -> bool:
    if app.config.get("TESTING"):
        return True
    if not is_sqlite_uri(app.config.get("SQLALCHEMY_DATABASE_URI", "")):
        return False
    return bool(app.config.get("DEBUG"))


def bootstrap_database(app) -> None:
    """
    TESTING veya AUTO_CREATE_DB=True (varsayılan: DEBUG + SQLite) ise create_all.
    Üretim / PostgreSQL: şema yalnızca `flask db upgrade` ile uygulanır.
    """
    if app.config.get("TESTING"):
        db.create_all()
        ensure_schema()
        return

    auto_create = env_to_bool(os.getenv("AUTO_CREATE_DB"), default=_auto_create_default(app))
    if auto_create:
        db.create_all()
        ensure_schema()
