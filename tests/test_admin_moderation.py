"""Admin AI moderasyon paneli testleri."""

import json

import pytest

from auth_utils import hash_password
from constants import MODERATION_STATUS_APPROVED, MODERATION_STATUS_PENDING_REVIEW
from extensions import db
from models import Atik, IlanModerasyonNot, User
from services.ai_moderation import enrich_explainability
from services.moderation_admin import dashboard_istatistikleri, ilan_detay_paketi, moderasyon_listesi
from services.moderation_analysis import analiz_gecmisi, analiz_kaydet, guncel_analiz, yeniden_ai_analizi
from services.moderation_messages import kullanici_moderasyon_mesaji
from services.moderation_timeline import timeline_ekle, timeline_listele


def _admin_user():
    user = User(
        username="modadmin",
        email="modadmin@test.com",
        password=hash_password("TestPass1"),
        is_admin=True,
        role="admin",
        is_completed=True,
        email_verified=True,
    )
    db.session.add(user)
    db.session.flush()
    return user


def _normal_user():
    user = User(
        username="normaluser",
        email="normal@test.com",
        password=hash_password("TestPass1"),
        is_completed=True,
        email_verified=True,
    )
    db.session.add(user)
    db.session.flush()
    return user


def _atik_ilan(user, status=MODERATION_STATUS_PENDING_REVIEW, risk=75):
    ilan = Atik(
        baslik="Bitkisel atık yağ",
        aciklama="Geri dönüşüm için 5 litre yağ verilecektir.",
        resim="default.jpg",
        latitude=41.0,
        longitude=29.0,
        user_id=user.id,
        kategori="Diğer",
        moderation_status=status,
        ai_risk_score=risk,
        moderation_reason="Test",
    )
    db.session.add(ilan)
    db.session.flush()
    return ilan


def _mock_ai_sonuc(risk=25, initial=80):
    return enrich_explainability(
        {
            "kategori": "Bitkisel Atık Yağ",
            "risk_skoru": risk,
            "initial_risk": initial,
            "guvenli": True,
            "moderation_status": MODERATION_STATUS_APPROVED,
            "is_recyclable": True,
            "purpose": "recycling",
            "confidence": 0.96,
            "matched_rules": ["purpose_detected", "whitelist_material"],
            "whitelist_applied": True,
            "risk_adjustment_reason": "Geri dönüşüm bağlamı",
            "reason": "Geri dönüşüm amaçlı paylaşım",
            "uygunsuz": False,
        },
        baslik="Bitkisel atık yağ",
        aciklama="Geri dönüşüm için verilecektir",
        tur="atik",
        initial_risk=initial,
    )


@pytest.fixture
def mod_setup(app):
    with app.app_context():
        admin = _admin_user()
        user = _normal_user()
        ilan = _atik_ilan(user)
        db.session.commit()
        yield {"admin_id": admin.id, "user_id": user.id, "ilan_id": ilan.id}


def test_enrich_explainability_fields():
    sonuc = _mock_ai_sonuc()
    assert sonuc["initial_risk"] == 80
    assert sonuc["final_risk"] == 25
    assert sonuc["risk_adjustment"] == 55
    assert sonuc["confidence"] == 0.96
    assert "purpose_detected" in sonuc["matched_rules"]


def test_analiz_kaydet_versioning(app, mod_setup):
    with app.app_context():
        ilan = db.session.get(Atik, mod_setup["ilan_id"])
        admin = db.session.get(User, mod_setup["admin_id"])
        a1 = analiz_kaydet(ilan, "atik", _mock_ai_sonuc(risk=30, initial=80), triggered_by="upload")
        a2 = analiz_kaydet(
            ilan, "atik", _mock_ai_sonuc(risk=20, initial=70),
            triggered_by="admin_reanalyze", admin_user_id=admin.id,
        )
        db.session.commit()
        assert a1.analysis_version == 1
        assert a2.analysis_version == 2
        assert a1.is_current is False
        assert a2.is_current is True
        assert len(analiz_gecmisi("atik", ilan.id)) == 2


def test_timeline_events(app, mod_setup):
    with app.app_context():
        ilan_id = mod_setup["ilan_id"]
        admin_id = mod_setup["admin_id"]
        timeline_ekle("atik", ilan_id, "ilan_created", "İlan oluşturuldu")
        timeline_ekle("atik", ilan_id, "admin_approved", "Admin onayladı", admin_user_id=admin_id)
        db.session.commit()
        events = timeline_listele("atik", ilan_id)
        assert len(events) == 2
        assert events[-1].event_type == "admin_approved"


