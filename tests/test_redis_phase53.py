"""Phase 5.3 — Redis altyapısı (opsiyonel, memory fallback)."""

import logging
from unittest.mock import MagicMock, patch

import pytest

from production_config import (
    resolve_rate_limit_storage_uri,
    resolve_socketio_message_queue,
)
from services.redis_manager import (
    get_redis,
    get_redis_url,
    health,
    ping,
    reset_redis_client,
    storage_label,
)


@pytest.fixture(autouse=True)
def _reset_redis_state(monkeypatch):
    reset_redis_client()
    monkeypatch.delenv("REDIS_URL", raising=False)
    yield
    reset_redis_client()


def test_redis_url_not_configured():
    assert get_redis_url() is None
    assert health() == "disabled"
    assert get_redis() is None
    assert ping() is False


def test_health_endpoint_without_redis(client):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.get_json()
    assert data["status"] == "ok"
    assert data["database"] == "up"
    assert data["redis"] == "disabled"
    assert data["storage"] == "memory"


def test_rate_limit_defaults_to_memory_without_redis(monkeypatch, caplog):
    monkeypatch.delenv("RATELIMIT_STORAGE_URI", raising=False)
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.setenv("RATELIMIT_BACKEND", "memory")
    with caplog.at_level(logging.INFO, logger="atikport.config"):
        assert resolve_rate_limit_storage_uri() == "memory://"


def test_rate_limit_uses_redis_url_when_set(monkeypatch):
    monkeypatch.delenv("RATELIMIT_STORAGE_URI", raising=False)
    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:6379/0")

    fake_client = MagicMock()
    fake_client.ping.return_value = True
    with patch("redis.from_url", return_value=fake_client):
        assert resolve_rate_limit_storage_uri() == "redis://127.0.0.1:6379/0"


def test_rate_limit_redis_fallback_logs_warning(monkeypatch, caplog):
    monkeypatch.delenv("RATELIMIT_STORAGE_URI", raising=False)
    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:59999/0")
    monkeypatch.setenv("RATELIMIT_STRICT", "false")

    with patch("redis.from_url", side_effect=ConnectionError("refused")):
        with caplog.at_level(logging.WARNING, logger="atikport.config"):
            uri = resolve_rate_limit_storage_uri()
    assert uri == "memory://"
    assert any("memory://" in r.message for r in caplog.records)


def test_redis_manager_fallback_logs_warning(monkeypatch, caplog):
    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:59999/0")
    with patch("redis.from_url", side_effect=ConnectionError("refused")):
        with caplog.at_level(logging.WARNING, logger="atikport.redis"):
            assert get_redis() is None
            assert health() == "degraded"
    assert any("memory fallback" in r.message for r in caplog.records)


def test_redis_manager_healthy_when_ping_succeeds(monkeypatch):
    monkeypatch.delenv("RATELIMIT_STORAGE_URI", raising=False)
    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:6379/0")
    fake_client = MagicMock()
    fake_client.ping.return_value = True
    with patch("redis.from_url", return_value=fake_client):
        assert health() == "healthy"
        assert ping() is True
        assert storage_label() == "redis"


def test_storage_label_memory_when_redis_degraded(monkeypatch):
    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:59999/0")
    with patch("redis.from_url", side_effect=ConnectionError("refused")):
        assert storage_label() == "memory"
        assert health() == "degraded"


def test_socketio_message_queue_none_without_redis(monkeypatch):
    monkeypatch.delenv("REDIS_URL", raising=False)
    assert resolve_socketio_message_queue() is None


def test_socketio_message_queue_when_redis_available(monkeypatch):
    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:6379/0")
    with patch("services.redis_manager.ping_redis_url", return_value=True):
        assert resolve_socketio_message_queue() == "redis://127.0.0.1:6379/0"


def test_socketio_message_queue_none_when_redis_unreachable(monkeypatch, caplog):
    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:59999/0")
    with patch("services.redis_manager.ping_redis_url", return_value=False):
        with caplog.at_level(logging.WARNING, logger="atikport.config"):
            assert resolve_socketio_message_queue() is None
    assert any("message queue" in r.message.lower() for r in caplog.records)


def test_app_config_redis_url_none_by_default(app):
    assert app.config.get("REDIS_URL") is None
