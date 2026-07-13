"""ROLE_MINISTRY — bakanlık paneli RBAC, KPI, map, statistics."""

from datetime import timedelta

import pytest
from flask_login import login_user

from auth_utils import hash_password
from constants import ROLE_MINISTRY, ROLE_MUNICIPALITY
from extensions import db
from models import Atik, CevreselEtki, Kaynak, User
from services.ministry_analytics import (
    co2e_to_energy_kwh,
    ministry_drilldown_options,
    ministry_kpi,
    ministry_map_data,
    ministry_statistics,
    province_statistics,
    top_bottom_provinces,
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
def ministry_data(app):
    with app.app_context():
        ministry = _user(
            username="bakan",
            email="bakan@test.com",
            role=ROLE_MINISTRY,
        )
        muni_a = _user(
            username="belediye_a",
            email="belediye_a@test.com",
            role=ROLE_MUNICIPALITY,
            il="Sakarya",
            ilce="Serdivan",
            latitude=40.77,
            longitude=30.39,
        )
        muni_b = _user(
            username="belediye_b",
            email="belediye_b@test.com",
            role=ROLE_MUNICIPALITY,
            il="Ankara",
            ilce="Çankaya",
            latitude=39.92,
            longitude=32.85,
        )
        kurum = _user(
            username="kurum_min",
            email="kurum_min@test.com",
            is_kurum=True,
            il="Sakarya",
            ilce="Serdivan",
        )
        citizen_sk = _user(
            username="vat_sk",
            email="vat_sk@test.com",
            il="Sakarya",
            ilce="Serdivan",
            latitude=40.76,
            longitude=30.38,
        )
        citizen_ank = _user(
            username="vat_ank",
            email="vat_ank@test.com",
            il="Ankara",
            ilce="Çankaya",
            latitude=39.91,
            longitude=32.86,
        )
        normal = _user(username="normal_min", email="normal_min@test.com")
        admin = _user(
            username="admin_min",
            email="admin_min@test.com",
            role="admin",
            is_admin=True,
        )

        kaynak = Kaynak(
            baslik="Koltuk",
            aciklama="Test",
            durum="Temiz",
            kategori="Mobilya",
            resim="default.jpg",
            latitude=40.77,
            longitude=30.39,
            ilan_durumu="Teslim Edildi",
            moderation_status="approved",
            user_id=citizen_sk.id,
            tarih=utc_now() - timedelta(days=3),
        )
        atik = Atik(
            baslik="Plastik",
            aciklama="Test",
            kategori="Plastik",
            latitude=39.92,
            longitude=32.85,
            ilan_durumu="Aktif",
            moderation_status="approved",
            user_id=citizen_ank.id,
            tarih=utc_now(),
        )
        db.session.add_all([kaynak, atik])
        db.session.flush()
        etki = CevreselEtki(
            user_id=citizen_sk.id,
            kaynak_id=kaynak.id,
            tur="kaynak",
            kategori="Mobilya",
            co2e_kg=45,
            su_litre=800,
            atik_kg=0,
            dongusel_skor=500,
            timestamp=utc_now(),
        )
        db.session.add(etki)
        db.session.commit()
        return {
            "ministry_id": ministry.id,
            "muni_a_id": muni_a.id,
            "muni_b_id": muni_b.id,
            "kurum_id": kurum.id,
            "normal_id": normal.id,
            "admin_id": admin.id,
        }


# --- RBAC ---


def test_ministry_dashboard_forbidden_for_normal(client, ministry_data):
    _login(client, "normal_min@test.com")
    assert client.get("/minister/dashboard").status_code == 403


def test_ministry_dashboard_forbidden_for_municipality(client, ministry_data):
    _login(client, "belediye_a@test.com")
    assert client.get("/minister/dashboard").status_code == 403


def test_ministry_dashboard_allowed(client, ministry_data):
    _login(client, "bakan@test.com")
    resp = client.get("/minister/dashboard")
    assert resp.status_code == 200
    text = resp.data.decode("utf-8", errors="ignore")
    assert "Bakanlık Yönetim Paneli" in text
    assert "Toplam İlan" in text
    assert "CO₂" in text or "CO2" in text


def test_ministry_dashboard_allowed_for_admin(client, ministry_data):
    _login(client, "admin_min@test.com")
    assert client.get("/minister/dashboard").status_code == 200


def test_ministry_apis_forbidden_for_normal(client, ministry_data):
    _login(client, "normal_min@test.com")
    for path in ("/minister/kpi", "/minister/map", "/minister/statistics"):
        assert client.get(path).status_code == 403, path


# --- API ---


def test_api_kpi(client, ministry_data):
    _login(client, "bakan@test.com")
    resp = client.get("/minister/kpi")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["toplam_ilan"] >= 2
    assert data["co2_tasarrufu_kg"] >= 45
    assert data["enerji_tasarrufu_kwh"] == co2e_to_energy_kwh(data["co2_tasarrufu_kg"])
    assert data["su_tasarrufu_litre"] >= 800
    assert data["aktif_belediye"] >= 2
    assert data["aktif_kurum"] >= 1
    assert "vatandas_katilim_orani" in data


def test_api_map(client, ministry_data):
    _login(client, "bakan@test.com")
    resp = client.get("/minister/map")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "heat" in data
    assert "il_yogunluk" in data
    assert isinstance(data["heat"], list)
    assert len(data["heat"]) >= 1


def test_api_statistics(client, ministry_data):
    _login(client, "bakan@test.com")
    resp = client.get("/minister/statistics")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "kpi" in data
    assert "rankings" in data
    assert "en_basarili" in data["rankings"]
    assert "en_dusuk" in data["rankings"]
    assert "drilldown" in data


def test_dashboard_json_format(client, ministry_data):
    _login(client, "bakan@test.com")
    resp = client.get("/minister/dashboard?format=json")
    assert resp.status_code == 200
    assert resp.is_json
    assert "kpi" in resp.get_json()


# --- Analytics ---


def test_drilldown_cascade(app, ministry_data):
    with app.app_context():
        opts = ministry_drilldown_options()
        assert "Sakarya" in opts["iller"]
        assert "Ankara" in opts["iller"]

        sk = ministry_drilldown_options(il="Sakarya")
        assert "Serdivan" in sk["ilceler"]
        assert any(b["id"] == ministry_data["muni_a_id"] for b in sk["belediyeler"])
        assert any(k["id"] == ministry_data["kurum_id"] for k in sk["kurumlar"])


def test_province_rankings(app, ministry_data):
    with app.app_context():
        rows = province_statistics()
        assert len(rows) >= 2
        for r in rows:
            assert 0 <= r["puan"] <= 100
        rankings = top_bottom_provinces(10)
        assert rankings["en_basarili"]
        assert rankings["en_dusuk"]


def test_map_data_structure(app, ministry_data):
    with app.app_context():
        data = ministry_map_data()
        assert all(len(p) == 3 for p in data["heat"])
        assert any(r["il"] == "Sakarya" for r in data["il_yogunluk"])


def test_kpi_filter_by_il(app, ministry_data):
    with app.app_context():
        all_kpi = ministry_kpi()
        sk = ministry_kpi(il="Sakarya")
        assert sk["toplam_ilan"] <= all_kpi["toplam_ilan"]
        assert sk["aktif_belediye"] >= 1


def test_is_ministry_user(app, ministry_data):
    from decorators import is_ministry_user, is_municipality_user

    with app.app_context():
        ministry = db.session.get(User, ministry_data["ministry_id"])
        muni = db.session.get(User, ministry_data["muni_a_id"])
        normal = db.session.get(User, ministry_data["normal_id"])
        with app.test_request_context():
            login_user(ministry)
            assert is_ministry_user(ministry) is True
            assert is_municipality_user(ministry) is False
            login_user(muni)
            assert is_ministry_user(muni) is False
            login_user(normal)
            assert is_ministry_user(normal) is False


def test_navbar_shows_ministry(client, ministry_data):
    _login(client, "bakan@test.com")
    resp = client.get("/")
    assert b"Bakanl" in resp.data


def test_ministry_sees_all_municipalities(app, ministry_data):
    with app.app_context():
        stats = ministry_statistics()
        belediyeler = stats["drilldown"]["belediyeler"]
        ids = {b["id"] for b in belediyeler}
        assert ministry_data["muni_a_id"] in ids
        assert ministry_data["muni_b_id"] in ids
