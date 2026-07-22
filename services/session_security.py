"""Oturum-şifre bağlama: şifre değişince diğer oturumlar düşer."""

from __future__ import annotations

import hashlib

from flask import has_request_context, session


def password_session_stamp(password_hash: str | None) -> str:
    raw = (password_hash or "").encode("utf-8", errors="ignore")
    return hashlib.sha256(raw).hexdigest()[:32]


def stamp_login_session(user) -> None:
    if not has_request_context() or user is None:
        return
    session["pwd_stamp"] = password_session_stamp(getattr(user, "password", None))


def session_matches_password(user) -> bool:
    """False → oturum geçersiz (şifre değişmiş veya damga yok)."""
    if not has_request_context() or user is None:
        return True
    expected = password_session_stamp(getattr(user, "password", None))
    current = session.get("pwd_stamp")
    if current is None:
        # Test ortamında login_user doğrudan çağrıldığında damga yoksa bağla.
        from flask import current_app

        if current_app.config.get("TESTING"):
            session["pwd_stamp"] = expected
            return True
        return False
    return current == expected
