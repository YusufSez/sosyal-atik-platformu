"""Superadmin kullanıcı düzenleme servisi."""

from __future__ import annotations

import re
from typing import Any

from werkzeug.datastructures import FileStorage

from extensions import db
from models import User
from services.audit import log_admin_action
from services.user_moderation import (
    count_active_superadmins,
    normalize_role,
    validate_user_deactivation,
)
from utils import delete_profile_picture, sanitize_input, save_profile_picture

_IMMUTABLE_USER_FIELDS = (
    "role",
    "is_admin",
    "is_banned",
    "banned_at",
    "ban_reason",
    "ban_expires_at",
    "banned_by_id",
    "password",
    "xp",
    "guven_puani",
    "is_kurum",
    "last_login_at",
    "last_seen",
    "terms_accepted_at",
    "email_verified_at",
)


class UserEditError(Exception):
    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


def _normalize_phone(phone: str | None) -> str | None:
    cleaned = (phone or "").strip()
    return cleaned or None


def _phone_taken(phone: str | None, exclude_user_id: int) -> bool:
    normalized = _normalize_phone(phone)
    if not normalized:
        return False
    existing = User.query.filter(
        User.id != exclude_user_id,
        User.telefon.isnot(None),
        User.telefon != "",
        User.telefon == normalized,
    ).first()
    return existing is not None


def _username_taken(username: str, exclude_user_id: int) -> bool:
    return (
        User.query.filter(
            User.id != exclude_user_id,
            db.func.lower(User.username) == username.lower(),
        ).first()
        is not None
    )


def _email_taken(email: str, exclude_user_id: int) -> bool:
    return (
        User.query.filter(
            User.id != exclude_user_id,
            db.func.lower(User.email) == email.lower(),
        ).first()
        is not None
    )


def _validate_name_optional(value: str, label: str) -> str | None:
    cleaned = sanitize_input(value, max_length=100)
    if not cleaned:
        return None
    if len(cleaned) < 2:
        raise UserEditError(f"{label} en az 2 karakter olmalıdır.")
    if not re.match(r"^[\w\sçğıöşüÇĞİÖŞÜ]+$", cleaned):
        raise UserEditError(f"{label} yalnızca harf ve boşluk içerebilir.")
    return cleaned


def _validate_username(username: str) -> str:
    cleaned = sanitize_input(username, max_length=30)
    if len(cleaned) < 3:
        raise UserEditError("Kullanıcı adı en az 3 karakter olmalıdır.")
    if not re.match(r"^[\w]+$", cleaned):
        raise UserEditError(
            "Kullanıcı adı yalnızca harf, rakam ve alt çizgi içerebilir (boşluk kullanmayın)."
        )
    return cleaned


def _validate_email(email: str) -> str:
    cleaned = sanitize_input(email, max_length=150).lower().strip()
    if not re.match(r"^[\w.+-]+@[\w-]+\.[\w.-]+$", cleaned):
        raise UserEditError("Geçerli bir e-posta adresi giriniz.")
    return cleaned


def _serialize(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "1" if value else "0"
    return str(value)


def _parse_bool(name: str, form) -> bool:
    return form.get(name) in ("1", "on", "true", "True")


def parse_admin_user_edit_form(form, files) -> dict:
    return {
        "ad": _validate_name_optional(form.get("ad"), "Ad"),
        "soyad": _validate_name_optional(form.get("soyad"), "Soyad"),
        "username": _validate_username(form.get("username")),
        "email": _validate_email(form.get("email")),
        "telefon": sanitize_input(form.get("telefon"), max_length=20) or None,
        "il": sanitize_input(form.get("il"), max_length=100) or None,
        "ilce": sanitize_input(form.get("ilce"), max_length=100) or None,
        "adres": sanitize_input(form.get("adres"), max_length=255) or None,
        "profil_aciklama": sanitize_input(form.get("profil_aciklama"), max_length=2000) or None,
        "is_deactivated": _parse_bool("is_deactivated", form),
        "email_verified": _parse_bool("email_verified", form),
        "telefon_verified": _parse_bool("telefon_verified", form),
        "remove_profile_image": _parse_bool("remove_profile_image", form),
        "profile_image": files.get("profile_image"),
    }


def apply_admin_user_edit(
    user: User,
    data: dict,
    *,
    actor_id: int,
) -> list[tuple[str, str, str]]:
    """
    Kullanıcı alanlarını günceller.
    Dönüş: [(alan_adı, eski_değer, yeni_değer), ...]
    """
    immutable_snapshot = {field: getattr(user, field) for field in _IMMUTABLE_USER_FIELDS}

    if _username_taken(data["username"], user.id):
        raise UserEditError("Bu kullanıcı adı zaten alınmış.")
    if _email_taken(data["email"], user.id):
        raise UserEditError("Bu e-posta zaten kayıtlı.")
    if _phone_taken(data["telefon"], user.id):
        raise UserEditError("Bu telefon numarası zaten kayıtlı.")

    try:
        validate_user_deactivation(
            user,
            actor_id=actor_id,
            new_is_deactivated=data["is_deactivated"],
        )
    except ValueError as exc:
        raise UserEditError(str(exc)) from exc

    changes: list[tuple[str, str, str]] = []
    scalar_fields = (
        "ad",
        "soyad",
        "username",
        "email",
        "telefon",
        "il",
        "ilce",
        "adres",
        "profil_aciklama",
        "is_deactivated",
        "email_verified",
        "telefon_verified",
    )
    for field in scalar_fields:
        new_val = data[field]
        old_val = getattr(user, field)
        if _serialize(old_val) != _serialize(new_val):
            changes.append((field, _serialize(old_val), _serialize(new_val)))
            setattr(user, field, new_val)

    profile_file: FileStorage | None = data.get("profile_image")
    if profile_file and profile_file.filename:
        try:
            new_image = save_profile_picture(profile_file)
        except ValueError as exc:
            raise UserEditError(str(exc)) from exc
        old_image = user.profile_image or "default.jpg"
        if old_image != new_image:
            changes.append(("profile_image", old_image, new_image))
            delete_profile_picture(user.profile_image)
            user.profile_image = new_image
    elif data.get("remove_profile_image") and (user.profile_image or "default.jpg") != "default.jpg":
        old_image = user.profile_image or "default.jpg"
        changes.append(("profile_image", old_image, "default.jpg"))
        delete_profile_picture(user.profile_image)
        user.profile_image = "default.jpg"

    for field, original in immutable_snapshot.items():
        if getattr(user, field) != original:
            raise UserEditError("Yetki veya moderasyon alanları düzenlenemez.")

    if not changes:
        return changes

    db.session.commit()
    for field, old_val, new_val in changes:
        log_admin_action(
            "user_edit",
            target=f"user:{user.id}",
            target_user_id=user.id,
            detail=field,
            old_value=old_val,
            new_value=new_val,
        )
    return changes


def can_deactivate_user_in_admin_edit(target: User, *, actor_id: int) -> bool:
    """UI için pasifleştirme izni (sunucu tarafı doğrulama yine zorunlu)."""
    if target.id == actor_id:
        return False
    if normalize_role(target) != "superadmin":
        return True
    return count_active_superadmins(exclude_user_id=target.id) >= 1


def find_registered_user_by_email(email: str | None) -> User | None:
    cleaned = (email or "").strip().lower()
    if not cleaned:
        return None
    return User.query.filter(db.func.lower(User.email) == cleaned).first()
