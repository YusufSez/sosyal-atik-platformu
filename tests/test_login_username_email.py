"""Kullanıcı adı veya e-posta ile giriş testleri."""

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


@pytest.fixture
def login_users(app):
    with app.app_context():
        users = [
            _create_user(
                username="normaluser",
                email="normal@test.com",
                password="TestPass1",
                role="user",
            ),
            _create_user(
                username="adminuser",
                email="admin@test.com",
                password="TestPass1",
                is_admin=True,
                role="admin",
            ),
            _create_user(
                username="superuser",
                email="super@test.com",
                password="TestPass1",
                is_admin=True,
                role="superadmin",
            ),
            _create_user(
                username="banneduser",
                email="banned@test.com",
                password="TestPass1",
                is_banned=True,
            ),
        ]
        db.session.add_all(users)
        db.session.commit()
    yield


def test_login_with_email(client, login_users):
    resp = client.post(
        "/giris",
        data={"email": "normal@test.com", "password": "TestPass1"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"Ho\xc5\x9f geldiniz" in resp.data or b"normaluser" in resp.data


def test_login_with_username(client, login_users):
    resp = client.post(
        "/giris",
        data={"email": "normaluser", "password": "TestPass1"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"normaluser" in resp.data


def test_login_wrong_email(client, login_users):
    resp = client.post(
        "/giris",
        data={"email": "yok@test.com", "password": "TestPass1"},
        follow_redirects=True,
    )
    text = resp.data.decode("utf-8", errors="ignore").lower()
    assert "hatal" in text


def test_login_wrong_username(client, login_users):
    resp = client.post(
        "/giris",
        data={"email": "olmayan_kullanici", "password": "TestPass1"},
        follow_redirects=True,
    )
    text = resp.data.decode("utf-8", errors="ignore").lower()
    assert "hatal" in text


def test_banned_user_cannot_login_with_email(client, login_users):
    resp = client.post(
        "/giris",
        data={"email": "banned@test.com", "password": "TestPass1"},
        follow_redirects=True,
    )
    text = resp.data.decode("utf-8", errors="ignore").lower()
    assert "ban" in text


def test_banned_user_cannot_login_with_username(client, login_users):
    resp = client.post(
        "/giris",
        data={"email": "banneduser", "password": "TestPass1"},
        follow_redirects=True,
    )
    text = resp.data.decode("utf-8", errors="ignore").lower()
    assert "ban" in text


def test_admin_login_with_username(client, login_users):
    resp = client.post(
        "/giris",
        data={"email": "adminuser", "password": "TestPass1"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    resp = client.get("/admin")
    assert resp.status_code == 200


def test_superadmin_login_with_email(client, login_users, monkeypatch):
    monkeypatch.setenv("SUPERADMIN_EMAIL", "super@test.com")
    resp = client.post(
        "/giris",
        data={"email": "super@test.com", "password": "TestPass1"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    resp = client.get("/admin/users")
    assert resp.status_code == 200
