"""Municipal waste map query: bbox, nearby, filters."""

from __future__ import annotations

from services.municipal_waste.query import filter_meta, parse_request_args, query_centers
from services.municipal_waste.text_utils import make_external_key
from utils import tr_time


def _seed_center(app, **kwargs):
    from extensions import db
    from models import MunicipalWasteCenter

    now = tr_time()
    defaults = dict(
        facility_type="Test Tesis",
        address="Test",
        district="Selçuklu",
        city="Konya",
        image_url=None,
        waste_types='["Cam", "Pil"]',
        description="d",
        source="konya",
        source_name="Konya Büyükşehir Belediyesi",
        is_active=True,
        last_seen_at=now,
        created_at=now,
        updated_at=now,
    )
    defaults.update(kwargs)
    if "external_key" not in defaults:
        defaults["external_key"] = make_external_key(
            defaults["source"], defaults["latitude"], defaults["longitude"]
        )
    row = MunicipalWasteCenter(**defaults)
    db.session.add(row)
    db.session.commit()
    return row


def test_bbox_filters_viewport(app):
    with app.app_context():
        _seed_center(app, name="Icinde", latitude=37.87, longitude=32.48)
        _seed_center(app, name="Disarida", latitude=40.0, longitude=29.0)
        inside = query_centers(north=38.0, south=37.0, east=33.0, west=32.0, limit=100)
        names = {r["ad"] for r in inside}
        assert "Icinde" in names
        assert "Disarida" not in names


def test_nearby_returns_top_n(app):
    with app.app_context():
        _seed_center(app, name="Yakin", latitude=37.8701, longitude=32.4801)
        _seed_center(app, name="Uzak", latitude=41.0, longitude=29.0)
        rows = query_centers(nearby=True, lat=37.87, lng=32.48, limit=1)
        assert len(rows) == 1
        assert rows[0]["ad"] == "Yakin"
        assert "mesafe" in rows[0]


def test_facility_and_waste_filters(app):
    with app.app_context():
        _seed_center(
            app,
            name="CamKutu",
            latitude=37.1,
            longitude=32.1,
            facility_type="Atık Cam",
            waste_types='["Cam"]',
        )
        _seed_center(
            app,
            name="PilKutu",
            latitude=37.2,
            longitude=32.2,
            facility_type="Mobil Merkez",
            waste_types='["Pil"]',
        )
        by_facility = query_centers(facility_type="Atık Cam")
        assert {r["ad"] for r in by_facility} == {"CamKutu"}
        by_waste = query_centers(waste_type="Pil")
        assert {r["ad"] for r in by_waste} == {"PilKutu"}


def test_city_district_filters(app):
    with app.app_context():
        _seed_center(app, name="Sel", latitude=37.3, longitude=32.3, city="Konya", district="Selçuklu")
        _seed_center(app, name="Mer", latitude=37.4, longitude=32.4, city="Konya", district="Meram")
        rows = query_centers(city="Konya", district="Meram")
        assert {r["ad"] for r in rows} == {"Mer"}


def test_parse_request_args_bbox_and_nearby():
    class Args(dict):
        def get(self, key, default=None):
            return super().get(key, default)

    bbox = parse_request_args(
        Args(north="38", south="37", east="33", west="32", limit="100")
    )
    assert bbox["north"] == 38.0
    assert bbox["nearby"] is False
    near = parse_request_args(Args(nearby="1", lat="37.8", lng="32.4", limit="20"))
    assert near["nearby"] is True
    assert near["limit"] == 20


def test_meta_endpoint_and_api(client, app):
    with app.app_context():
        _seed_center(app, name="Meta1", latitude=37.5, longitude=32.5)

    meta = client.get("/api/municipal_waste_centers/meta?source=konya").get_json()
    assert "facility_types" in meta
    assert "waste_types" in meta
    assert "cities" not in meta
    assert "districts" not in meta
    assert meta["geography"]["provinces_url"] == "/api/turkey/provinces"

    data = client.get(
        "/api/municipal_waste_centers?source=konya&north=38&south=37&east=33&west=32"
    ).get_json()
    assert isinstance(data, list)
    assert any(r["ad"] == "Meta1" for r in data)

    nearby = client.get(
        "/api/municipal_waste_centers?nearby=1&lat=37.5&lng=32.5&limit=5&source=konya"
    ).get_json()
    assert nearby and nearby[0]["ad"] == "Meta1"


def test_filter_meta_helper(app):
    with app.app_context():
        _seed_center(app, name="M2", latitude=37.6, longitude=32.6, waste_types='["Metal"]')
        meta = filter_meta(source="konya")
        assert "Metal" in meta["waste_types"]
        assert "cities" not in meta


def test_turkey_provinces_and_districts_api(client):
    provinces = client.get("/api/turkey/provinces").get_json()
    assert provinces["count"] == 81
    assert "Konya" in provinces["provinces"]
    assert "İstanbul" in provinces["provinces"]

    konya = client.get("/api/turkey/districts?city=Konya").get_json()
    assert konya["count"] > 10
    assert "Selçuklu" in konya["districts"]
    assert "Meram" in konya["districts"]

    missing = client.get("/api/turkey/districts")
    assert missing.status_code == 400

    unknown = client.get("/api/turkey/districts?city=Atlantis")
    assert unknown.status_code == 404


def test_city_filter_empty_region_still_works(app):
    """Veri olmayan il filtresi boş liste döner; sorgu kırılmaz."""
    with app.app_context():
        _seed_center(app, name="Sel", latitude=37.3, longitude=32.3, city="Konya", district="Selçuklu")
        rows = query_centers(city="Ağrı")
        assert rows == []
        rows_konya = query_centers(city="Konya")
        assert {r["ad"] for r in rows_konya} == {"Sel"}