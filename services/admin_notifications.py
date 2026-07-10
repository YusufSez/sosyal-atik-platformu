"""Admin kullanıcı bildirimleri."""

from __future__ import annotations

import logging

from extensions import db
from models import User
from services.notifications import bildirim_olustur_coklu

logger = logging.getLogger(__name__)


def _admin_users():
    return User.query.filter(
        User.is_deactivated.is_(False),
        db.or_(
            User.is_admin.is_(True),
            User.role.in_(("admin", "superadmin")),
        ),
    ).all()


def notify_admins(baslik: str, icerik: str, tur: str, link: str | None = None) -> None:
    admins = _admin_users()
    if not admins:
        return
    kayitlar = [
        {
            "user_id": admin.id,
            "baslik": baslik,
            "icerik": icerik,
            "tur": tur,
            "link": link,
        }
        for admin in admins
    ]
    try:
        bildirim_olustur_coklu(kayitlar)
    except Exception:
        logger.exception("Admin bildirimleri oluşturulamadı tur=%s", tur)
        raise
