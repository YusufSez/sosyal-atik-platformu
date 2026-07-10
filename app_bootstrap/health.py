from flask import jsonify
from sqlalchemy import text

from extensions import db
from services.redis_manager import health as redis_health
from services.redis_manager import storage_label


def health_response():
    """/health endpoint yanıtı — veritabanı, Redis ve depolama durumu."""
    db_status = "up"
    overall = "ok"
    http_code = 200

    try:
        db.session.execute(text("SELECT 1"))
    except Exception:
        db_status = "down"
        overall = "degraded"
        http_code = 503

    payload = {
        "status": overall,
        "database": db_status,
        "redis": redis_health(),
        "storage": storage_label(),
    }
    return jsonify(payload), http_code


def database_health_response():
    """Geriye dönük uyumluluk."""
    return health_response()
