"""Admin kullanıcı detay sayfası verileri."""

from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.orm import joinedload

from extensions import db
from models import (
    AdminAuditLog,
    Atik,
    Bildirim,
    Comment,
    IlanModerasyonAnaliz,
    Kaynak,
    Mesaj,
    User,
)
from services.gamification import kullanici_rozet_listesi, seviye_hesapla
from services.user_moderation import normalize_role


def build_admin_user_detail(user: User) -> dict:
    user_id = user.id
    ilan_sayisi = (
        (db.session.scalar(
            select(func.count()).select_from(Kaynak).where(Kaynak.user_id == user_id)
        ) or 0)
        + (db.session.scalar(
            select(func.count()).select_from(Atik).where(Atik.user_id == user_id)
        ) or 0)
    )
    mesaj_sayisi = db.session.scalar(
        select(func.count())
        .select_from(Mesaj)
        .where(or_(Mesaj.sender_id == user_id, Mesaj.receiver_id == user_id))
    ) or 0
    yorum_sayisi = db.session.scalar(
        select(func.count()).select_from(Comment).where(Comment.user_id == user_id)
    ) or 0
    bildirim_sayisi = db.session.scalar(
        select(func.count()).select_from(Bildirim).where(Bildirim.user_id == user_id)
    ) or 0

    kaynak_subq = select(Kaynak.id).where(Kaynak.user_id == user_id)
    atik_subq = select(Atik.id).where(Atik.user_id == user_id)

    moderasyon_kayitlari = (
        IlanModerasyonAnaliz.query.filter(
            IlanModerasyonAnaliz.is_current.is_(True),
            or_(
                IlanModerasyonAnaliz.kaynak_id.in_(kaynak_subq),
                IlanModerasyonAnaliz.atik_id.in_(atik_subq),
            ),
        )
        .order_by(IlanModerasyonAnaliz.id.desc())
        .limit(20)
        .all()
    )

    audit_kayitlari = (
        AdminAuditLog.query.options(joinedload(AdminAuditLog.admin))
        .filter(
            or_(
                AdminAuditLog.target_user_id == user_id,
                AdminAuditLog.target == f"user:{user_id}",
            )
        )
        .order_by(AdminAuditLog.id.desc())
        .limit(20)
        .all()
    )

    role = normalize_role(user)
    return {
        "user": user,
        "role": role,
        "is_superadmin": role == "superadmin",
        "is_admin": user.is_admin or role in ("admin", "superadmin"),
        "seviye": seviye_hesapla(user.xp),
        "rozetler": kullanici_rozet_listesi(user),
        "ilan_sayisi": ilan_sayisi,
        "mesaj_sayisi": mesaj_sayisi,
        "yorum_sayisi": yorum_sayisi,
        "bildirim_sayisi": bildirim_sayisi,
        "moderasyon_kayitlari": moderasyon_kayitlari,
        "audit_kayitlari": audit_kayitlari,
    }
