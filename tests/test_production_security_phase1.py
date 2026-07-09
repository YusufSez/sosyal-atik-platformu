"""Production Security Phase 1 testleri."""

from unittest.mock import patch

import pytest
from werkzeug.exceptions import Forbidden
from socketio.exceptions import ConnectionRefusedError

from factory import create_app
from auth_utils import hash_password
from extensions import db
from models import User
from services.admin_bootstrap import bootstrap_admin_from_env
from services.moderation_photos import (
    analyze_upload_photos,
    pick_primary_photo_analysis,
)
from services.user_moderation import apply_ban, deactivate_user


def _create_user(
    app,
    *,
    username: str,
    email: str,
    password: str = "TestPass1",
    email_verified: bool = False,
    role: str = "user",
    is_admin: bool = False,
):
    with app.app_context():
        user = User(
            username=username,
            email=email,
            password=hash_password(password),
            is_completed=True,
            email_verified=email_verified,
            role=role,
            is_admin=is_admin,
        )
        db.session.add(user)
        db.session.commit()
        return user.id


def test_bootstrap_promotes_verified_existing_user(monkeypatch, app):
    monkeypatch.setenv("SUPERADMIN_EMAIL", "admin@atikport.com")
    _create_user(app, username="admin1", email="admin@atikport.com", email_verified=True)

    with app.app_context():
        assert bootstrap_admin_from_env() is True
        user = User.query.filter_by(email="admin@atikport.com").first()
        assert user.role == "superadmin"
        assert user.is_admin is True


def test_bootstrap_skips_unverified_user(monkeypatch, app):
    monkeypatch.setenv("SUPERADMIN_EMAIL", "pending@atikport.com")
    _create_user(app, username="pending", email="pending@atikport.com", email_verified=False)

    with app.app_context():
        assert bootstrap_admin_from_env() is False
        user = User.query.filter_by(email="pending@atikport.com").first()
        assert user.role == "user"
        assert user.is_admin is False


def test_bootstrap_idempotent_for_existing_superadmin(monkeypatch, app):
    monkeypatch.setenv("SUPERADMIN_EMAIL", "sa@atikport.com")
    _create_user(
        app,
        username="sa",
        email="sa@atikport.com",
        email_verified=True,
        role="superadmin",
        is_admin=True,
    )

    with app.app_context():
        assert bootstrap_admin_from_env() is True
        assert User.query.filter_by(role="superadmin").count() == 1


def test_bootstrap_does_not_create_second_superadmin(monkeypatch, app):
    monkeypatch.setenv("SUPERADMIN_EMAIL", "new@atikport.com")
    _create_user(
        app,
        username="existing_sa",
        email="old@atikport.com",
        email_verified=True,
        role="superadmin",
        is_admin=True,
    )
    _create_user(app, username="new_sa", email="new@atikport.com", email_verified=True)

    with app.app_context():
        assert bootstrap_admin_from_env() is False
        new_user = User.query.filter_by(email="new@atikport.com").first()
        assert new_user.role == "user"
        assert User.query.filter_by(role="superadmin").count() == 1


def test_analyze_upload_photos_uses_max_risk(app):
    def fake_analyze(path, tur, aciklama, baslik=None, kategori_secim=None):
        if path.endswith("a.jpg"):
            return {"risk_skoru": 10, "guvenli": True, "kategori": "Diğer", "confidence": 0.5}
        return {"risk_skoru": 85, "guvenli": False, "uygunsuz": True, "kategori": "Diğer", "confidence": 0.9}

    def fake_analyze_photo(path, tur, baslik, aciklama, index, analyze_fn=None):
        raw = (analyze_fn or fake_analyze)(path, tur, aciklama, baslik)
        return {
            "index": index,
            "filename": path.split("/")[-1],
            "label": "Diğer",
            "confidence": float(raw.get("confidence", 0.5)),
            "risk_score": int(raw.get("risk_skoru", 0)),
            "raw": raw,
        }

    with app.app_context():
        app.config["UPLOAD_FOLDER"] = "static/item_pics"
        with patch("os.path.isfile", return_value=True):
            with patch(
                "services.moderation_photos.analyze_photo",
                side_effect=fake_analyze_photo,
            ):
                result = analyze_upload_photos(
                    ["a.jpg", "b.jpg"],
                    "atik",
                    "Başlık",
                    "Açıklama",
                    analyze_fn=fake_analyze,
                )

    assert result["risk_skoru"] == 85
    assert len(result["photo_analyses"]) == 2


