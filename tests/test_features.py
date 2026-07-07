from extensions import db
from models import Atik, Kaynak, User
from services.gamification import ilan_olusturuldu, liderlik_tablosu, rozetleri_kontrol_et, seviye_hesapla, teslim_tamamlandi
from services.kurum_analytics import isi_haritasi_noktalari, kurum_ozet
from services.recommendations import kullanici_onerileri


def test_seviye_hesapla():
    assert seviye_hesapla(0)["ad"] == "Yeni Üye"
    assert seviye_hesapla(100)["seviye"] >= 2


def test_gamification_ilan_ve_teslim(app):
    with app.app_context():
        user = User(username="gamer", email="gamer@test.com", password="x", is_completed=True)
        db.session.add(user)
        db.session.commit()
        ilan_olusturuldu(user)
        db.session.commit()
        assert user.xp >= 25
        kaynak = Kaynak(
            baslik="K", aciklama="A", durum="Temiz", kategori="Diğer",
            resim="default.jpg", latitude=41.0, longitude=29.0,
            user_id=user.id, ilan_durumu="Teslim Edildi",
        )
        db.session.add(kaynak)
        db.session.commit()
        teslim_tamamlandi(user)
        db.session.commit()
        rozetleri_kontrol_et(user)
        assert user.xp >= 75


def test_liderlik_tablosu(app):
    with app.app_context():
        tablo = liderlik_tablosu(limit=5)
        assert isinstance(tablo, list)


def test_kurum_ozet_ve_isi_harita(app):
    with app.app_context():
        ozet = kurum_ozet()
        assert "kullanici" in ozet
        noktalar = isi_haritasi_noktalari()
        assert isinstance(noktalar, list)


def test_oneriler_skorlama(app):
    with app.app_context():
        user = User(
            username="oneri", email="oneri@test.com", password="x",
            is_completed=True, il="İstanbul", ilce="Kadıköy",
            latitude=41.0, longitude=29.0,
        )
        db.session.add(user)
        db.session.commit()
        sahip = User(username="sahip", email="sahip3@test.com", password="x", il="İstanbul", is_completed=True)
        db.session.add(sahip)
        db.session.commit()
        kaynak = Kaynak(
            baslik="Masa", aciklama="İyi", durum="Temiz", kategori="Mobilya",
            resim="default.jpg", latitude=41.01, longitude=29.01,
            user_id=sahip.id,
        )
        db.session.add(kaynak)
        db.session.commit()
        oneriler = kullanici_onerileri(user, "kaynak", limit=3)
        assert len(oneriler) >= 1
        assert oneriler[0]["ilan"].baslik == "Masa"


def test_kurum_panel_yetki(client, app):
    response = client.get("/kurum/analiz", follow_redirects=True)
    assert response.status_code == 200
    with app.app_context():
        user = User(username="kurum", email="kurum@test.com", password="x", is_completed=True, is_kurum=True)
        db.session.add(user)
        db.session.commit()
    client.post("/kayit", data={"username": "kurum2", "email": "k2@test.com", "password": "TestPass1"}, follow_redirects=True)
    with app.app_context():
        u = User.query.filter_by(email="k2@test.com").first()
        u.is_kurum = True
        db.session.commit()


def test_liderlik_sayfasi(client):
    response = client.get("/liderlik-tablosu")
    assert response.status_code == 200
    assert b"Liderlik" in response.data
