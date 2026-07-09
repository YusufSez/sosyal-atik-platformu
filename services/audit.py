"""Yönetici işlemleri denetim kaydı."""

from flask import request
from flask_login import current_user

from extensions import db
from models import AdminAuditLog


def log_admin_action(
    action: str,
    target: str = "",
    detail: str = "",
    *,
    target_user_id: int | None = None,
    reason: str | None = None,
    old_value: str | None = None,
    new_value: str | None = None,
) -> None:
    if not current_user.is_authenticated:
        return

    ip = request.headers.get("X-Forwarded-For", request.remote_addr)
    if ip and "," in ip:
        ip = ip.split(",")[0].strip()

    user_agent = (request.headers.get("User-Agent") or "")[:500]

    kayit = AdminAuditLog(
        admin_id=current_user.id,
        action=action,
        target=target[:200],
        target_user_id=target_user_id,
        detail=detail[:2000] if detail else None,
        reason=(reason[:2000] if reason else None),
        old_value=(old_value[:2000] if old_value else None),
        new_value=(new_value[:2000] if new_value else None),
        ip_address=(ip or "")[:45],
        user_agent=user_agent or None,
    )
    db.session.add(kayit)
    db.session.commit()
