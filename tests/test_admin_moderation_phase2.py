"""Phase 2: Spam Score, Duplicate Detection, Priority Queue."""

from datetime import timedelta

import pytest

from auth_utils import hash_password
from constants import MODERATION_STATUS_PENDING_REVIEW
from extensions import db
from models import Atik, IlanModerasyonAnaliz, User
from services.duplicate_detection import detect_duplicates
from services.moderation_admin import dashboard_istatistikleri, moderasyon_listesi, spam_duplicate_analitigi
from services.moderation_analysis import analiz_kaydet
from services.moderation_priority import priority_sort_key, sort_moderation_items
from services.moderation_signals import enrich_upload_signals
from services.spam_score import compute_spam_score
from utils import utc_now


def _user(username, email):
    u = User(
        username=username,
        email=email,
        password=hash_password("TestPass1"),
        is_completed=True,
        email_verified=True,
    )
    db.session.add(u)
    db.session.flush()
    return u


def _atik(user, baslik="Test ilan", aciklama="Uzun bir test açıklaması burada yer alıyor.", **kw):
    ilan = Atik(
        baslik=baslik,
        aciklama=aciklama,
        resim="default.jpg",
        latitude=41.0,
        longitude=29.0,
        user_id=user.id,
        kategori="Diğer",
        moderation_status=MODERATION_STATUS_PENDING_REVIEW,
        ai_risk_score=75,
        **kw,
    )
    db.session.add(ilan)
    db.session.flush()
    return ilan


def _analiz(ilan, spam=0, dup=0, spam_reasons=None, dup_matches=None):
    return analiz_kaydet(
        ilan,
        "atik",
        {
            "risk_skoru": 75,
            "final_risk": 75,
            "initial_risk": 80,
            "moderation_status": MODERATION_STATUS_PENDING_REVIEW,
            "spam_score": spam,
            "duplicate_score": dup,
            "spam_reasons": spam_reasons or [],
            "duplicate_reasons": [],
            "duplicate_matches": dup_matches or [],
        },
        triggered_by="upload",
    )


@pytest.fixture
def p2_setup(app):
    with app.app_context():
        user = _user("p2user", "p2user@test.com")
        ilan = _atik(user)
        _analiz(ilan, spam=10, dup=5)
        db.session.commit()
        yield {"user_id": user.id, "ilan_id": ilan.id}


def test_spam_short_description(app):
    with app.app_context():
        user = _user("spam1", "spam1@test.com")
        result = compute_spam_score(
            baslik="Başlık",
            aciklama="kısa",
            user_id=user.id,
        )
        assert result["score"] >= 10
        codes = [r["code"] for r in result["reasons"]]
        assert "short_description" in codes


def test_spam_same_title(app):
    with app.app_context():
        user = _user("spam2", "spam2@test.com")
        _atik(user, baslik="Aynı Başlık Test")
        db.session.commit()
        result = compute_spam_score(
            baslik="Aynı Başlık Test",
            aciklama="Farklı ama yeterince uzun bir açıklama metni.",
            user_id=user.id,
        )
        codes = [r["code"] for r in result["reasons"]]
        assert "same_title" in codes


def test_spam_fast_creation(app):
    with app.app_context():
        user = _user("spam3", "spam3@test.com")
        ilan = _atik(user, baslik="İlk ilan")
        ilan.tarih = utc_now()
        db.session.commit()
        result = compute_spam_score(
            baslik="İkinci ilan",
            aciklama="Yeterince uzun ikinci ilan açıklaması burada.",
            user_id=user.id,
        )
        codes = [r["code"] for r in result["reasons"]]
        assert "fast_creation" in codes


def test_spam_repeating_words(app):
    with app.app_context():
        user = _user("spam4", "spam4@test.com")
        text = "atık atık atık atık atık atık geri dönüşüm"
        result = compute_spam_score(
            baslik="Başlık",
            aciklama=text,
            user_id=user.id,
        )
        codes = [r["code"] for r in result["reasons"]]
        assert "repeating_words" in codes


