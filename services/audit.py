"""Yönetici işlemleri denetim kaydı."""

from flask import request
from flask_login import current_user

from extensions import db
from models import AdminAuditLog


def log_admin_action(action: str, target: str = "", detail: str = "") -> None:
    if not current_user.is_authenticated:
        return

    ip = request.headers.get("X-Forwarded-For", request.remote_addr)
    if ip and "," in ip:
        ip = ip.split(",")[0].strip()

    kayit = AdminAuditLog(
        admin_id=current_user.id,
        action=action,
        target=target[:200],
        detail=detail[:2000] if detail else None,
        ip_address=(ip or "")[:45],
    )
    db.session.add(kayit)
    db.session.commit()
