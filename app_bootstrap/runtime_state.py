"""Çalışma zamanı durumu — health ve monitoring."""

from __future__ import annotations

import os
import time

_START_MONOTONIC = time.monotonic()
_START_WALL = time.time()


def uptime_seconds() -> int:
    return int(time.monotonic() - _START_MONOTONIC)


def started_at_iso() -> str:
    from datetime import datetime, timezone

    return datetime.fromtimestamp(_START_WALL, tz=timezone.utc).isoformat()


def app_version() -> str:
    return (os.getenv("APP_VERSION") or "1.0.0").strip() or "1.0.0"


def worker_info() -> dict:
    workers = int(os.getenv("GUNICORN_WORKERS", "1") or "1")
    worker_class = (os.getenv("GUNICORN_WORKER_CLASS") or "sync").strip()
    return {
        "class": worker_class,
        "count": workers,
        "label": f"{worker_class}x{workers}",
    }
