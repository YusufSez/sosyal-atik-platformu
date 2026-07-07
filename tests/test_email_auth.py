import pytest

from auth_utils import hash_password
from extensions import db
from models import EmailToken, User
from services.email_tokens import (
    create_reset_token,
    create_verify_token,
    peek_token,
    verify_email_token,
    verify_reset_token,
)


@pytest.fixture
def verified_app(app):
    app.config["EMAIL_VERIFICATION_REQUIRED"] = True
    app.config["MAIL_SUPPRESS_SEND"] = True
    return app


@pytest.fixture
def verify_client(verified_app):
    return verified_app.test_client()


def _add_user(app, email="verify@test.com", verified=False):
    with app.app_context():
        user = User(
            username="verifyuser",
            email=email,
            password=hash_password("TestPass1"),
            is_completed=True,
            email_verified=verified,
        )
        db.session.add(user)
        db.session.commit()
        return user.id


def test_create_and_verify_email_token(app):
    with app.app_context():
        user = User(
            username="tokuser",
            email="tok@test.com",
            password=hash_password("TestPass1"),
        )
        db.session.add(user)
        db.session.commit()

        token = create_verify_token(user)
        assert EmailToken.query.filter_by(user_id=user.id, purpose="verify", used_at=None).count() == 1

        verified_user, error = verify_email_token(token)
        assert error is None
        assert verified_user.id == user.id
        assert EmailToken.query.filter_by(user_id=user.id, purpose="verify", used_at=None).count() == 0

        _, error2 = verify_email_token(token)
        assert error2 == "invalid"


def test_reset_token_single_use(app):
    with app.app_context():
        user = User(username="resetuser", email="reset@test.com", password=hash_password("TestPass1"))
        db.session.add(user)
        db.session.commit()

        token = create_reset_token(user)
        _, error = peek_token(token, "reset")
        assert error is None

        user1, error = verify_reset_token(token)
        assert user1 is not None and error is None

        _, error2 = verify_reset_token(token)
        assert error2 == "invalid"


def test_unverified_cannot_create_listing(verify_client, verified_app):
    _add_user(verified_app, verified=False)
    verify_client.post("/giris", data={"email": "verify@test.com", "password": "TestPass1"}, follow_redirects=True)
    response = verify_client.get("/yukle_kaynak", follow_redirects=True)
    assert response.status_code == 200
    assert "doğrulamanız gerekiyor" in response.data.decode("utf-8")


def test_verified_can_open_listing_form(verify_client, verified_app):
    _add_user(verified_app, verified=True)
    verify_client.post("/giris", data={"email": "verify@test.com", "password": "TestPass1"}, follow_redirects=True)
    response = verify_client.get("/yukle_kaynak")
    assert response.status_code == 200


def test_email_verify_route(client, app):
    with app.app_context():
        user = User(
            username="routeuser",
            email="route@test.com",
            password=hash_password("TestPass1"),
            email_verified=False,
        )
        db.session.add(user)
        db.session.commit()
        token = create_verify_token(user)

    response = client.get(f"/eposta-dogrula/onay/{token}", follow_redirects=True)
    assert response.status_code == 200

    with app.app_context():
        user = User.query.filter_by(email="route@test.com").first()
        assert user.email_verified is True


def test_sifremi_unuttum_page(client):
    assert client.get("/sifremi-unuttum").status_code == 200


def test_absolute_url_for_uses_site_url(app):
    app.config["SITE_URL"] = "http://localhost:8080"
    with app.app_context():
        from services.email_links import absolute_url_for

        link = absolute_url_for("auth.sifre_sifirla", token="test-token")
        assert link == "http://localhost:8080/sifre-sifirla/test-token"


def test_absolute_url_for_without_site_url(app):
    app.config["SITE_URL"] = ""
    with app.app_context():
        from services.email_links import absolute_url_for

        link = absolute_url_for("auth.eposta_dogrula_onay", token="abc")
        assert link.startswith("http://")
        assert "/eposta-dogrula/onay/abc" in link


def test_email_links_use_site_url(app, monkeypatch):
    app.config["SITE_URL"] = "https://atikport.example.com"
    app.config["MAIL_SUPPRESS_SEND"] = True
    sent = {}

    def capture(alici, konu, html, metin=None):
        sent["html"] = html
        sent["metin"] = metin
        return True

    monkeypatch.setattr("services.email.eposta_gonder", capture)

    with app.app_context():
        user = User(username="mailuser", email="mail@test.com", password=hash_password("TestPass1"))
        db.session.add(user)
        db.session.commit()
        from services.email import dogrulama_epostasi_gonder

        dogrulama_epostasi_gonder(user, "signed-token")

    assert "https://atikport.example.com/eposta-dogrula/onay/signed-token" in sent["html"]
    assert "https://atikport.example.com/eposta-dogrula/onay/signed-token" in sent["metin"]
