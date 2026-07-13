"""MASTER_DATASET — sabit şehir senaryoları (rastgele değil)."""

from services.demo_provider import (
    MASTER_DATASET,
    dashboard_kpis,
    heat_map_points,
    marketplace_orgs,
    national_leaderboard,
    prediction_report,
    sustainability_score,
)


REQUIRED_CITIES = {
    "İstanbul",
    "Ankara",
    "İzmir",
    "Bursa",
    "Kocaeli",
    "Sakarya",
    "Eskişehir",
    "Konya",
    "Antalya",
    "Gaziantep",
    "Kayseri",
    "Trabzon",
    "Samsun",
    "Adana",
    "Mersin",
}


def test_master_dataset_covers_required_cities():
    assert REQUIRED_CITIES.issubset(set(MASTER_DATASET.keys()))
    assert len(MASTER_DATASET) >= 15


def test_sakarya_scenario_numbers():
    sak = MASTER_DATASET["Sakarya"]
    assert sak["dashboard"]["toplam_aktif_ilan"] == 3200
    assert sak["dashboard"]["vatandas_katilim_orani"] == 71.0
    assert sak["dashboard"]["teslim_orani"] == 82.0
    assert sak["co2_ton"] == 25.0
    assert sak["energy_kwh"] == 41000
    assert sak["water_ton"] == 650.0
    cats = sak["waste_categories"]
    assert cats["Plastik"] == 29
    assert cats["Elektronik"] == 18
    assert cats["Cam"] == 16
    assert sak["sustainability"]["puan"] == 74
    assert sak["sustainability"]["grade"] == "B"
    assert "Adapazarı" in sak["districts"]
    assert "Serdivan" in sak["districts"]
    assert "Kemalpaşa" in sak["districts"]["Serdivan"]


def test_same_source_across_panels():
    dash = dashboard_kpis(il="Sakarya")
    sus = sustainability_score(il="Sakarya")
    pred = prediction_report(il="Sakarya")
    assert dash["toplam_aktif_ilan"] == MASTER_DATASET["Sakarya"]["dashboard"]["toplam_aktif_ilan"]
    assert sus["puan"] == MASTER_DATASET["Sakarya"]["sustainability"]["puan"]
    assert pred["primary"]["history"] == MASTER_DATASET["Sakarya"]["monthly_history"][-12:]
    assert pred["narrative_source"] == "demo"
    heat = heat_map_points(il="Sakarya")
    assert 20 <= len(heat) <= 50
    assert all(len(p) == 3 for p in heat)


def test_prediction_follows_history_not_random():
    a = prediction_report(il="İzmir", include_all_lookbacks=False, lookback_months=12)
    b = prediction_report(il="İzmir", include_all_lookbacks=False, lookback_months=12)
    assert a["primary"]["forecasts"]["30"]["atik_miktari"]["predicted"] == (
        b["primary"]["forecasts"]["30"]["atik_miktari"]["predicted"]
    )
    hist = a["primary"]["history"]
    assert len(hist) == 12
    assert hist[-1]["atik_kg"] > 0


def test_leaderboard_and_marketplace_filled():
    board = national_leaderboard()
    assert len(board) >= 15
    assert board[0]["il"] == "İzmir"
    assert board[0]["puan"] == 90
    assert any(r["il"] == "Trabzon" and r["puan"] == 67 for r in board)
    orgs = marketplace_orgs(limit=40)
    assert len(orgs) >= 40


def test_activities_at_least_100():
    acts = MASTER_DATASET["Sakarya"]["activities"]
    assert len(acts) >= 100


def test_istanbul_districts_real_names():
    dists = MASTER_DATASET["İstanbul"]["districts"]
    for name in ("Kadıköy", "Beşiktaş", "Üsküdar", "Pendik", "Şişli"):
        assert name in dists


def test_dashboard_kpis_city_specific(app):
    with app.app_context():
        sak = dashboard_kpis(il="Sakarya")
        ist = dashboard_kpis(il="İstanbul")
        assert sak["toplam_aktif_ilan"] == 3200
        assert ist["toplam_aktif_ilan"] == 18400
        assert sak["co2e_kg"] != ist["co2e_kg"]


def test_heatmap_and_geography_from_master(app):
    from services.demo_manager import DEMO_MODE_KEY, save_demo_settings
    from services.municipality_analytics import geography_options, heat_map_points, kategori_analizi
    from auth_utils import hash_password
    from extensions import db
    from models import User

    with app.app_context():
        admin = User(
            username="geo_admin",
            email="geo_admin@test.com",
            password=hash_password("TestPass1"),
            is_completed=True,
            email_verified=True,
            role="admin",
            is_admin=True,
        )
        db.session.add(admin)
        db.session.commit()
        save_demo_settings({DEMO_MODE_KEY: True}, admin_id=admin.id, log_changes=False)

        geo = geography_options(il="Sakarya")
        assert "Adapazarı" in geo["ilceler"]
        assert "Serdivan" in geo["ilceler"]
        geo2 = geography_options(il="Sakarya", ilce="Serdivan")
        assert "Kemalpaşa" in geo2["mahalleler"]

        pts = heat_map_points(il="Sakarya")
        assert 20 <= len(pts) <= 50
        assert all(len(p) == 3 for p in pts)

        kat = kategori_analizi(il="Sakarya")
        assert kat["toplam"] > 0
        assert "Plastik" in kat["labels"]
