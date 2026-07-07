import os

import pytest

from services.database_config import is_postgres_uri, is_sqlite_uri, resolve_database_uri


def test_resolve_sqlite_default(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("USE_POSTGRES", "False")
    uri = resolve_database_uri("/tmp/proj")
    assert is_sqlite_uri(uri)
    assert uri.endswith("site.db")


def test_resolve_database_url(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg2://u:p@localhost:5432/atikport")
    monkeypatch.delenv("USE_POSTGRES", raising=False)
    monkeypatch.delenv("POSTGRES_HOST", raising=False)
    uri = resolve_database_uri("/tmp/proj")
    assert is_postgres_uri(uri)
    assert "atikport" in uri


def test_resolve_postgres_from_env(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("USE_POSTGRES", "True")
    monkeypatch.setenv("POSTGRES_HOST", "localhost")
    monkeypatch.setenv("POSTGRES_DB", "atikport")
    monkeypatch.setenv("POSTGRES_USER", "postgres")
    monkeypatch.setenv("POSTGRES_PASSWORD", "secret")
    uri = resolve_database_uri("/tmp/proj")
    assert uri.startswith("postgresql+psycopg2://postgres:")
    assert uri.endswith("/atikport")


def test_resolve_postgres_requires_password(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("USE_POSTGRES", "True")
    monkeypatch.setenv("POSTGRES_PASSWORD", "")
    with pytest.raises(RuntimeError, match="POSTGRES_PASSWORD"):
        resolve_database_uri("/tmp/proj")
