"""Sık kullanılan ORM eager-loading seçenekleri (N+1 önleme)."""

from sqlalchemy.orm import joinedload, selectinload

from models import AdminAuditLog, Atik, Comment, Kaynak, Sikayet


def ilan_listesi_options(model):
    return [selectinload(model.fotograflar), joinedload(model.sahip)]


def ilan_detay_options(model):
    return [joinedload(model.sahip), selectinload(model.fotograflar)]


def yorum_agaci_options():
    return [
        joinedload(Comment.user),
        selectinload(Comment.replies).joinedload(Comment.user),
    ]


def sikayet_listesi_options():
    return [
        joinedload(Sikayet.user),
        joinedload(Sikayet.reported_user),
    ]


def sikayet_detay_options():
    return [
        joinedload(Sikayet.user),
        joinedload(Sikayet.reported_user),
        joinedload(Sikayet.reviewer),
        joinedload(Sikayet.mesaj),
        joinedload(Sikayet.kaynak),
        joinedload(Sikayet.atik),
    ]


def audit_listesi_options():
    return [
        joinedload(AdminAuditLog.admin),
        joinedload(AdminAuditLog.target_user),
    ]
