"""Kurumsal Kaynak Pazarı — RBAC, teklif akışı, yakındakiler, AI, Kaynak izolasyonu."""

from unittest.mock import patch

import pytest

from auth_utils import hash_password
from constants import (
    MP_LISTING_ANLASILDI,
    MP_LISTING_IPTAL,
    MP_LISTING_REZERVE,
    MP_LISTING_TESLIM,
    MP_LISTING_YAYINDA,
    MP_OFFER_BEKLIYOR,
    MP_OFFER_IPTAL,
    MP_OFFER_KABUL,
    MP_OFFER_RED,
    ROLE_COMPANY,
    ROLE_INSTITUTION,
)
from decorators import is_marketplace_user
from extensions import db
from models import Kaynak, MarketplaceEvent, MarketplaceListing, MarketplaceOffer, User
from services.marketplace import (
    MarketplaceError,
    accept_offer,
    cancel_listing,
    cancel_offer,
    confirm_agreement,
    create_listing,
    mark_delivered,
    nearby_institutions,
    submit_offer,
)
from services.marketplace_ai import suggest_nearby_fit


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
def mp_data(app):
    with app.app_context():
        company = _user(
            username="firma_mp",
            email="firma_mp@test.com",
            role=ROLE_COMPANY,
            is_kurum=True,
            il="Sakarya",
            ilce="Serdivan",
            latitude=40.77,
            longitude=30.39,
        )
        institution = _user(
            username="kurum_mp",
            email="kurum_mp@test.com",
            role=ROLE_INSTITUTION,
            is_kurum=True,
            il="Sakarya",
            ilce="Adapazarı",
            latitude=40.78,
            longitude=30.40,
        )
        nearby_org = _user(
            username="yakin_mp",
            email="yakin_mp@test.com",
            role=ROLE_COMPANY,
            is_kurum=True,
            il="Sakarya",
            ilce="Erenler",
            latitude=40.76,
            longitude=30.38,
        )
        far_org = _user(
            username="uzak_mp",
            email="uzak_mp@test.com",
            role=ROLE_INSTITUTION,
            is_kurum=True,
            il="Ankara",
            ilce="Çankaya",
            latitude=39.92,
            longitude=32.85,
        )
        legacy_kurum = _user(
            username="legacy_kurum_mp",
            email="legacy_kurum_mp@test.com",
            is_kurum=True,
            il="Sakarya",
            latitude=40.775,
            longitude=30.395,
        )
        normal = _user(username="normal_mp", email="normal_mp@test.com")
        admin = _user(
            username="admin_mp",
            email="admin_mp@test.com",
            role="admin",
            is_admin=True,
        )
        return {
            "company_id": company.id,
            "institution_id": institution.id,
            "nearby_id": nearby_org.id,
            "far_id": far_org.id,
            "legacy_id": legacy_kurum.id,
            "normal_id": normal.id,
            "admin_id": admin.id,
        }


def test_is_marketplace_user_roles(app, mp_data):
    with app.app_context():
        assert is_marketplace_user(db.session.get(User, mp_data["company_id"]))
        assert is_marketplace_user(db.session.get(User, mp_data["institution_id"]))
        assert is_marketplace_user(db.session.get(User, mp_data["legacy_id"]))
        assert is_marketplace_user(db.session.get(User, mp_data["admin_id"]))
        assert not is_marketplace_user(db.session.get(User, mp_data["normal_id"]))


def test_panel_forbidden_for_normal_user(client, mp_data):
    _login(client, "normal_mp@test.com")
    assert client.get("/marketplace/panel").status_code == 403


def test_panel_allowed_for_company(client, mp_data):
    _login(client, "firma_mp@test.com")
    resp = client.get("/marketplace/panel")
    assert resp.status_code == 200
    assert b"Kurumsal Marketplace" in resp.data


def test_panel_allowed_for_legacy_kurum(client, mp_data):
    _login(client, "legacy_kurum_mp@test.com")
    assert client.get("/marketplace/panel").status_code == 200


