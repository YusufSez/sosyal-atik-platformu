"""Veritabanı bağlantı URI çözümlemesi (SQLite / PostgreSQL)."""

import os
from urllib.parse import quote_plus

from utils import env_to_bool


def is_sqlite_uri(uri: str) -> bool:
    return uri.startswith("sqlite:")


def is_postgres_uri(uri: str) -> bool:
    return uri.startswith("postgresql")


def resolve_database_uri(basedir: str) -> str:
    """
    Öncelik sırası:
    1) DATABASE_URL (tam bağlantı dizesi)
    2) POSTGRES_* değişkenleri (USE_POSTGRES=True ise)
    3) Yerel SQLite site.db
    """
    explicit = os.getenv("DATABASE_URL", "").strip()
    if explicit:
        return explicit

    use_postgres = env_to_bool(os.getenv("USE_POSTGRES"), default=False)
    if use_postgres:
        host = os.getenv("POSTGRES_HOST", "localhost").strip()
        port = os.getenv("POSTGRES_PORT", "5432").strip()
        database = os.getenv("POSTGRES_DB", "atikport").strip()
        user = os.getenv("POSTGRES_USER", "postgres").strip()
        password = os.getenv("POSTGRES_PASSWORD", "")
        if password is None or password == "":
            raise RuntimeError(
                "PostgreSQL kullanımı için POSTGRES_PASSWORD veya DATABASE_URL tanımlayın."
            )
        safe_user = quote_plus(user)
        safe_password = quote_plus(password)
        return f"postgresql+psycopg2://{safe_user}:{safe_password}@{host}:{port}/{database}"

    db_file = os.getenv("SQLITE_PATH", os.path.join(basedir, "site.db"))
    return f"sqlite:///{db_file}"
