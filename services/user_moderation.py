"""Kullanıcı moderasyon işlemleri ve yetki kontrolleri."""

from datetime import timedelta

from flask import abort, jsonify, request
from flask_login import current_user, logout_user

from constants import BAN_DURATION_OPTIONS
from decorators import is_super_admin
from extensions import db
from models import Atik, Kaynak, Mesaj, Sikayet, User
from utils import utc_now

_SUSPENDED_EXEMPT_PATHS = frozenset({
    "/health",
    "/giris",
    "/kayit",
    "/cikis",
    "/sifremi-unuttum",
    "/destek",
    "/ban-itiraz",
})

_SUSPENDED_EXEMPT_PREFIXES = (
    "/static/",
    "/eposta-dogrula",
    "/sifre-sifirla/",
)


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
        user.banned_by_id = None
    if expired:
        db.session.commit()
    return len(expired)


def is_user_banned(user) -> bool:
    if not user or not getattr(user, "is_banned", False):
        return False
    expires = getattr(user, "ban_expires_at", None)
    if expires and expires <= utc_now():
        return False
    return True


def is_account_suspended(user) -> bool:
    """Ban veya deaktivasyon nedeniyle hesap askıda mı."""
    if not user:
        return False
    if getattr(user, "is_deactivated", False):
        return True
    return is_user_banned(user)


def enforce_active_account():
    """
    Aktif oturumda ban/deaktivasyon kontrolü.
    Askıdaki hesap için logout + 403 döner; aksi halde None.
    """
    if not current_user.is_authenticated:
        return None

    path = request.path or ""
    if path in _SUSPENDED_EXEMPT_PATHS or any(
        path.startswith(prefix) for prefix in _SUSPENDED_EXEMPT_PREFIXES
    ):
        return None

    user = db.session.get(User, int(current_user.get_id()))
    if not user or not is_account_suspended(user):
        return None

    user_id = user.id
    logout_user()
    try:
        from socket_events import disconnect_user_sockets

        disconnect_user_sockets(user_id)
    except Exception:
        pass
    if path.startswith("/api/") or request.is_json:
        return jsonify({"error": "Hesabınız askıya alındı."}), 403
    abort(403)


def parse_ban_duration(duration_key: str | None) -> int | None:
    if not duration_key or duration_key == "permanent":
        return None
    return BAN_DURATION_OPTIONS.get(duration_key)


def normalize_ban_reason(reason: str | None) -> str | None:
    cleaned = (reason or "").strip()
    return cleaned or None


def apply_ban(
    user: User,
    reason: str | None,
    duration_days: int | None,
    *,
    banned_by_id: int | None = None,
) -> None:
    now = utc_now()
    user.is_banned = True
    user.banned_at = now
    user.ban_reason = normalize_ban_reason(reason)
    user.ban_expires_at = (
        now + timedelta(days=duration_days) if duration_days else None
    )
    user.banned_by_id = banned_by_id
    user.is_deactivated = False


def clear_ban(user: User) -> None:
    user.is_banned = False
    user.banned_at = None
    user.ban_reason = None
    user.ban_expires_at = None
    user.banned_by_id = None


def count_active_superadmins(*, exclude_user_id: int | None = None) -> int:
    """Aktif (pasif olmayan) süper admin sayısı."""
    query = User.query.filter(
        User.role == "superadmin",
        User.is_deactivated.is_(False),
    )
    if exclude_user_id is not None:
        query = query.filter(User.id != exclude_user_id)
    return query.count()


def validate_user_deactivation(
    target: User,
    *,
    actor_id: int,
    new_is_deactivated: bool,
) -> None:
    """Pasifleştirme işlemi güvenlik kurallarını doğrular."""
    if not new_is_deactivated:
        return
    if target.id == actor_id:
        raise ValueError("Kendi hesabınızı pasifleştiremezsiniz.")
    if normalize_role(target) == "superadmin":
        if count_active_superadmins(exclude_user_id=target.id) < 1:
            raise ValueError("Son aktif süper admin pasifleştirilemez.")


def toggle_admin_role(user: User) -> tuple[str, str]:
    old = normalize_role(user)
    if old == "superadmin":
        raise ValueError("Süper admin rolü düşürülemez.")
    if user.is_admin:
        user.is_admin = False
        user.role = "user"
    else:
        user.is_admin = True
        user.role = "admin"
    new = normalize_role(user)
    return old, new


def soft_delete_user(user: User, reason: str | None, *, banned_by_id: int | None = None) -> None:
    normalized = normalize_ban_reason(reason)
    if not normalized:
        raise ValueError("Ban sebebi zorunludur")
    apply_ban(user, normalized, None, banned_by_id=banned_by_id)


def deactivate_user(user: User, *, actor_id: int | None = None) -> None:
    if actor_id is not None:
        validate_user_deactivation(
            user,
            actor_id=actor_id,
            new_is_deactivated=True,
        )
    elif normalize_role(user) == "superadmin":
        if count_active_superadmins(exclude_user_id=user.id) < 1:
            raise ValueError("Son aktif süper admin pasifleştirilemez.")
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
