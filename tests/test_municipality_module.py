"""Belediye Yönetim Modülü — RBAC, analytics, AI, endpoints."""

from datetime import timedelta
from unittest.mock import patch

import pytest
from flask_login import login_user

from auth_utils import hash_password
from constants import ROLE_MUNICIPALITY
from extensions import db
from models import Atik, CevreselEtki, Kaynak, User
from services.municipality_ai import generate_municipality_insights
from services.municipality_analytics import (
    geography_options,
    heat_map_points,
    ilce_performans,
    kategori_analizi,
    mahalle_analizi,
    municipality_dashboard,
    municipality_ops_center,
    normalize_municipality_category,
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
    client.post(
        "/giris",
        data={"email": email, "password": "TestPass1"},
        follow_redirects=True,
    )


@pytest.fixture
def municipality_data(app):
    with app.app_context():
        muni = _user(
            username="belediye",
            email="belediye@test.com",
            role=ROLE_MUNICIPALITY,
            il="Sakarya",
            ilce="Serdivan",
            mahalle="Kemalpaşa",
        )
        citizen = _user(
            username="vatandas",
            email="vatandas@test.com",
            il="Sakarya",
            ilce="Serdivan",
            mahalle="Kemalpaşa",
            last_seen=utc_now(),
        )
        other = _user(
            username="diger",
            email="diger@test.com",
            il="Sakarya",
            ilce="Adapazarı",
            mahalle="Merkez",
        )
        kurum = _user(
            username="kurumcu",
            email="kurumcu@test.com",
            is_kurum=True,
            il="Sakarya",
            ilce="Serdivan",
            mahalle="Kemalpaşa",
        )
        admin = _user(
            username="adminmuni",
            email="adminmuni@test.com",
            role="admin",
            is_admin=True,
        )
        normal = _user(username="normal", email="normal@test.com")

        kaynak = Kaynak(
            baslik="Masa",
            aciklama="Ahşap masa",
            durum="Temiz",
            kategori="Mobilya",
            resim="default.jpg",
            latitude=40.77,
            longitude=30.39,
            ilan_durumu="Aktif",
            moderation_status="approved",
            user_id=citizen.id,
            tarih=utc_now(),
        )
        atik = Atik(
            baslik="Plastik şişe",
            aciklama="PET",
            kategori="Plastik",
            latitude=40.78,
            longitude=30.40,
            ilan_durumu="Aktif",
            moderation_status="approved",
            user_id=citizen.id,
            tarih=utc_now(),
        )
        atik2 = Atik(
            baslik="Eski telefon",
            aciklama="Elektronik",
            kategori="Elektronik Atık",
            latitude=40.75,
            longitude=30.38,
            ilan_durumu="Teslim Edildi",
            moderation_status="approved",
            user_id=other.id,
            tarih=utc_now() - timedelta(days=5),
        )
        db.session.add_all([kaynak, atik, atik2])
        db.session.flush()
        etki = CevreselEtki(
            user_id=other.id,
            atik_id=atik2.id,
            tur="atik",
            kategori="Elektronik Atık",
            co2e_kg=15,
            su_litre=0,
            atik_kg=4,
            dongusel_skor=10,
            timestamp=utc_now() - timedelta(days=2),
        )
        db.session.add(etki)
        db.session.commit()
        return {
            "muni_id": muni.id,
            "citizen_id": citizen.id,
            "other_id": other.id,
            "admin_id": admin.id,
            "normal_id": normal.id,
            "kurum_id": kurum.id,
            "kaynak_id": kaynak.id,
            "atik_id": atik.id,
            "atik2_id": atik2.id,
        }


# --- RBAC ---


def test_municipality_dashboard_forbidden_for_normal_user(client, municipality_data):
    _login(client, "normal@test.com")
    resp = client.get("/belediye/dashboard")
    assert resp.status_code == 403


def test_municipality_dashboard_allowed_for_municipality_role(client, municipality_data):
    _login(client, "belediye@test.com")
    resp = client.get("/belediye/dashboard")
    assert resp.status_code == 200
    text = resp.data.decode("utf-8", errors="ignore")
    assert "Operasyon Merkezi" in text or "Belediye" in text
    assert "Bugün açılan ilanlar" in text
    assert "AI Belediye Asistanı" in text
    assert "Son aktiviteler" in text


def test_municipality_dashboard_allowed_for_admin(client, municipality_data):
    _login(client, "adminmuni@test.com")
    assert client.get("/belediye/dashboard").status_code == 200


def test_all_municipality_pages_rbac(client, municipality_data):
    _login(client, "belediye@test.com")
    for path in (
        "/belediye/",
        "/belediye/dashboard",
        "/belediye/mahalle",
        "/belediye/heatmap",
        "/belediye/kategori",
        "/belediye/ai-asistan",
        "/belediye/performans",
    ):
        assert client.get(path).status_code == 200, path


def test_municipality_api_forbidden_for_normal(client, municipality_data):
    _login(client, "normal@test.com")
    assert client.get("/belediye/api/heatmap").status_code == 403
    assert client.get("/belediye/api/ai-insights").status_code == 403
    assert client.get("/belediye/api/geography").status_code == 403


# --- Analytics ---


def test_dashboard_metrics(app, municipality_data):
    with app.app_context():
        ozet = municipality_dashboard(il="Sakarya")
        assert ozet["toplam_aktif_ilan"] >= 2
        assert ozet["toplam_teslim"] >= 1
        assert ozet["geri_kazanilan_atik_kg"] >= 4
        assert ozet["aktif_kurum"] >= 1
        assert ozet["gunluk_kullanici"] >= 1
        assert ozet["bugun_ilan"] >= 2


def test_ops_center_cards(app, municipality_data):
    with app.app_context():
        ops = municipality_ops_center(il="Sakarya")
        assert "ozet" in ops
        cards = ops["cards"]
        for key in (
            "bugun_acilan",
            "bekleyen_teslimler",
            "son_24_saat",
            "en_yogun_mahalle",
            "riskli_bolgeler",
            "kritik_kategori",
            "vatandas_katilimi",
            "ai_uyarilari",
        ):
            assert key in cards
        assert isinstance(ops["aktiviteler"], list)
        assert cards["bugun_acilan"] == ops["ozet"]["bugun_ilan"]


def test_mahalle_analizi_cascade(app, municipality_data):
    with app.app_context():
        opts = geography_options(il="Sakarya")
        assert "Serdivan" in opts["ilceler"]
        opts2 = geography_options(il="Sakarya", ilce="Serdivan")
        assert "Kemalpaşa" in opts2["mahalleler"]

        rows = mahalle_analizi(il="Sakarya", ilce="Serdivan")
        assert any(r["bolge"] == "Kemalpaşa" for r in rows)
        kem = next(r for r in rows if r["bolge"] == "Kemalpaşa")
        assert kem["ilan_sayisi"] >= 1
        assert kem["kullanici_yogunlugu"] >= 1


def test_heatmap_modes(app, municipality_data):
    with app.app_context():
        atik_pts = heat_map_points(il="Sakarya", yogunluk="atik")
        kaynak_pts = heat_map_points(il="Sakarya", yogunluk="kaynak")
        teslim_pts = heat_map_points(il="Sakarya", yogunluk="teslim")
        assert isinstance(atik_pts, list)
        assert isinstance(kaynak_pts, list)
        assert len(teslim_pts) >= 1
        assert all(len(p) == 3 for p in teslim_pts)


def test_kategori_analizi_groups(app, municipality_data):
    with app.app_context():
        assert normalize_municipality_category("Elektronik Atık") == "Elektronik"
        assert normalize_municipality_category("Organik Atık") == "Organik"
        data = kategori_analizi(il="Sakarya")
        assert "Plastik" in data["labels"]
        assert "Elektronik" in data["labels"]
        assert data["toplam"] >= 2
        by_kat = {r["kategori"]: r["adet"] for r in data["rows"]}
        assert by_kat["Plastik"] >= 1
        assert by_kat["Elektronik"] >= 1


def test_ilce_performans_score_0_100(app, municipality_data):
    with app.app_context():
        rows = ilce_performans(il="Sakarya")
        assert rows
        for r in rows:
            assert 0 <= r["puan"] <= 100


def test_kurum_panel_still_works(client, municipality_data):
    """Mevcut kurum analizi bozulmamalı."""
    _login(client, "kurumcu@test.com")
    resp = client.get("/kurum/analiz")
    assert resp.status_code == 200
    assert b"Kurum Analiz Paneli" in resp.data


# --- AI ---


def test_ai_insights_rule_based_without_gemini(app, municipality_data, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with app.app_context():
        with patch("services.municipality_ai.get_client", return_value=None):
            result = generate_municipality_insights(il="Sakarya")
        assert result["source"] == "rules"
        assert len(result["insights"]) >= 1
        first = result["insights"][0]
        assert isinstance(first, dict)
        assert first.get("title")
        assert first.get("analysis")
        assert first.get("priority") in ("Kritik", "Yüksek", "Orta", "Düşük")
        assert "expected_impact" in first


def test_ai_insights_endpoint(client, municipality_data):
    _login(client, "belediye@test.com")
    with patch("services.municipality_ai.get_client", return_value=None):
        resp = client.get("/belediye/api/ai-insights?il=Sakarya")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "insights" in data
    assert isinstance(data["insights"], list)
    if data["insights"]:
        assert "title" in data["insights"][0]
        assert "analysis" in data["insights"][0]


def test_geography_api(client, municipality_data):
    _login(client, "belediye@test.com")
    resp = client.get("/belediye/api/geography?il=Sakarya")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "Serdivan" in data["ilceler"]


def test_is_municipality_user_helper(app, municipality_data):
    from decorators import is_municipality_user

    with app.app_context():
        muni = db.session.get(User, municipality_data["muni_id"])
        normal = db.session.get(User, municipality_data["normal_id"])
        admin = db.session.get(User, municipality_data["admin_id"])
        with app.test_request_context():
            login_user(muni)
            assert is_municipality_user(muni) is True
            login_user(normal)
            assert is_municipality_user(normal) is False
            login_user(admin)
            assert is_municipality_user(admin) is True


def test_navbar_shows_belediye_for_municipality(client, municipality_data):
    _login(client, "belediye@test.com")
    resp = client.get("/")
    assert b"Belediye Paneli" in resp.data
