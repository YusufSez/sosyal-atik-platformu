"""Kurumsal Kaynak Pazarı — MASTER_DATASET demo katalog testleri."""

from auth_utils import hash_password
from constants import ROLE_COMPANY
from extensions import db
from models import User
from services.demo_manager import DEMO_MODE_KEY, save_demo_settings
from services.demo_provider import (
    MARKETPLACE_ORGS,
    marketplace_catalog_stats,
    marketplace_matches,
)
from services.marketplace import list_published, resolve_listing, transaction_history
from services.marketplace_ai import generate_match_report
from services.marketplace_b2b import (
    demand_pool,
    list_suppliers,
    nearest_orgs_for_user,
    price_analysis,
)


REQUIRED_NAMES = {
    "ABC Plastik",
    "Yeşil Metal",
    "Anka Plastik",
    "EcoCam",
    "TeknoHurda",
    "Anadolu Geri Dönüşüm",
}


def _enable_demo(app):
    with app.app_context():
        admin = User(
            username="mp_demo_admin",
            email="mp_demo_admin@test.com",
            password=hash_password("TestPass1"),
            is_completed=True,
            email_verified=True,
            role="admin",
            is_admin=True,
        )
        company = User(
            username="mp_demo_co",
            email="mp_demo_co@test.com",
            password=hash_password("TestPass1"),
            is_completed=True,
            email_verified=True,
            role=ROLE_COMPANY,
            is_kurum=True,
            il="Sakarya",
            ilce="Serdivan",
            latitude=40.77,
            longitude=30.39,
        )
        db.session.add_all([admin, company])
        db.session.commit()
        save_demo_settings({DEMO_MODE_KEY: True}, admin_id=admin.id, log_changes=False)
        return company.email


def test_marketplace_catalog_minimum_counts():
    stats = marketplace_catalog_stats()
    assert stats["firma"] >= 40
    assert stats["ilan"] >= 120
    assert stats["teklif"] >= 80
    assert stats["rezervasyon"] >= 30
    assert stats["teslim"] >= 20
    names = {o["ad"] for o in MARKETPLACE_ORGS}
    assert REQUIRED_NAMES.issubset(names)


def test_marketplace_demo_fills_services(app):
    _enable_demo(app)
    with app.app_context():
        published = list_published()
        assert len(published) >= 40
        assert all(getattr(l, "publisher", None) is not None for l in published[:5])

        suppliers = list_suppliers(limit=50)
        assert len(suppliers) >= 40
        assert any(s["ad"] == "ABC Plastik" for s in suppliers)

        pool = demand_pool()
        assert len(pool) >= 20

        prices = price_analysis()
        assert prices["ozet"]["toplam_ilan"] >= 120
        assert prices["ozet"]["toplam_teslim"] >= 20

        history = transaction_history(user_id=999999, limit=50)
        assert len(history) >= 20

        company = User.query.filter_by(email="mp_demo_co@test.com").first()
        near = nearest_orgs_for_user(company, radius_km=500, limit=20)
        assert len(near) >= 5

        listing = published[0]
        report = generate_match_report(listing, limit=8)
        assert report["source"] == "demo"
        assert len(report["matches"]) >= 5
        top = report["matches"][0]
        assert set(top["skor_detay"]) >= {"mesafe", "kategori", "puan", "aktivite"}
        assert top["eslesme_skoru"] > 0

        resolved = resolve_listing(listing.id)
        assert resolved is not None
        assert resolved.baslik == listing.baslik


def test_marketplace_demo_panel_http(client, app):
    email = _enable_demo(app)
    client.post(
        "/giris",
        data={"email": email, "password": "TestPass1"},
        follow_redirects=True,
    )
    resp = client.get("/marketplace/panel")
    assert resp.status_code == 200
    assert b"marketplace-listings-data" in resp.data
    assert b"ABC Plastik" in resp.data or b"Ambalaj" in resp.data

    with app.app_context():
        published = list_published()
        listing_id = published[0].id
    matches = client.get(f"/marketplace/api/matches/{listing_id}")
    assert matches.status_code == 200
    payload = matches.get_json()
    assert payload["source"] == "demo"
    assert len(payload["matches"]) >= 3
    assert "skor_detay" in payload["matches"][0]

    nearby = client.get(f"/marketplace/api/nearby/{listing_id}")
    assert nearby.status_code == 200
    assert nearby.get_json()["nearby_count"] >= 1

    hist = client.get("/marketplace/gecmis")
    assert hist.status_code == 200
    assert b"teklif" in hist.data or b"Teslim" in hist.data or b"teslim" in hist.data

    yakin = client.get("/marketplace/yakin-kurumlar")
    assert yakin.status_code == 200
    assert b"ABC Plastik" in yakin.data or b"km" in yakin.data


def test_real_listings_skip_demo_when_mode_off(app):
    """Demo kapalı + gerçek ilan varsa katalog kullanılmaz."""
    from services.marketplace import create_listing

    with app.app_context():
        admin = User(
            username="mp_real_admin",
            email="mp_real_admin@test.com",
            password=hash_password("TestPass1"),
            is_completed=True,
            email_verified=True,
            role="admin",
            is_admin=True,
        )
        company = User(
            username="mp_real_co",
            email="mp_real_co@test.com",
            password=hash_password("TestPass1"),
            is_completed=True,
            email_verified=True,
            role=ROLE_COMPANY,
            il="Sakarya",
            latitude=40.77,
            longitude=30.39,
        )
        db.session.add_all([admin, company])
        db.session.commit()
        save_demo_settings({DEMO_MODE_KEY: False}, admin_id=admin.id, log_changes=False)

        listing = create_listing(
            company,
            {
                "baslik": "Gercek Test Ilani",
                "aciklama": "gercek veri",
                "kategori": "Hammadde",
                "miktar": 10,
                "birim": "kg",
                "latitude": 40.77,
                "longitude": 30.39,
                "il": "Sakarya",
                "ilce": "Serdivan",
            },
        )
        published = list_published()
        assert len(published) == 1
        assert published[0].id == listing.id
        assert published[0].baslik == "Gercek Test Ilani"


def test_ai_match_score_components():
    matches = marketplace_matches(limit=5, il="Sakarya")
    assert len(matches) >= 5
    for m in matches:
        d = m["skor_detay"]
        assert 0 <= d["mesafe"] <= 100
        assert 0 <= d["kategori"] <= 100
        assert 0 <= d["puan"] <= 100
        assert 0 <= d["aktivite"] <= 100
