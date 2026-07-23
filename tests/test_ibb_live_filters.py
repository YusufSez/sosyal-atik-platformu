"""İBB canlı katman: city alanı + harita filtreleri."""

from __future__ import annotations

from unittest.mock import patch

from services.municipal_waste.providers.ibb import (
    IBB_CITY,
    IbbMunicipalProvider,
    filter_ibb_live_centers,
)


SAMPLE = [
    {
        "id": 0,
        "ad": "Kadıköy",
        "lat": 40.99,
        "lng": 29.03,
        "adres": "Kadıköy",
        "city": IBB_CITY,
        "source": "ibb",
        "facility_type": "Atık Toplama Merkezi",
        "waste_types": [],
    },
    {
        "id": 1,
        "ad": "Beşiktaş",
        "lat": 41.04,
        "lng": 29.0,
        "adres": "Beşiktaş",
        "city": IBB_CITY,
        "source": "ibb",
        "facility_type": "Atık Toplama Merkezi",
        "waste_types": [],
    },
]


def test_filter_city_istanbul_keeps_ibb():
    rows = filter_ibb_live_centers(SAMPLE, city="İstanbul")
    assert len(rows) == 2


def test_filter_city_konya_hides_ibb():
    assert filter_ibb_live_centers(SAMPLE, city="Konya") == []


def test_filter_waste_type_does_not_zero_ibb():
    """waste_type Konya meta değerleri İBB'yi yanlışlıkla boşaltmamalı."""
    rows = filter_ibb_live_centers(SAMPLE, waste_type="Cam")
    assert len(rows) == 2


def test_filter_bbox_and_nearby():
    in_box = filter_ibb_live_centers(
        SAMPLE, north=41.1, south=40.9, east=29.1, west=28.9
    )
    assert {r["ad"] for r in in_box} == {"Kadıköy", "Beşiktaş"}

    near = filter_ibb_live_centers(
        SAMPLE, nearby=True, lat=40.99, lng=29.03, limit=1
    )
    assert len(near) == 1
    assert near[0]["ad"] == "Kadıköy"
    assert "mesafe" in near[0]


def test_ibb_provider_sets_city_istanbul():
    with patch(
        "services.municipal_waste.providers.ibb.fetch_ibb_merkezleri_live",
        return_value=[
            {"id": 0, "ad": "X", "lat": 41.0, "lng": 29.0, "adres": "a", "city": IBB_CITY},
        ],
    ):
        centers = IbbMunicipalProvider().load_centers(limit=1, timeout=1)
    assert len(centers) == 1
    assert centers[0].city == "İstanbul"
    assert centers[0].source == "ibb"


def test_ibb_api_city_and_source_filters(client):
    with patch(
        "blueprints.api.fetch_ibb_merkezleri_live",
        return_value=SAMPLE,
    ):
        all_rows = client.get("/api/ibb_atik_merkezleri").get_json()
        assert len(all_rows) == 2
        assert all(r["city"] == "İstanbul" for r in all_rows)

        istanbul = client.get("/api/ibb_atik_merkezleri?city=%C4%B0stanbul").get_json()
        assert len(istanbul) == 2

        konya = client.get("/api/ibb_atik_merkezleri?city=Konya").get_json()
        assert konya == []

        source_konya = client.get("/api/ibb_atik_merkezleri?source=konya").get_json()
        assert source_konya == []

        source_ibb = client.get("/api/ibb_atik_merkezleri?source=ibb").get_json()
        assert len(source_ibb) == 2
