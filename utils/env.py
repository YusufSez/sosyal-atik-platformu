"""Ortam değişkenleri ve .env yükleme politikası."""

from __future__ import annotations

import os


def env_to_bool(value, default=False):
    if value is None:
        return default
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def is_testing_runtime() -> bool:
    """pytest / CI / FLASK_ENV=testing — kişisel .env okunmamalı."""
    if env_to_bool(os.getenv("TESTING"), default=False):
        return True
    if (os.getenv("FLASK_ENV") or "").strip().lower() == "testing":
        return True
    if (os.getenv("APP_ENV") or "").strip().lower() in {"test", "testing"}:
        return True
    if env_to_bool(os.getenv("SKIP_DOTENV"), default=False):
        return True
    return False


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
