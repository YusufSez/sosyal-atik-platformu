"""Kayıt formu ad/soyad/kullanıcı adı testleri."""

from tests.helpers import kayit_form


def test_kayit_requires_ad_soyad_and_username(client):
    response = client.post("/kayit", data=kayit_form(), follow_redirects=True)
    assert response.status_code == 200

    response = client.post(
        "/kayit",
        data=kayit_form(ad="", soyad="Kullanıcı"),
        follow_redirects=True,
    )
    assert "Ad en az" in response.data.decode("utf-8", errors="ignore")

    response = client.post(
        "/kayit",
        data=kayit_form(username="ad soyad"),
        follow_redirects=True,
    )
    text = response.data.decode("utf-8", errors="ignore")
    assert "boşluk" in text.lower() or "alt çizgi" in text.lower()


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
        from models import User

        user = User.query.filter_by(email="ayse@test.com").first()
        assert user is not None
        assert user.ad == "Ayşe"
        assert user.soyad == "Yılmaz"
        assert user.username == "ayseyilmaz"
        assert user.display_name == "Ayşe Yılmaz"
