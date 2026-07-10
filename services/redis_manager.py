"""Redis bağlantı yardımcıları — opsiyonel; yoksa veya hata varsa memory fallback."""

from __future__ import annotations

import logging
import os

logger = logging.getLogger("atikport.redis")

_client = None
_client_url: str | None = None


def get_redis_url() -> str | None:
    url = (os.getenv("REDIS_URL") or "").strip()
    return url or None


def reset_redis_client() -> None:
    """Testler için önbelleğe alınmış istemciyi sıfırlar."""
    global _client, _client_url
    _client = None
    _client_url = None


def ping_redis_url(url: str) -> bool:
    if not url:
        return False
    try:
        import redis

        client = redis.from_url(url, socket_connect_timeout=1)
        client.ping()
        return True
    except Exception:
        return False


def get_redis():
    """Redis istemcisi döner; yapılandırılmamış veya erişilemezse None."""
    global _client, _client_url

    url = get_redis_url()
    if not url:
        return None

    if _client is not None and _client_url == url:
        return _client

    try:
        import redis

        client = redis.from_url(url, socket_connect_timeout=1, decode_responses=True)
        client.ping()
        _client = client
        _client_url = url
        return _client
    except ImportError:
        logger.warning("redis paketi yüklü değil; Redis devre dışı (memory fallback)")
        _client = None
        _client_url = None
        return None
    except Exception as exc:
        logger.warning(
            "Redis'e bağlanılamadı (%s); memory fallback kullanılıyor: %s",
            url,
            exc,
        )
        _client = None
        _client_url = None
        return None


def ping() -> bool:
    client = get_redis()
    if client is None:
        return False
    try:
        client.ping()
        return True
    except Exception:
        return False


def health() -> str:
    """
    Redis durumu:
    - disabled: REDIS_URL tanımlı değil
    - healthy: bağlantı başarılı
    - degraded: tanımlı ancak erişilemiyor
    """
    if not get_redis_url():
        return "disabled"
    if ping():
        return "healthy"
    return "degraded"


def storage_label() -> str:
    """Aktif rate-limit deposu etiketi: memory | redis."""
    explicit = (os.getenv("RATELIMIT_STORAGE_URI") or "").strip()
    if explicit == "memory://":
        return "memory"
    if explicit.startswith(("redis://", "rediss://", "valkey://")):
        return "redis" if health() == "healthy" else "memory"

    if get_redis_url() and health() == "healthy":
        return "redis"
    return "memory"
