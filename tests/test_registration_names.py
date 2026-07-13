"""Kayıt formu — username kuralları ve çakışma testleri."""

from models import User
from tests.helpers import kayit_form

VALID_USERNAMES = (
    "yusuf",
    "yusuf123",
    "test_user",
    "abc.xyz",
    "ABC123",
)

INVALID_USERNAMES = (
    "ab",
    "a b",
    "şaban",
    "ömer",
    "abc!",
    "abc@",
    "abc#",
    "😀user",
)


def _body(response) -> str:
    return response.data.decode("utf-8", errors="ignore")


def test_kayit_requires_ad_soyad_and_username(client):
    response = client.post("/kayit", data=kayit_form(), follow_redirects=True)
    assert response.status_code == 200

    response = client.post(
        "/kayit",
        data=kayit_form(ad="", soyad="Kullanıcı"),
        follow_redirects=True,
    )
    assert "Ad en az" in _body(response)

    response = client.post(
        "/kayit",
        data=kayit_form(username="ad soyad"),
        follow_redirects=True,
    )
    text = _body(response)
    assert "3-30 karakter" in text or "yalnızca harf" in text.lower()


def test_kayit_stores_ad_soyad(client, app):
    response = client.post(
        "/kayit",
        data=kayit_form(
            ad="Ayşe",
            soyad="Yılmaz",
            username="ayseyilmaz",
            email="ayse@test.com",
        ),
        follow_redirects=True,
    )
    assert response.status_code == 200
    with app.app_context():
        user = User.query.filter_by(email="ayse@test.com").first()
        assert user is not None
        assert user.ad == "Ayşe"
        assert user.soyad == "Yılmaz"
        assert user.username == "ayseyilmaz"
        assert user.display_name == "Ayşe Yılmaz"


def test_kayit_accepts_valid_usernames(client, app):
    for i, username in enumerate(VALID_USERNAMES):
        email = f"ok{i}@test.com"
        response = client.post(
            "/kayit",
            data=kayit_form(username=username, email=email),
            follow_redirects=True,
        )
        assert response.status_code == 200, username
        with app.app_context():
            user = User.query.filter_by(email=email).first()
            assert user is not None, username
            assert user.username == username


def test_kayit_rejects_invalid_usernames(client, app):
    for i, username in enumerate(INVALID_USERNAMES):
        email = f"bad{i}@test.com"
        response = client.post(
            "/kayit",
            data=kayit_form(username=username, email=email),
            follow_redirects=True,
        )
        text = _body(response)
        assert "3-30 karakter" in text or "yalnızca harf" in text.lower(), username
        with app.app_context():
            assert User.query.filter_by(email=email).first() is None, username


def test_kayit_rejects_too_long_username(client, app):
    long_name = "a" * 31
    response = client.post(
        "/kayit",
        data=kayit_form(username=long_name, email="long@test.com"),
        follow_redirects=True,
    )
    assert "3-30 karakter" in _body(response)
    with app.app_context():
        assert User.query.filter_by(email="long@test.com").first() is None


def test_kayit_duplicate_username_case_insensitive(client, app):
    client.post(
        "/kayit",
        data=kayit_form(username="Yusuf", email="first@test.com"),
        follow_redirects=True,
    )
    response = client.post(
        "/kayit",
        data=kayit_form(username="yusuf", email="second@test.com"),
        follow_redirects=True,
    )
    text = _body(response)
    assert "zaten kullanılıyor" in text.lower()
    with app.app_context():
        assert User.query.filter_by(email="second@test.com").first() is None


def test_kayit_duplicate_email(client, app):
    client.post(
        "/kayit",
        data=kayit_form(username="userone", email="same@test.com"),
        follow_redirects=True,
    )
    response = client.post(
        "/kayit",
        data=kayit_form(username="usertwo", email="same@test.com"),
        follow_redirects=True,
    )
    assert "e-posta zaten kayıtlı" in _body(response).lower()
    with app.app_context():
        assert User.query.filter_by(username="usertwo").first() is None


def test_register_html_username_pattern_matches_backend(client):
    """Escape hatası regresyonu: pattern [\\\\w] olmamalı."""
    response = client.get("/kayit")
    html = _body(response)
    assert 'pattern="[A-Za-z0-9_.]{3,30}"' in html
    assert "pattern=\"[\\\\w]+\"'" not in html
    assert "pattern=\"[\\w]+\"" not in html
    assert 'minlength="3"' in html
    assert 'maxlength="30"' in html
