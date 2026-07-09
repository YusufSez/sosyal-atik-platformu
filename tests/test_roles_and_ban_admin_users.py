import pytest

from auth_utils import hash_password
from extensions import db
from models import User


def _create_user(
    *,
    username: str,
    email: str,
    password: str,
    is_completed: bool = True,
    is_admin: bool = False,
    role: str = "user",
    is_banned: bool = False,
):
    return User(
        username=username,
        email=email,
        password=hash_password(password),
        is_completed=is_completed,
        is_admin=is_admin,
        role=role,
        is_banned=is_banned,
    )


def test_registration_does_not_assign_superadmin_from_env(monkeypatch, client, app):
    monkeypatch.setenv("SUPERADMIN_EMAIL", "super@test.com")

    client.post(
        "/kayit",
        data={
            "username": "superuser",
            "email": "super@test.com",
            "password": "TestPass1",
            "password_tekrar": "TestPass1",
            "kullanim_kosullari": "on",
        },
        follow_redirects=True,
    )

    with app.app_context():
        u = User.query.filter_by(email="super@test.com").first()
        assert u is not None
        assert u.role == "user"
        assert u.is_admin is False


def test_banned_user_cannot_login(monkeypatch, client, app):
    with app.app_context():
        u = _create_user(
            username="banned",
            email="banned@test.com",
            password="TestPass1",
            is_completed=True,
            is_admin=False,
            role="user",
            is_banned=True,
        )
        db.session.add(u)
        db.session.commit()

    resp = client.post(
        "/giris",
        data={"email": "banned@test.com", "password": "TestPass1"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    text = resp.data.decode("utf-8", errors="ignore").lower()
    assert "ban" in text


def test_admin_users_access_control(monkeypatch, client, app):
    monkeypatch.setenv("SUPERADMIN_EMAIL", "sa@test.com")

    with app.app_context():
        super_admin = _create_user(
            username="sa",
            email="sa@test.com",
            password="TestPass1",
            is_admin=True,
            role="superadmin",
        )
        admin_user = _create_user(
            username="admin",
            email="admin@test.com",
            password="TestPass1",
            is_admin=True,
            role="admin",
        )
        db.session.add_all([super_admin, admin_user])
        db.session.commit()

    # Non-superadmin (admin role) => 403
    client.post(
        "/giris",
        data={"email": "admin@test.com", "password": "TestPass1"},
        follow_redirects=True,
    )
    resp = client.get("/admin/users")
    assert resp.status_code == 403

    client.get("/cikis", follow_redirects=True)

    # Superadmin => 200
    client.post(
        "/giris",
        data={"email": "sa@test.com", "password": "TestPass1"},
        follow_redirects=True,
    )
    resp = client.get("/admin/users")
    assert resp.status_code == 200
    assert b"admin@test.com" in resp.data


def test_superadmin_cannot_ban_self_or_other_superadmin(monkeypatch, client, app):
    monkeypatch.setenv("SUPERADMIN_EMAIL", "sa1@test.com")

    with app.app_context():
        sa1 = _create_user(
            username="sa1",
            email="sa1@test.com",
            password="TestPass1",
            is_admin=True,
            role="superadmin",
        )
        sa2 = _create_user(
            username="sa2",
            email="sa2@test.com",
            password="TestPass1",
            is_admin=True,
            role="superadmin",
        )
        normal = _create_user(
            username="normal",
            email="normal@test.com",
            password="TestPass1",
            is_admin=False,
            role="user",
        )
        db.session.add_all([sa1, sa2, normal])
        db.session.commit()

        sa1_id, sa2_id, normal_id = sa1.id, sa2.id, normal.id

    # Login as sa1
    client.post(
        "/giris",
        data={"email": "sa1@test.com", "password": "TestPass1"},
        follow_redirects=True,
    )

    # Self ban => should not ban
    resp = client.post(f"/admin/users/ban/{sa1_id}", follow_redirects=True)
    assert resp.status_code == 200
    with app.app_context():
        refreshed = db.session.get(User, sa1_id)
        assert refreshed.is_banned is False

    # Ban another superadmin => 403
    resp = client.post(f"/admin/users/ban/{sa2_id}")
    assert resp.status_code == 403

    with app.app_context():
        refreshed = db.session.get(User, sa2_id)
        assert refreshed.is_banned is False

    # Ban normal user => success
    resp = client.post(f"/admin/users/ban/{normal_id}", follow_redirects=True)
    assert resp.status_code == 200
    with app.app_context():
        refreshed = db.session.get(User, normal_id)
        assert refreshed.is_banned is True

