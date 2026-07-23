"""Statik Türkiye il/ilçe sözlüğü."""

from services.turkey_geo import list_districts, list_provinces, province_exists


def test_list_provinces_has_81():
    from services.turkey_geo import reload_cache, resolve_il_ilce_json_path

    reload_cache()
    path = resolve_il_ilce_json_path()
    assert path.is_file()
    provinces = list_provinces()
    assert len(provinces) == 81
    assert provinces[0] == "Adana"
    assert "Konya" in provinces
    assert "İstanbul" in provinces


def test_list_districts_for_konya():
    districts = list_districts("Konya")
    assert "Selçuklu" in districts
    assert "Meram" in districts
    assert "Karatay" in districts
    # case-insensitive lookup
    assert list_districts("konya") == districts
    assert list_districts("KONYA") == districts


def test_unknown_or_empty_city():
    assert list_districts("") == []
    assert list_districts(None) == []
    assert list_districts("Atlantis") == []
    assert province_exists("Konya") is True
    assert province_exists("Atlantis") is False
