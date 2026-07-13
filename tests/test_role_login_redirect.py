"""Rol bazlı giriş yönlendirmesi — portal redirect regression."""

import pytest

from auth_utils import hash_password
from constants import (
    ROLE_ADMIN,
    ROLE_COMPANY,
    ROLE_INSTITUTION,
    ROLE_MINISTRY,
    ROLE_MUNICIPALITY,
    ROLE_SUPERADMIN,
    ROLE_USER,
)
from extensions import db
from models import User
from services.portal_redirect import post_login_endpoint, post_login_url


def _user(**kwargs):
    defaults = dict(
        password=hash_password("TestPass1"),
        is_completed=True,
        email_verified=True,
        role=ROLE_USER,
        is_admin=False,
    )
    defaults.update(kwargs)
    user = User(**defaults)
    db.session.add(user)
    db.session.commit()
    return user


def _login(client, email):
    client.get("/cikis", follow_redirects=True)
    return client.post(
        "/giris",
        data={"email": email, "password": "TestPass1"},
        follow_redirects=False,
    )


@pytest.fixture
def portal_users(app):
    with app.app_context():
        users = {
            "user": _user(username="portal_user", email="portal_user@test.com", role=ROLE_USER),
            "company": _user(
                username="portal_company",
                email="portal_company@test.com",
                role=ROLE_COMPANY,
                is_kurum=True,
            ),
            "institution": _user(
                username="portal_inst",
                email="portal_inst@test.com",
                role=ROLE_INSTITUTION,
                is_kurum=True,
            ),
            "municipality": _user(
                username="portal_muni",
                email="portal_muni@test.com",
                role=ROLE_MUNICIPALITY,
                il="Sakarya",
            ),
            "ministry": _user(
                username="portal_min",
                email="portal_min@test.com",
                role=ROLE_MINISTRY,
            ),
            "admin": _user(
                username="portal_admin",
                email="portal_admin@test.com",
                role=ROLE_ADMIN,
                is_admin=True,
            ),
            "superadmin": _user(
                username="portal_super",
                email="portal_super@test.com",
                role=ROLE_SUPERADMIN,
                is_admin=True,
            ),
        }
        return {k: u.id for k, u in users.items()}


@pytest.mark.parametrize(
    "key,expected_path",
    [
        ("user", "/anasayfa"),
        ("company", "/marketplace/panel"),
        ("institution", "/kurum/analiz"),
        ("municipality", "/belediye/dashboard"),
        ("ministry", "/minister/dashboard"),
        ("admin", "/admin"),
        ("superadmin", "/admin"),
    ],
)
def test_login_redirects_to_role_portal(client, portal_users, key, expected_path):
    email = {
        "user": "portal_user@test.com",
        "company": "portal_company@test.com",
        "institution": "portal_inst@test.com",
        "municipality": "portal_muni@test.com",
        "ministry": "portal_min@test.com",
        "admin": "portal_admin@test.com",
        "superadmin": "portal_super@test.com",
    }[key]
    resp = _login(client, email)
    assert resp.status_code in (302, 303)
    assert resp.headers["Location"].endswith(expected_path) or expected_path in resp.headers["Location"]


def test_post_login_endpoint_helper(app, portal_users):
    with app.app_context():
        mapping = {
            "user": "main.anasayfa",
            "company": "marketplace.panel",
            "institution": "kurum.analiz_paneli",
            "municipality": "belediye.dashboard",
            "ministry": "admin_ministry.dashboard",
            "admin": "admin.admin_panel",
            "superadmin": "admin.admin_panel",
        }
        for key, endpoint in mapping.items():
            user = db.session.get(User, portal_users[key])
            assert post_login_endpoint(user) == endpoint
        user = db.session.get(User, portal_users["user"])
        assert post_login_url(user).endswith("/anasayfa")


def test_citizen_still_reaches_home(client, portal_users):
    resp = _login(client, "portal_user@test.com")
    assert "/anasayfa" in resp.headers["Location"]
    followed = client.get(resp.headers["Location"], follow_redirects=True)
    assert followed.status_code == 200


def test_unauthorized_cannot_access_foreign_portals(client, portal_users):
    _login(client, "portal_user@test.com")
    assert client.get("/belediye/dashboard").status_code == 403
    assert client.get("/minister/dashboard").status_code == 403
    assert client.get("/admin").status_code == 403
    assert client.get("/marketplace/panel").status_code == 403
    # Kurum paneli yetkisizde 404 (mevcut davranış)
    assert client.get("/kurum/analiz").status_code == 404


def test_company_cannot_access_ministry_or_admin(client, portal_users):
    _login(client, "portal_company@test.com")
    assert client.get("/minister/dashboard").status_code == 403
    assert client.get("/admin").status_code == 403
    assert client.get("/marketplace/panel").status_code == 200


def test_institution_reaches_kurum_portal(client, portal_users):
    resp = _login(client, "portal_inst@test.com")
    assert "/kurum/analiz" in resp.headers["Location"]
    assert client.get("/kurum/analiz").status_code == 200


def test_municipality_forbidden_on_ministry(client, portal_users):
    _login(client, "portal_muni@test.com")
    assert client.get("/belediye/dashboard").status_code == 200
    assert client.get("/minister/dashboard").status_code == 403


def test_legacy_is_admin_flag_redirects_to_admin(app, client):
    with app.app_context():
        _user(
            username="legacy_admin",
            email="legacy_admin@test.com",
            role=ROLE_USER,
            is_admin=True,
        )
    resp = _login(client, "legacy_admin@test.com")
    assert "/admin" in resp.headers["Location"]
