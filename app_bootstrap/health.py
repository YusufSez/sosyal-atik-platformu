from flask import jsonify
from sqlalchemy import text

from app_bootstrap.runtime_state import app_version, uptime_seconds, worker_info
from extensions import db
from services.redis_manager import get_redis_url, health as redis_health
from services.redis_manager import storage_label


def scheduler_health() -> dict:
    from app_bootstrap.scheduler import scheduler_status

    return scheduler_status()


def health_response():
    """/health endpoint yanıtı — veritabanı, Redis ve runtime durumu."""
    db_status = "up"
    overall = "ok"
    http_code = 200

    try:
        db.session.execute(text("SELECT 1"))
    except Exception:
        db_status = "down"
        overall = "degraded"
        http_code = 503

    redis_status = redis_health()
    redis_enabled = bool(get_redis_url())

    if redis_status == "degraded":
        overall = "degraded"
    elif db_status == "down":
        overall = "degraded"

    sched = scheduler_health()
    payload = {
        "status": overall,
        "version": app_version(),
        "uptime_seconds": uptime_seconds(),
        "worker": worker_info(),
        "database": db_status,
        "redis": redis_status,
        "redis_enabled": redis_enabled,
        "storage": storage_label(),
        "scheduler": sched,
    }
    return jsonify(payload), http_code


def database_health_response():
    """Geriye dönük uyumluluk."""
    return health_response()
