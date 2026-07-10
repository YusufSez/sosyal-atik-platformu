"""İlan silme FK bağımlılık regression testleri."""

import pytest

from auth_utils import hash_password
from extensions import db
from models import Atik, Bildirim, Comment, Kaynak, Mesaj, Sikayet, User
from utils import cleanup_ilan_relations


def _user(**kwargs):
    defaults = dict(
        password=hash_password("TestPass1"),
        is_completed=True,
        email_verified=True,
    )
    defaults.update(kwargs)
    return User(**defaults)


def _login(client, email):
    client.post(
        "/giris",
        data={"email": email, "password": "TestPass1"},
        follow_redirects=True,
    )


@pytest.fixture
def ilan_users(app):
    with app.app_context():
        owner = _user(username="owner", email="owner@test.com")
        other = _user(username="other", email="other@test.com")
        admin = _user(
            username="adm",
            email="adm@test.com",
            is_admin=True,
            role="admin",
        )
        db.session.add_all([owner, other, admin])
        db.session.commit()
        ids = {"owner": owner.id, "other": other.id, "admin": admin.id}
    yield ids


def _kaynak(owner_id):
    kaynak = Kaynak(
        baslik="Test Kaynak",
        aciklama="Açıklama",
        durum="Temiz",
        kategori="Diğer",
        resim="default.jpg",
        latitude=41.0,
        longitude=29.0,
        user_id=owner_id,
    )
    db.session.add(kaynak)
    db.session.flush()
    return kaynak


def _atik(owner_id):
    atik = Atik(
        baslik="Test Atık",
        aciklama="Açıklama",
        resim="default.jpg",
        latitude=41.0,
        longitude=29.0,
        user_id=owner_id,
        kategori="Diğer",
    )
    db.session.add(atik)
    db.session.flush()
    return atik


def test_cleanup_kaynak_with_message_sikayet(app, ilan_users):
    with app.app_context():
        kaynak = _kaynak(ilan_users["owner"])
        mesaj = Mesaj(
            sender_id=ilan_users["owner"],
            receiver_id=ilan_users["other"],
            content="ilan mesajı",
            kaynak_id=kaynak.id,
        )
        db.session.add(mesaj)
        db.session.flush()
        sikayet = Sikayet(
            user_id=ilan_users["other"],
            reported_user_id=ilan_users["owner"],
            kaynak_id=kaynak.id,
            mesaj_id=mesaj.id,
            tur="mesaj",
            sebep=f"Mesaj şikayeti (#{mesaj.id}): ilan mesajı",
        )
        db.session.add(sikayet)
        db.session.commit()
        kaynak_id = kaynak.id
        mesaj_id = mesaj.id
        sikayet_id = sikayet.id

        cleanup_ilan_relations(kaynak_id=kaynak_id)
        db.session.delete(db.session.get(Kaynak, kaynak_id))
        db.session.commit()

        assert db.session.get(Kaynak, kaynak_id) is None
        assert db.session.get(Mesaj, mesaj_id) is None
        assert db.session.get(Sikayet, sikayet_id) is None


def test_cleanup_atik_with_message_sikayet(app, ilan_users):
    with app.app_context():
        atik = _atik(ilan_users["owner"])
        mesaj = Mesaj(
            sender_id=ilan_users["other"],
            receiver_id=ilan_users["owner"],
            content="atik mesajı",
            atik_id=atik.id,
        )
        db.session.add(mesaj)
        db.session.flush()
        sikayet = Sikayet(
            user_id=ilan_users["other"],
            reported_user_id=ilan_users["owner"],
            atik_id=atik.id,
            mesaj_id=mesaj.id,
            tur="mesaj",
            sebep=f"Mesaj şikayeti (#{mesaj.id}): atik mesajı",
        )
        db.session.add(sikayet)
        db.session.commit()
        atik_id = atik.id
        mesaj_id = mesaj.id

        cleanup_ilan_relations(atik_id=atik_id)
        db.session.delete(db.session.get(Atik, atik_id))
        db.session.commit()

        assert db.session.get(Atik, atik_id) is None
        assert db.session.get(Mesaj, mesaj_id) is None
        assert Sikayet.query.filter_by(mesaj_id=mesaj_id).count() == 0


def test_cleanup_kaynak_removes_mesaj_bildirimleri(app, ilan_users):
    with app.app_context():
        kaynak = _kaynak(ilan_users["owner"])
        mesaj = Mesaj(
            sender_id=ilan_users["owner"],
            receiver_id=ilan_users["other"],
            content="bildirimli",
            kaynak_id=kaynak.id,
        )
        db.session.add(mesaj)
        db.session.flush()
        bildirim = Bildirim(
            user_id=ilan_users["other"],
            baslik="Mesaj",
            icerik="x",
            tur="mesaj",
            link=f"/mesajlar/{ilan_users['owner']}/{kaynak.id}/0",
            mesaj_id=mesaj.id,
        )
        db.session.add(bildirim)
        db.session.commit()
        kaynak_id = kaynak.id
        bildirim_id = bildirim.id

        cleanup_ilan_relations(kaynak_id=kaynak_id)
        db.session.delete(db.session.get(Kaynak, kaynak_id))
        db.session.commit()

        assert db.session.get(Bildirim, bildirim_id) is None


