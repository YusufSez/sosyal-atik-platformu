import pytest

from extensions import db
from models import Atik, CevreselEtki, Kaynak, User
from services.impact import (
    backfill_mevcut_teslimler,
    format_etki_sayi,
    hesapla_etki,
    kaydet_etki,
    kullanici_ozeti,
    platform_ozeti,
    teslim_sonrasi_islem,
)


def _kullanici_olustur():
    user = User(
        username="etkiuser",
        email="etki@test.com",
        password="hash",
        is_completed=True,
        il="İstanbul",
    )
    db.session.add(user)
    db.session.commit()
    return user


def test_hesapla_etki_kaynak():
    etki = hesapla_etki("kaynak", "Mobilya")
    assert etki["co2e_kg"] == 45
    assert etki["su_litre"] == 800
    assert etki["atik_kg"] == 0


def test_hesapla_etki_atik():
    etki = hesapla_etki("atik", "Plastik")
    assert etki["co2e_kg"] == 3
    assert etki["atik_kg"] == 2


def test_kaydet_etki_tekil(app):
    with app.app_context():
        user = _kullanici_olustur()
        kaynak = Kaynak(
            baslik="Masa",
            aciklama="Test",
            durum="Temiz",
            kategori="Mobilya",
            resim="default.jpg",
            latitude=41.0,
            longitude=29.0,
            user_id=user.id,
            ilan_durumu="Teslim Edildi",
        )
        db.session.add(kaynak)
        db.session.commit()

        kayit1 = kaydet_etki(kaynak, "kaynak")
        db.session.commit()
        kayit2 = kaydet_etki(kaynak, "kaynak")

        assert kayit1 is not None
        assert kayit2 is None
        assert CevreselEtki.query.count() == 1


def test_teslim_sonrasi_islem_guven_puani(app):
    with app.app_context():
        user = _kullanici_olustur()
        atik = Atik(
            baslik="Plastik",
            aciklama="Test",
            kategori="Plastik",
            user_id=user.id,
            ilan_durumu="Teslim Edildi",
        )
        db.session.add(atik)
        db.session.commit()

        etki = teslim_sonrasi_islem(atik, "atik")
        db.session.commit()

        assert etki is not None
        assert user.guven_puani == 1


def test_platform_ve_kullanici_ozeti(app):
    with app.app_context():
        user = _kullanici_olustur()
        kaynak = Kaynak(
            baslik="Kitap",
            aciklama="Test",
            durum="Temiz",
            kategori="Kitap",
            resim="default.jpg",
            latitude=41.0,
            longitude=29.0,
            user_id=user.id,
            ilan_durumu="Teslim Edildi",
        )
        db.session.add(kaynak)
        db.session.commit()
        kaydet_etki(kaynak, "kaynak")
        db.session.commit()

        platform = platform_ozeti()
        kisi = kullanici_ozeti(user.id)

        assert platform["co2e_kg"] == 2
        assert platform["yeniden_kullanim"] == 1
        assert kisi["teslim_sayisi"] == 1


def test_backfill_mevcut_teslimler(app):
    with app.app_context():
        user = _kullanici_olustur()
        db.session.add(Kaynak(
            baslik="A",
            aciklama="A",
            durum="Temiz",
            kategori="Diğer",
            resim="default.jpg",
            latitude=41.0,
            longitude=29.0,
            user_id=user.id,
            ilan_durumu="Teslim Edildi",
        ))
        db.session.commit()

        count = backfill_mevcut_teslimler()
        assert count == 1
        assert CevreselEtki.query.count() == 1

        count2 = backfill_mevcut_teslimler()
        assert count2 == 0


def test_format_etki_sayi():
    assert "1.2K" in format_etki_sayi(1200)
    assert format_etki_sayi(45, "kg") == "45 kg"


def test_etki_api_public(client):
    response = client.get("/api/etki/ozet")
    assert response.status_code == 200
    data = response.get_json()
    assert "co2e_kg" in data
    assert data["tahmini"] is True


def test_etki_panelim_requires_login(client):
    response = client.get("/etki-panelim", follow_redirects=True)
    assert response.status_code == 200


def test_ilan_durum_teslim_etki(client, app):
    client.post("/kayit", data={
        "username": "other",
        "email": "other@test.com",
        "password": "TestPass1",
    }, follow_redirects=True)
    client.post("/profil_tamamla", data={
        "dogum_tarihi": "2000-01-01",
        "il": "İstanbul",
        "ilce": "Kadıköy",
        "telefon": "5551234567",
    }, follow_redirects=True)

    with app.app_context():
        user = User.query.filter_by(email="other@test.com").first()
        kaynak = Kaynak(
            baslik="Sandalye",
            aciklama="Test",
            durum="Temiz",
            kategori="Mobilya",
            resim="default.jpg",
            latitude=41.0,
            longitude=29.0,
            user_id=user.id,
        )
        db.session.add(kaynak)
        db.session.commit()
        kid = kaynak.id

    client.post(f"/ilan_durum_guncelle/kaynak/{kid}", data={
        "ilan_durumu": "Teslim Edildi",
    }, follow_redirects=True)

    with app.app_context():
        assert CevreselEtki.query.filter_by(kaynak_id=kid).count() == 1


def test_teslim_geri_al_etki_sifirlanir(app):
    with app.app_context():
        user = _kullanici_olustur()
        kaynak = Kaynak(
            baslik="Masa",
            aciklama="Test",
            durum="Temiz",
            kategori="Mobilya",
            resim="default.jpg",
            latitude=41.0,
            longitude=29.0,
            user_id=user.id,
            ilan_durumu="Teslim Edildi",
        )
        db.session.add(kaynak)
        db.session.commit()
        from services.impact import ilan_durum_etki_sync, kullanici_ozeti, teslim_sonrasi_islem

        teslim_sonrasi_islem(kaynak, "kaynak")
        db.session.commit()
        assert kullanici_ozeti(user.id)["co2e_kg"] == 45

        kaynak.ilan_durumu = "Aktif"
        ilan_durum_etki_sync(kaynak, "kaynak", "Teslim Edildi", "Aktif")
        db.session.commit()

        assert CevreselEtki.query.count() == 0
        assert kullanici_ozeti(user.id)["co2e_kg"] == 0
        assert user.guven_puani == 0