def test_duplicate_same_title_and_user(app):
    with app.app_context():
        user = _user("dup1", "dup1@test.com")
        existing = _atik(
            user,
            baslik="Duplicate Test Başlık",
            aciklama="Orijinal açıklama metni yeterince uzun.",
        )
        existing.kategori = "Metal"
        db.session.commit()
        result = detect_duplicates(
            baslik="Duplicate Test Başlık",
            aciklama="Farklı açıklama ama yeterince uzun metin.",
            tur="atik",
            user_id=user.id,
            kategori="Metal",
            latitude=41.0,
            longitude=29.0,
            exclude_ilan_id=None,
        )
        assert result["score"] >= 40
        assert len(result["matches"]) >= 1
        assert result["matches"][0]["ilan_id"] == existing.id


def test_duplicate_similar_description(app):
    with app.app_context():
        user = _user("dup2", "dup2@test.com")
        desc = "Bu açıklama duplicate test için kullanılıyor ve yeterince uzun."
        _atik(user, baslik="İlan A", aciklama=desc)
        db.session.commit()
        result = detect_duplicates(
            baslik="İlan B",
            aciklama=desc,
            tur="atik",
            user_id=user.id,
            exclude_ilan_id=None,
        )
        assert result["score"] >= 30
        assert "Aynı açıklama" in result["reasons"]


def test_enrich_upload_signals(app):
    with app.app_context():
        user = _user("sig1", "sig1@test.com")
        ai_sonuc = {"risk_skoru": 50, "moderation_status": "approved"}
        enrich_upload_signals(
            ai_sonuc,
            tur="atik",
            ilan_id=None,
            baslik="Test",
            aciklama="kısa",
            user_id=user.id,
            upload_ip="127.0.0.1",
            user_agent="TestAgent/1.0",
        )
        assert "spam_score" in ai_sonuc
        assert "duplicate_score" in ai_sonuc
        assert ai_sonuc["upload_ip"] == "127.0.0.1"


def test_priority_queue_sort():
    from services.moderation_admin import ModerasyonListeOgesi
    from datetime import datetime

    items = [
        ModerasyonListeOgesi(
            tur="atik", ilan_id=1, baslik="A", aciklama_ozet="", kullanici="u", kullanici_id=1,
            tarih=datetime(2026, 1, 3), risk_skoru=70, moderation_status=MODERATION_STATUS_PENDING_REVIEW,
            category=None, purpose=None, confidence=None, spam_score=20, duplicate_score=10,
            kapak="default.jpg", kategori=None, alt_kategori=None,
        ),
        ModerasyonListeOgesi(
            tur="atik", ilan_id=2, baslik="B", aciklama_ozet="", kullanici="u", kullanici_id=1,
            tarih=datetime(2026, 1, 1), risk_skoru=90, moderation_status=MODERATION_STATUS_PENDING_REVIEW,
            category=None, purpose=None, confidence=None, spam_score=50, duplicate_score=30,
            kapak="default.jpg", kategori=None, alt_kategori=None,
        ),
        ModerasyonListeOgesi(
            tur="atik", ilan_id=3, baslik="C", aciklama_ozet="", kullanici="u", kullanici_id=1,
            tarih=datetime(2026, 1, 2), risk_skoru=90, moderation_status=MODERATION_STATUS_PENDING_REVIEW,
            category=None, purpose=None, confidence=None, spam_score=60, duplicate_score=20,
            kapak="default.jpg", kategori=None, alt_kategori=None,
        ),
    ]
    sorted_items = sort_moderation_items(items)
    assert sorted_items[0].ilan_id == 3
    assert sorted_items[1].ilan_id == 2


