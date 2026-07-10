"""Admin kullanıcı detay sayfası verileri."""

from __future__ import annotations

from sqlalchemy import or_
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
        Kaynak.query.filter_by(user_id=user_id).count()
        + Atik.query.filter_by(user_id=user_id).count()
    )
    mesaj_sayisi = (
        Mesaj.query.filter_by(sender_id=user_id).count()
        + Mesaj.query.filter_by(receiver_id=user_id).count()
    )
    yorum_sayisi = Comment.query.filter_by(user_id=user_id).count()
    bildirim_sayisi = Bildirim.query.filter_by(user_id=user_id).count()

    kaynak_ids = [row[0] for row in db.session.query(Kaynak.id).filter_by(user_id=user_id).all()]
    atik_ids = [row[0] for row in db.session.query(Atik.id).filter_by(user_id=user_id).all()]

    moderasyon_kayitlari = []
    if kaynak_ids or atik_ids:
        q = IlanModerasyonAnaliz.query.filter(IlanModerasyonAnaliz.is_current.is_(True))
        filters = []
        if kaynak_ids:
            filters.append(IlanModerasyonAnaliz.kaynak_id.in_(kaynak_ids))
        if atik_ids:
            filters.append(IlanModerasyonAnaliz.atik_id.in_(atik_ids))
        moderasyon_kayitlari = q.filter(or_(*filters)).order_by(
            IlanModerasyonAnaliz.id.desc()
        ).limit(20).all()

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
