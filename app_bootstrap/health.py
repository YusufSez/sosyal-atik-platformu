from flask import jsonify
from sqlalchemy import text

from extensions import db


def database_health_response():
    """/health endpoint'i için veritabanı durum yanıtı."""
    try:
        db.session.execute(text("SELECT 1"))
        return jsonify(status="ok", database="up"), 200
    except Exception:
        return jsonify(status="degraded", database="down"), 503
