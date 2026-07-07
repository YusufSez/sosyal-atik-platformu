from auth_utils import hash_password
from extensions import db
from models import Atik, Comment, Kaynak, User
from services.yorumlar import kok_yorumlari_getir, yorum_cevapla


def _ilan_ve_yorum(app):
    with app.app_context():
        sahip = User(
            username="sahip_yorum",
            email="sahip_yorum@test.com",
            password=hash_password("TestPass1"),
            is_completed=True,
            email_verified=True,
        )
        yorumcu = User(
            username="yorumcu",
            email="yorumcu@test.com",
            password=hash_password("TestPass1"),
            is_completed=True,
            email_verified=True,
        )
        db.session.add_all([sahip, yorumcu])
        db.session.commit()

        kaynak = Kaynak(
            baslik="Test Masa",
            aciklama="Aciklama",
            durum="Temiz",
            kategori="Mobilya",
            resim="default.jpg",
            latitude=41.0,
            longitude=29.0,
            user_id=sahip.id,
        )
        db.session.add(kaynak)
        db.session.commit()

        yorum = Comment(content="Fiyat son mu?", user_id=yorumcu.id, kaynak_id=kaynak.id)
        db.session.add(yorum)
        db.session.commit()
        return sahip.id, yorumcu.id, kaynak.id, yorum.id


def test_kok_yorumlari_getir(app):
    _, _, kaynak_id, yorum_id = _ilan_ve_yorum(app)
    with app.app_context():
        kok = kok_yorumlari_getir(kaynak_id=kaynak_id)
        assert len(kok) == 1
        assert kok[0].id == yorum_id


def test_yorum_cevapla_sahip_basari(app):
    sahip_id, _, _, yorum_id = _ilan_ve_yorum(app)
    with app.app_context():
        sahip_db = db.session.get(User, sahip_id)
        yorum = db.session.get(Comment, yorum_id)
        cevap = yorum_cevapla(sahip_db, yorum_id, "Evet, son fiyat.")
        assert cevap.parent_id == yorum_id
        assert cevap.user_id == sahip_id
        db.session.refresh(yorum)
        assert len(yorum.replies) == 1


def test_yorum_cevapla_yetkisiz(app):
    _, yorumcu_id, _, yorum_id = _ilan_ve_yorum(app)
    with app.app_context():
        yorumcu_db = db.session.get(User, yorumcu_id)
        try:
            yorum_cevapla(yorumcu_db, yorum_id, "Kendi cevabim")
            assert False, "PermissionError bekleniyordu"
        except PermissionError:
            pass


def test_yorum_cevapla_route(client, app):
    _, _, kaynak_id, yorum_id = _ilan_ve_yorum(app)
    client.post("/giris", data={"email": "sahip_yorum@test.com", "password": "TestPass1"}, follow_redirects=True)
    response = client.post(
        f"/yorum_cevapla/{kaynak_id}/{yorum_id}",
        data={"yorum": "Tesekkurler, urun durumu iyi."},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "Cevabınız eklendi" in response.data.decode("utf-8")

    with app.app_context():
        cevaplar = Comment.query.filter_by(parent_id=yorum_id).all()
        assert len(cevaplar) == 1
        assert "urun durumu" in cevaplar[0].content