def test_priority_sort_key_risk_first():
    class Item:
        moderation_status = MODERATION_STATUS_PENDING_REVIEW
        risk_skoru = 80
        spam_score = 10
        duplicate_score = 10
        tarih = utc_now()

    class Item2:
        moderation_status = MODERATION_STATUS_PENDING_REVIEW
        risk_skoru = 90
        spam_score = 5
        duplicate_score = 5
        tarih = utc_now()

    assert priority_sort_key(Item2) < priority_sort_key(Item)


def test_spam_duplicate_analitigi(app, p2_setup):
    with app.app_context():
        user = db.session.get(User, p2_setup["user_id"])
        ilan2 = _atik(user, baslik="Spam ilan 2")
        _analiz(ilan2, spam=65, dup=55)
        db.session.commit()
        stats = spam_duplicate_analitigi()
        assert stats["spam_dagilimi"]["61-100"] >= 1
        assert stats["duplicate_orani"] >= 0


def test_dashboard_phase2_stats(app, p2_setup):
    with app.app_context():
        stats = dashboard_istatistikleri()
        assert "spam_dagilimi" in stats
        assert "duplicate_orani" in stats
        assert "en_spam_kullanicilar" in stats
        assert "en_tekrar_ilanlar" in stats


def test_moderasyon_listesi_priority(app, p2_setup):
    with app.app_context():
        user = db.session.get(User, p2_setup["user_id"])
        ilan_high = _atik(user, baslik="Yüksek risk")
        ilan_high.ai_risk_score = 95
        ilan_high.moderation_status = MODERATION_STATUS_PENDING_REVIEW
        _analiz(ilan_high, spam=80, dup=70)
        db.session.commit()
        items = moderasyon_listesi({"status": MODERATION_STATUS_PENDING_REVIEW})
        pending = [i for i in items if i.moderation_status == MODERATION_STATUS_PENDING_REVIEW]
        if len(pending) >= 2:
            assert pending[0].risk_skoru >= pending[1].risk_skoru or pending[0].spam_score >= pending[1].spam_score


def test_analiz_kaydet_spam_fields(app, p2_setup):
    with app.app_context():
        ilan = db.session.get(Atik, p2_setup["ilan_id"])
        kayit = analiz_kaydet(
            ilan, "atik",
            {
                "risk_skoru": 50, "final_risk": 50, "initial_risk": 50,
                "moderation_status": "approved",
                "spam_score": 42,
                "duplicate_score": 55,
                "spam_reasons": [{"code": "short_description", "label": "Kısa", "points": 10}],
                "duplicate_reasons": ["Aynı başlık"],
                "duplicate_matches": [{"tur": "atik", "ilan_id": 1, "baslik": "X", "score": 50}],
            },
            triggered_by="upload",
        )
        db.session.commit()
        assert kayit.spam_score == 42
        assert kayit.duplicate_score == 55


def test_detail_page_spam_duplicate(client, app, p2_setup):
    with app.app_context():
        admin = User(
            username="p2admin",
            email="p2admin@test.com",
            password=hash_password("TestPass1"),
            is_admin=True,
            role="admin",
            is_completed=True,
            email_verified=True,
        )
        db.session.add(admin)
        ilan = db.session.get(Atik, p2_setup["ilan_id"])
        analiz_kaydet(
            ilan, "atik",
            {
                "risk_skoru": 75, "final_risk": 75, "initial_risk": 80,
                "moderation_status": MODERATION_STATUS_PENDING_REVIEW,
                "spam_score": 45,
                "duplicate_score": 60,
                "spam_reasons": [{"code": "same_title", "label": "Aynı başlık", "points": 18}],
                "duplicate_reasons": ["Aynı başlık"],
                "duplicate_matches": [],
            },
            triggered_by="upload",
        )
        db.session.commit()
        ilan_id = p2_setup["ilan_id"]
    client.post("/giris", data={"email": "p2admin@test.com", "password": "TestPass1"}, follow_redirects=True)
    resp = client.get(f"/admin/moderasyon/ilan/atik/{ilan_id}")
    assert resp.status_code == 200
    assert b"Spam" in resp.data
    assert b"Duplicate" in resp.data
