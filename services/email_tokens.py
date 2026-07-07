"""İmzalı, süreli ve tek kullanımlık e-posta tokenları."""

import secrets
from datetime import datetime, timedelta

from flask import current_app
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from extensions import db
from models import EmailToken, User


def _now() -> datetime:
    return datetime.utcnow()

VERIFY_SALT = "email-verify-v1"
RESET_SALT = "password-reset-v1"


def _serializer(salt: str) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"], salt=salt)


def _invalidate_pending(user_id: int, purpose: str) -> None:
    now = _now()
    EmailToken.query.filter_by(user_id=user_id, purpose=purpose, used_at=None).update(
        {"used_at": now}
    )


def _create_token_record(user_id: int, purpose: str, hours: int = 24) -> str:
    _invalidate_pending(user_id, purpose)
    nonce = secrets.token_urlsafe(24)
    row = EmailToken(
        user_id=user_id,
        purpose=purpose,
        nonce=nonce,
        expires_at=_now() + timedelta(hours=hours),
    )
    db.session.add(row)
    db.session.commit()
    return nonce


def create_verify_token(user: User) -> str:
    nonce = _create_token_record(user.id, "verify")
    return _serializer(VERIFY_SALT).dumps({"uid": user.id, "n": nonce})


def create_reset_token(user: User) -> str:
    nonce = _create_token_record(user.id, "reset")
    return _serializer(RESET_SALT).dumps({"uid": user.id, "n": nonce})


def _consume_token(token: str, purpose: str):
    salt = VERIFY_SALT if purpose == "verify" else RESET_SALT
    max_age = current_app.config.get("EMAIL_TOKEN_MAX_AGE", 86400)
    try:
        data = _serializer(salt).loads(token, max_age=max_age)
    except SignatureExpired:
        return None, "expired"
    except BadSignature:
        return None, "invalid"

    row = EmailToken.query.filter_by(
        user_id=data["uid"],
        purpose=purpose,
        nonce=data["n"],
        used_at=None,
    ).first()
    if not row or row.expires_at < _now():
        return None, "invalid"

    row.used_at = _now()
    db.session.commit()
    user = db.session.get(User, data["uid"])
    if not user:
        return None, "invalid"
    return user, None


def verify_email_token(token: str):
    return _consume_token(token, "verify")


def verify_reset_token(token: str):
    return _consume_token(token, "reset")


def peek_token(token: str, purpose: str):
    """Token geçerliliğini kontrol eder; tüketmez."""
    salt = VERIFY_SALT if purpose == "verify" else RESET_SALT
    max_age = current_app.config.get("EMAIL_TOKEN_MAX_AGE", 86400)
    try:
        data = _serializer(salt).loads(token, max_age=max_age)
    except SignatureExpired:
        return None, "expired"
    except BadSignature:
        return None, "invalid"

    row = EmailToken.query.filter_by(
        user_id=data["uid"],
        purpose=purpose,
        nonce=data["n"],
        used_at=None,
    ).first()
    if not row or row.expires_at < _now():
        return None, "invalid"

    user = db.session.get(User, data["uid"])
    if not user:
        return None, "invalid"
    return user, None
