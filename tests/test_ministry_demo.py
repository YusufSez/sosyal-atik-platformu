"""Ulusal Yönetim Merkezi — MASTER_DATASET agregasyon testleri."""

from auth_utils import hash_password
from extensions import db
from models import User
from services.demo_manager import DEMO_MODE_KEY, save_demo_settings
from services.demo_provider import MASTER_DATASET, ministry_kpi, ministry_national_center
from services.ministry_analytics import (
    ministry_kpi as analytics_kpi,
    ministry_map_data,
    ministry_national_center as analytics_center,
)


def _admin(app):
    with app.app_context():
        admin = User(
            username="min_demo_admin",
            email="min_demo_admin@test.com",
            password=hash_password("TestPass1"),
            is_completed=True,
            email_verified=True,
            role="admin",
            is_admin=True,
        )
        db.session.add(admin)
        db.session.commit()
        save_demo_settings({DEMO_MODE_KEY: True}, admin_id=admin.id, log_changes=False)
        return admin.id


def test_ministry_kpi_national_aggregation():
    kpi = ministry_kpi()
    assert kpi["toplam_ilan"] == sum(
        MASTER_DATASET[c]["dashboard"]["toplam_aktif_ilan"] for c in MASTER_DATASET
    )
    assert kpi["co2_tasarrufu_kg"] == sum(
        MASTER_DATASET[c]["co2_ton"] * 1000.0 for c in MASTER_DATASET
    )
    assert kpi["enerji_tasarrufu_kwh"] == sum(
        MASTER_DATASET[c]["energy_kwh"] for c in MASTER_DATASET
    )
    assert kpi["aktif_belediye"] == 15
    assert kpi["vatandas_katilim_orani"] > 0


def test_ministry_national_center_lists_filled():
    center = ministry_national_center()
    assert center["kpi"]["toplam_ilan"] > 0
    assert len(center["map_data"]["heat"]) >= 20
    assert len(center["map_data"]["il_merkezleri"]) == 15
    assert all(c.get("renk") for c in center["map_data"]["il_merkezleri"])
    assert center["en_basarili_belediyeler"][0]["il"] == "İzmir"
    assert center["riskli_belediyeler"][0]["puan"] <= center["en_basarili_belediyeler"][0]["puan"]
    assert len(center["gelisim_gosteren"]) >= 1
    assert len(center["ai_ozeti"]) >= 3
    assert center["province_rankings"]["en_basarili"][0]["il"] == "İzmir"


def test_analytics_uses_master_when_demo_mode(app):
    _admin(app)
    with app.app_context():
        kpi = analytics_kpi()
        assert kpi["aktif_belediye"] == 15
        assert kpi["toplam_ilan"] > 1000
        mmap = ministry_map_data()
        assert len(mmap["il_merkezleri"]) == 15
        center = analytics_center()
        assert len(center["en_basarili_belediyeler"]) == 10
        assert len(center["riskli_belediyeler"]) >= 1
        assert len(center["ai_ozeti"]) >= 3
        assert any("ilan" in t.lower() or "ulusal" in t.lower() for t in center["ai_ozeti"])
