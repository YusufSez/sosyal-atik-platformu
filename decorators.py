"""Yetkilendirme dekoratörleri."""

import os
from functools import wraps

from flask import abort, current_app, flash, jsonify, redirect, request, url_for
from flask_login import current_user

from constants import EMAIL_VERIFY_REQUIRED_MSG
from models import User


def _verification_required() -> bool:
    if not current_app.config.get("EMAIL_VERIFICATION_REQUIRED", True):
        return False
    if not current_user.is_authenticated:
        return False
    # Admin / superadmin hesapları e-posta doğrulaması zorunluluğundan muaf.
    if getattr(current_user, "is_admin", False) or getattr(current_user, "role", None) in (
        "admin",
        "superadmin",
    ):
        return False
    return not getattr(current_user, "email_verified", False)


def email_verified_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if _verification_required():
            if request.path.startswith("/api/") or request.is_json:
                return jsonify({"error": EMAIL_VERIFY_REQUIRED_MSG}), 403
            flash(EMAIL_VERIFY_REQUIRED_MSG, "warning")
            return redirect(url_for("auth.eposta_dogrula_bekle"))
        return view(*args, **kwargs)

    return wrapped


def require_email_verified_response():
    """JSON veya form yanıtları için yardımcı; None dönerse işlem devam eder."""
    if not _verification_required():
        return None
    if request.path.startswith("/api/") or request.is_json:
        return jsonify({"error": EMAIL_VERIFY_REQUIRED_MSG}), 403
    flash(EMAIL_VERIFY_REQUIRED_MSG, "warning")
    return redirect(url_for("auth.eposta_dogrula_bekle"))


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user.is_authenticated:
            abort(403)
        role = getattr(current_user, "role", None)
        if role in ("admin", "superadmin"):
            return view(*args, **kwargs)
        # Geriye uyumluluk: role alanı yoksa is_admin ile devam et.
        if not getattr(current_user, "is_admin", False):
            abort(403)
        return view(*args, **kwargs)

    return wrapped


def is_super_admin(user) -> bool:
    if not user or not user.is_authenticated:
        return False

    role = getattr(user, "role", None)
    if role == "superadmin":
        return True

    # Yeni akış: SUPERADMIN_EMAIL'i kullan.
    # Eğer tanımlı değilse geriye dönük uyumluluk için ADMIN_EMAIL'e fallback yapılır.
    super_email = os.getenv("SUPERADMIN_EMAIL", "").strip().lower()
    admin_email = os.getenv("ADMIN_EMAIL", "").strip().lower()
    target_email = super_email or admin_email
    if target_email:
        # superadmin için is_admin/role eşleşmesi beklenir.
        if not getattr(user, "is_admin", False):
            return False
        return (user.email or "").lower() == target_email

    # Env hiç tanımlı değilse: geriye uyumluluk (ilk admin).
    first_admin = User.query.filter_by(is_admin=True).order_by(User.id.asc()).first()
    return first_admin is not None and first_admin.id == user.id


def super_admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not is_super_admin(current_user):
            abort(403)
        return view(*args, **kwargs)

    return wrapped
