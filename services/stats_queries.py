"""Paylaşılan platform istatistik sorguları."""

from sqlalchemy import func, select

from extensions import db
from models import Atik, Kaynak, User


def homepage_stats() -> dict:
    """Anasayfa kartları — 3 sorgu (önceden 5 ayrı COUNT)."""
    kaynak_row = db.session.execute(
        select(
            func.count(Kaynak.id),
            func.count().filter(Kaynak.ilan_durumu == "Teslim Edildi"),
        )
    ).one()
    atik_row = db.session.execute(
        select(
            func.count(Atik.id),
            func.count().filter(Atik.ilan_durumu == "Teslim Edildi"),
        )
    ).one()
    user_count = db.session.scalar(select(func.count()).select_from(User)) or 0
    return {
        "kullanici": int(user_count),
        "kaynak": int(kaynak_row[0] or 0),
        "atik": int(atik_row[0] or 0),
        "teslim": int(kaynak_row[1] or 0) + int(atik_row[1] or 0),
    }


def admin_dashboard_counts() -> dict:
    """Admin panel üst sayaçları — tek sorguda 3 tablo."""
    kaynak_count, atik_count, user_count = db.session.execute(
        select(
            select(func.count()).select_from(Kaynak).scalar_subquery(),
            select(func.count()).select_from(Atik).scalar_subquery(),
            select(func.count()).select_from(User).scalar_subquery(),
        )
    ).one()
    return {
        "user_count": int(user_count or 0),
        "kaynak_count": int(kaynak_count or 0),
        "atik_count": int(atik_count or 0),
    }
