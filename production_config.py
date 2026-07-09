"""Production yapılandırma yardımcıları — rate limit ve Socket.IO CORS."""

from __future__ import annotations

import logging
import os
from urllib.parse import urlparse

logger = logging.getLogger("atikport.config")

_DEV_SOCKET_CORS = (
    "http://localhost:5000",
    "http://127.0.0.1:5000",
    "http://localhost:8080",
    "http://127.0.0.1:8080",
)


def _env_to_bool(value: str | None, *, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


def _origin_from_site_url(site_url: str) -> str | None:
    parsed = urlparse(site_url.strip())
    if parsed.scheme and parsed.netloc:
        return f"{parsed.scheme}://{parsed.netloc}"
    return None


def resolve_rate_limit_storage_uri() -> str:
    """Rate limit deposu: memory:// (varsayılan) veya Redis/Valkey URI."""
    explicit = os.getenv("RATELIMIT_STORAGE_URI", "").strip()
    if explicit:
        return _validate_storage_uri(explicit)

    backend = os.getenv("RATELIMIT_BACKEND", "memory").strip().lower()
    if backend == "redis":
        redis_url = os.getenv("REDIS_URL", "").strip()
        if not redis_url:
            raise RuntimeError(
                "RATELIMIT_BACKEND=redis için REDIS_URL tanımlanmalıdır. "
                "Örnek: REDIS_URL=redis://redis:6379/0"
            )
        return _validate_storage_uri(redis_url)

    logger.info("Rate limit storage: memory://")
    return "memory://"


def _validate_storage_uri(uri: str) -> str:
    if uri.startswith(("redis://", "rediss://", "valkey://")):
        strict = _env_to_bool(os.getenv("RATELIMIT_STRICT"), default=False)
        try:
            import redis

            client = redis.from_url(uri, socket_connect_timeout=1)
            client.ping()
            logger.info("Rate limit storage: Redis (%s)", uri)
            return uri
        except ImportError as exc:
            if strict:
                raise RuntimeError(
                    "RATELIMIT_STRICT etkin: redis paketi gerekli (pip install redis)"
                ) from exc
            logger.warning(
                "Redis URI ayarlı ancak redis paketi yüklü değil; memory:// kullanılıyor"
            )
            return "memory://"
        except Exception as exc:
            if strict:
                raise RuntimeError(
                    f"RATELIMIT_STRICT etkin: Redis'e bağlanılamadı ({uri})"
                ) from exc
            logger.warning(
                "Redis'e bağlanılamadı (%s); rate limit memory:// backend'ine düşürüldü: %s",
                uri,
                exc,
            )
            return "memory://"
    if uri == "memory://":
        logger.info("Rate limit storage: memory://")
    return uri


def resolve_socketio_cors_origins(*, is_testing: bool, debug: bool) -> list[str] | None:
    """Socket.IO CORS kökenleri."""
    if is_testing:
        return None

    explicit = os.getenv("SOCKETIO_CORS_ORIGINS", "").strip()
    if explicit:
        origins = [origin.strip() for origin in explicit.split(",") if origin.strip()]
        if origins:
            return origins

    if debug:
        return list(_DEV_SOCKET_CORS)

    site_url = os.getenv("SITE_URL", "").strip()
    origin = _origin_from_site_url(site_url) if site_url else None
    if origin:
        logger.warning(
            "SOCKETIO_CORS_ORIGINS tanımlı değil; SITE_URL kökeni kullanılıyor: %s",
            origin,
        )
        return [origin]

    logger.warning(
        "SOCKETIO_CORS_ORIGINS ve SITE_URL yok; Socket.IO CORS kısıtlanmadı. "
        "Üretimde SOCKETIO_CORS_ORIGINS ayarlayın."
    )
    return None