def test_ilan_sil_endpoint_kaynak_with_message_report(client, app, ilan_users):
    with app.app_context():
        kaynak = _kaynak(ilan_users["owner"])
        mesaj = Mesaj(
            sender_id=ilan_users["owner"],
            receiver_id=ilan_users["other"],
            content="şikayetli",
            kaynak_id=kaynak.id,
        )
        db.session.add(mesaj)
        db.session.flush()
        db.session.add(
            Sikayet(
                user_id=ilan_users["other"],
                reported_user_id=ilan_users["owner"],
                mesaj_id=mesaj.id,
                kaynak_id=kaynak.id,
                tur="mesaj",
                sebep=f"Mesaj şikayeti (#{mesaj.id}): şikayetli",
            )
        )
        db.session.commit()
        kaynak_id = kaynak.id

    _login(client, "owner@test.com")
    resp = client.post(f"/ilan_sil/kaynak/{kaynak_id}", follow_redirects=True)
    assert resp.status_code == 200

    with app.app_context():
        assert db.session.get(Kaynak, kaynak_id) is None
        assert Mesaj.query.filter_by(kaynak_id=kaynak_id).count() == 0
        assert Sikayet.query.filter_by(kaynak_id=kaynak_id).count() == 0


def test_admin_ilan_sil_atik_with_message_report(client, app, ilan_users):
    with app.app_context():
        atik = _atik(ilan_users["owner"])
        mesaj = Mesaj(
            sender_id=ilan_users["other"],
            receiver_id=ilan_users["owner"],
            content="admin sil",
            atik_id=atik.id,
        )
        db.session.add(mesaj)
        db.session.flush()
        db.session.add(
            Sikayet(
                user_id=ilan_users["other"],
                reported_user_id=ilan_users["owner"],
                mesaj_id=mesaj.id,
                atik_id=atik.id,
                tur="mesaj",
                sebep=f"Mesaj şikayeti (#{mesaj.id}): admin sil",
            )
        )
        db.session.commit()
        atik_id = atik.id

    _login(client, "adm@test.com")
    resp = client.post(f"/admin/ilan_sil/atik/{atik_id}", follow_redirects=True)
    assert resp.status_code == 200

    with app.app_context():
        assert db.session.get(Atik, atik_id) is None
        assert Sikayet.query.filter_by(atik_id=atik_id).count() == 0


def test_cleanup_kaynak_with_nested_comments(app, ilan_users):
    with app.app_context():
        kaynak = _kaynak(ilan_users["owner"])
        parent = Comment(
            content="üst yorum",
            user_id=ilan_users["other"],
            kaynak_id=kaynak.id,
        )
        db.session.add(parent)
        db.session.flush()
        reply = Comment(
            content="yanıt",
            user_id=ilan_users["owner"],
            kaynak_id=kaynak.id,
            parent_id=parent.id,
        )
        db.session.add(reply)
        db.session.commit()
        kaynak_id = kaynak.id
        parent_id = parent.id
        reply_id = reply.id

        cleanup_ilan_relations(kaynak_id=kaynak_id)
        db.session.delete(db.session.get(Kaynak, kaynak_id))
        db.session.commit()

        assert db.session.get(Comment, parent_id) is None
        assert db.session.get(Comment, reply_id) is None


def test_cleanup_atik_with_moderasyon_records(app, ilan_users):
    from models import IlanModerasyonAnaliz, IlanModerasyonKarar

    with app.app_context():
        atik = _atik(ilan_users["owner"])
        analiz = IlanModerasyonAnaliz(
            tur="atik",
            atik_id=atik.id,
            moderation_status="pending_review",
        )
        db.session.add(analiz)
        db.session.flush()
        karar = IlanModerasyonKarar(
            tur="atik",
            atik_id=atik.id,
            analiz_id=analiz.id,
            action_type="review",
            ai_decision="pending_review",
            admin_decision="approved",
            admin_user_id=ilan_users["admin"],
        )
        db.session.add(karar)
        db.session.commit()
        atik_id = atik.id
        analiz_id = analiz.id
        karar_id = karar.id

        from utils import cleanup_atik_relations

        cleanup_atik_relations(atik_id)
        db.session.delete(db.session.get(Atik, atik_id))
        db.session.commit()

        assert db.session.get(IlanModerasyonKarar, karar_id) is None
        assert db.session.get(IlanModerasyonAnaliz, analiz_id) is None


def test_cleanup_kaynak_with_ilan_sikayeti(app, ilan_users):
    with app.app_context():
        kaynak = _kaynak(ilan_users["owner"])
        sikayet = Sikayet(
            user_id=ilan_users["other"],
            reported_user_id=ilan_users["owner"],
            kaynak_id=kaynak.id,
            tur="ilan",
            sebep="Uygunsuz ilan",
        )
        db.session.add(sikayet)
        db.session.commit()
        kaynak_id = kaynak.id
        sikayet_id = sikayet.id

        cleanup_ilan_relations(kaynak_id=kaynak_id)
        db.session.delete(db.session.get(Kaynak, kaynak_id))
        db.session.commit()

        assert db.session.get(Sikayet, sikayet_id) is None
