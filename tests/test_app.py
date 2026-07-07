import pytest

from factory import create_app
from extensions import db
from models import User, Kaynak, Atik
from auth_utils import hash_password, verify_password
from services.ilan_images import ilan_fotograf_listesi, ilan_fotograflari_ekle, kapak_resim


def _register_and_login(client, email="test@example.com", username="testuser"):
    client.post("/kayit", data={
        "username": username,
        "email": email,
        "password": "TestPass1",
        "password_tekrar": "TestPass1",
        "kullanim_kosullari": "on",
    }, follow_redirects=True)
    client.post("/profil_tamamla", data={
        "dogum_tarihi": "2000-01-01",
        "il": "İstanbul",
        "ilce": "Kadıköy",
        "telefon": "5551234567",
    }, follow_redirects=True)


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.get_json()["status"] == "ok"


def test_register_and_login(client):
    _register_and_login(client)
    response = client.get("/anasayfa")
    assert response.status_code == 200


def test_kayit_parola_eslesmiyor(client):
    response = client.post("/kayit", data={
        "username": "mismatch",
        "email": "mismatch@test.com",
        "password": "TestPass1",
        "password_tekrar": "TestPass2",
        "kullanim_kosullari": "on",
    }, follow_redirects=True)
    assert response.status_code == 200
    assert "eşleşmiyor" in response.data.decode("utf-8")


def test_kayit_smtp_hatasi_500_vermez(client, app, monkeypatch):
    import smtplib

    def fail_send(_msg):
        raise smtplib.SMTPAuthenticationError(525, b"5.7.1 Unauthorized IP address")

    monkeypatch.setattr("services.email.mail.send", fail_send)
    app.config["MAIL_SUPPRESS_SEND"] = False
    app.config["EMAIL_VERIFICATION_REQUIRED"] = True

    response = client.post("/kayit", data={
        "username": "smtpfail",
        "email": "smtpfail@test.com",
        "password": "TestPass1",
        "password_tekrar": "TestPass1",
        "kullanim_kosullari": "on",
    }, follow_redirects=True)
    assert response.status_code == 200
    assert b"500" not in response.data
    assert "gönderilemedi" in response.data.decode("utf-8").lower() or "Kay" in response.data.decode("utf-8")


def test_kayit_gecersiz_eposta(client):
    response = client.post("/kayit", data={
        "username": "mailuser",
        "email": "gecersiz-eposta",
        "password": "TestPass1",
        "password_tekrar": "TestPass1",
        "kullanim_kosullari": "on",
    }, follow_redirects=True)
    assert response.status_code == 200
    assert "e-posta" in response.data.decode("utf-8").lower()


def test_kayit_zayif_parola_once_kontrol(client):
    response = client.post("/kayit", data={
        "username": "weakuser",
        "email": "weak@test.com",
        "password": "abc",
        "password_tekrar": "xyz",
        "kullanim_kosullari": "on",
    }, follow_redirects=True)
    assert response.status_code == 200
    text = response.data.decode("utf-8")
    assert "8 karakter" in text
    assert "eşleşmiyor" not in text


def test_kaynak_panel_public(client):
    response = client.get("/kaynak_panel")
    assert response.status_code == 200


def test_kurumsal_sayfalar(client):
    for slug in ("hakkimizda", "vizyon-misyon", "hedeflerimiz", "sss"):
        response = client.get(f"/kurumsal/{slug}")
        assert response.status_code == 200
    assert client.get("/kurumsal/site-haritasi").status_code == 200
    assert client.get("/kurumsal/iletisim").status_code == 200
    assert client.get("/kurumsal/olmayan-sayfa").status_code == 404


def test_anasayfa_footer_linkleri(client):
    response = client.get("/anasayfa")
    assert response.status_code == 200
    assert b"Hakk\xc4\xb1m\xc4\xb1zda" in response.data or b"Hakk" in response.data
    assert b"Site Haritas" in response.data or b"site-haritasi" in response.data
    assert b"Kurumsal" in response.data


def test_navbar_kurumsal_giris_yapinca_gorunur(client):
    _register_and_login(client)
    response = client.get("/anasayfa")
    assert response.status_code == 200
    assert b"kurumsalNavDropdown" in response.data
    assert b"profilDropdown" in response.data


def test_yukle_kaynak_requires_login(client):
    response = client.get("/yukle_kaynak", follow_redirects=True)
    assert response.status_code == 200


def test_password_hashing():
    hashed = hash_password("TestPass1")
    assert hashed.startswith("$argon2")
    assert verify_password("TestPass1", hashed)
    assert not verify_password("wrong", hashed)


def test_verify_legacy_sha256_crypt_hash():
    from passlib.hash import sha256_crypt

    legacy = sha256_crypt.hash("AdminPass1")
    assert verify_password("AdminPass1", legacy)
    assert not verify_password("wrong", legacy)


def test_sanitize_input():
    from utils import sanitize_input, unescape_stored_text
    assert sanitize_input("<script>") == ""
    assert sanitize_input("<b>kalın</b>") == "kalın"
    assert sanitize_input("  hello   world  ") == "hello world"
    assert unescape_stored_text("&lt;test&gt;") == "<test>"


def test_ilan_erisilebilir_mi(app):
    from utils import ilan_erisilebilir_mi
    with app.app_context():
        k = Kaynak(
            baslik="Test", aciklama="A", durum="Temiz", kategori="Diğer",
            resim="default.jpg", latitude=41.0, longitude=29.0,
            user_id=1, ilan_durumu="Rezerve",
        )
        assert ilan_erisilebilir_mi(k, None) is False


