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
    return [joinedload(Sikayet.user)]


def audit_listesi_options():
    return [joinedload(AdminAuditLog.admin)]
