"""Production Hardening Phase testleri."""

import logging

import pytest

from production_config import (
    resolve_rate_limit_storage_uri,
    resolve_socketio_cors_origins,
)


def test_rate_limit_defaults_to_memory(monkeypatch, caplog):
    monkeypatch.delenv("RATELIMIT_STORAGE_URI", raising=False)
    monkeypatch.setenv("RATELIMIT_BACKEND", "memory")
    with caplog.at_level(logging.INFO, logger="atikport.config"):
        assert resolve_rate_limit_storage_uri() == "memory://"
    assert any("memory://" in r.message for r in caplog.records)


def test_rate_limit_explicit_uri(monkeypatch):
    monkeypatch.setenv("RATELIMIT_STORAGE_URI", "memory://")
    monkeypatch.setenv("RATELIMIT_BACKEND", "redis")
    assert resolve_rate_limit_storage_uri() == "memory://"


def test_rate_limit_redis_backend_requires_url(monkeypatch):
    monkeypatch.delenv("RATELIMIT_STORAGE_URI", raising=False)
    monkeypatch.setenv("RATELIMIT_BACKEND", "redis")
    monkeypatch.delenv("REDIS_URL", raising=False)
    with pytest.raises(RuntimeError, match="REDIS_URL"):
        resolve_rate_limit_storage_uri()


def test_rate_limit_redis_fallback_logs_warning(monkeypatch, caplog):
    monkeypatch.setenv("RATELIMIT_STORAGE_URI", "redis://127.0.0.1:59999/0")
    monkeypatch.setenv("RATELIMIT_STRICT", "false")
    with caplog.at_level(logging.WARNING, logger="atikport.config"):
        uri = resolve_rate_limit_storage_uri()
    assert uri == "memory://"
    assert any("memory://" in r.message for r in caplog.records)


def test_socket_cors_falls_back_to_site_url(monkeypatch):
    monkeypatch.delenv("SOCKETIO_CORS_ORIGINS", raising=False)
    monkeypatch.setenv("SITE_URL", "https://atikport.com")
    origins = resolve_socketio_cors_origins(is_testing=False, debug=False)
    assert origins == ["https://atikport.com"]


def test_socket_cors_localhost_in_debug(monkeypatch):
    monkeypatch.delenv("SOCKETIO_CORS_ORIGINS", raising=False)
    origins = resolve_socketio_cors_origins(is_testing=False, debug=True)
    assert "http://localhost:5000" in origins
    assert "http://127.0.0.1:8080" in origins


def test_socket_cors_explicit_list(monkeypatch):
    monkeypatch.setenv("SOCKETIO_CORS_ORIGINS", "https://a.com, https://b.com")
    origins = resolve_socketio_cors_origins(is_testing=False, debug=False)
    assert origins == ["https://a.com", "https://b.com"]


def test_socket_cors_testing_unrestricted():
    assert resolve_socketio_cors_origins(is_testing=True, debug=False) is None


def test_socket_cors_none_without_env_warns(monkeypatch, caplog):
    monkeypatch.delenv("SOCKETIO_CORS_ORIGINS", raising=False)
    monkeypatch.delenv("SITE_URL", raising=False)
    with caplog.at_level(logging.WARNING, logger="atikport.config"):
        assert resolve_socketio_cors_origins(is_testing=False, debug=False) is None
    assert caplog.records


def test_dockerfile_non_root_with_gosu():
    content = open("Dockerfile", encoding="utf-8").read()
    assert "useradd" in content
    assert "atikport" in content
    assert "gosu" in content


def test_email_token_index_in_model():
    from models import EmailToken

    index_names = {idx.name for idx in EmailToken.__table__.indexes}
    assert "ix_email_token_nonce_purpose" in index_names


def test_unread_cache_warms_on_first_request(app):
    from auth_utils import hash_password
    from blueprints.messages import inject_unread_from_cache
    from extensions import db
    from flask_login import login_user
    from models import Mesaj, User
    from services.message_unread_cache import clear_unread_cache, get_message_unread_count

    with app.app_context():
        clear_unread_cache()
        sender = User(
            username="warm_sender",
            email="warm_sender@test.com",
            password=hash_password("TestPass1"),
            is_completed=True,
            email_verified=True,
        )
        receiver = User(
            username="warm_receiver",
            email="warm_receiver@test.com",
            password=hash_password("TestPass1"),
            is_completed=True,
            email_verified=True,
        )
        db.session.add_all([sender, receiver])
        db.session.commit()
        db.session.add(
            Mesaj(sender_id=sender.id, receiver_id=receiver.id, content="x", is_read=False)
        )
        db.session.commit()

        with app.test_request_context("/"):
            login_user(receiver)
            inject_unread_from_cache()
            from flask import g

            assert g.unread_count == 1
            assert get_message_unread_count(receiver.id) == 1


def test_unread_cache_cleared_on_logout(client, app):
    from auth_utils import hash_password
    from extensions import db
    from models import Mesaj, User
    from services.message_unread_cache import get_message_unread_count, refresh_unread_cache

    with app.app_context():
        sender = User(
            username="logout_sender",
            email="logout_sender@test.com",
            password=hash_password("TestPass1"),
            is_completed=True,
            email_verified=True,
        )
        receiver = User(
            username="logout_cache",
            email="logout_cache@test.com",
            password=hash_password("TestPass1"),
            is_completed=True,
            email_verified=True,
        )
        db.session.add_all([sender, receiver])
        db.session.commit()
        db.session.add(
            Mesaj(sender_id=sender.id, receiver_id=receiver.id, content="x", is_read=False)
        )
        db.session.commit()
        refresh_unread_cache(receiver.id)
        assert get_message_unread_count(receiver.id) == 1

    client.post(
        "/giris",
        data={"email": "logout_cache@test.com", "password": "TestPass1"},
        follow_redirects=True,
    )
    # GET /cikis oturumu silmez (CSRF); cache temizliği POST çıkışta yapılır.
    client.post("/cikis", follow_redirects=True)

    with app.app_context():
        assert get_message_unread_count(receiver.id, warm_if_missing=False) == 0
