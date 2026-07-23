"""Belediye atık merkezi — production seviye birim testleri."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from services.municipal_waste import sync_all, sync_source
from services.municipal_waste.providers.konya import (
    extract_konumlar_array,
    parse_aciklama_html,
    record_to_center,
)
from services.municipal_waste.text_utils import make_external_key, parse_title_parts
from services.municipal_waste.types import NormalizedCenter
from services.municipal_waste.waste_types import normalize_waste_type, normalize_waste_types
from utils import tr_time

FIXTURE = """<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>test</title></head><body>
<script>
var konumlar = [{
                "kor": {
                    "lat": "37.87165986657434",
                    "lng": "32.48137740945633"
                },
                "aciklama": "<div class='mapImgWrap'> <img src='https:\\/\\/sifiratik.konya.bel.tr\\/uploads\\/galeri\\/gorsel\\/mobil.png' class='img-fluid' \\/><\\/div><div class='mapContent'><span>MOB\\u0130L ATIK GET\\u0130RME MERKEZ\\u0130 (KA\\u011eIT, PLAST\\u0130K, CAM, METAL, P\\u0130L ) - M\\u0130LLET CD MOB\\u0130L ATIK GET\\u0130RME<\\/span><div class='infoWrap mt-2'><div class='mb-3'><span class='icon-location mr-1'>\\u0130HSAN\\u0130YE, M\\u0130LLET CD, No:\\/ SEL\\u00c7UKLU\\/KONYA<\\/span><\\/div><\\/div><\\/div>"
            }, {
                "kor": {
                    "lat": "37.90",
                    "lng": "32.50"
                },
                "aciklama": "<div class='mapContent'><span>TEKST\\u0130L KUMBARASI - TEST NOKTA<\\/span><div class='infoWrap mt-2'><div class='mb-3'><span class='icon-location mr-1'>MERAM\\/KONYA<\\/span><\\/div><\\/div><\\/div>"
            }];
</script>
</body></html>
"""

DIV_FIXTURE_HTML = """
<div class='mapImgWrap'><img src='https://example.com/a.png'/></div>
<div class='mapContent'>
  <div class='title'>MOBİL ATIK GETİRME MERKEZİ (KAĞIT, PİL) - DENEME</div>
  <div class='infoWrap'><div class='icon-location'>SELÇUKLU/KONYA</div></div>
