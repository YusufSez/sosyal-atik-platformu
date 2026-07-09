"""Production: AI Health, Export, Compare, Flow, Explainability."""

import pytest

from auth_utils import hash_password
from constants import MODERATION_STATUS_PENDING_REVIEW
from extensions import db
from models import AiModerasyonHealthLog, Atik, User
from services.ai_health import ai_health_stats, record_ai_request
from services.moderation_compare import compare_analyses, latest_reanalyze_comparison
from services.moderation_explainability import compute_explainability_signals, enrich_explainability_signals
from services.moderation_export import EXPORT_SCOPES, export_csv
from services.moderation_flow import build_moderation_flow
from services.moderation_admin import dashboard_istatistikleri, ilan_detay_paketi


def _admin():
    u = User(
        username="prodadmin",
        email="prodadmin@test.com",
        password=hash_password("TestPass1"),
        is_admin=True,
        role="admin",
        is_completed=True,
        email_verified=True,
    )
    db.session.add(u)
    db.session.flush()
    return u


def _analiz_dict(**kw):
    base = {
        "analysis_version": 1,
        "model_name": "gemini-2.5-flash",
        "prompt_version": "2.1",
        "final_risk": 75,
        "initial_risk": 80,
        "confidence": 0.9,
        "purpose": "recycling",
        "category": "Metal",
        "matched_rules": ["purpose_recycling", "recycling_context"],
        "reason": "Geri dönüşüm",
        "moderation_status": MODERATION_STATUS_PENDING_REVIEW,
        "whitelist_applied": True,
        "spam_score": 10,
        "duplicate_score": 5,
        "text_analysis": {"risk_skoru": 20},
        "vision_analysis": {"primary_label": "Metal"},
        "photo_analyses": [],
        "triggered_by": "upload",
        "is_current": True,
    }
    base.update(kw)
    return enrich_explainability_signals(base)


@pytest.fixture
def prod_setup(app):
    with app.app_context():
        _admin()
        db.session.commit()
        yield {}


def test_ai_health_stats(app, prod_setup):
    with app.app_context():
        record_ai_request(model_name="gemini-2.5-flash", success=True, response_time_ms=450)
        record_ai_request(model_name="gemini-2.5-flash", success=False, response_time_ms=30000, error_type="timeout")
        db.session.commit()
        stats = ai_health_stats()
        assert stats["today_requests"] >= 2
        assert stats["model_name"]
        assert stats["prompt_version"]
        assert "healthy" in stats
        assert stats["timeout_count"] >= 1


def test_dashboard_includes_ai_health(app, prod_setup):
    with app.app_context():
        stats = dashboard_istatistikleri()
        assert "ai_health" in stats
        assert "model_name" in stats["ai_health"]


def test_explainability_signals():
    sonuc = _analiz_dict()
    pos, neg = compute_explainability_signals(sonuc)
    assert "purpose_recycling" in pos or "recycling_context" in pos
    enriched = enrich_explainability_signals(sonuc)
    assert "positive_signals" in enriched
    assert "negative_signals" in enriched


def test_prompt_compare():
    old = _analiz_dict(final_risk=80, analysis_version=1, confidence=0.7)
    new = _analiz_dict(final_risk=25, analysis_version=2, confidence=0.95, triggered_by="admin_reanalyze")
    cmp = compare_analyses(old, new)
    assert cmp["has_changes"] is True
    risk_row = next(r for r in cmp["rows"] if r["key"] == "final_risk")
    assert risk_row["changed"] is True
    assert risk_row["old"] == 80
    assert risk_row["new"] == 25


def test_latest_reanalyze_comparison():
    gecmis = [_analiz_dict(analysis_version=2), _analiz_dict(analysis_version=1, final_risk=90)]
    cmp = latest_reanalyze_comparison(gecmis)
    assert cmp is not None
    assert cmp["old_version"] == 1


def test_moderation_flow():
    analiz = _analiz_dict()
    steps = build_moderation_flow(analiz, [{"event_type": "ilan_created", "title": "İlan oluşturuldu"}])
    titles = [s["title"] for s in steps]
    assert "İlan" in titles[0]
    assert "Decision" in titles[-1]
    assert any(s["status"] == "done" for s in steps)


def test_export_csv_records(app, prod_setup):
    with app.app_context():
        user = User(username="u1", email="u1@test.com", password=hash_password("TestPass1"), is_completed=True, email_verified=True)
        db.session.add(user)
        db.session.flush()
        ilan = Atik(
            baslik="Export test", aciklama="Test", resim="default.jpg",
            latitude=41.0, longitude=29.0, user_id=user.id, kategori="Diğer",
            moderation_status=MODERATION_STATUS_PENDING_REVIEW, ai_risk_score=50,
        )
        db.session.add(ilan)
        db.session.commit()
        data, filename = export_csv("records")
        assert filename.endswith(".csv")
        assert b"Export test" in data or b"tur" in data


def test_export_scopes():
    assert "records" in EXPORT_SCOPES
    assert "dashboard" in EXPORT_SCOPES
    assert "decisions" in EXPORT_SCOPES
    assert "timeline" in EXPORT_SCOPES


def test_detail_includes_flow_and_compare(app, prod_setup):
    with app.app_context():
        user = User(username="u2", email="u2@test.com", password=hash_password("TestPass1"), is_completed=True, email_verified=True)
        db.session.add(user)
        db.session.flush()
        ilan = Atik(
            baslik="Flow test", aciklama="Uzun açıklama metni", resim="default.jpg",
            latitude=41.0, longitude=29.0, user_id=user.id, kategori="Diğer",
            moderation_status=MODERATION_STATUS_PENDING_REVIEW, ai_risk_score=70,
        )
        db.session.add(ilan)
        db.session.flush()
        from services.moderation_analysis import analiz_kaydet
        analiz_kaydet(ilan, "atik", _analiz_dict(), triggered_by="upload")
        analiz_kaydet(ilan, "atik", _analiz_dict(final_risk=30, analysis_version=2), triggered_by="admin_reanalyze")
        db.session.commit()
        paket = ilan_detay_paketi("atik", ilan.id)
        assert paket["moderation_flow"]
        assert paket["prompt_karsilastirma"] is not None


def test_export_endpoint_requires_admin(client, prod_setup):
    client.post("/giris", data={"email": "prodadmin@test.com", "password": "TestPass1"}, follow_redirects=True)
    resp = client.get("/admin/moderasyon/export/dashboard/csv")
    assert resp.status_code == 200
    assert "text/csv" in resp.content_type


def test_export_forbidden_for_user(client, app, prod_setup):
    with app.app_context():
        user = User(username="norm", email="norm@test.com", password=hash_password("TestPass1"), is_completed=True, email_verified=True)
        db.session.add(user)
        db.session.commit()
    client.post("/giris", data={"email": "norm@test.com", "password": "TestPass1"}, follow_redirects=True)
    assert client.get("/admin/moderasyon/export/records/csv").status_code == 403


def test_dashboard_health_card(client, app, prod_setup):
    with app.app_context():
        record_ai_request(model_name="gemini-2.5-flash", success=True, response_time_ms=200)
        db.session.commit()
    client.post("/giris", data={"email": "prodadmin@test.com", "password": "TestPass1"}, follow_redirects=True)
    resp = client.get("/admin/moderasyon/")
    assert resp.status_code == 200
    assert b"AI Health" in resp.data
