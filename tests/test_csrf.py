"""CSRF koruması testleri (WTF_CSRF_ENABLED=True)."""

import pytest

from factory import create_app
from extensions import db


@pytest.fixture
def csrf_app():
    app = create_app({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        "WTF_CSRF_ENABLED": True,
        "TURNSTILE_ENABLED": False,
    })
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def csrf_client(csrf_app):
    return csrf_app.test_client()


def test_post_without_csrf_rejected(csrf_client):
    response = csrf_client.post("/giris", data={"email": "a@b.com", "password": "x"})
    assert response.status_code == 302


def test_post_with_csrf_token_allowed(csrf_client):
    response = csrf_client.get("/giris")
    assert response.status_code == 200

    with csrf_client.session_transaction() as sess:
        token = sess.get("csrf_token")
    assert token

    response = csrf_client.post(
        "/giris",
        data={"email": "a@b.com", "password": "x", "csrf_token": token},
    )
    assert response.status_code != 400


def test_api_post_without_csrf_header_rejected(csrf_client, csrf_app):
    from auth_utils import hash_password
    from models import User

    with csrf_app.app_context():
        user = User(
            username="csrfuser",
            email="csrf@test.com",
            password=hash_password("TestPass1"),
            is_completed=True,
        )
        db.session.add(user)
        db.session.commit()

    csrf_client.post(
        "/giris",
        data={
            "email": "csrf@test.com",
            "password": "TestPass1",
            "csrf_token": _get_csrf_token(csrf_client),
        },
        follow_redirects=True,
    )

    response = csrf_client.post(
        "/api/sikayet",
        json={"kaynak_id": 1, "sebep": "test"},
    )
    assert response.status_code == 400
    assert response.is_json


def test_get_requests_do_not_require_csrf(csrf_client):
    response = csrf_client.get("/anasayfa")
    assert response.status_code == 200


def _get_csrf_token(client):
    with client.session_transaction() as sess:
        return sess.get("csrf_token")
