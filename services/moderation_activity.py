"""Moderasyon paneli admin activity log."""

from __future__ import annotations

from flask import request
from flask_login import current_user

from extensions import db
from models import IlanModerasyonActivityLog, User
from sqlalchemy.orm import joinedload
from utils import utc_now


def _request_meta() -> tuple[str | None, str | None]:
    from services.client_ip import client_ip

    ip = client_ip() if request else None
    user_agent = (request.headers.get("User-Agent") or "")[:500] if request else None
    return ip, user_agent


def log_moderasyon_activity(
    action: str,
    tur: str | None = None,
    ilan_id: int | None = None,
    note: str | None = None,
    admin_user_id: int | None = None,
) -> IlanModerasyonActivityLog:
    """Moderasyon admin işlemini kaydeder."""
    ip, user_agent = _request_meta()
    kayit = IlanModerasyonActivityLog(
        tur=tur,
        kaynak_id=ilan_id if tur == "kaynak" else None,
        atik_id=ilan_id if tur == "atik" else None,
        admin_user_id=admin_user_id or current_user.id,
        action=action,
        note=(note[:2000] if note else None),
        ip_address=ip,
        user_agent=user_agent,
        created_at=utc_now(),
    )
    db.session.add(kayit)
    return kayit


def activity_listesi(
    *,
    action: str | None = None,
    admin_id: int | None = None,
    tur: str | None = None,
    limit: int = 100,
) -> list[IlanModerasyonActivityLog]:
    """Activity log listesi (yeniden eskiye)."""
    q = IlanModerasyonActivityLog.query
    if action:
        q = q.filter(IlanModerasyonActivityLog.action == action)
    if admin_id:
        q = q.filter(IlanModerasyonActivityLog.admin_user_id == admin_id)
    if tur:
        q = q.filter(IlanModerasyonActivityLog.tur == tur)
    return (
        q.options(joinedload(IlanModerasyonActivityLog.admin))
        .order_by(IlanModerasyonActivityLog.created_at.desc())
        .limit(limit)
        .all()
    )


def activity_dict(log: IlanModerasyonActivityLog) -> dict:
    """Şablon için activity satırı."""
    ilan_id = log.kaynak_id or log.atik_id
    ilan_label = f"{log.tur}:{ilan_id}" if log.tur and ilan_id else "—"
    return {
        "id": log.id,
        "admin": log.admin.username if log.admin else "?",
        "action": log.action,
        "ilan": ilan_label,
        "tur": log.tur,
        "ilan_id": ilan_id,
        "created_at": log.created_at,
        "ip_address": log.ip_address,
        "user_agent": log.user_agent,
        "note": log.note,
    }
