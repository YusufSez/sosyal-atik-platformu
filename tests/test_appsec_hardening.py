"""AppSec regression — session stamp, municipality geo lock, client IP."""

from auth_utils import hash_password
from extensions import db
from models import User
from services.client_ip import client_ip
from services.session_security import password_session_stamp, stamp_login_session


def _login(client, email, password="TestPass1"):
    return client.post(
        "/giris",
        data={"email": email, "password": password},
        follow_redirects=True,
    )


def test_password_change_invalidates_other_session_stamp(app, client):
    """Şifre değişince eski pwd_stamp eşleşmez (oturum düşer)."""
    with app.app_context():
        user = User(
            username="stamp_user",
            email="stamp_user@test.com",
            password=hash_password("TestPass1"),
            is_completed=True,
            email_verified=True,
            role="user",
        )
        db.session.add(user)
        db.session.commit()
        old_stamp = password_session_stamp(user.password)
        user.password = hash_password("TestPass2!")
        db.session.commit()
        new_stamp = password_session_stamp(user.password)
        assert old_stamp != new_stamp

    with app.test_request_context("/"):
        from flask import session

        session["pwd_stamp"] = old_stamp
        with app.app_context():
            u = User.query.filter_by(email="stamp_user@test.com").first()
            from services.session_security import session_matches_password

            assert session_matches_password(u) is False
            session["pwd_stamp"] = new_stamp
            assert session_matches_password(u) is True


def test_municipality_cannot_override_il_query(client, app):
    with app.app_context():
        muni = User(
            username="muni_geo",
            email="muni_geo@test.com",
            password=hash_password("TestPass1"),
            is_completed=True,
            email_verified=True,
            role="municipality",
            il="İstanbul",
            ilce="Kadıköy",
        )
        db.session.add(muni)
        db.session.commit()

    _login(client, "muni_geo@test.com")
    from blueprints.belediye import _filters_from_request
    from flask_login import login_user

    with app.test_request_context("/belediye/dashboard?il=Ankara&ilce=Çankaya"):
        with app.app_context():
            user = User.query.filter_by(email="muni_geo@test.com").first()
            login_user(user)
            stamp_login_session(user)
            filters = _filters_from_request()
            assert filters["il"] == "İstanbul"
            assert filters["ilce"] == "Kadıköy"
            assert filters["mahalle"] is None


def test_client_ip_ignores_leftmost_xff(app):
    with app.test_request_context(
        "/",
        environ_base={"REMOTE_ADDR": "203.0.113.10"},
        headers={"X-Forwarded-For": "1.2.3.4, 203.0.113.10"},
    ):
        # ProxyFix yoksa remote_addr ortamdan gelir; spoof edilen sol değer kullanılmaz.
        assert client_ip() == "203.0.113.10"
