"""Sustainability Scoring Engine — skor, not, sıralama, AI, PDF."""

from datetime import timedelta
from unittest.mock import patch

import pytest

from auth_utils import hash_password
from constants import (
    ROLE_MINISTRY,
    ROLE_MUNICIPALITY,
    SUSTAINABILITY_WEIGHTS,
)
from extensions import db
from models import Atik, CevreselEtki, Kaynak, User
from services.sustainability_ai import generate_sustainability_suggestions
from services.sustainability_pdf import export_sustainability_pdf
from services.sustainability_scoring import (
    grade_for_score,
    municipality_leaderboard,
    province_ranking,
    score_municipality,
    score_region,
    sustainability_dashboard,
    turkey_ranking,
)
from utils import utc_now


def _user(**kwargs):
    defaults = dict(
        password=hash_password("TestPass1"),
        is_completed=True,
        email_verified=True,
        role="user",
        is_admin=False,
    )
    defaults.update(kwargs)
    user = User(**defaults)
    db.session.add(user)
    db.session.commit()
    return user


def _login(client, email):
    client.get("/cikis", follow_redirects=True)
    client.post(
        "/giris",
        data={"email": email, "password": "TestPass1"},
        follow_redirects=True,
    )


@pytest.fixture
def sustainability_data(app):
    with app.app_context():
        muni_a = _user(
            username="belediye_sus_a",
            email="belediye_sus_a@test.com",
            role=ROLE_MUNICIPALITY,
            il="Sakarya",
            ilce="Serdivan",
            latitude=40.77,
            longitude=30.39,
        )
        muni_b = _user(
            username="belediye_sus_b",
            email="belediye_sus_b@test.com",
            role=ROLE_MUNICIPALITY,
            il="Ankara",
            ilce="Çankaya",
            latitude=39.92,
            longitude=32.85,
        )
        citizen_a = _user(
            username="vat_sus_a",
            email="vat_sus_a@test.com",
            il="Sakarya",
            ilce="Serdivan",
            latitude=40.76,
            longitude=30.38,
        )
        citizen_a2 = _user(
            username="vat_sus_a2",
            email="vat_sus_a2@test.com",
            il="Sakarya",
            ilce="Serdivan",
        )
        citizen_b = _user(
            username="vat_sus_b",
            email="vat_sus_b@test.com",
            il="Ankara",
            ilce="Çankaya",
        )
        ministry = _user(
            username="bakan_sus",
            email="bakan_sus@test.com",
            role=ROLE_MINISTRY,
        )
        normal = _user(username="normal_sus", email="normal_sus@test.com")
        admin = _user(
            username="admin_sus",
            email="admin_sus@test.com",
            role="admin",
            is_admin=True,
        )

        now = utc_now()
        kaynak = Kaynak(
            baslik="Koltuk Sus",
            aciklama="Test",
            durum="Temiz",
            kategori="Mobilya",
            resim="default.jpg",
            latitude=40.77,
            longitude=30.39,
            ilan_durumu="Teslim Edildi",
            moderation_status="approved",
            ai_risk_score=15,
            user_id=citizen_a.id,
            tarih=now - timedelta(days=5),
        )
        atik = Atik(
            baslik="Plastik Sus",
            aciklama="Test",
            kategori="Plastik",
            resim="default.jpg",
            latitude=40.77,
            longitude=30.39,
            ilan_durumu="Teslim Edildi",
            moderation_status="approved",
            ai_risk_score=20,
            user_id=citizen_a.id,
            tarih=now - timedelta(days=4),
        )
        atik_elektronik = Atik(
            baslik="Telefon Sus",
            aciklama="Elektronik",
            kategori="Elektronik",
            resim="default.jpg",
            latitude=40.77,
            longitude=30.39,
            ilan_durumu="Aktif",
            moderation_status="approved",
            ai_risk_score=25,
            user_id=citizen_a2.id,
            tarih=now - timedelta(days=1),
        )
        atik_ank = Atik(
            baslik="Cam Ank",
            aciklama="Test",
            kategori="Cam",
            resim="default.jpg",
            latitude=39.92,
            longitude=32.85,
            ilan_durumu="Aktif",
            moderation_status="approved",
            ai_risk_score=80,
            user_id=citizen_b.id,
            tarih=now - timedelta(days=2),
        )
        db.session.add_all([kaynak, atik, atik_elektronik, atik_ank])
        db.session.flush()

        db.session.add(
            CevreselEtki(
                user_id=citizen_a.id,
                kaynak_id=kaynak.id,
                tur="kaynak",
                kategori="Mobilya",
                atik_kg=0,
                co2e_kg=12.0,
                su_litre=10,
                dongusel_skor=8,
                timestamp=now - timedelta(days=2),
            )
        )
        db.session.add(
            CevreselEtki(
                user_id=citizen_a.id,
                atik_id=atik.id,
                tur="atik",
                kategori="Plastik",
                atik_kg=5.0,
                co2e_kg=8.0,
                su_litre=5,
                dongusel_skor=0,
                timestamp=now - timedelta(days=1),
            )
        )
        db.session.commit()

        return {
            "muni_a_id": muni_a.id,
            "muni_b_id": muni_b.id,
            "citizen_a_id": citizen_a.id,
            "ministry_id": ministry.id,
            "normal_id": normal.id,
            "admin_id": admin.id,
        }


