"""Phase 1: Admin karar analitiği, activity log, dashboard metrikleri."""

import json

import pytest

from auth_utils import hash_password
from constants import (
    MODERATION_STATUS_APPROVED,
    MODERATION_STATUS_PENDING_REVIEW,
    MODERATION_STATUS_REJECTED,
)
from extensions import db
from models import Atik, IlanModerasyonActivityLog, IlanModerasyonKarar, User
from services.moderation_activity import activity_listesi, log_moderasyon_activity
from services.moderation_admin import dashboard_istatistikleri, ilan_detay_paketi
from services.moderation_admin_actions import kaydet_moderasyon_aksiyonu
from services.moderation_analysis import analiz_kaydet
from services.moderation_decisions import ilan_karar_ozeti, karar_analitigi, kaydet_admin_karar


def _admin_user():
    user = User(
        username="phase1admin",
        email="phase1admin@test.com",
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
        username="phase1user",
        email="phase1user@test.com",
        password=hash_password("TestPass1"),
        is_completed=True,
        email_verified=True,
    )
    db.session.add(user)
    db.session.flush()
    return user


def _mock_ai_sonuc(status=MODERATION_STATUS_PENDING_REVIEW, risk=75):
    return {
        "kategori": "Bitkisel Atık Yağ",
        "risk_skoru": risk,
        "initial_risk": 80,
        "final_risk": risk,
        "guvenli": status == MODERATION_STATUS_APPROVED,
        "moderation_status": status,
        "is_recyclable": True,
        "purpose": "recycling",
        "confidence": 0.9,
        "matched_rules": ["purpose_detected"],
        "whitelist_applied": False,
        "reason": "Test analiz",
        "uygunsuz": False,
    }


