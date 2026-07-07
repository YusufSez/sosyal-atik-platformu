import pytest

from extensions import db
from models import IlanResim, Kaynak, User
from services.ilan_images import (
    ensure_ilan_fotograflari,
    ilan_fotograf_listesi,
    ilan_fotograflari_ekle,
    ilan_fotograflari_sil,
    kapak_resim,
    save_ilan_fotograflari,
)
from constants import MAX_ILAN_FOTOSU


def test_save_ilan_fotograflari_limit_raises(app):
    with app.app_context():
        class FakeFile:
            filename = "test.jpg"

        with pytest.raises(ValueError, match=str(MAX_ILAN_FOTOSU)):
            save_ilan_fotograflari([FakeFile()], mevcut_adet=MAX_ILAN_FOTOSU)


def test_ilan_coklu_foto_model(app):
    with app.app_context():
        user = User(username="foto", email="foto@test.com", password="x", is_completed=True)
        db.session.add(user)
        db.session.commit()

        kaynak = Kaynak(
            baslik="Test",
            aciklama="A",
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

        assert len(ilan_fotograf_listesi(kaynak)) == 2
        assert kapak_resim(kaynak) == "a.jpg"
        assert IlanResim.query.filter_by(kaynak_id=kaynak.id).count() == 2


def test_ilan_fotograf_silme(app):
    with app.app_context():
        user = User(username="foto2", email="foto2@test.com", password="x", is_completed=True)
        db.session.add(user)
        db.session.commit()
        kaynak = Kaynak(
            baslik="T",
            aciklama="A",
            durum="Temiz",
            kategori="Diğer",
            resim="x.jpg",
            latitude=41.0,
            longitude=29.0,
            user_id=user.id,
        )
        db.session.add(kaynak)
        db.session.flush()
        ilan_fotograflari_ekle(kaynak, "kaynak", ["x.jpg", "y.jpg"])
        db.session.commit()
        ilk = kaynak.fotograflar[0]
        ilan_fotograflari_sil(kaynak, [ilk.id])
        db.session.commit()
        assert len(ilan_fotograf_listesi(kaynak)) == 1
        assert kapak_resim(kaynak) == "y.jpg"


def test_ensure_ilan_fotograflari_legacy_resim(app):
    with app.app_context():
        user = User(username="legacy", email="legacy@test.com", password="x", is_completed=True)
        db.session.add(user)
        db.session.commit()
        kaynak = Kaynak(
            baslik="Eski",
            aciklama="A",
            durum="Temiz",
            kategori="Diğer",
            resim="legacy.jpg",
            latitude=41.0,
            longitude=29.0,
            user_id=user.id,
        )
        db.session.add(kaynak)
        db.session.commit()
        assert not kaynak.fotograflar
        assert ensure_ilan_fotograflari(kaynak, "kaynak") is True
        db.session.commit()
        assert len(kaynak.fotograflar) == 1
        assert kaynak.fotograflar[0].dosya == "legacy.jpg"
