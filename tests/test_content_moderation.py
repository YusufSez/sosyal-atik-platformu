from auth_utils import hash_password
from extensions import db
from models import Mesaj, Sikayet, User
from services.content_filter import argo_iceriyor, mesaj_uygun_mu


def test_argo_iceriyor_kufur():
    assert argo_iceriyor("bu ne siktir") is True


def test_argo_iceriyor_normal_metin():
    assert argo_iceriyor("Merhaba, ürün hâlâ mevcut mu?") is False


def test_argo_iceriyor_yanlis_pozitif_mal():
    assert argo_iceriyor("malzeme durumu iyi") is False


def test_argo_iceriyor_salak():
    assert argo_iceriyor("sen salak mısın") is True


def test_mesaj_uygun_mu_liste_yedegi(app):
    with app.app_context():
        uygun, hata = mesaj_uygun_mu("normal mesaj")
        assert uygun is True
        assert hata == ""

        uygun, hata = mesaj_uygun_mu("amk ne diyorsun")
        assert uygun is False
        assert "uygunsuz" in hata.lower()


def test_mesaj_uygun_mu_ai_engeller(app, monkeypatch):
    def _ai_engel(_metin):
        return {
            "uygun": False,
            "risk_skoru": 80,
            "kategori": "argo",
            "mesaj": "Mesajınız yapay zeka içerik denetimi tarafından uygunsuz bulundu.",
            "kaynak": "ai",
            "hata": None,
        }

    monkeypatch.setattr("services.content_filter.ai_mesaj_moderasyon", _ai_engel)
    with app.app_context():
        uygun, hata = mesaj_uygun_mu("s a l a k")
        assert uygun is False
        assert "yapay zeka" in hata.lower()


def test_mesaj_uygun_mu_ai_izin_verir(app, monkeypatch):
    def _ai_izin(_metin):
        return {
            "uygun": True,
            "risk_skoru": 5,
            "kategori": "temiz",
            "mesaj": "",
            "kaynak": "ai",
            "hata": None,
        }

    monkeypatch.setattr("services.content_filter.ai_mesaj_moderasyon", _ai_izin)
    with app.app_context():
        uygun, hata = mesaj_uygun_mu("Ürün hâlâ mevcut mu?")
        assert uygun is True
        assert hata == ""


def _iki_kullanici(app):
    with app.app_context():
        gonderen = User(
            username="gonderen",
            email="gonderen@test.com",
            password=hash_password("TestPass1"),
            is_completed=True,
            email_verified=True,
        )
        alici = User(
            username="alici",
            email="alici@test.com",
            password=hash_password("TestPass1"),
            is_completed=True,
            email_verified=True,
        )
        db.session.add_all([gonderen, alici])
        db.session.commit()
        return gonderen.id, alici.id


def test_send_message_argo_engellenir(client, app):
    gonderen_id, alici_id = _iki_kullanici(app)
    client.post("/giris", data={"email": "gonderen@test.com", "password": "TestPass1"}, follow_redirects=True)

    response = client.post(
        "/send_message",
        json={"alici_id": alici_id, "content": "siktir git", "kaynak_id": 0, "atik_id": 0},
    )
    assert response.status_code == 400
    assert "uygunsuz" in response.get_json()["error"].lower()

    with app.app_context():
        assert Mesaj.query.filter_by(sender_id=gonderen_id).count() == 0


def test_mesaj_sikayet_api(client, app):
    gonderen_id, alici_id = _iki_kullanici(app)
    with app.app_context():
        mesaj = Mesaj(sender_id=gonderen_id, receiver_id=alici_id, content="Merhaba")
        db.session.add(mesaj)
        db.session.commit()
        mesaj_id = mesaj.id

    client.post("/giris", data={"email": "alici@test.com", "password": "TestPass1"}, follow_redirects=True)
    response = client.post("/api/mesaj_sikayet", json={"mesaj_id": mesaj_id, "sebep": "Spam"})
    assert response.status_code == 200
    assert response.get_json()["success"] is True

    with app.app_context():
        sikayet = Sikayet.query.filter_by(user_id=alici_id, mesaj_id=mesaj_id).first()
        assert sikayet is not None
        assert "Mesaj şikayeti" in sikayet.sebep


def test_mesaj_sikayet_tekrar_engeli(client, app):
    gonderen_id, alici_id = _iki_kullanici(app)
    with app.app_context():
        mesaj = Mesaj(sender_id=gonderen_id, receiver_id=alici_id, content="Test")
        db.session.add(mesaj)
        db.session.commit()
        mesaj_id = mesaj.id

    client.post("/giris", data={"email": "alici@test.com", "password": "TestPass1"}, follow_redirects=True)
    client.post("/api/mesaj_sikayet", json={"mesaj_id": mesaj_id})
    response = client.post("/api/mesaj_sikayet", json={"mesaj_id": mesaj_id})
    assert response.status_code == 400