def test_grade_for_score_bands():
    assert grade_for_score(95) == "A+"
    assert grade_for_score(90) == "A"
    assert grade_for_score(85) == "B+"
    assert grade_for_score(70) == "B"
    assert grade_for_score(55) == "C"
    assert grade_for_score(35) == "D"
    assert grade_for_score(11) == "F"
    assert grade_for_score(31) == "D"
    # 11 ve 31 aynı harf bandında olmamalı
    assert grade_for_score(11) != grade_for_score(31)


def test_weights_sum_100():
    assert sum(SUSTAINABILITY_WEIGHTS.values()) == 100


def test_score_region_bounds_and_criteria(app, sustainability_data):
    with app.app_context():
        scored = score_region(il="Sakarya", ilce="Serdivan")
        assert 0 <= scored["puan"] <= 100
        assert scored["grade"] in ("A+", "A", "B+", "B", "C+", "C", "D+", "D", "E", "F")
        keys = {c["key"] for c in scored["criteria"]}
        assert keys == set(SUSTAINABILITY_WEIGHTS)
        # Ağırlıklı katkı toplamı ≈ puan
        weighted = sum(c["weighted"] for c in scored["criteria"])
        assert abs(weighted - scored["puan"]) < 0.6
        assert scored["metrics"]["teslim"] >= 2
        assert scored["metrics"]["co2e_kg"] >= 20


def test_score_municipality_leaderboard(app, sustainability_data):
    with app.app_context():
        muni = db.session.get(User, sustainability_data["muni_a_id"])
        scored = score_municipality(muni)
        assert scored["belediye_id"] == muni.id
        assert scored["il"] == "Sakarya"

        board = turkey_ranking()
        assert len(board) >= 2
        assert board[0]["sira"] == 1
        assert board[0]["puan"] >= board[-1]["puan"]

        provinces = province_ranking()
        assert any(p["il"] == "Sakarya" for p in provinces)
        assert any(p["il"] == "Ankara" for p in provinces)


def test_dashboard_bundle(app, sustainability_data):
    with app.app_context():
        muni = db.session.get(User, sustainability_data["muni_a_id"])
        dash = sustainability_dashboard(belediye_user=muni)
        assert "leaderboard" in dash
        assert "turkey_ranking" in dash
        assert "province_ranking" in dash
        assert "il_ranking" in dash
        assert "comparison" in dash
        assert dash["comparison"].get("message")
        assert dash["current"]["belediye_id"] == muni.id
        assert dash["my_rank"] is not None
        assert "radar" in dash
        assert len(dash["radar"]["labels"]) == len(SUSTAINABILITY_WEIGHTS)
        assert "category_scores" in dash
        assert "history" in dash
        assert len(dash["history"]["series"]) >= 3
        assert "similar_municipalities" in dash
        assert "rankings" in dash
        assert dash["rankings"]["turkey"]["sira"] is not None