def test_full_offer_to_delivery_flow(app, mp_data):
    with app.app_context():
        publisher = db.session.get(User, mp_data["company_id"])
        offerer = db.session.get(User, mp_data["institution_id"])
        other = db.session.get(User, mp_data["nearby_id"])

        listing = create_listing(
            publisher,
            {
                "baslik": "Fazla Palet",
                "aciklama": "Ahşap palet stoku",
                "kategori": "Ahşap",
                "miktar": 100,
                "birim": "adet",
                "latitude": 40.77,
                "longitude": 30.39,
                "il": "Sakarya",
                "ilce": "Serdivan",
            },
        )
        assert listing.durum == MP_LISTING_YAYINDA

        offer_a = submit_offer(listing, offerer, {"mesaj": "Alabiliriz", "miktar": 50})
        offer_b = submit_offer(listing, other, {"mesaj": "Biz de isteriz"})
        assert offer_a.durum == MP_OFFER_BEKLIYOR

        accept_offer(listing, offer_a, publisher)
        db.session.refresh(listing)
        db.session.refresh(offer_a)
        db.session.refresh(offer_b)
        assert listing.durum == MP_LISTING_REZERVE
        assert listing.accepted_offer_id == offer_a.id
        assert offer_a.durum == MP_OFFER_KABUL
        assert offer_b.durum == MP_OFFER_RED

        confirm_agreement(listing, offerer)
        db.session.refresh(listing)
        assert listing.durum == MP_LISTING_ANLASILDI

        mark_delivered(listing, publisher)
        db.session.refresh(listing)
        assert listing.durum == MP_LISTING_TESLIM

        actions = [e.action for e in MarketplaceEvent.query.filter_by(listing_id=listing.id).all()]
        assert "yayinla" in actions
        assert "teklif" in actions
        assert "rezervasyon" in actions
        assert "anlasma" in actions
        assert "teslim" in actions


def test_cancel_listing_and_pending_offers(app, mp_data):
    with app.app_context():
        publisher = db.session.get(User, mp_data["company_id"])
        offerer = db.session.get(User, mp_data["institution_id"])
        listing = create_listing(
            publisher,
            {
                "baslik": "İptal Test",
                "aciklama": "Açıklama",
                "kategori": "Diğer",
                "latitude": 40.77,
                "longitude": 30.39,
            },
        )
        offer = submit_offer(listing, offerer, {"mesaj": "Teklif"})
        cancel_listing(listing, publisher, reason="Stok kalmadı")
        db.session.refresh(listing)
        db.session.refresh(offer)
        assert listing.durum == MP_LISTING_IPTAL
        assert offer.durum == MP_OFFER_IPTAL


def test_cancel_offer_by_offerer(app, mp_data):
    with app.app_context():
        publisher = db.session.get(User, mp_data["company_id"])
        offerer = db.session.get(User, mp_data["institution_id"])
        listing = create_listing(
            publisher,
            {
                "baslik": "Teklif İptal",
                "aciklama": "Açıklama",
                "kategori": "Diğer",
                "latitude": 40.77,
                "longitude": 30.39,
            },
        )
        offer = submit_offer(listing, offerer, {"mesaj": "Vazgeçeceğim"})
        cancel_offer(offer, offerer)
        db.session.refresh(offer)
        assert offer.durum == MP_OFFER_IPTAL


def test_cannot_offer_own_listing(app, mp_data):
    with app.app_context():
        publisher = db.session.get(User, mp_data["company_id"])
        listing = create_listing(
            publisher,
            {
                "baslik": "Kendi",
                "aciklama": "Açıklama",
                "kategori": "Diğer",
                "latitude": 40.77,
                "longitude": 30.39,
            },
        )
        with pytest.raises(MarketplaceError):
            submit_offer(listing, publisher, {"mesaj": "Ben"})