</div>
"""


def test_external_key_stable_on_name_change():
    k1 = make_external_key("konya", 37.87, 32.48)
    k2 = make_external_key("konya", 37.87, 32.48)
    assert k1 == k2
    assert len(k1) == 64
    # Farklı source → farklı key
    assert make_external_key("ibb", 37.87, 32.48) != k1


def test_waste_type_normalization_dictionary():
    assert normalize_waste_type("Atık Pil") == "Pil"
    assert normalize_waste_type("PİL") == "Pil"
    assert normalize_waste_type("Atık Piller") == "Pil"
    assert normalize_waste_type("AEEE") == "Elektronik Atık"
    assert normalize_waste_type("Elektrikli Elektronik Atık") == "Elektronik Atık"
    assert normalize_waste_type("Bitkisel Atık Yağ") == "Bitkisel Atık Yağı"
    assert normalize_waste_type("Atık Yağ") == "Bitkisel Atık Yağı"
    assert normalize_waste_type("Atık Cam") == "Cam"
    assert normalize_waste_type("Metal Ambalaj") == "Metal"
    assert normalize_waste_type("Kağıt Karton") == "Kağıt"
    assert normalize_waste_types("KAĞIT, PLASTİK, CAM, METAL, PİL") == [
        "Kağıt",
        "Plastik",
        "Cam",
        "Metal",
        "Pil",
    ]


def test_parser_robust_with_div_instead_of_span():
    title, address, image = parse_aciklama_html(DIV_FIXTURE_HTML)
    assert "MOBİL" in title.upper() or "Mobil" in title
    assert "SELÇUKLU" in address.upper() or "Selçuklu" in address
    assert image and "a.png" in image


def test_parse_title_and_record(tmp_path: Path):
    path = tmp_path / "konya.html"
    path.write_text(FIXTURE, encoding="utf-8")
    records = extract_konumlar_array(path.read_text(encoding="utf-8"))
    center = record_to_center(records[0])
    assert center is not None
    assert center.source == "konya"
    assert center.source_name == "Konya Büyükşehir Belediyesi"
    assert center.external_key == make_external_key("konya", center.latitude, center.longitude)
    assert center.waste_types == ["Kağıt", "Plastik", "Cam", "Metal", "Pil"]
    facility, name, waste = parse_title_parts(
        "MOBİL ATIK GETİRME MERKEZİ (KAĞIT, PLASTİK, CAM, METAL, PİL ) - MİLLET CD"
    )
    assert "Mobil" in facility
    assert waste == ["Kağıt", "Plastik", "Cam", "Metal", "Pil"]


def test_upsert_updates_fields_not_duplicate(app, tmp_path: Path):
    from models import MunicipalWasteCenter

    path = tmp_path / "konya.html"
    path.write_text(FIXTURE, encoding="utf-8")

    with app.app_context():
        s1 = sync_source("konya", file_path=path)
        assert s1.created == 2
        row = MunicipalWasteCenter.query.filter_by(source="konya").first()
        old_key = row.external_key
        row.name = "Eski İsim"
        from extensions import db

        db.session.commit()

        s2 = sync_source("konya", file_path=path)
        assert s2.created == 0
        assert s2.updated >= 1
        assert MunicipalWasteCenter.query.filter_by(source="konya").count() == 2
        refreshed = MunicipalWasteCenter.query.filter_by(external_key=old_key).first()
        assert refreshed is not None
        assert refreshed.name != "Eski İsim"
        assert refreshed.last_seen_at is not None


def test_soft_delete_marks_stale_inactive(app):
    from extensions import db
    from models import MunicipalWasteCenter
    from services.municipal_waste.upsert import upsert_centers

    with app.app_context():
        now = tr_time()
        stale = MunicipalWasteCenter(
            name="Eski Nokta",
            facility_type="Test",
            address="X",
            district=None,
            city="Konya",
            latitude=37.0,
            longitude=32.0,
            image_url=None,
            waste_types="[]",
            description="x",
            source="konya",
            source_name="Konya Büyükşehir Belediyesi",
            external_key=make_external_key("konya", 37.0, 32.0),
            is_active=True,
            last_seen_at=now - timedelta(days=120),
            created_at=now - timedelta(days=200),
            updated_at=now - timedelta(days=120),
        )
        fresh = NormalizedCenter(
            name="Yeni",
            facility_type="Test",
            address="Y",
            district=None,
            city="Konya",
            latitude=38.0,
            longitude=33.0,
            image_url=None,
            waste_types=["Cam"],
            description="y",
            source="konya",
            source_name="Konya Büyükşehir Belediyesi",
            external_key=make_external_key("konya", 38.0, 33.0),
        )
        db.session.add(stale)
        db.session.commit()

        stats = upsert_centers([fresh], source="konya", source_name="Konya", stale_days=90)
        assert stats.created == 1
        assert stats.inactivated == 1
        assert MunicipalWasteCenter.query.filter_by(external_key=stale.external_key).first().is_active is False
        assert MunicipalWasteCenter.query.filter_by(external_key=fresh.external_key).first().is_active is True


def test_sync_all_runs_providers(app, tmp_path: Path):
    path = tmp_path / "konya.html"
    path.write_text(FIXTURE, encoding="utf-8")

    with app.app_context():
        with patch(
            "services.municipal_waste.providers.ibb.fetch_ibb_merkezleri_live",
            return_value=[
                {"id": 0, "ad": "Test İBB", "lat": 41.0, "lng": 29.0, "adres": "Kadıköy"},
            ],
        ):
            agg = sync_all(file_path=path, limit=10, timeout=1)
        assert len(agg.providers) == 2
        sources = {p.source for p in agg.providers}
        assert sources == {"ibb", "konya"}
        assert agg.found >= 3
        assert agg.errors == 0
        lines = "\n".join(agg.log_lines())
        assert "Toplam" in lines


def test_api_source_filter(client, app, tmp_path: Path):
    path = tmp_path / "konya.html"
    path.write_text(FIXTURE, encoding="utf-8")
    with app.app_context():
        sync_source("konya", file_path=path)

    all_rows = client.get("/api/municipal_waste_centers").get_json()
    konya = client.get("/api/municipal_waste_centers?source=konya").get_json()
    ibb = client.get("/api/municipal_waste_centers?source=ibb").get_json()
    assert len(konya) == 2
    assert all(r["source"] == "konya" for r in konya)
    assert ibb == []
    assert len(all_rows) >= 2


def test_inactive_hidden_from_default_api(client, app):
    from extensions import db
    from models import MunicipalWasteCenter

    with app.app_context():
        now = tr_time()
        db.session.add(
            MunicipalWasteCenter(
                name="Gizli",
                facility_type="T",
                address="A",
                city="Konya",
                latitude=39.0,
                longitude=34.0,
                source="konya",
                source_name="Konya Büyükşehir Belediyesi",
                external_key=make_external_key("konya", 39.0, 34.0),
                is_active=False,
                last_seen_at=now,
                created_at=now,
                updated_at=now,
            )
        )
        db.session.commit()

    visible = client.get("/api/municipal_waste_centers?source=konya").get_json()
    assert all(r["ad"] != "Gizli" for r in visible)
    with_inactive = client.get(
        "/api/municipal_waste_centers?source=konya&include_inactive=1"
    ).get_json()
    assert any(r["ad"] == "Gizli" for r in with_inactive)