def test_pick_primary_photo_prefers_highest_risk():
    analyses = [
        {"risk_score": 20, "confidence": 0.99, "raw": {"risk_skoru": 20}},
        {"risk_score": 80, "confidence": 0.6, "raw": {"risk_skoru": 80, "uygunsuz": True}},
    ]
    primary = pick_primary_photo_analysis(analyses)
    assert primary["risk_score"] == 80


def test_banned_user_mid_session_gets_403():
    """Oturum açıkken ban sonrası HTTP 403 (tam uygulama yığını)."""
    from sqlalchemy.pool import StaticPool

    app = create_app({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite://",
        "SQLALCHEMY_ENGINE_OPTIONS": {
            "poolclass": StaticPool,
            "connect_args": {"check_same_thread": False},
        },
        "WTF_CSRF_ENABLED": False,
        "TURNSTILE_ENABLED": False,
    })
    with app.app_context():
        db.create_all()
        user = User(
            username="midban2",
            email="midban2@test.com",
            password=hash_password("TestPass1"),
            is_completed=True,
        )
        db.session.add(user)
        db.session.commit()
        user_id = user.id

    client = app.test_client()
    client.post("/giris", data={"email": "midban2@test.com", "password": "TestPass1"})
    assert client.get("/anasayfa").status_code == 200

    with app.app_context():
        user = db.session.get(User, user_id)
        apply_ban(user, "test", None)
        db.session.commit()

    assert client.get("/anasayfa").status_code == 403


def test_deactivated_user_mid_session_gets_403():
    """Oturum açıkken deaktivasyon sonrası HTTP 403."""
    from sqlalchemy.pool import StaticPool

    app = create_app({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite://",
        "SQLALCHEMY_ENGINE_OPTIONS": {
            "poolclass": StaticPool,
            "connect_args": {"check_same_thread": False},
        },
        "WTF_CSRF_ENABLED": False,
        "TURNSTILE_ENABLED": False,
    })
    with app.app_context():
        db.create_all()
        user = User(
            username="middeact",
            email="middeact@test.com",
            password=hash_password("TestPass1"),
            is_completed=True,
        )
        db.session.add(user)
        db.session.commit()
        user_id = user.id

    client = app.test_client()
    client.post("/giris", data={"email": "middeact@test.com", "password": "TestPass1"})
    assert client.get("/anasayfa").status_code == 200

    with app.app_context():
        user = db.session.get(User, user_id)
        deactivate_user(user)
        db.session.commit()

    assert client.get("/anasayfa").status_code == 403


def test_enforce_active_account_unit(app):
    from flask_login import login_user
    from services.user_moderation import enforce_active_account

    with app.app_context():
        user = User(
            username="unitban",
            email="unitban@test.com",
            password=hash_password("TestPass1"),
            is_completed=True,
            is_banned=True,
        )
        db.session.add(user)
        db.session.commit()
        user_id = user.id

    with app.test_request_context("/anasayfa"):
        login_user(db.session.get(User, user_id))
        with pytest.raises(Forbidden):
            enforce_active_account()


def test_banned_user_socket_connect_rejected_after_ban(app):
    import socket_events

    with app.app_context():
        user = User(
            username="sockban",
            email="sockban@test.com",
            password=hash_password("TestPass1"),
            is_completed=True,
            is_banned=True,
        )
        db.session.add(user)
        db.session.commit()
        user_id = user.id

    with app.test_request_context("/"):
        from flask_login import login_user

        login_user(db.session.get(User, user_id))
        with pytest.raises(ConnectionRefusedError):
            socket_events.handle_connect()


def test_deactivated_user_socket_connect_rejected_after_deactivate(app):
    import socket_events

    with app.app_context():
        user = User(
            username="sockdeact",
            email="sockdeact@test.com",
            password=hash_password("TestPass1"),
            is_completed=True,
            is_deactivated=True,
        )
        db.session.add(user)
        db.session.commit()
        user_id = user.id

    with app.test_request_context("/"):
        from flask_login import login_user

        login_user(db.session.get(User, user_id))
        with pytest.raises(ConnectionRefusedError):
            socket_events.handle_connect()
