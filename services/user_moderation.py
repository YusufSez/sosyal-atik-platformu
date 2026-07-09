"""Kullanıcı moderasyon işlemleri ve yetki kontrolleri."""

from datetime import timedelta

from flask_login import current_user

from constants import BAN_DURATION_OPTIONS
from decorators import is_super_admin
from extensions import db
from models import Atik, Kaynak, Mesaj, Sikayet, User
from utils import utc_now


def normalize_role(user) -> str:
    if not user:
        return "user"
    role = getattr(user, "role", None)
    if role:
        return role
    return "admin" if getattr(user, "is_admin", False) else "user"


def can_superadmin_manage_user(actor, target) -> bool:
    if not actor or not target:
        return False
    if target.id == actor.id:
        return False
    if is_super_admin(target):
        return False
    if normalize_role(target) == "admin" and not is_super_admin(actor):
        return False
    return is_super_admin(actor)


def can_admin_review_report(actor) -> bool:
    role = normalize_role(actor)
    return role in ("admin", "superadmin") or getattr(actor, "is_admin", False)


def expire_temporary_bans() -> int:
    now = utc_now()
    expired = User.query.filter(
        User.is_banned.is_(True),
        User.ban_expires_at.isnot(None),
        User.ban_expires_at <= now,
    ).all()
    for user in expired:
        user.is_banned = False
        user.banned_at = None
        user.ban_reason = None
        user.ban_expires_at = None
    if expired:
        db.session.commit()
    return len(expired)


def is_user_banned(user) -> bool:
    if not user or not getattr(user, "is_banned", False):
        return False
    expires = getattr(user, "ban_expires_at", None)
    if expires and expires <= utc_now():
        user.is_banned = False
        user.banned_at = None
        user.ban_reason = None
        user.ban_expires_at = None
        db.session.commit()
        return False
    return True


def parse_ban_duration(duration_key: str | None) -> int | None:
    if not duration_key or duration_key == "permanent":
        return None
    return BAN_DURATION_OPTIONS.get(duration_key)


def apply_ban(user: User, reason: str | None, duration_days: int | None) -> None:
    now = utc_now()
    user.is_banned = True
    user.banned_at = now
    user.ban_reason = (reason or "").strip() or None
    user.ban_expires_at = (
        now + timedelta(days=duration_days) if duration_days else None
    )
    user.is_deactivated = False


def clear_ban(user: User) -> None:
    user.is_banned = False
    user.banned_at = None
    user.ban_reason = None
    user.ban_expires_at = None


def toggle_admin_role(user: User) -> tuple[str, str]:
    old = normalize_role(user)
    if user.is_admin:
        user.is_admin = False
        user.role = "user"
    else:
        user.is_admin = True
        user.role = "admin"
    new = normalize_role(user)
    return old, new


def soft_delete_user(user: User, reason: str | None) -> None:
    apply_ban(user, reason or "Silindi", None)


def deactivate_user(user: User) -> None:
    user.is_deactivated = True


def activate_user(user: User) -> None:
    user.is_deactivated = False


def kullanici_istatistikleri(user_id: int) -> dict:
    paylasim = (
        Kaynak.query.filter_by(user_id=user_id).count()
        + Atik.query.filter_by(user_id=user_id).count()
    )
    return {
        "paylasim": paylasim,
        "mesaj_gonderilen": Mesaj.query.filter_by(sender_id=user_id).count(),
        "mesaj_alinan": Mesaj.query.filter_by(receiver_id=user_id).count(),
        "sikayet_alinan": Sikayet.query.filter_by(reported_user_id=user_id).count(),
        "sikayet_olusturulan": Sikayet.query.filter_by(user_id=user_id).count(),
    }


def resolve_reported_user_id(
    *,
    reporter_id: int,
    mesaj_id=None,
    kaynak_id=None,
    atik_id=None,
) -> tuple[str | None, int | None]:
    if mesaj_id:
        mesaj = db.session.get(Mesaj, mesaj_id)
        if not mesaj:
            return "mesaj", None
        reported = mesaj.sender_id if mesaj.sender_id != reporter_id else mesaj.receiver_id
        return "mesaj", reported
    if kaynak_id:
        kaynak = db.session.get(Kaynak, kaynak_id)
        return "kaynak", kaynak.user_id if kaynak else None
    if atik_id:
        atik = db.session.get(Atik, atik_id)
        return "atik", atik.user_id if atik else None
    return None, None