def test_yeniden_ai_analizi_mock(app, mod_setup, monkeypatch):
    with app.app_context():
        ilan_id = mod_setup["ilan_id"]
        admin_id = mod_setup["admin_id"]

        monkeypatch.setattr(
            "services.moderation_analysis.tam_ilan_analizi_yap",
            lambda *a, **k: _mock_ai_sonuc(risk=24, initial=81),
        )
        ai_sonuc, kayit = yeniden_ai_analizi("atik", ilan_id, admin_id)
        db.session.commit()
        assert kayit.analysis_version >= 1
        assert ai_sonuc["risk_skoru"] == 24
        assert guncel_analiz("atik", ilan_id).final_risk == 24


def test_admin_not_kaydi(app, mod_setup):
    with app.app_context():
        ilan_id = mod_setup["ilan_id"]
        admin_id = mod_setup["admin_id"]
        db.session.add(IlanModerasyonNot(
            tur="atik", atik_id=ilan_id, admin_user_id=admin_id, note="Manuel inceleme tamam",
        ))
        db.session.commit()
        assert len(ilan_detay_paketi("atik", ilan_id)["notlar"]) == 1


def test_dashboard_istatistikleri(app, mod_setup):
    with app.app_context():
        ilan = db.session.get(Atik, mod_setup["ilan_id"])
        analiz_kaydet(ilan, "atik", _mock_ai_sonuc(), triggered_by="upload")
        db.session.commit()
        stats = dashboard_istatistikleri()
        assert stats["toplam_analiz"] >= 1
        assert "grafik_7_gun" in stats


def test_moderasyon_listesi_filtre(app, mod_setup):
    with app.app_context():
        ilan_id = mod_setup["ilan_id"]
        items = moderasyon_listesi({"status": MODERATION_STATUS_PENDING_REVIEW})
        assert any(i.ilan_id == ilan_id for i in items)


def test_kullanici_mesajlari():
    msg, cat = kullanici_moderasyon_mesaji(MODERATION_STATUS_PENDING_REVIEW)
    assert "yapay zekâ" in msg
    assert cat == "info"
    msg2, cat2 = kullanici_moderasyon_mesaji(MODERATION_STATUS_APPROVED)
    assert "yayınlandı" in msg2
    assert cat2 == "success"


def _login(client, email):
    client.post("/giris", data={"email": email, "password": "TestPass1"}, follow_redirects=True)


def test_admin_moderation_requires_admin(client, mod_setup):
    _login(client, "normal@test.com")
    assert client.get("/admin/moderasyon/").status_code == 403


def test_admin_moderation_dashboard_access(client, mod_setup):
    _login(client, "modadmin@test.com")
    resp = client.get("/admin/moderasyon/")
    assert resp.status_code == 200
    assert b"AI Moderasyon Dashboard" in resp.data


def test_admin_moderation_list_filter(client, mod_setup):
    _login(client, "modadmin@test.com")
    resp = client.get("/admin/moderasyon/ilanlar?status=pending_review")
    assert resp.status_code == 200
    assert b"Bitkisel" in resp.data or b"Moderasyon" in resp.data


def test_admin_moderation_detail(client, app, mod_setup):
    with app.app_context():
        ilan = db.session.get(Atik, mod_setup["ilan_id"])
        analiz_kaydet(ilan, "atik", _mock_ai_sonuc(), triggered_by="upload")
        db.session.commit()
        ilan_id = ilan.id
    _login(client, "modadmin@test.com")
    resp = client.get(f"/admin/moderasyon/ilan/atik/{ilan_id}")
    assert resp.status_code == 200
    assert b"AI Analiz Raporu" in resp.data
    assert b"Timeline" in resp.data


def test_ham_json_admin_only(client, app, mod_setup):
    with app.app_context():
        ilan = db.session.get(Atik, mod_setup["ilan_id"])
        analiz_kaydet(ilan, "atik", _mock_ai_sonuc(), triggered_by="upload")
        db.session.commit()
        ilan_id = ilan.id
    _login(client, "modadmin@test.com")
    resp = client.get(f"/admin/moderasyon/json/atik/{ilan_id}")
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert data.get("purpose") == "recycling" or data.get("matched_rules")


def test_admin_onayla_action(client, app, mod_setup):
    with app.app_context():
        ilan_id = mod_setup["ilan_id"]
    _login(client, "modadmin@test.com")
    resp = client.post(f"/admin/moderasyon/onayla/atik/{ilan_id}", follow_redirects=True)
    assert resp.status_code == 200
    with app.app_context():
        ilan = db.session.get(Atik, ilan_id)
        assert ilan.moderation_status == MODERATION_STATUS_APPROVED


def test_photo_analysis_structure():
    from services.moderation_photos import merge_photo_analyses

    photos = [
        {"index": 1, "label": "Bitkisel Atık Yağı", "confidence": 0.97, "risk_score": 20, "detected": {}},
        {"index": 2, "label": "Metal Varil", "confidence": 0.91, "risk_score": 25, "detected": {}},
    ]
    merged = merge_photo_analyses(photos)
    assert merged["photo_count"] == 2
    assert merged["primary_label"] == "Metal Varil"