def test_ai_suggestions_rule_based(app, sustainability_data):
    with app.app_context():
        with patch("services.sustainability_ai.get_client", return_value=None):
            result = generate_sustainability_suggestions(il="Sakarya", ilce="Serdivan")
        assert result["source"] == "rules"
        assert result["suggestions"]
        first = result["suggestions"][0]
        assert isinstance(first, dict)
        assert first.get("title")
        assert first.get("description")
        assert first.get("priority") in ("Kritik", "Yüksek", "Orta", "Düşük")
        assert first.get("duration") in ("Kısa", "Orta", "Uzun")
        assert first.get("reason")
        report = result["report"]
        assert len(report["strengths"]) == 3
        assert len(report["improvements"]) == 3
        assert len(report["recommendations"]) == 3
        assert report["expected_gains"]
        text = " ".join(
            f"{s.get('title','')} {s.get('description','')} {s.get('reason','')}"
            for s in result["suggestions"]
        ).lower()
        assert "elektronik" in text or "bitkisel" in text or "puan" in text or "teslim" in text


def test_pdf_export(app, sustainability_data):
    with app.app_context():
        muni = db.session.get(User, sustainability_data["muni_a_id"])
        dash = sustainability_dashboard(belediye_user=muni)
        with patch("services.sustainability_ai.get_client", return_value=None):
            ai = generate_sustainability_suggestions(scored=dash["current"])
        data, filename = export_sustainability_pdf(
            dash,
            ai.get("suggestions") or [],
            report=ai.get("report") or {},
        )
        assert filename.endswith(".pdf") or filename.endswith(".txt")
        assert len(data) > 50
        if filename.endswith(".pdf"):
            assert data[:4] == b"%PDF"


def test_belediye_page_rbac(client, sustainability_data):
    _login(client, "normal_sus@test.com")
    assert client.get("/belediye/surdurulebilirlik").status_code == 403

    _login(client, "belediye_sus_a@test.com")
    with patch("services.sustainability_ai.get_client", return_value=None):
        resp = client.get("/belediye/surdurulebilirlik")
    assert resp.status_code == 200
    assert b"Sustainability Scoring" in resp.data
    assert b"Radar" in resp.data or b"radar" in resp.data
    assert b"AI De" in resp.data or b"G" in resp.data  # AI Değerlendirmesi / Güçlü
    assert b"S" in resp.data  # Sıralaması


def test_belediye_api_and_pdf(client, sustainability_data):
    _login(client, "belediye_sus_a@test.com")
    with patch("services.sustainability_ai.get_client", return_value=None):
        api = client.get("/belediye/api/sustainability")
    assert api.status_code == 200
    body = api.get_json()
    assert "current" in body
    assert "turkey_ranking" in body
    assert "suggestions" in body
    assert "radar" in body
    assert "history" in body
    assert "similar_municipalities" in body
    assert "report" in body["suggestions"] or "suggestions" in body["suggestions"]
    # suggestions key still wraps AI payload
    ai = body["suggestions"]
    assert "suggestions" in ai
    assert "report" in ai

    pdf = client.get("/belediye/surdurulebilirlik/pdf")
    assert pdf.status_code == 200
    assert pdf.headers["Content-Disposition"].startswith("attachment")


def test_ministry_sustainability_page(client, sustainability_data):
    _login(client, "bakan_sus@test.com")
    with patch("services.sustainability_ai.get_client", return_value=None):
        resp = client.get("/minister/surdurulebilirlik")
    assert resp.status_code == 200
    assert b"Sustainability Scoring" in resp.data

    pdf = client.get("/minister/surdurulebilirlik/pdf")
    assert pdf.status_code == 200
