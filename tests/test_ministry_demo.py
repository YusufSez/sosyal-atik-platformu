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


def test_decision_support_center_master_schema():
    from services.demo_provider import decision_support_center

    center = decision_support_center()
    kpi = center["kpi"]
    assert kpi["co2_tasarrufu_kg"] > 0
    assert kpi["vatandas_katilim_orani"] > 0
    assert kpi["aktif_belediye"] == 15
    assert center["weekly_report"]["metrics"]["ilan"] > 0
    assert center["monthly_report"]["metrics"]["co2e_kg"] > 0
    risk = center["risk_analysis"]
    assert risk["level"] in ("dusuk", "orta", "yuksek")
    assert risk["riskli_belediye_sayisi"] >= 1
    assert risk["findings"]
    assert risk["riskli_belediyeler"][0]["belediye_adi"]
    assert center["campaigns"][0]["description"]
    assert center["municipality_comparisons"]["chart"]["labels"]
    assert center["category_shifts"]["chart"]["labels"]
    assert len(center["participation_trends"]["labels"]) == 8
    assert center["participation_trends"]["trend"]
    assert center["ai"]["overview"]
    assert center["ai_source"] == "demo"


def test_karar_destek_demo_mode_http_200(client, app):
    from constants import ROLE_MINISTRY
    from services.decision_support_ai import enrich_decision_support
    from services.decision_support_pdf import export_decision_support_pdf

    _admin(app)
    with app.app_context():
        ministry = User(
            username="ds_demo_min",
            email="ds_demo_min@test.com",
            password=hash_password("TestPass1"),
            is_completed=True,
            email_verified=True,
            role=ROLE_MINISTRY,
            is_admin=False,
            il=None,
            ilce=None,
        )
        db.session.add(ministry)
        db.session.commit()

        center = enrich_decision_support()
        assert center["source"] == "demo"
        assert center["kpi"]["co2_tasarrufu_kg"] > 0
        assert center["ai_source"] == "demo"
        for rtype in ("weekly", "monthly", "full"):
            data, filename = export_decision_support_pdf(center, report_type=rtype)
            assert len(data) > 40
            if filename.endswith(".pdf"):
                assert data[:4] == b"%PDF"

    client.post(
        "/giris",
        data={"email": "ds_demo_min@test.com", "password": "TestPass1"},
        follow_redirects=True,
    )
    resp = client.get("/minister/karar-destek")
    assert resp.status_code == 200
    body = resp.data
    assert b"Ulusal Karar Destek" in body
    assert b"Haftal" in body
    assert b"Risk" in body
    assert b"Kategori" in body
    assert b"Kampanya" in body
    assert b"Kat" in body  # Katılım
    assert b"ds-center-config" in body

    pdf = client.get("/minister/karar-destek/pdf?type=full")
    assert pdf.status_code == 200
    assert pdf.headers["Content-Disposition"].startswith("attachment")
    assert pdf.data[:4] == b"%PDF" or len(pdf.data) > 40