def _atik_ilan(user, status=MODERATION_STATUS_PENDING_REVIEW, risk=75):
    ilan = Atik(
        baslik="Phase1 test ilanı",
        aciklama="Test açıklama",
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


@pytest.fixture
def phase1_setup(app):
    with app.app_context():
        admin = _admin_user()
        user = _normal_user()
        ilan = _atik_ilan(user)
        analiz_kaydet(ilan, "atik", _mock_ai_sonuc(), triggered_by="upload")
        db.session.commit()
        yield {"admin_id": admin.id, "ilan_id": ilan.id}


def test_override_kaydi(app, phase1_setup):
    with app.app_context():
        ilan_id = phase1_setup["ilan_id"]
        admin_id = phase1_setup["admin_id"]
        kaydet_admin_karar(
            "atik",
            ilan_id,
            admin_id,
            MODERATION_STATUS_APPROVED,
            "approve",
            ai_decision=MODERATION_STATUS_PENDING_REVIEW,
            category="Bitkisel Atık Yağ",
            purpose="recycling",
            decision_version=1,
        )
        db.session.commit()
        karar = IlanModerasyonKarar.query.filter_by(atik_id=ilan_id).first()
        assert karar is not None
        assert karar.override is True
        assert karar.decision_match is False
        assert karar.ai_decision == MODERATION_STATUS_PENDING_REVIEW
        assert karar.admin_decision == MODERATION_STATUS_APPROVED


def test_activity_log_kaydi(app, phase1_setup):
    with app.app_context():
        ilan_id = phase1_setup["ilan_id"]
        admin_id = phase1_setup["admin_id"]
        log_moderasyon_activity(
            "approve",
            tur="atik",
            ilan_id=ilan_id,
            note="Test onay",
            admin_user_id=admin_id,
        )
        db.session.commit()
        logs = activity_listesi(tur="atik")
        assert len(logs) >= 1
        assert logs[0].action == "approve"
        assert logs[0].note == "Test onay"


def test_karar_analitigi(app, phase1_setup):
    with app.app_context():
        ilan_id = phase1_setup["ilan_id"]
        admin_id = phase1_setup["admin_id"]
        kaydet_admin_karar(
            "atik", ilan_id, admin_id, MODERATION_STATUS_APPROVED, "approve",
            ai_decision=MODERATION_STATUS_PENDING_REVIEW,
            category="Bitkisel Atık Yağ", purpose="recycling",
        )
        kaydet_admin_karar(
            "atik", ilan_id, admin_id, MODERATION_STATUS_REJECTED, "reject",
            ai_decision=MODERATION_STATUS_APPROVED,
            category="Metal", purpose="disposal",
        )
        db.session.commit()
        stats = karar_analitigi()
        assert stats["false_positive"] >= 1
        assert stats["false_negative"] >= 1
        assert stats["pending_to_approved"] >= 1
        assert stats["override_rate"] > 0


def test_dashboard_phase1_stats(app, phase1_setup):
    with app.app_context():
        ilan_id = phase1_setup["ilan_id"]
        admin_id = phase1_setup["admin_id"]
        kaydet_admin_karar(
            "atik", ilan_id, admin_id, MODERATION_STATUS_APPROVED, "approve",
            ai_decision=MODERATION_STATUS_PENDING_REVIEW,
        )
        db.session.commit()
        stats = dashboard_istatistikleri()
        assert "ai_accuracy" in stats
        assert "override_rate" in stats
        assert "false_positive" in stats
        assert "pending_to_approved" in stats


def test_ilan_karar_ozeti(app, phase1_setup):
    with app.app_context():
        ilan_id = phase1_setup["ilan_id"]
        admin_id = phase1_setup["admin_id"]
        kaydet_admin_karar(
            "atik", ilan_id, admin_id, MODERATION_STATUS_APPROVED, "approve",
            ai_decision=MODERATION_STATUS_PENDING_REVIEW,
        )
        db.session.commit()
        ozet = ilan_karar_ozeti("atik", ilan_id, MODERATION_STATUS_APPROVED)
        assert ozet["ai_decision"] == MODERATION_STATUS_PENDING_REVIEW
        assert ozet["admin_decision"] == MODERATION_STATUS_APPROVED
        assert ozet["override"] is True


def test_detay_sayfasi_karar_karsilastirma(client, app, phase1_setup):
    with app.app_context():
        ilan_id = phase1_setup["ilan_id"]
        admin_id = phase1_setup["admin_id"]
        kaydet_admin_karar(
            "atik", ilan_id, admin_id, MODERATION_STATUS_APPROVED, "approve",
            ai_decision=MODERATION_STATUS_PENDING_REVIEW,
        )
        db.session.commit()
    client.post("/giris", data={"email": "phase1admin@test.com", "password": "TestPass1"}, follow_redirects=True)
    resp = client.get(f"/admin/moderasyon/ilan/atik/{phase1_setup['ilan_id']}")
    assert resp.status_code == 200
    assert b"Karar Kar\xc5\x9f\xc4\xb1la\xc5\x9ft\xc4\xb1rmas\xc4\xb1" in resp.data or b"Karar" in resp.data
    assert b"AI Karar" in resp.data or b"AI Karar\xc4\xb1" in resp.data


def test_activity_log_sayfasi(client, app, phase1_setup):
    with app.app_context():
        ilan_id = phase1_setup["ilan_id"]
        admin_id = phase1_setup["admin_id"]
        log_moderasyon_activity("note", tur="atik", ilan_id=ilan_id, note="Test", admin_user_id=admin_id)
        db.session.commit()
    client.post("/giris", data={"email": "phase1admin@test.com", "password": "TestPass1"}, follow_redirects=True)
    resp = client.get("/admin/moderasyon/activity")
    assert resp.status_code == 200
    assert b"Activity Log" in resp.data


def test_activity_log_yetki(client, phase1_setup):
    client.post("/giris", data={"email": "phase1user@test.com", "password": "TestPass1"}, follow_redirects=True)
    assert client.get("/admin/moderasyon/activity").status_code == 403


def test_onayla_override_ve_activity(client, app, phase1_setup):
    with app.app_context():
        ilan_id = phase1_setup["ilan_id"]
    client.post("/giris", data={"email": "phase1admin@test.com", "password": "TestPass1"}, follow_redirects=True)
    client.post(f"/admin/moderasyon/onayla/atik/{ilan_id}", follow_redirects=True)
    with app.app_context():
        karar = IlanModerasyonKarar.query.filter_by(atik_id=ilan_id, action_type="approve").first()
        assert karar is not None
        assert karar.override is True
        assert IlanModerasyonActivityLog.query.filter_by(atik_id=ilan_id, action="approve").count() >= 1


def test_moderasyon_aksiyonu_entegrasyon(app, phase1_setup):
    with app.app_context():
        ilan_id = phase1_setup["ilan_id"]
        admin_id = phase1_setup["admin_id"]
        kaydet_moderasyon_aksiyonu(
            "reject",
            "atik",
            ilan_id,
            admin_id,
            admin_decision=MODERATION_STATUS_REJECTED,
            ilan_status_before=MODERATION_STATUS_PENDING_REVIEW,
            activity_note="Red test",
        )
        db.session.commit()
        assert IlanModerasyonKarar.query.filter_by(atik_id=ilan_id).count() == 1
        assert IlanModerasyonActivityLog.query.filter_by(atik_id=ilan_id).count() == 1
