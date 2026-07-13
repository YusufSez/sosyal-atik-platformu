"""TEKNOFEST Final QA — demo panellerinin dolu olması."""

from auth_utils import hash_password
from constants import ROLE_COMPANY, ROLE_MINISTRY, ROLE_MUNICIPALITY
from extensions import db
from models import User
from services.demo_manager import DEMO_MODE_KEY, save_demo_settings
from services.demo_provider import (
    MASTER_DATASET,
    dashboard_kpis,
    heat_map_points,
    ministry_national_center,
    ops_center,
    prediction_report,
    sustainability_dashboard_overlay,
)
from services.decision_support import build_decision_support_center
from services.kurum_analytics import (
    isi_haritasi_noktalari,
    kurum_ozet,
    mevcut_iller,
)
from services.ministry_analytics import ministry_drilldown_options


def _enable_demo(app, *, email_prefix="qa"):
    with app.app_context():
        admin = User(
            username=f"{email_prefix}_admin",
            email=f"{email_prefix}_admin@test.com",
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


def test_ops_center_charts_and_heat_filled():
    ops = ops_center(il="Sakarya")
    assert ops["source"] == "demo"
    assert len(ops["heatmap"]) >= 8
    assert len(ops["heat_points"]) >= 8
    assert ops["charts"]["category"]["labels"]
    assert ops["charts"]["waste_categories"]["labels"]
    assert sum(ops["charts"]["category"]["values"]) > 0
    assert len(ops["charts"]["trend"]["labels"]) >= 6
    assert ops["charts"]["monthly_trend"]["values"]
    assert sum(ops["charts"]["trend"]["values"]) > 0
    assert ops["charts"]["teslim_history"]["values"]
    assert ops["charts"]["delivery_history"]["values"]
    assert ops["prediction"]["primary"]["forecasts"]
    assert ops["prediction"]["primary"]["prediction_history"]
    assert ops["prediction"]["primary"]["prediction_forecast"]
    heat = heat_map_points(il="Sakarya", ilce="Serdivan")
    assert len(heat) >= 5
    city = dashboard_kpis(il="Sakarya")
    dist = dashboard_kpis(il="Sakarya", ilce="Serdivan")
    assert dist["toplam_aktif_ilan"] < city["toplam_aktif_ilan"]


def test_prediction_and_sustainability_radar_filled():
    pred = prediction_report(12, il="Sakarya", ilce="Serdivan")
    assert pred["primary"]["forecasts"]
    assert pred["primary"]["history"]
    sus = sustainability_dashboard_overlay(il="Sakarya")
    assert sus["radar"]["labels"]
    assert sus["radar"]["values"]
    assert sus["sustainability_categories"]["values"]
    assert sus["history"]["puanlar"]


def test_ministry_15_cities_and_distinct_rankings(app):
    _enable_demo(app)
    with app.app_context():
        drill = ministry_drilldown_options()
        assert len(drill["iller"]) == 15
        assert set(drill["iller"]) == set(MASTER_DATASET.keys())
        drill_sak = ministry_drilldown_options(il="Sakarya")
        assert "Serdivan" in drill_sak["ilceler"] or len(drill_sak["ilceler"]) >= 3

        center = ministry_national_center()
        top_ils = [r["il"] for r in center["en_basarili_belediyeler"][:5]]
        risk_ils = [r["il"] for r in center["riskli_belediyeler"][:5]]
        grow_ils = [r["il"] for r in center["gelisim_gosteren"][:5]]
        assert top_ils != risk_ils
        assert grow_ils != risk_ils or grow_ils != top_ils
        assert center["ai_ozeti"]
        assert center["charts"]["trend"]["values"]
        assert center["charts"]["radar"]["values"]


def test_decision_support_charts_filled(app):
    _enable_demo(app)
    with app.app_context():
        center = build_decision_support_center()
        assert center["participation_trends"]["labels"]
        assert any(v > 0 for v in center["participation_trends"]["aktif"])
        assert center["category_shifts"]["chart"]["labels"]
        assert center["municipality_comparisons"]["top"]
        assert center["kpi"]["co2_tasarrufu_kg"] > 0


def test_kurum_panel_demo_filled(app):
    _enable_demo(app, email_prefix="qa_kurum")
    with app.app_context():
        iller = mevcut_iller()
        assert len(iller) == 15
        ozet = kurum_ozet("Sakarya")
        assert ozet["source"] == "demo"
        assert ozet["aktif_kaynak"] > 0
        assert ozet["ai_ozeti"]
        assert ozet["charts"]["category"]["labels"]
        heat = isi_haritasi_noktalari("Sakarya")
        assert len(heat) >= 8


def test_ops_and_ministry_http_demo(client, app):
    _enable_demo(app, email_prefix="qa_http")
    with app.app_context():
        muni = User(
            username="qa_muni",
            email="qa_muni@test.com",
            password=hash_password("TestPass1"),
            is_completed=True,
            email_verified=True,
            role=ROLE_MUNICIPALITY,
            il="Sakarya",
            ilce="Serdivan",
            latitude=40.77,
            longitude=30.39,
        )
        ministry = User(
            username="qa_min",
            email="qa_min@test.com",
            password=hash_password("TestPass1"),
            is_completed=True,
            email_verified=True,
            role=ROLE_MINISTRY,
        )
        company = User(
            username="qa_co",
            email="qa_co@test.com",
            password=hash_password("TestPass1"),
            is_completed=True,
            email_verified=True,
            role=ROLE_COMPANY,
            is_kurum=True,
            il="Sakarya",
            latitude=40.77,
            longitude=30.39,
        )
        db.session.add_all([muni, ministry, company])
        db.session.commit()

    client.post(
        "/giris",
        data={"email": "qa_muni@test.com", "password": "TestPass1"},
        follow_redirects=True,
    )
    dash = client.get("/belediye/dashboard?ilce=Serdivan")
    assert dash.status_code == 200
    assert b"ops-center-config" in dash.data
    assert b"heatmap" in dash.data
    assert b'"demoSource": true' in dash.data or b'"demoSource":true' in dash.data
    assert b"waste_categories" in dash.data or b"monthly_trend" in dash.data
    assert b"prediction-panel-config" in dash.data
    assert b"bootstrap" in dash.data
    assert b"vendor/chart.js" in dash.data
    # MASTER serileri HTML bootstrap'ta dolu olmalı
    import json
    import re

    html = dash.data.decode("utf-8")
    cfg = json.loads(re.search(r'id="ops-center-config">(.*?)</script>', html, re.S).group(1))
    assert cfg["demoSource"] is True
    assert len(cfg.get("heatmap") or cfg.get("heat_points") or []) >= 5
    charts = cfg.get("charts") or {}
    assert (charts.get("category") or charts.get("waste_categories") or {}).get("labels")
    assert (charts.get("monthly_trend") or charts.get("trend") or {}).get("values")
    assert (charts.get("delivery_history") or charts.get("teslim_history") or {}).get("values")
    assert (charts.get("radar") or {}).get("labels")
    assert b"opsRadarChart" in dash.data
    pcfg = json.loads(
        re.search(r'id="prediction-panel-config">(.*?)</script>', html, re.S).group(1)
    )
    assert (pcfg.get("bootstrap") or {}).get("primary", {}).get("forecasts")
    heat = client.get("/belediye/api/heatmap?il=Sakarya&ilce=Serdivan")
    assert heat.status_code == 200
    assert len(heat.get_json()) >= 5
    pred = client.get("/belediye/api/predictions?il=Sakarya&ilce=Serdivan")
    assert pred.status_code == 200
    body = pred.get_json()
    assert body.get("primary", {}).get("forecasts")
    assert body.get("primary", {}).get("prediction_history")
    assert body.get("primary", {}).get("prediction_forecast")

    client.get("/cikis", follow_redirects=True)
    client.post(
        "/giris",
        data={"email": "qa_min@test.com", "password": "TestPass1"},
        follow_redirects=True,
    )
    nat = client.get("/minister/")
    assert nat.status_code == 200
    drill = client.get("/minister/api/drilldown")
    assert drill.status_code == 200
    assert len(drill.get_json().get("iller") or []) == 15
    kd = client.get("/minister/karar-destek")
    assert kd.status_code == 200
    assert b"ds-center-config" in kd.data

    client.get("/cikis", follow_redirects=True)
    client.post(
        "/giris",
        data={"email": "qa_co@test.com", "password": "TestPass1"},
        follow_redirects=True,
    )
    kurum = client.get("/kurum/analiz?il=Sakarya")
    assert kurum.status_code == 200
    assert b"kurum-analiz-config" in kurum.data
    assert b"kurumCategoryChart" in kurum.data
