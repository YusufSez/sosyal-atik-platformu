"""Ortam değişkenleri ve .env yükleme politikası."""

from __future__ import annotations

import os

# Tek kaynak: dağınık ortam adı karşılaştırması yapılmaz.
_TESTING_ENVS = frozenset({"test", "testing"})
_DEVELOPMENT_ENVS = frozenset({"development", "dev", "local"})
_PRODUCTION_ENVS = frozenset({"production", "prod"})


def env_to_bool(value, default=False):
    if value is None:
        return default
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def resolve_app_env() -> str:
    """
    Çalışma ortamını mevcut mimariye göre çözer.

    Öncelik: APP_ENV → FLASK_ENV → TESTING → DEBUG → production (güvenli varsayılan).
    VPS/Docker'da APP_ENV/FLASK_ENV yok + DEBUG=False → production.
    """
    for key in ("APP_ENV", "FLASK_ENV"):
        value = (os.getenv(key) or "").strip().lower()
        if value:
            return value
    if env_to_bool(os.getenv("TESTING"), default=False) or bool(os.getenv("PYTEST_CURRENT_TEST")):
        return "testing"
    if env_to_bool(os.getenv("DEBUG"), default=False):
        return "development"
    return "production"


def is_testing_runtime() -> bool:
    """pytest / CI / FLASK_ENV=testing — kişisel .env okunmamalı."""
    if env_to_bool(os.getenv("TESTING"), default=False):
        return True
    if env_to_bool(os.getenv("SKIP_DOTENV"), default=False):
        return True
    return resolve_app_env() in _TESTING_ENVS


def is_development_runtime() -> bool:
    """Yerel geliştirme (production fail-fast doğrulaması uygulanmaz)."""
    return resolve_app_env() in _DEVELOPMENT_ENVS


def is_production_env() -> bool:
    """Production fail-fast doğrulamasının uygulanacağı ortam."""
    env = resolve_app_env()
    if env in _PRODUCTION_ENVS:
        return True
    if env in _TESTING_ENVS or env in _DEVELOPMENT_ENVS:
        return False
    # Bilinmeyen değerler production sayılır (güvenli taraf).
    return True


def load_app_dotenv(*, override: bool = False) -> bool:
    """Production / development / Docker / VPS: .env yükle. Test runtime: no-op.

    Returns:
        True if a .env file was considered for loading; False if skipped.
    """
    if is_testing_runtime():
        return False
    from dotenv import load_dotenv

    load_dotenv(override=override)
    return True