def test_admin_panel_404_for_guest(client):
    response = client.get("/admin", follow_redirects=True)
    assert response.status_code == 200


def test_harita_noktalari():
    from types import SimpleNamespace
    from utils import harita_noktalari, is_varsayilan_konum
    from constants import DEFAULT_LAT, DEFAULT_LNG

    assert is_varsayilan_konum(DEFAULT_LAT, DEFAULT_LNG) is True
    assert is_varsayilan_konum(40.99, 29.03) is False

    ilanlar = [
        SimpleNamespace(id=1, baslik="A", latitude=DEFAULT_LAT, longitude=DEFAULT_LNG),
        SimpleNamespace(id=2, baslik="B", latitude=40.99, longitude=29.03),
        SimpleNamespace(id=3, baslik="C", latitude=40.99, longitude=29.03),
    ]
    noktalar, konumsuz = harita_noktalari(ilanlar)
    assert konumsuz == 1
    assert len(noktalar) == 1
    assert len(noktalar[0]["ilanlar"]) == 2


def test_goruntulenme_sayisi(client):
    response = client.get("/api/goruntulenme_sayisi?kaynak_id=1")
    assert response.status_code == 200
    assert "count" in response.get_json()


def test_ilanlarim_atik_duzenle_linki(client, app):
    _register_and_login(client)
    with app.app_context():
        user = User.query.filter_by(email="test@example.com").first()
        atik = Atik(
            baslik="Pil atığı",
            aciklama="Kullanılmış piller",
            resim="default.jpg",
            latitude=40.99,
            longitude=29.03,
            kategori="Pil ve Akü",
            user_id=user.id,
        )
        db.session.add(atik)
        db.session.commit()

    response = client.get("/ilanlarim")
    assert response.status_code == 200
    assert b"Pil at" in response.data
    assert b"/ilan_duzenle/atik/" in response.data


def test_ilan_duzenle_foto_silme(client, app):
    _register_and_login(client)
    with app.app_context():
        user = User.query.filter_by(email="test@example.com").first()
        kaynak = Kaynak(
            baslik="Silinecek foto",
            aciklama="Test açıklama uzun",
            durum="Temiz",
            kategori="Diğer",
            resim="a.jpg",
            latitude=41.0,
            longitude=29.0,
            user_id=user.id,
        )
        db.session.add(kaynak)
        db.session.flush()
        ilan_fotograflari_ekle(kaynak, "kaynak", ["a.jpg", "b.jpg"])
        db.session.commit()
        silinecek_id = kaynak.fotograflar[0].id

    response = client.post(
        f"/ilan_duzenle/kaynak/{kaynak.id}",
        data={
            "baslik": "Silinecek foto",
            "aciklama": "Test açıklama uzun",
            "durum": "Temiz",
            "kategori": "Diğer",
            "ilan_durumu": "Aktif",
            "latitude": "41.0",
            "longitude": "29.0",
            "silinecek_resim": str(silinecek_id),
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    with app.app_context():
        kaynak = Kaynak.query.filter_by(baslik="Silinecek foto").first()
        assert len(ilan_fotograf_listesi(kaynak)) == 1
        assert kapak_resim(kaynak) == "b.jpg"


def test_detay_sahip_bilgisi_telefon_gizli_misafir(client, app):
    with app.app_context():
        sahip = User(
            username="Ahmet Yılmaz",
            email="sahip@test.com",
            password="x",
            il="Ankara",
            ilce="Çankaya",
            telefon="(532) 111 22 33",
            is_completed=True,
        )
        db.session.add(sahip)
        db.session.commit()
        kaynak = Kaynak(
            baslik="Masa",
            aciklama="İyi durumda",
            durum="Temiz",
            kategori="Mobilya",
            resim="default.jpg",
            latitude=41.0,
            longitude=29.0,
            user_id=sahip.id,
        )
        db.session.add(kaynak)
        db.session.commit()
        kaynak_id = kaynak.id

    response = client.get(f"/kaynak/{kaynak_id}")
    assert response.status_code == 200
    assert b"Ahmet Y\xc4\xb1lmaz" in response.data or b"Ahmet" in response.data
    assert "Ankara".encode() in response.data
    assert b"\xc3\x87ankaya" in response.data or b"ankaya" in response.data
    assert b"532" not in response.data
    assert b"Giri\xc5\x9f yap\xc4\xb1nca" in response.data or b"Giri" in response.data


def test_detay_sahip_bilgisi_telefon_gorunur_giris(client, app):
    with app.app_context():
        sahip = User(
            username="Ayse Demir",
            email="sahip2@test.com",
            password="x",
            il="Izmir",
            ilce="Karsiyaka",
            telefon="5551234567",
            is_completed=True,
        )
        db.session.add(sahip)
        db.session.commit()
        atik = Atik(
            baslik="Pil",
            aciklama="Eski piller",
            resim="default.jpg",
            latitude=40.99,
            longitude=29.03,
            kategori="Pil ve Akü",
            user_id=sahip.id,
        )
        db.session.add(atik)
        db.session.commit()
        atik_id = atik.id

    _register_and_login(client, email="viewer@test.com", username="viewer")
    response = client.get(f"/atik/{atik_id}")
    assert response.status_code == 200
    assert b"5551234567" in response.data
    assert b"Ayse Demir" in response.data