def test_nearby_institutions_distance(app, mp_data):
    with app.app_context():
        publisher = db.session.get(User, mp_data["company_id"])
        listing = create_listing(
            publisher,
            {
                "baslik": "Yakın Test",
                "aciklama": "Açıklama",
                "kategori": "Diğer",
                "latitude": 40.77,
                "longitude": 30.39,
            },
        )
        nearby = nearby_institutions(
            listing, radius_km=50, exclude_user_id=publisher.id
        )
        ids = {n["id"] for n in nearby}
        assert mp_data["institution_id"] in ids
        assert mp_data["nearby_id"] in ids
        assert mp_data["legacy_id"] in ids
        assert mp_data["far_id"] not in ids
        assert all(n["mesafe_km"] <= 50 for n in nearby)


def test_ai_suggestion_rule_based(app, mp_data, monkeypatch):
    with app.app_context():
        publisher = db.session.get(User, mp_data["company_id"])
        listing = create_listing(
            publisher,
            {
                "baslik": "AI Test",
                "aciklama": "Açıklama",
                "kategori": "Kağıt",
                "latitude": 40.77,
                "longitude": 30.39,
            },
        )
        with patch("services.marketplace_ai.get_client", return_value=None):
            result = suggest_nearby_fit(listing)
        assert result["source"] == "rules"
        assert result["nearby_count"] >= 1
        assert "yakınınızdaki" in result["suggestion"]
        assert "kurum için uygundur" in result["suggestion"]


def test_http_create_offer_accept(client, app, mp_data):
    _login(client, "firma_mp@test.com")
    resp = client.post(
        "/marketplace/ilan/yeni",
        data={
            "baslik": "HTTP Palet",
            "aciklama": "HTTP ile yayın",
            "kategori": "Ahşap",
            "miktar": "20",
            "birim": "adet",
            "latitude": "40.77",
            "longitude": "30.39",
            "il": "Sakarya",
            "ilce": "Serdivan",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200

    with app.app_context():
        listing = MarketplaceListing.query.filter_by(baslik="HTTP Palet").one()
        listing_id = listing.id

    _login(client, "kurum_mp@test.com")
    resp = client.post(
        f"/marketplace/ilan/{listing_id}/teklif",
        data={"mesaj": "HTTP teklif", "miktar": "10"},
        follow_redirects=True,
    )
    assert resp.status_code == 200

    with app.app_context():
        offer = MarketplaceOffer.query.filter_by(listing_id=listing_id).one()
        offer_id = offer.id

    _login(client, "firma_mp@test.com")
    resp = client.post(
        f"/marketplace/teklif/{offer_id}/kabul",
        follow_redirects=True,
    )
    assert resp.status_code == 200
    with app.app_context():
        listing = db.session.get(MarketplaceListing, listing_id)
        assert listing.durum == MP_LISTING_REZERVE


def test_api_nearby_and_map(client, app, mp_data):
    with app.app_context():
        publisher = db.session.get(User, mp_data["company_id"])
        listing = create_listing(
            publisher,
            {
                "baslik": "API Map",
                "aciklama": "Açıklama",
                "kategori": "Diğer",
                "latitude": 40.77,
                "longitude": 30.39,
            },
        )
        listing_id = listing.id

    _login(client, "firma_mp@test.com")
    with patch("services.marketplace_ai.get_client", return_value=None):
        nearby_resp = client.get(f"/marketplace/api/nearby/{listing_id}")
    assert nearby_resp.status_code == 200
    data = nearby_resp.get_json()
    assert "suggestion" in data
    assert "nearby_count" in data

    map_resp = client.get("/marketplace/api/map")
    assert map_resp.status_code == 200
    assert isinstance(map_resp.get_json(), list)


def test_marketplace_does_not_create_kaynak(app, mp_data):
    with app.app_context():
        before = Kaynak.query.count()
        publisher = db.session.get(User, mp_data["company_id"])
        create_listing(
            publisher,
            {
                "baslik": "İzolasyon",
                "aciklama": "Kaynak tablosuna yazmamalı",
                "kategori": "Diğer",
                "latitude": 40.77,
                "longitude": 30.39,
            },
        )
        assert Kaynak.query.count() == before
        assert MarketplaceListing.query.filter_by(baslik="İzolasyon").count() == 1
